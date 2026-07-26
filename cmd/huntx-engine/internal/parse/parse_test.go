package parse_test

import (
	"strings"
	"testing"

	"huntx-engine/internal/parse"
)

func TestParseReader_ValidVlessLine(t *testing.T) {
	input := "vless://some-uuid@192.0.2.1:443?security=tls&sni=example.com\n"
	records, err := parse.ParseReader(strings.NewReader(input))
	if err != nil {
		t.Fatalf("ParseReader returned unexpected error: %v", err)
	}
	if len(records) == 0 {
		t.Fatal("expected >= 1 record for valid vless line, got 0")
	}
}

func TestParseReader_EmptyInput(t *testing.T) {
	records, err := parse.ParseReader(strings.NewReader(""))
	if err != nil {
		t.Fatalf("ParseReader should not error on empty input, got: %v", err)
	}
	if records == nil {
		t.Fatal("expected non-nil (empty) slice, got nil")
	}
}

func BenchmarkParseReader_1000Lines(b *testing.B) {
	line := "vless://abc@192.0.2.1:443?security=tls&sni=example.com\n"
	input := strings.Repeat(line, 1000)
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		if _, err := parse.ParseReader(strings.NewReader(input)); err != nil {
			b.Fatalf("ParseReader failed during benchmark: %v", err)
		}
	}
}
