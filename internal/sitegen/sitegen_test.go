package sitegen

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
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

func TestGenerateReplacesExistingCatalog(t *testing.T) {
	dataDir := t.TempDir()
	dist := filepath.Join(dataDir, "dist")
	if err := os.MkdirAll(dist, 0o755); err != nil {
		t.Fatal(err)
	}
	artifact := filepath.Join(dist, "all_sources.npvt.b64sub")
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
	published, err := os.ReadFile(filepath.Join(docsDir, "artifacts", "release", "all_sources.npvt.b64sub"))
	if err != nil || string(published) != "second-release" {
		t.Fatalf("published release = %q, err=%v", published, err)
	}
}

// TestArtifactMetaClassifiesEveryShippedFormat guards the two ways this table
// has regressed: an underscored variant (all_sources_npvt_singbox.json) used to
// fall through to a generic JSON type and never appear in the dashboard's
// format filters, and undescribed formats shipped the placeholder description.
func TestArtifactMetaClassifiesEveryShippedFormat(t *testing.T) {
	shipped := []string{
		"all_sources.conf_lines",
		"all_sources.dark",
		"all_sources.ehi",
		"all_sources.hc",
		"all_sources.nm",
		"all_sources.npvt",
		"all_sources.npvt.b64sub",
		"all_sources.npvt.decoded.json",
		"all_sources.npvt.nekobox.json",
		"all_sources.npvt.raw.txt",
		"all_sources.npvt.singbox.json",
		"all_sources.npvt.xray.json",
		"all_sources.opaque_bundle",
		"all_sources.ovpn",
		"all_sources.sip",
		"all_sources_npvt_b64sub.txt",
		"all_sources_npvt_decoded.json",
		"all_sources_npvt_nekobox.json",
		"all_sources_npvt_raw.txt",
		"all_sources_npvt_singbox.json",
		"all_sources_npvt_xray.json",
	}
	for _, name := range shipped {
		tags, description, kind := artifactMeta(name)
		if description == "" || description == "Verified artifact from the latest published run" {
			t.Errorf("%s: undescribed artifact: %q", name, description)
		}
		if len(tags) < 3 {
			t.Errorf("%s: tags = %v, want the release base tags plus format tags", name, tags)
		}
		if kind == "JSON" || kind == "TXT" {
			// The decoded dataset is a JSON document and the raw copy is plain
			// text; every other feed has a format-specific type. A generic type
			// there means the name slipped past the classification table.
			if !strings.HasSuffix(name, "decoded.json") && !strings.HasSuffix(name, "raw.txt") {
				t.Errorf("%s: generic type %q", name, kind)
			}
		}
	}
}

// TestArtifactMetaKeepsClientConfigsOutOfSubscriptionTags encodes the contract
// the dashboard and the parity gate both depend on: a complete client
// configuration is a profile import, and advertising it as a subscription is
// what made clients import one JSON profile instead of a node list.
func TestArtifactMetaKeepsClientConfigsOutOfSubscriptionTags(t *testing.T) {
	for _, name := range []string{
		"all_sources.npvt.singbox.json",
		"all_sources_npvt_singbox.json",
		"all_sources.npvt.xray.json",
		"all_sources_npvt_xray.json",
	} {
		tags, _, kind := artifactMeta(name)
		if kind != "SINGBOX" && kind != "XRAY" {
			t.Errorf("%s: kind = %q, want SINGBOX or XRAY", name, kind)
		}
		for _, tag := range tags {
			if tag == "subscription" {
				t.Errorf("%s: complete client config must not carry the subscription tag", name)
			}
		}
	}
}

// TestEmbeddedTableIsTheOnePythonReads pins the single-source-of-truth claim:
// the bytes the Go tool compiles in must be the same bytes on disk that
// scripts/generate_site_data.py::_infer_tags_and_type reads. A copy of the
// table drifting from the original is the failure this prevents.
func TestEmbeddedTableIsTheOnePythonReads(t *testing.T) {
	embedded := artifactFormatsTable
	onDisk, err := os.ReadFile("artifact_formats.json")
	if err != nil {
		t.Fatalf("read table: %v", err)
	}
	if !bytes.Equal(embedded, onDisk) {
		t.Fatal("embedded artifact_formats.json differs from internal/sitegen/artifact_formats.json")
	}

	// The Python reader applies base_tags then the first matching rule; the Go
	// lookup must agree with it on every name either generator catalogs.
	// Expected values are generated from the same table by the Python parity
	// test in tests/test_output_telemetry_coverage.py, so a change here must be
	// made in the table and mirrored by regenerating that expectation.
	for _, name := range []string{
		"all_sources.npvt.singbox.json",
		"all_sources_npvt_xray.json",
		"all_sources.npvt.nekobox.json",
		"all_sources.npvt.b64sub",
		"all_sources.npvt",
		"all_sources.npvt.decoded.json",
		"all_sources.npvt.raw.txt",
	} {
		tags, description, kind := artifactMeta(name)
		section := sharedArtifactFormats.Sections["release"]
		if got, want := tags[0], section.BaseTags[0]; got != want {
			t.Errorf("%s: first tag = %q, want %q", name, got, want)
		}
		if description == "" {
			t.Errorf("%s: empty description", name)
		}
		if kind == "" {
			t.Errorf("%s: empty kind", name)
		}
	}
}

