package releasemanifest

import (
	"os"
	"path/filepath"
	"testing"
)

const validEmpty = `{"schema_version":1,"status":"success","record_count":0,"reason":"no_eligible_records","generated_at":"2026-09-17T20:00:00Z","min_ingested_at":"2026-09-14T20:00:00Z"}`

func TestExplicitEmptyReleaseContract(t *testing.T) {
	root := t.TempDir()
	marker := filepath.Join(root, EmptyReleaseArtifact)
	if err := os.WriteFile(marker, []byte(validEmpty), 0o600); err != nil {
		t.Fatal(err)
	}
	manifest, err := Build(root, []string{marker})
	if err != nil || !IsEmptyRelease(manifest) {
		t.Fatalf("expected explicit empty release: %v", err)
	}
	if err := Verify(root, manifest); err != nil {
		t.Fatal(err)
	}
	if _, err := Build(root, nil); err == nil {
		t.Fatal("missing artifacts must not imply intentional empty")
	}
	if err := Verify(root, Manifest{SchemaVersion: 1, Artifacts: []Artifact{}}); err == nil {
		t.Fatal("zero-artifact manifest must remain invalid")
	}
	other := filepath.Join(root, "other.txt")
	if err := os.WriteFile(other, []byte("stale"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Build(root, []string{marker, other}); err == nil {
		t.Fatal("empty marker cannot coexist with stale artifacts")
	}
	if err := os.WriteFile(other, nil, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Build(root, []string{other}); err == nil {
		t.Fatal("generic nonempty validation must remain enforced")
	}
}

func TestInvalidEmptyReleaseMarkers(t *testing.T) {
	for _, payload := range []string{
		`{}`,
		`{"schema_version":1,"status":"failed","record_count":0,"reason":"no_eligible_records","generated_at":"2026-09-17T20:00:00Z"}`,
		`{"schema_version":1,"status":"success","reason":"no_eligible_records","generated_at":"2026-09-17T20:00:00Z"}`,
		`{"schema_version":1,"status":"success","record_count":1,"reason":"no_eligible_records","generated_at":"2026-09-17T20:00:00Z"}`,
		`{"schema_version":1,"status":"success","record_count":0,"reason":"no_eligible_records"}`,
		`{"schema_version":1,"status":"success","record_count":0,"reason":"no_eligible_records","generated_at":"2026-09-17T20:00:00Z","min_ingested_at":null}`,
		`{"schema_version":1,"status":"success","record_count":0,"reason":"no_eligible_records","generated_at":"2026-09-17T20:00:00Z","min_ingested_at":""}`,
		validEmpty + `{}`,
	} {
		t.Run(payload, func(t *testing.T) {
			root := t.TempDir()
			marker := filepath.Join(root, EmptyReleaseArtifact)
			if err := os.WriteFile(marker, []byte(payload), 0o600); err != nil {
				t.Fatal(err)
			}
			if _, err := Build(root, []string{marker}); err == nil {
				t.Fatal("invalid marker accepted")
			}
		})
	}
}
