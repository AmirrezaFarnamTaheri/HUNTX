package chain

import (
	"context"
	"testing"
	"time"
)

func BenchmarkSynthesizerScoring(b *testing.B) {
	engine := New(WithStrategy(StrategyLowestLatency))
	pool := []Node{
		{UniqueHash: "h1", Protocol: "vless", CountryCode: "DE", Latency: 40 * time.Millisecond, Alive: true, Address: "1.1.1.1", Port: 443},
		{UniqueHash: "h2", Protocol: "hysteria2", CountryCode: "US", Latency: 75 * time.Millisecond, Alive: true, Address: "8.8.8.8", Port: 8443},
		{UniqueHash: "h3", Protocol: "trojan", CountryCode: "SG", Latency: 120 * time.Millisecond, Alive: true, Address: "9.9.9.9", Port: 443},
	}

	ctx := context.Background()
	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		_, _ = engine.Synthesize(ctx, pool)
	}
}
