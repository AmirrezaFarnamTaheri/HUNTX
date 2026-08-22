package chain

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"
)

// Engine implements the Synthesizer interface.
type Engine struct {
	Strategy        ChainStrategy
	MaxLatency      time.Duration
	DomesticCountry string
	MaxChains       int
}

var _ Synthesizer = (*Engine)(nil)

// New creates a new multi-hop chain synthesis engine with functional options.
func New(opts ...Option) *Engine {
	e := &Engine{
		Strategy:        StrategyLowestLatency,
		MaxLatency:      1500 * time.Millisecond,
		DomesticCountry: "IR",
		MaxChains:       20,
	}
	for _, opt := range opts {
		opt(e)
	}
	return e
}

// Synthesize evaluates a pool of candidate nodes and generates a sorted slice of multi-hop chains.
func (e *Engine) Synthesize(ctx context.Context, pool []Node) ([]SynthesizedChain, error) {
	if err := ctx.Err(); err != nil {
		return nil, fmt.Errorf("context cancelled before synthesis: %w", err)
	}

	// 1. Filter out dead nodes and unroutable endpoints
	var validNodes []Node
	for _, n := range pool {
		if n.Alive && n.Address != "" && n.Port > 0 {
			validNodes = append(validNodes, n)
		}
	}

	if len(validNodes) < 2 {
		return []SynthesizedChain{}, nil
	}

	var candidates []SynthesizedChain

	// 2. Generate candidate pairs based on the active strategy
	switch e.Strategy {
	case StrategyDomesticRelayInternationalExit:
		candidates = e.synthesizeDomesticInternational(validNodes)
	case StrategyMultiRegionMesh:
		candidates = e.synthesizeMultiRegion(validNodes)
	case StrategyLowestLatency:
		fallthrough
	default:
		candidates = e.synthesizeLowestLatency(validNodes)
	}

	// 3. Filter by maximum latency ceiling
	var filtered []SynthesizedChain
	for _, c := range candidates {
		if c.EstimatedRTT <= e.MaxLatency {
			filtered = append(filtered, c)
		}
	}

	// 4. Sort by composite score descending (highest quality first), then latency ascending
	sort.Slice(filtered, func(i, j int) bool {
		if filtered[i].CompositeScore == filtered[j].CompositeScore {
			return filtered[i].EstimatedRTT < filtered[j].EstimatedRTT
		}
		return filtered[i].CompositeScore > filtered[j].CompositeScore
	})

	// 5. Cap output to MaxChains
	if len(filtered) > e.MaxChains {
		filtered = filtered[:e.MaxChains]
	}

	return filtered, nil
}

func (e *Engine) synthesizeDomesticInternational(nodes []Node) []SynthesizedChain {
	domesticCode := strings.ToUpper(strings.TrimSpace(e.DomesticCountry))
	var entries []Node
	var exits []Node

	for _, n := range nodes {
		if strings.ToUpper(n.CountryCode) == domesticCode {
			entries = append(entries, n)
		} else {
			exits = append(exits, n)
		}
	}

	var result []SynthesizedChain
	for _, entry := range entries {
		for _, exit := range exits {
			if entry.UniqueHash == exit.UniqueHash || entry.Address == exit.Address {
				continue // loop prevention
			}
			rtt := entry.Latency + exit.Latency
			score := CalculateCompositeScore(entry, exit, rtt)
			result = append(result, SynthesizedChain{
				ID:             GenerateChainID(entry.UniqueHash, exit.UniqueHash),
				Strategy:       e.Strategy,
				StrategyName:   e.Strategy.String(),
				Entry:          entry,
				Exit:           exit,
				EstimatedRTT:   rtt,
				CompositeScore: score,
				GeneratedAt:    time.Now().UTC(),
			})
		}
	}
	return result
}

func (e *Engine) synthesizeLowestLatency(nodes []Node) []SynthesizedChain {
	var result []SynthesizedChain
	for i := 0; i < len(nodes); i++ {
		for j := 0; j < len(nodes); j++ {
			if i == j {
				continue
			}
			entry := nodes[i]
			exit := nodes[j]
			if entry.UniqueHash == exit.UniqueHash || entry.Address == exit.Address {
				continue // loop prevention
			}

			rtt := entry.Latency + exit.Latency
			score := CalculateCompositeScore(entry, exit, rtt)
			result = append(result, SynthesizedChain{
				ID:             GenerateChainID(entry.UniqueHash, exit.UniqueHash),
				Strategy:       e.Strategy,
				StrategyName:   e.Strategy.String(),
				Entry:          entry,
				Exit:           exit,
				EstimatedRTT:   rtt,
				CompositeScore: score,
				GeneratedAt:    time.Now().UTC(),
			})
		}
	}
	return result
}

func (e *Engine) synthesizeMultiRegion(nodes []Node) []SynthesizedChain {
	var result []SynthesizedChain
	for i := 0; i < len(nodes); i++ {
		for j := 0; j < len(nodes); j++ {
			if i == j {
				continue
			}
			entry := nodes[i]
			exit := nodes[j]
			if entry.CountryCode == exit.CountryCode || entry.Address == exit.Address {
				continue
			}

			rtt := entry.Latency + exit.Latency
			score := CalculateCompositeScore(entry, exit, rtt)
			result = append(result, SynthesizedChain{
				ID:             GenerateChainID(entry.UniqueHash, exit.UniqueHash),
				Strategy:       e.Strategy,
				StrategyName:   e.Strategy.String(),
				Entry:          entry,
				Exit:           exit,
				EstimatedRTT:   rtt,
				CompositeScore: score,
				GeneratedAt:    time.Now().UTC(),
			})
		}
	}
	return result
}
