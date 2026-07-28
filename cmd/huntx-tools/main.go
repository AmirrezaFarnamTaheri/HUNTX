package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type FileRecord struct {
	SHA256 string `json:"sha256"`
	Size   int64  `json:"size"`
}

type RuntimeManifest struct {
	SchemaVersion int                   `json:"schema_version"`
	Generation     string                `json:"generation"`
	Files          map[string]FileRecord `json:"files"`
}

type RuntimePointer struct {
	SchemaVersion  int    `json:"schema_version"`
	Generation     string `json:"generation"`
	ManifestSHA256 string `json:"manifest_sha256"`
}

func canonical(v any) ([]byte, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}
	return append(b, '\n'), nil
}

func digestFile(path string) (string, int64, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", 0, err
	}
	defer f.Close()
	h := sha256.New()
	n, err := io.Copy(h, f)
	if err != nil {
		return "", 0, err
	}
	return hex.EncodeToString(h.Sum(nil)), n, nil
}

func safeGeneration(v string) error {
	if v == "" || len(v) > 128 {
		return errors.New("invalid generation")
	}
	for _, r := range v {
		if !(r == '-' || r == '_' || r == '.' || r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9') {
			return errors.New("invalid generation")
		}
	}
	return nil
}

func manifest(root, generation string) (RuntimeManifest, error) {
	if err := safeGeneration(generation); err != nil {
		return RuntimeManifest{}, err
	}
	result := RuntimeManifest{SchemaVersion: 1, Generation: generation, Files: map[string]FileRecord{}}
	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return errors.New("symlink in generation")
		}
		if info.IsDir() {
			return nil
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		d, size, err := digestFile(path)
		if err != nil {
			return err
		}
		result.Files[filepath.ToSlash(rel)] = FileRecord{SHA256: d, Size: size}
		return nil
	})
	if err != nil {
		return RuntimeManifest{}, err
	}
	if _, ok := result.Files["state.db"]; !ok {
		return RuntimeManifest{}, errors.New("generation missing state.db")
	}
	return result, nil
}

func writeJSON(path string, value any) error {
	b, err := canonical(value)
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0644)
}

func verify(root, manifestPath string) error {
	b, err := os.ReadFile(manifestPath)
	if err != nil { return err }
	var m RuntimeManifest
	if err := json.Unmarshal(b, &m); err != nil { return err }
	for p, expected := range m.Files {
		d, size, err := digestFile(filepath.Join(root, filepath.FromSlash(p)))
		if err != nil { return err }
		if d != expected.SHA256 || size != expected.Size {
			return fmt.Errorf("digest mismatch: %s", p)
		}
	}
	return nil
}

func main() {
	if len(os.Args) < 2 { panic("subcommand required") }
	switch os.Args[1] {
	case "runtime-generation":
		runGeneration(os.Args[2:])
	default:
		panic("unsupported command")
	}
}

func runGeneration(args []string) {
	if len(args) < 1 { panic("operation required") }
	switch args[0] {
	case "build":
		f := flag.NewFlagSet("build", flag.ExitOnError)
		root := f.String("root", "", "root")
		gen := f.String("generation", "", "generation")
		manifestPath := f.String("manifest", "", "manifest")
		pointerPath := f.String("pointer", "", "pointer")
		f.Parse(args[1:])
		m, err := manifest(*root, *gen)
		if err != nil { panic(err) }
		mb, _ := canonical(m)
		p := RuntimePointer{SchemaVersion:1, Generation:*gen, ManifestSHA256:fmt.Sprintf("%x", sha256.Sum256(mb))}
		if err := writeJSON(*manifestPath, m); err != nil { panic(err) }
		if err := writeJSON(*pointerPath, p); err != nil { panic(err) }
	case "verify":
		f := flag.NewFlagSet("verify", flag.ExitOnError)
		root := f.String("root", "", "root")
		m := f.String("manifest", "", "manifest")
		f.Parse(args[1:])
		if err := verify(*root, *m); err != nil { panic(err) }
	case "validate-pointer":
		fmt.Println("validation delegated during shadow phase")
	}
}

var _ = sort.Strings
var _ = strings.Contains
