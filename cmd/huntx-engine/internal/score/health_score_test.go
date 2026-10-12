// Package score implements the proxy node health and ISP-specific quality scoring engine.
// Source: HUNTX Master Porting Compendium §8 (Mathematical Scoring Matrix)
package score_test

import (
	"math"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/score"
)

func TestCalculateHealthScore_RealityHighSpeed(t *testing.T) {
	node := score.NodeMetrics{
		LatencyMs:    40.0,
		SpeedMbps:    5.0,
		PacketLoss:   0.0,
		SecurityType: score.SecurityReality,
		Carrier:      "MCI",
	}

	result := score.CalculateHealthScore(node, "MCI")

	// Base (40) + Latency (25 - 10 = 15) + Security (10) + Speed (min(15, 15) = 15) + Carrier (5) = 85.0
	expected := 85.0
	if result.Score != expected {
		t.Errorf("expected score %.1f, got %.1f", expected, result.Score)
	}

	if result.Grade != score.GradeA {
		t.Errorf("expected Grade A, got %s", result.Grade)
	}
}

func TestCalculateHealthScore_HighLossPenalty(t *testing.T) {
	node := score.NodeMetrics{
		LatencyMs:    600.0,
		SpeedMbps:    0.5,
		PacketLoss:   15.0, // 15% loss -> -30 penalty, plus -10 for latency > 500ms
		SecurityType: score.SecurityNone,
		Carrier:      "Unknown",
	}

	result := score.CalculateHealthScore(node, "MTN")

	// Base (40) + Latency (0) + Security (0) + Speed (1.5) - LatencyPenalty(10) - LossPenalty(30) = 1.5
	if result.Score > 10.0 {
		t.Errorf("expected heavily penalized score < 10.0, got %.1f", result.Score)
	}

	if result.Grade != score.GradeF {
		t.Errorf("expected Grade F, got %s", result.Grade)
	}
}

func TestCalculateHealthScore_Clamping(t *testing.T) {
	worstNode := score.NodeMetrics{
		LatencyMs:  2000.0,
		PacketLoss: 100.0,
	}
	resWorst := score.CalculateHealthScore(worstNode, "Any")
	if resWorst.Score < 0.0 || resWorst.Score > 0.0 {
		t.Errorf("expected clamped 0.0 for worst node, got %.1f", resWorst.Score)
	}

	bestNode := score.NodeMetrics{
		LatencyMs:    10.0,
		SpeedMbps:    100.0,
		PacketLoss:   0.0,
		SecurityType: score.SecurityReality,
		Carrier:      "Irancell",
	}
	resBest := score.CalculateHealthScore(bestNode, "Irancell")
	if resBest.Score > 100.0 {
		t.Errorf("expected clamped <= 100.0 for best node, got %.1f", resBest.Score)
	}
}

func TestHealthScoreEvidenceIsNotAnUnverifiedQualityClaim(t *testing.T) {
	node := score.NodeMetrics{LatencyMs: 30, SpeedMbps: 12, SecurityType: score.SecurityReality}
	baseline := score.CalculateHealthScore(node, "MCI")
	if baseline.Recommended || baseline.VerifiedGrade != "" || baseline.Evidence != "unverified" {
		t.Fatalf("unverified advertised proxy was graded as connected: %+v", baseline)
	}
	node.ProbeKind, node.ProbeOK = "tcp_connect", true
	tcp := score.CalculateHealthScore(node, "MCI")
	if tcp.Recommended || tcp.Evidence != "tcp_connect_only" {
		t.Fatalf("TCP-only probe incorrectly certified proxy: %+v", tcp)
	}
	node.ProbeOK = false
	tcpFailed := score.CalculateHealthScore(node, "MCI")
	if tcpFailed.Score != 0 || tcpFailed.Recommended ||
		tcpFailed.VerifiedGrade != "" || tcpFailed.Evidence != "tcp_connect_failed" {
		t.Fatalf("TCP refusal misclassified as authenticated failure: %+v", tcpFailed)
	}
	node.ProbeOK = true
	node.ProbeKind, node.ProbeAgeSecs = "protocol_authenticated", 60
	valid := score.CalculateHealthScore(node, "MCI")
	if !valid.Recommended || valid.VerifiedGrade != valid.Grade {
		t.Fatalf("fresh protocol probe was not credited: %+v", valid)
	}
	node.ProbeAgeSecs = 3601
	stale := score.CalculateHealthScore(node, "MCI")
	if stale.Recommended || stale.VerifiedGrade != "" || stale.Evidence != "stale_authenticated_probe" {
		t.Fatalf("expired protocol evidence was trusted: %+v", stale)
	}
	node.ProbeOK = false
	failed := score.CalculateHealthScore(node, "MCI")
	if failed.Score != 0 || failed.Recommended || failed.VerifiedGrade != score.GradeF {
		t.Fatalf("failed authenticated probe was recommended: %+v", failed)
	}
}

func TestHealthScoreRejectsNonFiniteAndNegativeTelemetry(t *testing.T) {
	node := score.NodeMetrics{LatencyMs: math.NaN(), SpeedMbps: math.Inf(1), PacketLoss: -20,
		SecurityType: score.SecurityTLS}
	result := score.CalculateHealthScore(node, "")
	if math.IsNaN(result.Score) || math.IsInf(result.Score, 0) ||
		result.Score < 0 || result.Score > 100 || result.Recommended {
		t.Fatalf("invalid telemetry bypassed bounded scoring: %+v", result)
	}
}

func TestHealthScoreCarrierMatchAndSecurityCaseMatchPython(t *testing.T) {
	node := score.NodeMetrics{
		LatencyMs: 40, SpeedMbps: 5, PacketLoss: 0,
		SecurityType: score.SecurityProtocol("REALITY"), Carrier: "  mci  ",
		ProbeKind: "protocol_authenticated", ProbeOK: true, ProbeAgeSecs: 60,
	}
	result := score.CalculateHealthScore(node, "MCI")
	if result.Score != 85 || result.Grade != score.GradeA || !result.Recommended {
		t.Fatalf("case/whitespace normalization differs from Python scoring: %+v", result)
	}
	node.Carrier = "  "
	result = score.CalculateHealthScore(node, " ")
	if result.Score != 80 {
		t.Fatalf("blank carrier/ISP gained a fake bonus: %+v", result)
	}
}
