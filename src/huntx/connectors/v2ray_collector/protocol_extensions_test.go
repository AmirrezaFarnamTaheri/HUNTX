package main

import "testing"

func TestHysteria2PatternAcceptsBothOfficialSchemes(t *testing.T) {
	fixtures := []string{
		"hy2://secret@example.com:443",
		"hysteria2://secret@example.com:443",
	}
	for _, fixture := range fixtures {
		if got := patterns["hysteria2"].FindString(fixture); got != fixture {
			t.Fatalf("matcher missed %q: got %q", fixture, got)
		}
	}
}
