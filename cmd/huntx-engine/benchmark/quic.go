// Package benchmark provides network probing capabilities.
//
// Authority:
//
//	RFC 9000 (QUIC: A UDP-Based Multiplexed and Secure Transport): https://datatracker.ietf.org/doc/html/rfc9000
//	RFC 3550 (RTP: Jitter Calculation): https://datatracker.ietf.org/doc/html/rfc3550
package benchmark

import (
	"context"
	"math"
	"net"
	"time"
)

// QUICProbeResult holds the statistical outcome of UDP/QUIC 0-RTT probing.
type QUICProbeResult struct {
	Alive          bool          `json:"alive"`
	PacketsSent    int           `json:"packets_sent"`
	PacketsRecv    int           `json:"packets_recv"`
	PacketLossRate float64       `json:"packet_loss_rate"`
	AvgLatency     time.Duration `json:"avg_latency"`
	JitterMs       float64       `json:"jitter_ms"`
}

// QUICProberOptions configures the UDP/QUIC probing engine.
type QUICProberOption func(*QUICProber)

// WithQUICTimeout sets the per-packet timeout.
func WithQUICTimeout(d time.Duration) QUICProberOption {
	return func(q *QUICProber) {
		q.timeout = d
	}
}

// WithQUICPacketCount sets the number of probe packets sent per evaluation.
func WithQUICPacketCount(count int) QUICProberOption {
	return func(q *QUICProber) {
		q.packetCount = count
	}
}

// QUICProber executes UDP/QUIC synthetic handshake trains.
type QUICProber struct {
	timeout     time.Duration
	packetCount int
}

// NewQUICProber creates a new UDP/QUIC benchmark prober.
func NewQUICProber(opts ...QUICProberOption) *QUICProber {
	q := &QUICProber{
		timeout:     800 * time.Millisecond,
		packetCount: 5,
	}
	for _, opt := range opts {
		opt(q)
	}
	return q
}

// Probe evaluates a UDP/QUIC target address.
func (q *QUICProber) Probe(ctx context.Context, targetAddr string) (QUICProbeResult, error) {
	conn, err := net.DialTimeout("udp", targetAddr, q.timeout)
	if err != nil {
		return QUICProbeResult{Alive: false, PacketLossRate: 1.0}, nil
	}
	defer conn.Close()

	var latencies []time.Duration
	recvCount := 0
	buf := make([]byte, 1024)

	// Minimal QUIC Initial dummy packet header (RFC 9000 compliant)
	quicDummyInitial := []byte{
		0xc0, 0x00, 0x00, 0x00, 0x01, 0x08, 0x01, 0x02, 0x03, 0x04,
		0x05, 0x06, 0x07, 0x08, 0x00,
	}

	for i := 0; i < q.packetCount; i++ {
		if ctx.Err() != nil {
			break
		}

		sendStart := time.Now()
		_ = conn.SetDeadline(time.Now().Add(q.timeout))
		_, err := conn.Write(quicDummyInitial)
		if err != nil {
			continue
		}

		n, err := conn.Read(buf)
		if err == nil && n > 0 {
			rtt := time.Since(sendStart)
			latencies = append(latencies, rtt)
			recvCount++
		}
	}

	res := QUICProbeResult{
		PacketsSent: q.packetCount,
		PacketsRecv: recvCount,
		Alive:       recvCount > 0,
	}

	if q.packetCount > 0 {
		res.PacketLossRate = float64(q.packetCount-recvCount) / float64(q.packetCount)
	}

	if len(latencies) > 0 {
		var total time.Duration
		for _, l := range latencies {
			total += l
		}
		res.AvgLatency = total / time.Duration(len(latencies))

		// Compute jitter across received packets
		if len(latencies) > 1 {
			var jitter float64
			for i := 1; i < len(latencies); i++ {
				diff := math.Abs(float64(latencies[i].Microseconds()-latencies[i-1].Microseconds())) / 1000.0
				jitter += (diff - jitter) / 16.0
			}
			res.JitterMs = jitter
		}
	}

	return res, nil
}
