// Package geoip_test benchmarks GeoIP resolution and autonomous system routing.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package geoip_test

import (
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/geoip"
)

func BenchmarkGeoIPProvider_LookupIP(b *testing.B) {
	provider := geoip.NewGeoIPProvider(nil)

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_, _ = provider.LookupIP("1.1.1.1")
	}
}

func BenchmarkGeoIPProvider_LookupTLD(b *testing.B) {
	provider := geoip.NewGeoIPProvider(nil)

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_ = provider.InferCountryFromDomain("proxy.nodes.de")
	}
}
