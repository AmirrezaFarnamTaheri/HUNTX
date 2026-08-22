// Package benchmark provides high-throughput network probing.
package benchmark

import (
	"context"
	"net"
	"time"
)

// FastTCPResult holds the outcome of a TCP SYN handshake probe.
type FastTCPResult struct {
	Alive   bool          `json:"alive"`
	Latency time.Duration `json:"latency"`
}

// FastTCPProber executes optimized non-blocking TCP handshakes.
type FastTCPProber struct {
	timeout time.Duration
}

// NewFastTCPProber creates a TCP prober with optimized dialer settings.
func NewFastTCPProber(timeout time.Duration) *FastTCPProber {
	if timeout <= 0 {
		timeout = 1000 * time.Millisecond
	}
	return &FastTCPProber{timeout: timeout}
}

// ProbeTarget performs a fast TCP handshake against the target address.
func (p *FastTCPProber) ProbeTarget(ctx context.Context, target string) (FastTCPResult, error) {
	d := net.Dialer{
		Timeout:   p.timeout,
		KeepAlive: -1, // Disable keep-alive overhead
	}

	start := time.Now()
	conn, err := d.DialContext(ctx, "tcp", target)
	if err != nil {
		return FastTCPResult{Alive: false}, nil
	}
	latency := time.Since(start)
	_ = conn.Close()

	return FastTCPResult{
		Alive:   true,
		Latency: latency,
	}, nil
}
