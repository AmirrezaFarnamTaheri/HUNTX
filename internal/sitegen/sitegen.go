package sitegen

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/releasemanifest"
)

type Catalog struct {
	SchemaVersion int `json:"schema_version"`
	GeneratedAt string `json:"generated_at"`
	ReleaseManifest string `json:"release_manifest"`
	TotalFiles int `json:"total_files"`
	TotalSize int64 `json:"total_size"`
	Files []map[string]any `json:"files"`
}

func Generate(dataDir, docsDir string, generatedAt time.Time) (Catalog, error) {
	dist := filepath.Join(dataDir, "dist")
	manifestPath := filepath.Join(dist, "manifest.json")
	files, err := releasemanifest.Discover(dist, manifestPath)
	if err != nil { return Catalog{}, err }
	manifest, err := releasemanifest.Build(dist, files)
	if err != nil { return Catalog{}, err }
	if err := releasemanifest.Verify(dist, manifest); err != nil { return Catalog{}, err }
	artifacts := filepath.Join(docsDir, "artifacts")
	stage := artifacts + ".stage"
	_ = os.RemoveAll(stage)
	if err := os.MkdirAll(stage, 0755); err != nil { return Catalog{}, err }
	entries := make([]map[string]any, 0, len(manifest.Artifacts))
	sorted := append([]releasemanifest.Artifact(nil), manifest.Artifacts...)
	sort.Slice(sorted, func(i,j int) bool { return sorted[i].Path < sorted[j].Path })
	for _, artifact := range sorted {
		src := filepath.Join(dist, filepath.FromSlash(artifact.Path))
		dst := filepath.Join(stage, filepath.FromSlash(artifact.Path))
		if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil { return Catalog{}, err }
		data, err := os.ReadFile(src)
		if err != nil { return Catalog{}, err }
		if err := os.WriteFile(dst, data, 0600); err != nil { return Catalog{}, err }
		entries = append(entries, map[string]any{"filename": filepath.Base(artifact.Path), "path": filepath.ToSlash(filepath.Join("artifacts", artifact.Path)), "size": artifact.Size, "media_type": artifact.MediaType, "sha256": artifact.SHA256, "tags": []string{"release"}})
	}
	if err := os.Rename(stage, artifacts); err != nil { return Catalog{}, err }
	catalog := Catalog{SchemaVersion: 1, GeneratedAt: generatedAt.UTC().Format(time.RFC3339Nano), ReleaseManifest: "artifacts/manifest.json", TotalFiles: len(entries), TotalSize: 0, Files: entries}
	for _, item := range manifest.Artifacts { catalog.TotalSize += item.Size }
	payload, err := json.MarshalIndent(catalog, "", "  ")
	if err != nil { return Catalog{}, err }
	if err := os.WriteFile(filepath.Join(docsDir, "catalog.json"), append(payload, '\n'), 0644); err != nil { return Catalog{}, err }
	return catalog, nil
}

func ValidateCatalog(c Catalog) error {
	if c.SchemaVersion != 1 || c.TotalFiles != len(c.Files) || c.TotalFiles == 0 { return errors.New("invalid catalog") }
	for _, file := range c.Files { if file["sha256"] == nil { return fmt.Errorf("catalog entry missing digest") } }
	return nil
}
