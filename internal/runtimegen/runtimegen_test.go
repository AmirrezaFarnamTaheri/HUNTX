package runtimegen

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestVerifyRequiresStateDatabase(t *testing.T) {
	root := t.TempDir()
	manifest := Manifest{SchemaVersion: 1, Generation: "test", Files: map[string]FileRecord{}}
	if err := Verify(root, manifest); err == nil || !strings.Contains(err.Error(), "missing state.db") {
		t.Fatalf("expected missing state.db error, got %v", err)
	}
}

func TestVerifyBuiltGeneration(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "state.db"), []byte("synthetic state"), 0o600); err != nil {
		t.Fatal(err)
	}
	manifest, err := Build(root, "test")
	if err != nil {
		t.Fatal(err)
	}
	if err := Verify(root, manifest); err != nil {
		t.Fatalf("Verify built generation: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "extra.txt"), []byte("extra"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := Verify(root, manifest); err == nil {
		t.Fatal("expected unexpected file to fail verification")
	}
}
