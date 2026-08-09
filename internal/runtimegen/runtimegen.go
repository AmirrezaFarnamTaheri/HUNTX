package runtimegen

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var (
	generationPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`)
	digestPattern     = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

type FileRecord struct {
	SHA256 string `json:"sha256"`
	Size   int64  `json:"size"`
}

type Manifest struct {
	SchemaVersion int                   `json:"schema_version"`
	Generation    string                `json:"generation"`
	Files         map[string]FileRecord `json:"files"`
}

type Pointer struct {
	SchemaVersion  int    `json:"schema_version"`
	Generation     string `json:"generation"`
	ManifestSHA256 string `json:"manifest_sha256"`
}

func validateGeneration(generation string) error {
	if !generationPattern.MatchString(generation) {
		return fmt.Errorf("invalid generation identifier: %q", generation)
	}
	return nil
}

func safeRelativePath(value string) error {
	if value == "" || strings.Contains(value, `\`) || strings.HasPrefix(value, "/") {
		return fmt.Errorf("unsafe manifest path: %q", value)
	}
	clean := path.Clean(value)
	if clean != value || clean == "." || clean == ".." || strings.HasPrefix(clean, "../") {
		return fmt.Errorf("unsafe manifest path: %q", value)
	}
	for _, part := range strings.Split(value, "/") {
		if part == "" || part == "." || part == ".." {
			return fmt.Errorf("unsafe manifest path: %q", value)
		}
	}
	return nil
}

func digestFile(filePath string) (string, int64, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return "", 0, err
	}
	defer file.Close()
	infoBefore, err := file.Stat()
	if err != nil {
		return "", 0, err
	}
	if !infoBefore.Mode().IsRegular() {
		return "", 0, fmt.Errorf("not a regular file: %s", filePath)
	}
	hash := sha256.New()
	written, err := io.Copy(hash, file)
	if err != nil {
		return "", 0, err
	}
	infoAfter, err := file.Stat()
	if err != nil {
		return "", 0, err
	}
	if infoBefore.Size() != infoAfter.Size() || written != infoAfter.Size() || !infoAfter.ModTime().Equal(infoBefore.ModTime()) {
		return "", 0, fmt.Errorf("file changed while hashing: %s", filePath)
	}
	return hex.EncodeToString(hash.Sum(nil)), written, nil
}

func Build(root, generation string) (Manifest, error) {
	if err := validateGeneration(generation); err != nil {
		return Manifest{}, err
	}
	resolvedRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return Manifest{}, err
	}
	resolvedRoot, err = filepath.Abs(resolvedRoot)
	if err != nil {
		return Manifest{}, err
	}
	info, err := os.Stat(resolvedRoot)
	if err != nil {
		return Manifest{}, err
	}
	if !info.IsDir() {
		return Manifest{}, fmt.Errorf("generation root is not a directory: %s", resolvedRoot)
	}
	manifest := Manifest{SchemaVersion: 1, Generation: generation, Files: map[string]FileRecord{}}
	err = filepath.WalkDir(resolvedRoot, func(filePath string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if filePath == resolvedRoot {
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("generation contains symlink: %s", filePath)
		}
		if entry.IsDir() {
			return nil
		}
		entryInfo, err := entry.Info()
		if err != nil {
			return err
		}
		if !entryInfo.Mode().IsRegular() {
			return fmt.Errorf("generation contains non-regular file: %s", filePath)
		}
		relative, err := filepath.Rel(resolvedRoot, filePath)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		digest, size, err := digestFile(filePath)
		if err != nil {
			return err
		}
		manifest.Files[relative] = FileRecord{SHA256: digest, Size: size}
		return nil
	})
	if err != nil {
		return Manifest{}, err
	}
	if _, ok := manifest.Files["state.db"]; !ok {
		return Manifest{}, errors.New("generation is missing state.db")
	}
	return manifest, nil
}

func Verify(root string, manifest Manifest) error {
	if manifest.SchemaVersion != 1 {
		return errors.New("unsupported runtime manifest schema")
	}
	if err := validateGeneration(manifest.Generation); err != nil {
		return err
	}
	if manifest.Files == nil {
		return errors.New("runtime manifest files must be an object")
	}
	resolvedRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return err
	}
	resolvedRoot, err = filepath.Abs(resolvedRoot)
	if err != nil {
		return err
	}
	expected := make(map[string]struct{}, len(manifest.Files))
	for relative, metadata := range manifest.Files {
		if err := safeRelativePath(relative); err != nil {
			return err
		}
		if !digestPattern.MatchString(metadata.SHA256) {
			return fmt.Errorf("invalid digest for %s", relative)
		}
		if metadata.Size < 0 {
			return fmt.Errorf("invalid size for %s", relative)
		}
		expected[relative] = struct{}{}
		candidate := filepath.Join(resolvedRoot, filepath.FromSlash(relative))
		entryInfo, err := os.Lstat(candidate)
		if err != nil || entryInfo.Mode()&os.ModeSymlink != 0 || !entryInfo.Mode().IsRegular() {
			return fmt.Errorf("generation file missing: %s", relative)
		}
		if entryInfo.Size() != metadata.Size {
			return fmt.Errorf("size mismatch for %s", relative)
		}
		digest, _, err := digestFile(candidate)
		if err != nil {
			return err
		}
		if digest != metadata.SHA256 {
			return fmt.Errorf("digest mismatch for %s", relative)
		}
	}
	actual := map[string]struct{}{}
	err = filepath.WalkDir(resolvedRoot, func(filePath string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if filePath == resolvedRoot {
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("generation contains symlink: %s", filePath)
		}
		if entry.IsDir() {
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("generation contains non-regular file: %s", filePath)
		}
		relative, err := filepath.Rel(resolvedRoot, filePath)
		if err != nil {
			return err
		}
		actual[filepath.ToSlash(relative)] = struct{}{}
		return nil
	})
	if err != nil {
		return err
	}
	if len(actual) != len(expected) {
		return fileSetMismatch(expected, actual)
	}
	for relative := range expected {
		if _, ok := actual[relative]; !ok {
			return fileSetMismatch(expected, actual)
		}
	}
	return nil
}

func fileSetMismatch(expected, actual map[string]struct{}) error {
	missing := make([]string, 0)
	unexpected := make([]string, 0)
	for value := range expected {
		if _, ok := actual[value]; !ok {
			missing = append(missing, value)
		}
	}
	for value := range actual {
		if _, ok := expected[value]; !ok {
			unexpected = append(unexpected, value)
		}
	}
	sort.Strings(missing)
	sort.Strings(unexpected)
	return fmt.Errorf("generation file set mismatch: missing=%v unexpected=%v", missing, unexpected)
}

func BuildPointer(generation string, manifest Manifest) (Pointer, error) {
	if err := validateGeneration(generation); err != nil {
		return Pointer{}, err
	}
	if manifest.Generation != generation {
		return Pointer{}, errors.New("pointer generation does not match manifest")
	}
	payload, err := CanonicalBytes(manifest)
	if err != nil {
		return Pointer{}, err
	}
	digest := sha256.Sum256(payload)
	return Pointer{SchemaVersion: 1, Generation: generation, ManifestSHA256: hex.EncodeToString(digest[:])}, nil
}

func ValidatePointer(pointer Pointer, manifest *Manifest) (string, error) {
	if pointer.SchemaVersion != 1 {
		return "", errors.New("unsupported runtime pointer schema")
	}
	if err := validateGeneration(pointer.Generation); err != nil {
		return "", err
	}
	if !digestPattern.MatchString(pointer.ManifestSHA256) {
		return "", errors.New("invalid runtime pointer manifest digest")
	}
	if manifest != nil {
		if manifest.Generation != pointer.Generation {
			return "", errors.New("pointer and manifest generations differ")
		}
		payload, err := CanonicalBytes(*manifest)
		if err != nil {
			return "", err
		}
		digest := sha256.Sum256(payload)
		if hex.EncodeToString(digest[:]) != pointer.ManifestSHA256 {
			return "", errors.New("runtime manifest does not match pointer")
		}
	}
	return pointer.Generation, nil
}

func CanonicalBytes(value any) ([]byte, error) {
	var canonical any = value
	switch typed := value.(type) {
	case Manifest:
		files := make(map[string]any, len(typed.Files))
		for name, record := range typed.Files {
			files[name] = map[string]any{"sha256": record.SHA256, "size": record.Size}
		}
		canonical = map[string]any{
			"files":          files,
			"generation":     typed.Generation,
			"schema_version": typed.SchemaVersion,
		}
	case *Manifest:
		return CanonicalBytes(*typed)
	case Pointer:
		canonical = map[string]any{
			"generation":      typed.Generation,
			"manifest_sha256": typed.ManifestSHA256,
			"schema_version":  typed.SchemaVersion,
		}
	case *Pointer:
		return CanonicalBytes(*typed)
	}
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(canonical); err != nil {
		return nil, err
	}
	return buffer.Bytes(), nil
}

func WriteAtomic(filePath string, value any) error {
	payload, err := CanonicalBytes(value)
	if err != nil {
		return err
	}
	return WriteBytesAtomic(filePath, payload, 0o600)
}

func WriteBytesAtomic(filePath string, payload []byte, mode os.FileMode) error {
	directory := filepath.Dir(filePath)
	if err := os.MkdirAll(directory, 0o755); err != nil {
		return err
	}
	temporary, err := os.CreateTemp(directory, "."+filepath.Base(filePath)+".*")
	if err != nil {
		return err
	}
	temporaryName := temporary.Name()
	committed := false
	defer func() {
		_ = temporary.Close()
		if !committed {
			_ = os.Remove(temporaryName)
		}
	}()
	if err := temporary.Chmod(mode); err != nil {
		return err
	}
	if _, err := temporary.Write(payload); err != nil {
		return err
	}
	if err := temporary.Sync(); err != nil {
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	if err := os.Rename(temporaryName, filePath); err != nil {
		return err
	}
	committed = true
	syncDirectory(directory)
	return nil
}

func syncDirectory(directory string) {
	if handle, err := os.Open(directory); err == nil {
		_ = handle.Sync()
		_ = handle.Close()
	}
}

func ReadManifest(filePath string) (Manifest, error) {
	payload, err := os.ReadFile(filePath)
	if err != nil {
		return Manifest{}, err
	}
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(payload, &raw); err != nil {
		return Manifest{}, err
	}
	if len(raw) != 3 || raw["schema_version"] == nil || raw["generation"] == nil || raw["files"] == nil {
		return Manifest{}, errors.New("runtime manifest has unexpected or missing fields")
	}
	var manifest Manifest
	if err := json.Unmarshal(payload, &manifest); err != nil {
		return Manifest{}, err
	}
	return manifest, nil
}

func ReadPointer(filePath string) (Pointer, error) {
	payload, err := os.ReadFile(filePath)
	if err != nil {
		return Pointer{}, err
	}
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(payload, &raw); err != nil {
		return Pointer{}, err
	}
	if len(raw) != 3 || raw["schema_version"] == nil || raw["generation"] == nil || raw["manifest_sha256"] == nil {
		return Pointer{}, errors.New("runtime pointer has unexpected or missing fields")
	}
	var pointer Pointer
	if err := json.Unmarshal(payload, &pointer); err != nil {
		return Pointer{}, err
	}
	return pointer, nil
}
