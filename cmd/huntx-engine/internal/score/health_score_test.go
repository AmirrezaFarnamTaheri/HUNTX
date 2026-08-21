// Package score implements the proxy node health and ISP-specific quality scoring engine.
// Source: HUNTX Master Porting Compendium §8 (Mathematical Scoring Matrix)
package score_test

import (
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
