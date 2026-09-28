package sitegen

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/releasemanifest"
)

// The publisher is a workflow_run consumer: it checks out the current code but
// consumes a dist produced by whichever pipeline run last succeeded, which may
// predate a rename. When the allowlist accepted only the post-rename names, a
// pre-rename dist matched nothing, produced a catalog with zero products, and
// failed the release with "catalog file count mismatch" - which is exactly what
// happened on main after the artifact rename merged.
func writeDist(t *testing.T, names ...string) (string, string) {
	t.Helper()
	dataDir := t.TempDir()
	dist := filepath.Join(dataDir, "dist")
	if err := os.MkdirAll(dist, 0o755); err != nil {
		t.Fatal(err)
	}
	// Build takes filesystem paths and records each artifact's path relative to
	// root, which is what Generate later joins back onto dist. JSON artifacts get
	// parsed while the manifest is built, so they must be valid JSON.
	paths := make([]string, 0, len(names))
	for _, name := range names {
		payload := []byte(name + " payload")
		if filepath.Ext(name) == ".json" {
			payload = []byte(`{"ok":true,"artifact":"` + name + `"}`)
		}
		full := filepath.Join(dist, name)
		if err := os.WriteFile(full, payload, 0o600); err != nil {
			t.Fatal(err)
		}
		paths = append(paths, full)
	}
	manifest, err := releasemanifest.Build(dist, paths)
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
	return dataDir, dist
}

func generatedNames(t *testing.T, catalog Catalog) []string {
	t.Helper()
	names := make([]string, 0, len(catalog.Files))
	for _, f := range catalog.Files {
		names = append(names, f.Filename)
	}
	return names
}

func TestGenerateAcceptsAPreRenameDist(t *testing.T) {
	dataDir, _ := writeDist(t,
		"all_sources.npvt",
		"all_sources.npvt.b64sub",
		"all_sources_npvt_decoded.json",
		"all_sources_npvt_nekobox.json",
		"all_sources_npvt_singbox.json",
		"all_sources_npvt_xray.json",
		"all_sources.ovpn",
	)

	catalog, err := Generate(dataDir, filepath.Join(t.TempDir(), "docs"), time.Now())
	if err != nil {
		t.Fatalf("a dist from before the rename must still publish: %v", err)
	}
	if got, want := len(catalog.Files), 6; got != want {
		t.Fatalf("catalog files = %d (%v), want %d", got, generatedNames(t, catalog), want)
	}
	if catalog.TotalFiles != len(catalog.Files) {
		t.Fatalf("TotalFiles = %d, want %d", catalog.TotalFiles, len(catalog.Files))
	}
}

func TestGenerateAcceptsAPostRenameDist(t *testing.T) {
	dataDir, _ := writeDist(t,
		"all_sources.txt",
		"all_sources_base64.txt",
		"all_sources.json",
		"all_sources_nekobox.json",
		"all_sources_singbox.json",
		"all_sources_xray.json",
		"all_sources.ovpn",
	)

	catalog, err := Generate(dataDir, filepath.Join(t.TempDir(), "docs"), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(catalog.Files), 6; got != want {
		t.Fatalf("catalog files = %d (%v), want %d", got, generatedNames(t, catalog), want)
	}
}

func TestGenerateAdvertisesEachProductOnceWhenBothNamesArePresent(t *testing.T) {
	// After the rename the export publishes the canonical name *and* its frozen
	// aliases, so the dist legitimately carries both. The catalog must list the
	// product once, under the canonical name, not once per filename.
	dataDir, _ := writeDist(t,
		"all_sources.npvt",
		"all_sources.npvt.raw.txt",
		"all_sources.npvt.b64sub",
		"all_sources.txt",
		"all_sources_base64.txt",
		"all_sources_npvt_b64sub.txt",
		"all_sources_npvt_raw.txt",
	)

	catalog, err := Generate(dataDir, filepath.Join(t.TempDir(), "docs"), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	names := generatedNames(t, catalog)
	if got, want := len(names), 2; got != want {
		t.Fatalf("catalog files = %d (%v), want %d", got, names, want)
	}
	for _, want := range []string{"all_sources.txt", "all_sources_base64.txt"} {
		found := false
		for _, name := range names {
			if name == want {
				found = true
			}
		}
		if !found {
			t.Errorf("canonical name %q missing from %v", want, names)
		}
	}
}

func TestNonProductArtifactsStayUnadvertised(t *testing.T) {
	dataDir, _ := writeDist(t,
		"all_sources.txt",
		"all_sources.ovpn",
		"all_sources.opaque_bundle",
		"all_sources.conf_lines",
	)

	catalog, err := Generate(dataDir, filepath.Join(t.TempDir(), "docs"), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	names := generatedNames(t, catalog)
	if len(names) != 1 || names[0] != "all_sources.txt" {
		t.Fatalf("catalog = %v, want only the raw feed", names)
	}
}
