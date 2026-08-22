package sitegen

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/releasemanifest"
)

func TestGeneratePublishesReleasePathsAndCatalogFields(t *testing.T) {
	dataDir := t.TempDir()
	dist := filepath.Join(dataDir, "dist")
	if err := os.MkdirAll(dist, 0o755); err != nil {
		t.Fatal(err)
	}
	artifact := filepath.Join(dist, "all_sources.npvt.b64sub")
	if err := os.WriteFile(artifact, []byte("dm1lc3M6Ly9leGFtcGxl"), 0o600); err != nil {
		t.Fatal(err)
	}
	manifest, err := releasemanifest.Build(dist, []string{artifact})
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dist, "manifest.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}

	docsDir := filepath.Join(t.TempDir(), "docs")
	catalog, err := Generate(dataDir, docsDir, time.Date(2026, 8, 22, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if got, want := catalog.Files[0].Path, "artifacts/release/all_sources.npvt.b64sub"; got != want {
		t.Fatalf("artifact path = %q, want %q", got, want)
	}
	if got, want := catalog.Files[0].Type, "B64SUB"; got != want {
		t.Fatalf("artifact type = %q, want %q", got, want)
	}
	for _, path := range []string{
		filepath.Join(docsDir, "catalog.json"),
		filepath.Join(docsDir, "artifacts", "release", "all_sources.npvt.b64sub"),
		filepath.Join(docsDir, "artifacts", "release", "manifest.json"),
	} {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("expected published file %q: %v", path, err)
		}
	}
}
