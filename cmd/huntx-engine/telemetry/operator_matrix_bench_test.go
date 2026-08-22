// Package telemetry_test benchmarks carrier evaluation and dynamic remark rewriting.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package telemetry_test

import (
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/score"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/telemetry"
)

func BenchmarkOperatorMatrix_Evaluate(b *testing.B) {
	matrix := telemetry.NewOperatorMatrix()
	node := stream.NormalizedNode{
		Protocol: "vless",
		Host:     "198.51.100.1",
		Port:     443,
		Security: "reality",
		Network:  "grpc",
	}

	metrics := telemetry.TelemetryMetrics{
		LatencyMs:  42.0,
		PacketLoss: 0.00,
		JitterMs:   3.1,
		SpeedMbps:  30.0,
	}

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_ = matrix.Evaluate(node, metrics, "MCI")
	}
}

func BenchmarkOperatorMatrix_RewriteRemark(b *testing.B) {
	matrix := telemetry.NewOperatorMatrix()
	node := stream.NormalizedNode{
		Protocol: "vless",
		Host:     "198.51.100.1",
		Port:     443,
		Security: "reality",
		Network:  "grpc",
	}

	evalResult := telemetry.EvaluationResult{
		Score:       95.0,
		Grade:       score.GradeAplus,
		Carrier:     "MCI",
		CountryCode: "DE",
		City:        "Frankfurt",
		LatencyMs:   42.0,
	}

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_ = matrix.RewriteRemark(node, evalResult)
	}
}

func BenchmarkCountryCodeToFlagEmoji(b *testing.B) {
	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_ = telemetry.CountryCodeToFlagEmoji("DE")
	}
}
