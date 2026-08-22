// Package dns_test benchmarks concurrent hybrid DNS resolution.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package dns_test

import (
	"context"
	"testing"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/dns"
)

func BenchmarkHyperResolve_DirectIP(b *testing.B) {
	resolver := dns.NewHyperResolver(nil)
	ctx := context.Background()

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_, _ = resolver.Resolve(ctx, "1.1.1.1")
	}
}

func BenchmarkHyperResolve_CacheHit(b *testing.B) {
	resolver := dns.NewHyperResolver(nil)
	resolver.SetCache("benchmark.huntx.internal", "10.0.0.1", 10*time.Minute)
	ctx := context.Background()

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_, _ = resolver.Resolve(ctx, "benchmark.huntx.internal")
	}
}
