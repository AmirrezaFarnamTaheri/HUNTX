package releasemanifest

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/runtimegen"
)

var digestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

type Artifact struct {
	Path      string `json:"path"`
	Size      int64  `json:"size"`
	SHA256    string `json:"sha256"`
	MediaType string `json:"media_type"`
}

type Manifest struct {
	SchemaVersion int        `json:"schema_version"`
	ArtifactCount int        `json:"artifact_count"`
	Artifacts     []Artifact `json:"artifacts"`
}

func Discover(root, manifestPath string) ([]string, error) {
	absoluteRoot, err := filepath.Abs(root)
	if err != nil {
		return nil, err
	}
	manifestAbs, err := filepath.Abs(manifestPath)
	if err != nil {
		return nil, err
	}
	candidates := make([]string, 0)
	err = filepath.WalkDir(absoluteRoot, func(filePath string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if filePath == absoluteRoot {
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("symlink artifacts are forbidden: %s", filePath)
		}
		if entry.IsDir() {
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("artifact is not a regular file: %s", filePath)
		}
		currentAbs, err := filepath.Abs(filePath)
		if err != nil {
			return err
		}
		if currentAbs != manifestAbs {
			candidates = append(candidates, currentAbs)
		}
		return nil
	})
	sort.Strings(candidates)
	return candidates, err
}

func Build(root string, files []string) (Manifest, error) {
	rootAbs, err := filepath.Abs(root)
	if err != nil {
		return Manifest{}, err
	}
	seen := map[string]struct{}{}
	records := make([]Artifact, 0, len(files))
	sorted := append([]string(nil), files...)
	sort.Strings(sorted)
	for _, candidate := range sorted {
		info, err := os.Lstat(candidate)
		if err != nil {
			return Manifest{}, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return Manifest{}, fmt.Errorf("symlink artifacts are forbidden: %s", candidate)
		}
		if !info.Mode().IsRegular() {
			return Manifest{}, fmt.Errorf("artifact is not a regular file: %s", candidate)
		}
		candidateAbs, err := filepath.Abs(candidate)
		if err != nil {
			return Manifest{}, err
		}
		relative, err := filepath.Rel(rootAbs, candidateAbs)
		if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(os.PathSeparator)) {
			return Manifest{}, fmt.Errorf("artifact escapes release root: %s", candidate)
		}
		relative = filepath.ToSlash(relative)
		if err := validateRelative(relative); err != nil {
			return Manifest{}, err
		}
		if _, ok := seen[relative]; ok {
			return Manifest{}, fmt.Errorf("duplicate artifact coordinate: %s", relative)
		}
		seen[relative] = struct{}{}
		size, digest, err := inspect(candidateAbs)
		if err != nil {
			return Manifest{}, err
		}
		if size <= 0 {
			return Manifest{}, fmt.Errorf("empty artifact is not publishable: %s", candidate)
		}
		if isJSON(relative) {
			payload, err := os.ReadFile(candidateAbs)
			if err != nil {
				return Manifest{}, err
			}
			var value any
			if err := json.Unmarshal(payload, &value); err != nil {
				return Manifest{}, err
			}
		}
		records = append(records, Artifact{Path: relative, Size: size, SHA256: digest, MediaType: mediaType(relative)})
	}
	if len(records) == 0 {
		return Manifest{}, errors.New("a release must contain at least one validated artifact")
	}
	return Manifest{SchemaVersion: 1, ArtifactCount: len(records), Artifacts: records}, nil
}

func Verify(root string, manifest Manifest) error {
	if manifest.SchemaVersion != 1 {
		return errors.New("unsupported manifest schema version")
	}
	if manifest.ArtifactCount <= 0 || manifest.ArtifactCount != len(manifest.Artifacts) {
		return errors.New("manifest artifact count is inconsistent")
	}
	rootAbs, err := filepath.Abs(root)
	if err != nil {
		return err
	}
	seen := map[string]struct{}{}
	for _, record := range manifest.Artifacts {
		if err := validateRelative(record.Path); err != nil {
			return err
		}
		if _, ok := seen[record.Path]; ok {
			return fmt.Errorf("duplicate artifact coordinate: %s", record.Path)
		}
		seen[record.Path] = struct{}{}
		if record.Size <= 0 {
			return fmt.Errorf("invalid artifact size: %s", record.Path)
		}
		if !digestPattern.MatchString(record.SHA256) {
			return fmt.Errorf("invalid artifact digest: %s", record.Path)
		}
		if record.MediaType == "" {
			return fmt.Errorf("invalid artifact media type: %s", record.Path)
		}
		candidate := filepath.Join(rootAbs, filepath.FromSlash(record.Path))
		info, err := os.Lstat(candidate)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return fmt.Errorf("artifact is not a regular file: %s", candidate)
		}
		size, digest, err := inspect(candidate)
		if err != nil {
			return err
		}
		if size != record.Size {
			return fmt.Errorf("artifact size mismatch: %s", record.Path)
		}
		if digest != record.SHA256 {
			return fmt.Errorf("artifact digest mismatch: %s", record.Path)
		}
		if isJSON(record.Path) {
			payload, err := os.ReadFile(candidate)
			if err != nil {
				return err
			}
			var value any
			if err := json.Unmarshal(payload, &value); err != nil {
				return err
			}
		}
	}
	return nil
}

func WriteAtomic(filePath string, manifest Manifest) error {
	payload, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return err
	}
	return runtimegen.WriteBytesAtomic(filePath, append(payload, '\n'), 0o600)
}

func Read(filePath string) (Manifest, error) {
	payload, err := os.ReadFile(filePath)
	if err != nil {
		return Manifest{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	var manifest Manifest
	if err := decoder.Decode(&manifest); err != nil {
		return Manifest{}, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return Manifest{}, errors.New("manifest contains trailing JSON values")
		}
		return Manifest{}, err
	}
	return manifest, nil
}

func inspect(filePath string) (int64, string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return 0, "", err
	}
	defer file.Close()
	before, err := file.Stat()
	if err != nil {
		return 0, "", err
	}
	hash := sha256.New()
	written, err := io.Copy(hash, file)
	if err != nil {
		return 0, "", err
	}
	after, err := file.Stat()
	if err != nil {
		return 0, "", err
	}
	if !after.Mode().IsRegular() || before.Size() != after.Size() || written != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		return 0, "", fmt.Errorf("artifact changed while being inspected: %s", filePath)
	}
	return written, hex.EncodeToString(hash.Sum(nil)), nil
}

func validateRelative(value string) error {
	if value == "" || strings.Contains(value, `\`) || strings.HasPrefix(value, "/") || path.Clean(value) != value {
		return fmt.Errorf("manifest path is not canonical: %s", value)
	}
	for _, part := range strings.Split(value, "/") {
		if part == "" || part == "." || part == ".." {
			return fmt.Errorf("manifest path is not canonical: %s", value)
		}
	}
	return nil
}

func isJSON(name string) bool {
	return strings.HasSuffix(name, ".json") || strings.HasSuffix(name, ".decoded.json")
}

func mediaType(name string) string {
	lower := strings.ToLower(name)
	switch {
	case strings.HasSuffix(lower, ".json") || strings.HasSuffix(lower, ".decoded.json"):
		return "application/json"
	case strings.HasSuffix(lower, ".yaml") || strings.HasSuffix(lower, ".yml"):
		return "application/yaml"
	case strings.HasSuffix(lower, ".zip"):
		return "application/zip"
	default:
		if value := mime.TypeByExtension(filepath.Ext(lower)); value != "" {
			return strings.Split(value, ";")[0]
		}
		return "application/octet-stream"
	}
}
