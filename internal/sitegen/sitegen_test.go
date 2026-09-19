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
	artifact := filepath.Join(dist, "all_sources_npvt_raw.txt")
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
	if got, want := catalog.Files[0].Path, "artifacts/release/all_sources_npvt_raw.txt"; got != want {
		t.Fatalf("artifact path = %q, want %q", got, want)
	}
	if got, want := catalog.Files[0].Type, "NPVT"; got != want {
		t.Fatalf("artifact type = %q, want %q", got, want)
	}
	for _, path := range []string{
		filepath.Join(docsDir, "catalog.json"),
		filepath.Join(docsDir, "artifacts", "release", "all_sources_npvt_raw.txt"),
		filepath.Join(docsDir, "artifacts", "release", "manifest.json"),
	} {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("expected published file %q: %v", path, err)
		}
	}
}

func TestGenerateReplacesExistingCatalog(t *testing.T) {
	dataDir := t.TempDir()
	dist := filepath.Join(dataDir, "dist")
	if err := os.MkdirAll(dist, 0o755); err != nil {
		t.Fatal(err)
	}
	artifact := filepath.Join(dist, "all_sources_npvt_raw.txt")
	writeRelease := func(payload string) {
		t.Helper()
		if err := os.WriteFile(artifact, []byte(payload), 0o600); err != nil {
			t.Fatal(err)
		}
		manifest, err := releasemanifest.Build(dist, []string{artifact})
		if err != nil {
			t.Fatal(err)
		}
		encoded, err := json.Marshal(manifest)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dist, "manifest.json"), encoded, 0o600); err != nil {
			t.Fatal(err)
		}
	}

	docsDir := filepath.Join(t.TempDir(), "docs")
	writeRelease("first")
	if _, err := Generate(dataDir, docsDir, time.Now()); err != nil {
		t.Fatal(err)
	}
	writeRelease("second-release")
	if _, err := Generate(dataDir, docsDir, time.Now()); err != nil {
		t.Fatalf("second generation must replace catalog and artifacts: %v", err)
	}
	published, err := os.ReadFile(filepath.Join(docsDir, "artifacts", "release", "all_sources_npvt_raw.txt"))
	if err != nil || string(published) != "second-release" {
		t.Fatalf("published release = %q, err=%v", published, err)
	}
}


func TestGenerateKeepsCompatibilityArtifactsOutOfProductCatalog(t *testing.T) {
	dataDir := t.TempDir()
	dist := filepath.Join(dataDir, "dist")
	if err := os.MkdirAll(dist, 0o755); err != nil {
		t.Fatal(err)
	}
	visible := filepath.Join(dist, "all_sources_npvt_raw.txt")
	stale := filepath.Join(dist, "all_sources.npvt.raw.txt")
	if err := os.WriteFile(visible, []byte("vless://canonical.example:443\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(stale, []byte("vless://legacy.example:443\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	manifest, err := releasemanifest.Build(dist, []string{visible, stale})
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
	catalog, err := Generate(dataDir, docsDir, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(catalog.Files), 1; got != want {
		t.Fatalf("catalog files = %d, want %d", got, want)
	}
	if got, want := catalog.Files[0].Filename, "all_sources_npvt_raw.txt"; got != want {
		t.Fatalf("catalog filename = %q, want %q", got, want)
	}
	if _, err := os.Stat(filepath.Join(docsDir, "artifacts", "release", "all_sources.npvt.raw.txt")); err != nil {
		t.Fatalf("compatibility artifact should remain directly downloadable: %v", err)
	}
}
