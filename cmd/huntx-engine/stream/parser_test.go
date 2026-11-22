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
	if len(records[0].UniqueHash) != 64 {
		t.Fatalf("expected full SHA-256 hex identity, got %q", records[0].UniqueHash)
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

func TestParseStreamURLSafeUnpaddedBase64(t *testing.T) {
	raw := "hy2://secret@host.example:443\n"
	b64 := base64.RawURLEncoding.EncodeToString([]byte(raw))

	records, err := NewStreamParser(64).ParseStream(strings.NewReader(b64))
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}
	if len(records) != 1 || records[0].Protocol != "hy2" {
		t.Fatalf("unexpected records: %#v", records)
	}
}

func TestParseStreamIgnoresOrdinaryWebURLsAndProse(t *testing.T) {
	raw := "See https://example.com/docs\nhello world\nvless://user@host.example:443\n"
	records, err := NewStreamParser(64).ParseStream(strings.NewReader(raw))
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}
	if len(records) != 1 || records[0].Protocol != "vless" {
		t.Fatalf("ordinary web/prose input must not become proxy records: %#v", records)
	}
}

func TestParseStreamDeduplicatesByFullIdentity(t *testing.T) {
	uri := "trojan://secret@host.example:443"
	records, err := NewStreamParser(64).ParseStream(strings.NewReader(uri + "\n" + uri + "\n"))
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}
	if len(records) != 1 {
		t.Fatalf("expected one deduplicated record, got %d", len(records))
	}
}

func TestParseStreamRejectsExcessiveNestedBase64(t *testing.T) {
	payload := "vless://user@host.example:443\n"
	for i := 0; i < 4; i++ {
		payload = base64.StdEncoding.EncodeToString([]byte(payload))
	}
	sp := NewStreamParser(64)
	sp.MaxBase64Depth = 2

	if _, err := sp.ParseStream(strings.NewReader(payload)); err == nil {
		t.Fatal("expected excessive nested base64 to be rejected")
	}
}

func TestParseStreamBoundsDecodedPayload(t *testing.T) {
	raw := strings.Repeat("A", 256)
	b64 := base64.StdEncoding.EncodeToString([]byte(raw))
	sp := NewStreamParser(64)
	sp.MaxDecodedBytes = 64

	if _, err := sp.ParseStream(strings.NewReader(b64)); err == nil {
		t.Fatal("expected decoded payload size limit to be enforced")
	}
}

func TestParseStreamEmbeddedTelegramURIs(t *testing.T) {
	raw := "Quote Quote wireguard://cHJpdmF0ZQ==\\@198.51.100.2:51820?publickey=cHVibGlj\n" +
		"Please see https://example.org/docs for details\n" +
		"Reply: 'soar://eyJzY2hlbWEiOiJ3aGl0ZWRucy5wcm9maWxlIn0='\n" +
		"Quote Quote cottendns\\://Zm9v\n" +
		"Quote Quote slipnet-enc://QUJDREVGR0g=\n"
	sp := NewStreamParser(64)
	records, err := sp.ParseStream(strings.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	if len(records) != 4 {
		t.Fatalf("expected 4 embedded links, got %#v", records)
	}
	if records[0].Protocol != "wireguard" || strings.Contains(records[0].RawURI, "\\@") {
		t.Fatalf("Markdown normalization failed: %#v", records[0])
	}
	if records[1].Protocol != "soar" || records[2].Protocol != "cottendns" || records[3].Protocol != "slipnet-enc" {
		t.Fatalf("mixed formats lost: %#v", records)
	}
}

func BenchmarkParseStreamTelegramMixed(b *testing.B) {
	raw := strings.Repeat("Quote Quote vless://11111111-2222-3333-4444-555555555555@proxy.example.org:443#node\nIgnore https://example.org/docs\n", 300)
	sp := NewStreamParser(65536)
	b.SetBytes(int64(len(raw)))
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		if _, err := sp.ParseStream(strings.NewReader(raw)); err != nil {
			b.Fatal(err)
		}
	}
}
func TestParseStreamRecoversPrefixedHyphenatedScheme(t *testing.T) {
    raw := "Note:slipnet-enc://QUJDREVGR0g=\n"
    records, err := NewStreamParser(64).ParseStream(strings.NewReader(raw))
    if err != nil {
        t.Fatal(err)
    }
    if len(records) != 1 || records[0].RawURI != "slipnet-enc://QUJDREVGR0g=" {
        t.Fatalf("prefixed encrypted share was lost: %#v", records)
    }
}

func TestParseStreamLongSingleLineProfileWithSmallInitialBuffer(t *testing.T) {
    uri := "soar://" + strings.Repeat("A", 70000)
    records, err := NewStreamParser(64).ParseStream(strings.NewReader(uri + "\n"))
    if err != nil {
        t.Fatalf("valid bounded profile should not exceed scanner token size: %v", err)
    }
    if len(records) != 1 || records[0].RawURI != uri {
        t.Fatalf("long single-line profile was truncated or lost")
    }
}
