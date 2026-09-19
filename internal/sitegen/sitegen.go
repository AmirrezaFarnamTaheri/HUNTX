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
	IntentionalEmpty bool    `json:"intentional_empty,omitempty"`
	MinIngestedAt    string  `json:"min_ingested_at,omitempty"`
	SchemaVersion    int     `json:"schema_version"`
	GeneratedAt      string  `json:"generated_at"`
	ReleaseManifest  string  `json:"release_manifest"`
	TotalFiles       int     `json:"total_files"`
	TotalSize        int64   `json:"total_size"`
	TotalSizeString  string  `json:"total_size_str"`
	Files            []Entry `json:"files"`
}

type productMetadata struct {
	Tags        []string
	Description string
}

// frontendReleaseProducts is deliberately narrower than the release manifest.
// The manifest remains the compatibility/source-of-truth inventory, while the
// dashboard shows only the canonical end-user products. Legacy aliases and
// specialist formats stay downloadable by direct URL without being advertised
// as separate products.
var frontendReleaseProducts = map[string]productMetadata{
	"all_sources_npvt_raw.txt": {
		Tags: []string{"release", "verified", "subscription", "multi-node", "uri-feed"},
		Description: "Canonical multi-node proxy URI subscription feed. Add this URL as a subscription in compatible clients; each line is an individual proxy node.",
	},
	"all_sources_npvt_singbox.json": {
		Tags: []string{"release", "verified", "singbox", "full-config", "profile"},
		Description: "Complete sing-box client configuration containing all representable proxy outbounds. Importing this JSON creates one profile by design; use the raw TXT feed for a multi-node subscription.",
	},
	"all_sources_npvt_xray.json": {
		Tags: []string{"release", "verified", "xray", "full-config", "profile"},
		Description: "Complete Xray client configuration containing all representable proxy outbounds. Importing this JSON creates one profile by design; use the raw TXT feed for a multi-node subscription.",
	},
	"all_sources_npvt_nekobox.json": {
		Tags: []string{"release", "verified", "nekobox", "outbound-bundle", "profile"},
		Description: "NekoBox-compatible outbound bundle. Clients that import JSON as a custom configuration show this as one profile; use the raw TXT feed when a subscription URL is required.",
	},
	"all_sources_npvt_decoded.json": {
		Tags: []string{"release", "verified", "decoded", "diagnostic", "dataset"},
		Description: "Decoded structured proxy dataset for inspection and dashboard telemetry. This is diagnostic JSON, not a client subscription.",
	},
}

func frontendReleaseProduct(path string) (productMetadata, bool) {
	metadata, ok := frontendReleaseProducts[filepath.Base(path)]
	return metadata, ok
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
	intentionalEmpty := releasemanifest.IsEmptyRelease(manifest)
	var emptyMarker releasemanifest.EmptyRelease
	if intentionalEmpty {
		emptyMarker, err = releasemanifest.ReadEmptyRelease(filepath.Join(dist, releasemanifest.EmptyReleaseArtifact))
		if err != nil {
			return Catalog{}, err
		}
		generatedAt, err = time.Parse(time.RFC3339Nano, emptyMarker.GeneratedAt)
		if err != nil {
			return Catalog{}, err
		}
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
		metadata, visible := frontendReleaseProduct(record.Path)
		if intentionalEmpty || !visible {
			continue
		}
		entries = append(entries, Entry{
			Filename:    filepath.Base(record.Path),
			Path:        filepath.ToSlash(filepath.Join("artifacts", "release", record.Path)),
			Size:        record.Size,
			SizeString:  formatSize(record.Size),
			MediaType:   record.MediaType,
			SHA256:      record.SHA256,
			Tags:        append([]string(nil), metadata.Tags...),
			Section:     "release",
			Type:        artifactType(record.Path),
			Ext:         artifactType(record.Path),
			Description: metadata.Description,
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
		IntentionalEmpty: intentionalEmpty,
		MinIngestedAt:    emptyMarker.MinIngestedAt,
		SchemaVersion:    1,
		GeneratedAt:      generatedAt.UTC().Format(time.RFC3339Nano),
		ReleaseManifest:  "artifacts/release/manifest.json",
		TotalFiles:       len(entries),
		TotalSize:        total,
		TotalSizeString:  formatSize(total),
		Files:            entries,
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
	defer os.Remove(catalogStage)

	target := filepath.Join(docsDir, "artifacts")
	backup := target + ".backup"
	catalogTarget := filepath.Join(docsDir, "catalog.json")
	catalogBackup := catalogTarget + ".backup"
	_ = os.RemoveAll(backup)
	_ = os.Remove(catalogBackup)
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
	hadOldCatalog := false
	if _, err := os.Stat(catalogTarget); err == nil {
		if err := os.Rename(catalogTarget, catalogBackup); err != nil {
			_ = os.RemoveAll(target)
			if hadOld {
				_ = os.Rename(backup, target)
			}
			return Catalog{}, err
		}
		hadOldCatalog = true
	} else if !os.IsNotExist(err) {
		_ = os.RemoveAll(target)
		if hadOld {
			_ = os.Rename(backup, target)
		}
		return Catalog{}, err
	}
	if err := os.Rename(catalogStage, catalogTarget); err != nil {
		_ = os.RemoveAll(target)
		if hadOld {
			_ = os.Rename(backup, target)
		}
		if hadOldCatalog {
			_ = os.Rename(catalogBackup, catalogTarget)
		}
		return Catalog{}, err
	}
	if hadOld {
		_ = os.RemoveAll(backup)
	}
	if hadOldCatalog {
		_ = os.Remove(catalogBackup)
	}
	return catalog, nil
}

func ValidateCatalog(catalog Catalog) error {
	if catalog.SchemaVersion != 1 {
		return errors.New("unsupported catalog schema")
	}
	if catalog.IntentionalEmpty {
		if catalog.TotalFiles != 0 || len(catalog.Files) != 0 || catalog.Files == nil || catalog.TotalSize != 0 {
			return errors.New("intentional empty catalog contains artifacts")
		}
		if _, err := time.Parse(time.RFC3339Nano, catalog.GeneratedAt); err != nil || catalog.ReleaseManifest == "" {
			return errors.New("intentional empty catalog requires release metadata")
		}
	} else if catalog.TotalFiles <= 0 || catalog.TotalFiles != len(catalog.Files) {
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
	case strings.HasSuffix(filename, ".singbox.json"), strings.HasSuffix(filename, "_singbox.json"):
		return "SINGBOX"
	case strings.HasSuffix(filename, ".xray.json"), strings.HasSuffix(filename, "_xray.json"):
		return "XRAY"
	case strings.HasSuffix(filename, ".nekobox.json"), strings.HasSuffix(filename, "_nekobox.json"):
		return "NEKOBOX"
	case strings.HasSuffix(filename, ".b64sub"), strings.HasSuffix(filename, "_b64sub.txt"):
		return "B64SUB"
	case strings.HasSuffix(filename, ".ovpn"):
		return "OVPN"
	case strings.HasSuffix(filename, "_raw.txt"):
		return "NPVT"
	case strings.HasSuffix(filename, ".json"):
		return "JSON"
	case strings.HasSuffix(filename, ".txt"):
		return "TXT"
	}
	return strings.TrimPrefix(strings.ToUpper(filepath.Ext(filename)), ".")
}
