package benchmark

import "time"

// Option configures a Benchmarker instance using functional options.
type Option func(*Benchmarker)

// WithTimeout sets the dial timeout for network latency checks.
// If d is zero or negative, the default timeout (3s) is preserved.
func WithTimeout(d time.Duration) Option {
	return func(b *Benchmarker) {
		if d > 0 {
			b.Timeout = d
		}
	}
}

// WithConcurrency sets the maximum number of concurrent dialer workers.
// If n is less than or equal to zero, the default concurrency (100) is preserved.
func WithConcurrency(n int) Option {
	return func(b *Benchmarker) {
		if n > 0 {
			b.Concurrency = n
		}
	}
}
