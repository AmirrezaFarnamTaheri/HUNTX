package stream

import (
	"encoding/base64"
	"strings"
	"testing"
)

func TestParseStreamRaw(t *testing.T) {
	raw := "vless://user1@host1:443#US\nvmess://user2@host2:443#DE\n"
	sp := NewStreamParser(64)
	records, err := sp.ParseStream(strings.NewReader(raw))
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if len(records) != 2 {
		t.Fatalf("Expected 2 records, got %d", len(records))
	}

	if records[0].Protocol != "vless" {
		t.Errorf("Expected vless, got %s", records[0].Protocol)
	}
}

func TestParseStreamBase64(t *testing.T) {
	raw := "vless://user1@host1:443#US\ntrojan://user3@host3:443#JP\n"
	b64 := base64.StdEncoding.EncodeToString([]byte(raw))

	sp := NewStreamParser(64)
	records, err := sp.ParseStream(strings.NewReader(b64))
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if len(records) != 2 {
		t.Fatalf("Expected 2 records, got %d", len(records))
	}

	if records[1].Protocol != "trojan" {
		t.Errorf("Expected trojan, got %s", records[1].Protocol)
	}
}
