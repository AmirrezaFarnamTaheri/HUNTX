package chain

import "time"

// Option configures the multi-hop chain synthesis engine.
type Option func(*Engine)

// WithStrategy sets the synthesis strategy heuristic.
func WithStrategy(strategy ChainStrategy) Option {
	return func(e *Engine) {
		if strategy > StrategyUnknown && strategy <= StrategyMultiRegionMesh {
			e.Strategy = strategy
		}
	}
}

// WithMaxLatencyCeiling filters out chains whose composite RTT exceeds maxLatency.
func WithMaxLatencyCeiling(maxLatency time.Duration) Option {
	return func(e *Engine) {
		if maxLatency > 0 {
			e.MaxLatency = maxLatency
		}
	}
}

// WithDomesticCountry sets the home/domestic country ISO code for relay selection.
func WithDomesticCountry(countryCode string) Option {
	return func(e *Engine) {
		if countryCode != "" {
			e.DomesticCountry = countryCode
		}
	}
}

// WithMaxChains sets the upper limit on the number of synthesized chains to output.
func WithMaxChains(maxChains int) Option {
	return func(e *Engine) {
		if maxChains > 0 {
			e.MaxChains = maxChains
		}
	}
}
