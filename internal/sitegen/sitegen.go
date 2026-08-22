package sitegen

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/releasemanifest"
	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/runtimegen"
)

type Entry struct {
	Filename    string   `json:"filename"`
	Path        string   `json:"path"`
	Size        int64    `json:"size"`
	SizeString  string   `json:"size_str"`
	MediaType   string   `json:"media_type"`
	SHA256      string   `json:"sha256"`
	Tags        []string `json:"tags"`
	Section     string   `json:"section"`
	Type        string   `json:"type"`
	Ext         string   `json:"ext"`
	Description string   `json:"description"`
}

type Catalog struct {
	SchemaVersion   int     `json:"schema_version"`
	GeneratedAt     string  `json:"generated_at"`
	ReleaseManifest string  `json:"release_manifest"`
	TotalFiles      int     `json:"total_files"`
	TotalSize       int64   `json:"total_size"`
	TotalSizeString string  `json:"total_size_str"`
	Files           []Entry `json:"files"`
}

func Generate(dataDir, docsDir string, generatedAt time.Time) (Catalog, error) {
	dist := filepath.Join(dataDir, "dist")
	manifestPath := filepath.Join(dist, "manifest.json")
	manifest, err := releasemanifest.Read(manifestPath)
	if err != nil {
		return Catalog{}, err
	}
	if err := releasemanifest.Verify(dist, manifest); err != nil {
		return Catalog{}, err
	}
	if err := os.MkdirAll(docsDir, 0o755); err != nil {
		return Catalog{}, err
	}
	stage, err := os.MkdirTemp(docsDir, ".artifacts-stage-")
	if err != nil {
		return Catalog{}, err
	}
	defer os.RemoveAll(stage)

	entries := make([]Entry, 0, len(manifest.Artifacts))
	var total int64
	for _, record := range manifest.Artifacts {
		source := filepath.Join(dist, filepath.FromSlash(record.Path))
		destination := filepath.Join(stage, "release", filepath.FromSlash(record.Path))
		if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
			return Catalog{}, err
		}
		payload, err := os.ReadFile(source)
		if err != nil {
			return Catalog{}, err
		}
		if err := runtimegen.WriteBytesAtomic(destination, payload, 0o600); err != nil {
			return Catalog{}, err
		}
		entries = append(entries, Entry{
			Filename:    filepath.Base(record.Path),
			Path:        filepath.ToSlash(filepath.Join("artifacts", "release", record.Path)),
			Size:        record.Size,
			SizeString:  formatSize(record.Size),
			MediaType:   record.MediaType,
			SHA256:      record.SHA256,
			Tags:        []string{"release", "verified"},
			Section:     "release",
			Type:        artifactType(record.Path),
			Ext:         artifactType(record.Path),
			Description: "Verified artifact from the latest published run",
		})
		total += record.Size
	}

	manifestBytes, err := os.ReadFile(manifestPath)
	if err != nil {
		return Catalog{}, err
	}
	if err := runtimegen.WriteBytesAtomic(filepath.Join(stage, "release", "manifest.json"), manifestBytes, 0o600); err != nil {
		return Catalog{}, err
	}

	catalog := Catalog{
		SchemaVersion:   1,
		GeneratedAt:     generatedAt.UTC().Format(time.RFC3339Nano),
		ReleaseManifest: "artifacts/release/manifest.json",
		TotalFiles:      len(entries),
		TotalSize:       total,
		TotalSizeString: formatSize(total),
		Files:           entries,
	}
	if err := ValidateCatalog(catalog); err != nil {
		return Catalog{}, err
	}
	payload, err := json.MarshalIndent(catalog, "", "  ")
	if err != nil {
		return Catalog{}, err
	}
	catalogStage := filepath.Join(docsDir, ".catalog.json.stage")
	if err := runtimegen.WriteBytesAtomic(catalogStage, append(payload, '\n'), 0o600); err != nil {
		return Catalog{}, err
	}

	target := filepath.Join(docsDir, "artifacts")
	backup := target + ".backup"
	_ = os.RemoveAll(backup)
	hadOld := false
	if _, err := os.Stat(target); err == nil {
		if err := os.Rename(target, backup); err != nil {
			return Catalog{}, err
		}
		hadOld = true
	} else if !os.IsNotExist(err) {
		return Catalog{}, err
	}
	if err := os.Rename(stage, target); err != nil {
		if hadOld {
			_ = os.Rename(backup, target)
		}
		return Catalog{}, err
	}
	if err := os.Rename(catalogStage, filepath.Join(docsDir, "catalog.json")); err != nil {
		_ = os.RemoveAll(target)
		if hadOld {
			_ = os.Rename(backup, target)
		}
		return Catalog{}, err
	}
	if hadOld {
		_ = os.RemoveAll(backup)
	}
	return catalog, nil
}

func ValidateCatalog(catalog Catalog) error {
	if catalog.SchemaVersion != 1 {
		return errors.New("unsupported catalog schema")
	}
	if catalog.TotalFiles <= 0 || catalog.TotalFiles != len(catalog.Files) {
		return errors.New("catalog file count mismatch")
	}
	var total int64
	seen := map[string]bool{}
	for _, entry := range catalog.Files {
		if entry.Path == "" || entry.SHA256 == "" || entry.Size <= 0 || seen[entry.Path] {
			return fmt.Errorf("invalid catalog entry: %s", entry.Path)
		}
		seen[entry.Path] = true
		total += entry.Size
	}
	if total != catalog.TotalSize {
		return errors.New("catalog size mismatch")
	}
	return nil
}

func formatSize(size int64) string {
	if size < 1024 {
		return fmt.Sprintf("%d B", size)
	}
	if size < 1024*1024 {
		return fmt.Sprintf("%.1f KB", float64(size)/1024)
	}
	return fmt.Sprintf("%.1f MB", float64(size)/(1024*1024))
}

func artifactType(path string) string {
	filename := strings.ToLower(filepath.Base(path))
	switch {
	case strings.HasSuffix(filename, ".singbox.json"):
		return "SINGBOX"
	case strings.HasSuffix(filename, ".b64sub"):
		return "B64SUB"
	case strings.HasSuffix(filename, ".ovpn"):
		return "OVPN"
	case strings.HasSuffix(filename, ".json"):
		return "JSON"
	case strings.HasSuffix(filename, ".txt"):
		return "TXT"
	}
	return strings.TrimPrefix(strings.ToUpper(filepath.Ext(filename)), ".")
}
