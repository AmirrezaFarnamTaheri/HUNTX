package releasemanifest

import (
	"strings"
	"testing"
)

func TestValidateClientJSONContracts(t *testing.T) {
	cases := []struct {
		name    string
		content string
		reject  bool
	}{
		{"all_sources_nekobox.json", `[{"type":"trojan","tag":"node"}]`, false},
		{"all_sources_npvt_nekobox.json", `[{"type":"vless","tag":"node"}]`, false},
		{"all_sources.npvt.nekobox.json", `[{"type":"vless","tag":"node"}]`, false},
		{"all_sources_nekobox.json", `{"outbounds":[{"type":"trojan","tag":"node"}]}`, true},
		{"all_sources_npvt_nekobox.json", `[]`, true},
		{"all_sources_nekobox.json", `[{"type":"trojan"}]`, true},
		{"all_sources_nekobox.json", `[{"type":"direct","tag":"direct"}]`, true},
		{"all_sources_nekobox.json", `[{"type":"trojan","tag":"a"},{"type":"vless","tag":"a"}]`, true},
		{"all_sources_singbox_nodes.json", `{"outbounds":[{"type":"trojan","tag":"a"}]}`, false},
		{"all_sources_singbox_nodes.json", `{"inbounds":[],"outbounds":[{"type":"trojan","tag":"a"}]}`, true},
		{"all_sources_xray_nodes.json", `{"outbounds":[{"protocol":"vless","tag":"a"}]}`, false},
		{"all_sources_xray_nodes.json", `{"outbounds":[{"type":"vless","tag":"a"}]}`, true},
		{"all_sources_singbox.json", `{"inbounds":[{}],"outbounds":[{}],"dns":{},"route":{}}`, false},
		{"all_sources_singbox.json", `{"outbounds":[{}]}`, true},
		{"all_sources_npvt_xray.json", `{"inbounds":[{}],"outbounds":[{}]}`, false},
		{"all_sources_xray.json", `{"outbounds":[{}]}`, true},
		{"all_sources.json", `{"entries":[{"type":"vless"}]}`, false},
	}
	for _, tc := range cases {
		t.Run(tc.name+"/"+tc.content, func(t *testing.T) {
			err := ValidateClientJSON(tc.name, []byte(tc.content))
			if tc.reject && err == nil {
				t.Fatalf("accepted invalid %s: %s", tc.name, tc.content)
			}
			if !tc.reject && err != nil {
				t.Fatalf("rejected valid %s: %v", tc.name, err)
			}
		})
	}
}

func TestMalformedJSONIncludesArtifactFilename(t *testing.T) {
	err := ValidateClientJSON("all_sources_nekobox.json", []byte("{"))
	if err == nil || !strings.Contains(err.Error(), "all_sources_nekobox.json") {
		t.Fatalf("missing filename context: %v", err)
	}
}
