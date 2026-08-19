package outputverify

import (
	"os"
	"path/filepath"
	"testing"
)

func TestVerifySkipsInternalOutputOwnershipManifest(t *testing.T) {
	dataDir := t.TempDir()
	outputDir := filepath.Join(dataDir, "outputs")
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		filepath.Join(outputDir, "route.npvt"),
		[]byte("vless://uuid@example.com:443\n"),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		filepath.Join(outputDir, outputOwnershipManifest),
		[]byte(`{"schema_version":1,"files":{"route.npvt":{"route":"route","format":"npvt"}}}`),
		0o600,
	); err != nil {
		t.Fatal(err)
	}

	summary, err := Verify(dataDir)
	if err != nil {
		t.Fatalf("Verify returned error: %v", err)
	}
	if summary.Files != 1 {
		t.Fatalf("expected exactly one distributable file, got %d", summary.Files)
	}
	if _, err := os.Stat(filepath.Join(dataDir, "dist", outputOwnershipManifest)); !os.IsNotExist(err) {
		t.Fatalf("internal ownership manifest leaked into dist: err=%v", err)
	}
	if _, err := os.Stat(filepath.Join(dataDir, "dist", "route.npvt")); err != nil {
		t.Fatalf("expected route.npvt in dist: %v", err)
	}
}
