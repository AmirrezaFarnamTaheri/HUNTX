// Package telemetry_test validates operator-specific penalty matrix calculations and remark formatting.
// Source: HUNTX Master Porting Compendium §4 & §8
package telemetry_test

import (
	"strings"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/score"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/telemetry"
)

func TestEvaluateCarrierScore(t *testing.T) {
	matrix := telemetry.NewOperatorMatrix()

	node := stream.NormalizedNode{
		Protocol: "vless",
		Host:     "198.51.100.1",
		Port:     443,
		Security: "reality",
		Network:  "grpc",
	}

	rawMetrics := telemetry.TelemetryMetrics{
		LatencyMs:  45.0,
		PacketLoss: 0.00,
		JitterMs:   2.5,
		SpeedMbps:  25.0,
	}

	resMCI := matrix.Evaluate(node, rawMetrics, "MCI")
	if resMCI.Score < 85.0 {
		t.Errorf("expected high score for Reality+gRPC on MCI, got %f", resMCI.Score)
	}
	if resMCI.Grade != score.GradeAplus {
		t.Errorf("expected Grade A+, got %s", resMCI.Grade)
	}

	// Vulnerable node on MCI: Shadowsocks with plaintext/standard stream
	nodeSS := stream.NormalizedNode{
		Protocol: "shadowsocks",
		Host:     "198.51.100.2",
		Port:     8388,
		Security: "none",
		Network:  "tcp",
	}
	resSS := matrix.Evaluate(nodeSS, rawMetrics, "MCI")
	if resSS.Score >= resMCI.Score {
		t.Errorf("expected shadowsocks to have lower score than reality on MCI: ss=%f reality=%f", resSS.Score, resMCI.Score)
	}
}

func TestRewriteRemark(t *testing.T) {
	matrix := telemetry.NewOperatorMatrix()

	node := stream.NormalizedNode{
		Protocol: "vless",
		Host:     "198.51.100.1",
		Port:     443,
		Security: "reality",
		Network:  "grpc",
		Remark:   "Old Promo Remark",
	}

	evalResult := telemetry.EvaluationResult{
		Score:       96.5,
		Grade:       score.GradeAplus,
		Carrier:     "MCI",
		CountryCode: "DE",
		City:        "Frankfurt",
		LatencyMs:   38.0,
	}

	rewritten := matrix.RewriteRemark(node, evalResult)
	if !strings.HasPrefix(rewritten, "[MCI-⚡A+]") {
		t.Errorf("expected prefix [MCI-⚡A+], got %s", rewritten)
	}

	if rewritten != "[MCI-⚡A+] 🇩🇪 Frankfurt VLESS-Reality (38ms)" {
		t.Errorf("unexpected rewritten remark: %s", rewritten)
	}
}

func TestCountryCodeToFlagEmoji(t *testing.T) {
	tests := []struct {
		code     string
		expected string
	}{
		{"DE", "🇩🇪"},
		{"US", "🇺🇸"},
		{"GB", "🇬🇧"},
		{"FR", "🇫🇷"},
		{"NL", "🇳🇱"},
		{"XX", "🌐"},
		{"LAN", "🏠"},
	}

	for _, tt := range tests {
		got := telemetry.CountryCodeToFlagEmoji(tt.code)
		if got != tt.expected {
			t.Errorf("CountryCodeToFlagEmoji(%q) = %q, want %q", tt.code, got, tt.expected)
		}
	}
}

func TestRewriteRemark_EmptySecurityAndUnknownCountry(t *testing.T) {
	matrix := telemetry.NewOperatorMatrix()

	node := stream.NormalizedNode{
		Protocol: "trojan",
		Host:     "198.51.100.3",
		Port:     443,
		Security: "",
	}

	evalResult := telemetry.EvaluationResult{
		Score:       72.0,
		Grade:       score.GradeB,
		Carrier:     "GENERIC",
		CountryCode: "123",
		City:        "",
		LatencyMs:   120.0,
	}

	rewritten := matrix.RewriteRemark(node, evalResult)
	expected := "[GENERIC-B] 🌐 Global TROJAN-Direct (120ms)"
	if rewritten != expected {
		t.Errorf("expected %q, got %q", expected, rewritten)
	}
}
