// Package chain provides dynamic multi-hop proxy mesh synthesis, combining low-latency entry
// relays with clean-IP international exit nodes with automatic cycle detection and latency scoring.
package chain

import (
	"context"
	"time"
)

// ChainStrategy specifies the algorithmic heuristic used for assembling multi-hop chains.
type ChainStrategy int

const (
	// StrategyUnknown represents an uninitialized or invalid strategy.
	StrategyUnknown ChainStrategy = iota
	// StrategyLowestLatency pairs entry and exit nodes minimizing total composite latency.
	StrategyLowestLatency
	// StrategyDomesticRelayInternationalExit pairs a domestic entry relay with an international exit.
	StrategyDomesticRelayInternationalExit
	// StrategyMultiRegionMesh forms diverse geographic chains across distinct regional zones.
	StrategyMultiRegionMesh
)

// String returns the canonical human-readable name of the strategy.
func (s ChainStrategy) String() string {
	switch s {
	case StrategyLowestLatency:
		return "lowest_latency"
	case StrategyDomesticRelayInternationalExit:
		return "domestic_relay_international_exit"
	case StrategyMultiRegionMesh:
		return "multi_region_mesh"
	default:
		return "unknown"
	}
}

// HopRole indicates whether a node acts as an entry relay or egress exit.
type HopRole int

const (
	// HopRoleUnknown represents an unassigned hop role.
	HopRoleUnknown HopRole = iota
	// HopRoleRelay indicates the node acts as a bridge/ingress forwarder.
	HopRoleRelay
	// HopRoleExit indicates the node acts as the egress gateway to the internet.
	HopRoleExit
)

// Node encapsulates proxy endpoint metadata necessary for chain evaluation.
type Node struct {
	UniqueHash  string        `json:"unique_hash"`
	RawURI      string        `json:"raw_uri"`
	Protocol    string        `json:"protocol"`
	Address     string        `json:"address"`
	Port        int           `json:"port"`
	CountryCode string        `json:"country_code"`
	Latency     time.Duration `json:"latency"`
	Alive       bool          `json:"alive"`
}

// SynthesizedChain represents a verified multi-hop route.
type SynthesizedChain struct {
	ID             string        `json:"id"`
	Strategy       ChainStrategy `json:"strategy"`
	StrategyName   string        `json:"strategy_name"`
	Entry          Node          `json:"entry"`
	Exit           Node          `json:"exit"`
	EstimatedRTT   time.Duration `json:"estimated_rtt"`
	CompositeScore float64       `json:"composite_score"`
	GeneratedAt    time.Time     `json:"generated_at"`
}

// Synthesizer defines the interface for generating multi-hop proxy chains from a node pool.
type Synthesizer interface {
	Synthesize(ctx context.Context, pool []Node) ([]SynthesizedChain, error)
}
