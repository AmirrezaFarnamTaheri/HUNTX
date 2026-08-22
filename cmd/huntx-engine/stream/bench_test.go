package stream

import (
	"bytes"
	"testing"
)

func BenchmarkStreamParserThroughput(b *testing.B) {
	samplePayload := bytes.Repeat([]byte("vless://11111111-2222-3333-4444-555555555555@server.example.com:443?type=ws&security=tls#US-Node\n"), 1000)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		reader := bytes.NewReader(samplePayload)
		parser := NewStreamParser(65536)
		records, err := parser.ParseStream(reader)
		if err != nil {
			b.Fatalf("benchmark failed: %v", err)
		}
		if len(records) == 0 {
			b.Fatalf("expected records, got 0")
		}
	}
}
