// Package telemetry implements operator-specific quality scoring, carrier penalty matrices, and dynamic remark rewriting.
// Source: HUNTX Master Porting Compendium §4 & §8
package telemetry

import (
	"fmt"
	"math"
	"strings"
	"sync"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/score"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
)

// TelemetryMetrics holds raw probe measurements for latency, jitter, loss, and throughput.
type TelemetryMetrics struct {
	LatencyMs  float64 `json:"latency_ms"`
	PacketLoss float64 `json:"packet_loss"` // 0.00 to 1.00
	JitterMs   float64 `json:"jitter_ms"`
	SpeedMbps  float64 `json:"speed_mbps"`
}

// EvaluationResult contains the evaluated carrier health metrics and assigned tier grade.
type EvaluationResult struct {
	Score       float64          `json:"score"`
	Grade       score.ScoreGrade `json:"grade"`
	Carrier     string           `json:"carrier"`
	CountryCode string           `json:"country_code"`
	City        string           `json:"city"`
	LatencyMs   float64          `json:"latency_ms"`
}

// OperatorMatrix computes carrier-specific performance scores with tailored vulnerability weights.
type OperatorMatrix struct {
	mu           sync.RWMutex
	carrierRules map[string]CarrierRule
}

// CarrierRule defines carrier-specific protocol preferences and penalty multipliers.
type CarrierRule struct {
	RealityBonus    float64
	GRPCBonus       float64
	WebSocketBonus  float64
	ShadowsocksLoss float64
	LossMultiplier  float64
	JitterPenalty   float64
}

// NewOperatorMatrix initializes the operator matrix with optimized rules for major carriers.
func NewOperatorMatrix() *OperatorMatrix {
	m := &OperatorMatrix{
		carrierRules: make(map[string]CarrierRule),
	}

	// Iranian Major Telecoms
	m.carrierRules["MCI"] = CarrierRule{
		RealityBonus:    15.0,
		GRPCBonus:       10.0,
		WebSocketBonus:  2.0,
		ShadowsocksLoss: 25.0,
		LossMultiplier:  40.0,
		JitterPenalty:   0.25,
	}

	m.carrierRules["MTN"] = CarrierRule{
		RealityBonus:    12.0,
		GRPCBonus:       12.0,
		WebSocketBonus:  5.0,
		ShadowsocksLoss: 20.0,
		LossMultiplier:  35.0,
		JitterPenalty:   0.20,
	}

	m.carrierRules["RTL"] = CarrierRule{
		RealityBonus:    10.0,
		GRPCBonus:       8.0,
		WebSocketBonus:  6.0,
		ShadowsocksLoss: 15.0,
		LossMultiplier:  30.0,
		JitterPenalty:   0.20,
	}

	m.carrierRules["SHATEL"] = CarrierRule{
		RealityBonus:    8.0,
		GRPCBonus:       6.0,
		WebSocketBonus:  8.0,
		ShadowsocksLoss: 10.0,
		LossMultiplier:  25.0,
		JitterPenalty:   0.15,
	}

	return m
}

// Evaluate computes a nuanced composite score for a node against the specified target carrier.
func (m *OperatorMatrix) Evaluate(node stream.NormalizedNode, metrics TelemetryMetrics, carrier string) EvaluationResult {
	m.mu.RLock()
	rule, exists := m.carrierRules[strings.ToUpper(carrier)]
	m.mu.RUnlock()

	if !exists {
		// Default rule for generic networks
		rule = CarrierRule{
			RealityBonus:    8.0,
			GRPCBonus:       6.0,
			WebSocketBonus:  5.0,
			ShadowsocksLoss: 10.0,
			LossMultiplier:  25.0,
			JitterPenalty:   0.15,
		}
	}

	baseScore := 40.0

	// 1. Latency Component (Max 25 pts)
	latencyScore := 0.0
	if metrics.LatencyMs > 0 {
		latencyScore = math.Max(0.0, 25.0-(metrics.LatencyMs/4.0))
	}

	// 2. Speed Component (Max 15 pts)
	speedScore := math.Min(15.0, metrics.SpeedMbps*1.5)

	// 3. Security Protocol Bonuses
	secBonus := 0.0
	switch strings.ToLower(node.Security) {
	case "reality":
		secBonus += rule.RealityBonus
	case "tls":
		secBonus += 8.0
	}

	// 4. Transport Network Bonuses
	netBonus := 0.0
	switch strings.ToLower(node.Network) {
	case "grpc":
		netBonus += rule.GRPCBonus
	case "ws", "websocket":
		netBonus += rule.WebSocketBonus
	case "h2", "httpupgrade":
		netBonus += 4.0
	}

	// 5. Protocol Penalties
	protoPenalty := 0.0
	if strings.ToLower(node.Protocol) == "shadowsocks" && strings.ToLower(node.Security) == "none" {
		protoPenalty += rule.ShadowsocksLoss
	}

	// 6. Packet Loss and Jitter Penalties
	lossPenalty := metrics.PacketLoss * rule.LossMultiplier
	jitterPenalty := metrics.JitterMs * rule.JitterPenalty

	finalScore := baseScore + latencyScore + speedScore + secBonus + netBonus - protoPenalty - lossPenalty - jitterPenalty
	finalScore = math.Max(0.0, math.Min(100.0, finalScore))

	grade := score.GradeF
	switch {
	case finalScore >= 90.0:
		grade = score.GradeAplus
	case finalScore >= 80.0:
		grade = score.GradeA
	case finalScore >= 70.0:
		grade = score.GradeB
	case finalScore >= 55.0:
		grade = score.GradeC
	case finalScore >= 40.0:
		grade = score.GradeD
	default:
		grade = score.GradeF
	}

	return EvaluationResult{
		Score:     finalScore,
		Grade:     grade,
		Carrier:   strings.ToUpper(carrier),
		LatencyMs: metrics.LatencyMs,
	}
}

// RewriteRemark generates a standardized, carrier-aware node tag for subscriptions.
// Format: [CARRIER-⚡GRADE] FLAG CITY PROTOCOL-SECURITY (LATENCYms)
func (m *OperatorMatrix) RewriteRemark(node stream.NormalizedNode, res EvaluationResult) string {
	flag := CountryCodeToFlagEmoji(res.CountryCode)
	city := res.City
	if city == "" {
		city = "Global"
	}

	proto := strings.ToUpper(node.Protocol)
	sec := "Direct"
	if len(node.Security) > 0 {
		sec = strings.ToUpper(node.Security[:1]) + strings.ToLower(node.Security[1:])
		if sec == "None" {
			sec = "Direct"
		}
	}

	bolt := ""
	if res.Grade == score.GradeAplus || res.Grade == score.GradeA {
		bolt = "⚡"
	}

	return fmt.Sprintf("[%s-%s%s] %s %s %s-%s (%dms)",
		res.Carrier,
		bolt,
		res.Grade,
		flag,
		city,
		proto,
		sec,
		int(math.Round(res.LatencyMs)),
	)
}

// CountryCodeToFlagEmoji converts a 2-letter ISO country code into Unicode regional indicator flags.
func CountryCodeToFlagEmoji(countryCode string) string {
	code := strings.ToUpper(strings.TrimSpace(countryCode))
	if code == "LAN" {
		return "🏠"
	}
	if len(code) != 2 || code == "XX" || code[0] < 'A' || code[0] > 'Z' || code[1] < 'A' || code[1] > 'Z' {
		return "🌐"
	}

	r1 := rune(code[0]) - 'A' + 0x1F1E6
	r2 := rune(code[1]) - 'A' + 0x1F1E6
	return string([]rune{r1, r2})
}
