// Package score implements the proxy node health and ISP-specific quality scoring engine.
// Source: HUNTX Master Porting Compendium §8 (Mathematical Scoring Matrix)
package score

import (
	"math"
	"strings"
)

// SecurityProtocol represents the cryptographic transport layer of the proxy.
type SecurityProtocol string

const (
	SecurityReality   SecurityProtocol = "reality"
	SecurityTLS       SecurityProtocol = "tls"
	SecurityGRPC      SecurityProtocol = "grpc"
	SecurityH2        SecurityProtocol = "h2"
	SecurityWebSocket SecurityProtocol = "ws"
	SecurityNone      SecurityProtocol = "none"
)

// ScoreGrade classifies node quality into discrete tiers.
type ScoreGrade string

const (
	GradeAplus ScoreGrade = "A+"
	GradeA     ScoreGrade = "A"
	GradeB     ScoreGrade = "B"
	GradeC     ScoreGrade = "C"
	GradeD     ScoreGrade = "D"
	GradeF     ScoreGrade = "F"
)

// NodeMetrics contains raw latency, speed, and reliability metrics.
type NodeMetrics struct {
	LatencyMs    float64
	SpeedMbps    float64
	PacketLoss   float64
	SecurityType SecurityProtocol
	Carrier      string
}

// HealthResult contains the computed health score, tier grade, and recommendation status.
type HealthResult struct {
	Score       float64
	Grade       ScoreGrade
	Recommended bool
}

// CalculateHealthScore computes the quality score of a node based on the mathematical matrix:
// Score = 40.0 + max(0, 25 - latency/4) + Sum(Ws) + min(15, speed_mbps * 3) - Penalties
func CalculateHealthScore(node NodeMetrics, targetISP string) HealthResult {
	baseScore := 40.0

	// 1. Latency Component
	latencyScore := 0.0
	if node.LatencyMs > 0 {
		latencyScore = math.Max(0.0, 25.0-(node.LatencyMs/4.0))
	}

	// 2. Security Weight (Ws)
	securityWeight := 0.0
	switch node.SecurityType {
	case SecurityReality:
		securityWeight = 10.0
	case SecurityTLS, SecurityGRPC, SecurityH2:
		securityWeight = 8.0
	case SecurityWebSocket:
		securityWeight = 5.0
	default:
		securityWeight = 0.0
	}

	// 3. Speed Component
	speedScore := math.Min(15.0, node.SpeedMbps*3.0)

	// 4. Carrier Alignment Boost
	carrierBoost := 0.0
	if targetISP != "" && strings.EqualFold(node.Carrier, targetISP) {
		carrierBoost = 5.0
	}

	// 5. Penalties
	penalties := 0.0
	if node.PacketLoss > 5.0 {
		penalties += node.PacketLoss * 2.0
	}
	if node.LatencyMs > 500.0 {
		penalties += 10.0
	}

	total := baseScore + latencyScore + securityWeight + speedScore + carrierBoost - penalties

	// Clamp to [0.0, 100.0]
	if total < 0.0 {
		total = 0.0
	}
	if total > 100.0 {
		total = 100.0
	}

	// Grade classification
	var grade ScoreGrade
	switch {
	case total >= 90.0:
		grade = GradeAplus
	case total >= 80.0:
		grade = GradeA
	case total >= 70.0:
		grade = GradeB
	case total >= 55.0:
		grade = GradeC
	case total >= 40.0:
		grade = GradeD
	default:
		grade = GradeF
	}

	return HealthResult{
		Score:       total,
		Grade:       grade,
		Recommended: total >= 75.0,
	}
}
