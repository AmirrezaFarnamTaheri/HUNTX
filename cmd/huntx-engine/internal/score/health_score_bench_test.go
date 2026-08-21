// Package score_test benchmarks carrier-aware proxy scoring and telemetry matrix.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package score_test

import (
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/score"
)

func BenchmarkCalculateHealthScore(b *testing.B) {
	node := score.NodeMetrics{
		LatencyMs:    45.0,
		SpeedMbps:    12.5,
		PacketLoss:   0.01,
		SecurityType: score.SecurityReality,
		Carrier:      "MCI",
	}

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_ = score.CalculateHealthScore(node, "MCI")
	}
}
