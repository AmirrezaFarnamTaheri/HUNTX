package chain

import (
	"fmt"
	"time"
)

// CalculateCompositeScore generates a composite fitness score (0.0 to 100.0)
// considering overall latency, protocol resilience, and geographic diversity.
func CalculateCompositeScore(entry Node, exit Node, rtt time.Duration) float64 {
	// Base score from latency (lower RTT yields higher score, up to 70 pts)
	latencyScore := 70.0 - (float64(rtt.Milliseconds()) * 0.1)
	if latencyScore < 0 {
		latencyScore = 0
	}

	// Protocol bonus (15 pts): VLESS / Hysteria2 / TUIC get bonus resilience
	protoBonus := 10.0
	if entry.Protocol == "vless" || entry.Protocol == "hysteria2" {
		protoBonus += 5.0
	}

	// Geographic diversity bonus (15 pts): Crossing regions prevents local routing throttling
	geoBonus := 5.0
	if entry.CountryCode != exit.CountryCode && entry.CountryCode != "XX" && exit.CountryCode != "XX" {
		geoBonus = 15.0
	}

	total := latencyScore + protoBonus + geoBonus
	if total > 100.0 {
		total = 100.0
	}
	return total
}

// GenerateChainID creates a deterministic hash-based identifier for the route.
func GenerateChainID(entryHash, exitHash string) string {
	return fmt.Sprintf("chain-%s-%s", entryHash, exitHash)
}