// TestEmbeddedTablePrecedenceIsSpecificToGeneric pins the ordering the table
// depends on: "all_sources.npvt.singbox.json" matches the generic npvt rule as
// well as the specific singbox one, and only file order makes the right one win.
// A rule inserted ahead of these, or a reorder that promotes npvt, would
// silently retype every prefixed variant.
func TestEmbeddedTablePrecedenceIsSpecificToGeneric(t *testing.T) {
	cases := []struct {
		name string
		kind string
	}{
		{"all_sources.npvt.singbox.json", "SINGBOX"},
		{"all_sources_npvt_singbox.json", "SINGBOX"},
		{"all_sources.npvt.xray.json", "XRAY"},
		{"all_sources_npvt_xray.json", "XRAY"},
		{"all_sources.npvt.nekobox.json", "NEKOBOX"},
		{"all_sources_npvt_nekobox.json", "NEKOBOX"},
		{"all_sources.npvt.decoded.json", "JSON"},
		{"all_sources_npvt_decoded.json", "JSON"},
		{"all_sources.npvt.raw.txt", "TXT"},
		{"all_sources_npvt_raw.txt", "TXT"},
		{"all_sources.npvt.b64sub", "B64SUB"},
		{"all_sources_npvt_b64sub.txt", "B64SUB"},
		// The unprefixed feed has no more specific rule, so npvt wins here.
		{"all_sources.npvt", "NPVT"},
	}
	for _, tc := range cases {
		_, _, kind := artifactMeta(tc.name)
		if kind != tc.kind {
			t.Errorf("%s: kind = %q, want %q", tc.name, kind, tc.kind)
		}
	}
}

// TestRuleMatchesImplementsEveryTableKind locks the match semantics the
// embedded table shares with scripts/generate_site_data.py::_rule_matches.
// Both generators read the same file, so a matcher that drifts here would
// retype artifacts with no test failing on the Python side.
func TestRuleMatchesImplementsEveryTableKind(t *testing.T) {
	cases := []struct {
		name  string
		rule  artifactFormatRule
		input string
		want  bool
	}{
		{"contains hit", artifactFormatRule{Match: map[string]any{"kind": "contains", "value": "singbox"}}, "all_sources.npvt.singbox.json", true},
		{"contains miss", artifactFormatRule{Match: map[string]any{"kind": "contains", "value": "singbox"}}, "all_sources.npvt.json", false},
		{"contains does not lowercase the caller's input", artifactFormatRule{Match: map[string]any{"kind": "contains", "value": "SINGBOX"}}, "all_sources.npvt.singbox.json", false},
		{"contains_any second of two", artifactFormatRule{Match: map[string]any{"kind": "contains_any", "value": []any{"v2ray", "xray"}}}, "all_sources.npvt.xray.json", true},
		{"contains_any neither", artifactFormatRule{Match: map[string]any{"kind": "contains_any", "value": []any{"v2ray", "xray"}}}, "all_sources.npvt.json", false},
		{"endswith hit", artifactFormatRule{Match: map[string]any{"kind": "endswith", "value": "decoded.json"}}, "all_sources.npvt.decoded.json", true},
		{"endswith is a suffix, not a substring", artifactFormatRule{Match: map[string]any{"kind": "endswith", "value": "decoded.json"}}, "decoded.json.all_sources", false},
		{"endswith_any one of three", artifactFormatRule{Match: map[string]any{"kind": "endswith_any", "value": []any{".tut", ".sks", ".tmt"}}}, "tunnel.sks", true},
		{"starts_with hit", artifactFormatRule{Match: map[string]any{"kind": "starts_with", "value": "proxies_chunk_"}}, "proxies_chunk_001.json", true},
		{"equals exact", artifactFormatRule{Match: map[string]any{"kind": "equals", "value": "proxies.json"}}, "proxies.json", true},
		{"equals rejects a longer name", artifactFormatRule{Match: map[string]any{"kind": "equals", "value": "proxies.json"}}, "proxies.json.bak", false},
		{"unknown kind never matches", artifactFormatRule{Match: map[string]any{"kind": "regex", "value": ".*"}}, "anything", false},
		{"empty predicate never matches", artifactFormatRule{Match: map[string]any{"kind": "contains", "value": ""}}, "all_sources.npvt.json", false},
		{"non-string predicate never matches", artifactFormatRule{Match: map[string]any{"kind": "contains", "value": 42}}, "all_sources.npvt.json", false},
		{"nil match never matches", artifactFormatRule{Match: nil}, "all_sources.npvt.json", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := ruleMatches(tc.input, tc.rule); got != tc.want {
				t.Errorf("ruleMatches(%q, %+v) = %v, want %v", tc.input, tc.rule, got, tc.want)
			}
		})
	}
}
