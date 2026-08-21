package benchmark

import (
	"context"
	"net"
	"testing"
	"time"
)

func TestQUICProberLoopback(t *testing.T) {
	// Start mock UDP server
	pc, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen UDP: %v", err)
	}
	defer pc.Close()

	go func() {
		buf := make([]byte, 1500)
		for {
			n, addr, err := pc.ReadFrom(buf)
			if err != nil {
				return
			}
			// Echo back
			_, _ = pc.WriteTo(buf[:n], addr)
		}
	}()

	prober := NewQUICProber(WithQUICTimeout(500 * time.Millisecond), WithQUICPacketCount(5))
	res, err := prober.Probe(context.Background(), pc.LocalAddr().String())
	if err != nil {
		t.Fatalf("unexpected probe error: %v", err)
	}

	if !res.Alive {
		t.Errorf("expected alive = true")
	}
	if res.PacketsSent != 5 {
		t.Errorf("expected 5 packets sent, got %d", res.PacketsSent)
	}
	if res.PacketLossRate > 0.1 {
		t.Errorf("expected near zero loss rate, got %.2f", res.PacketLossRate)
	}
	if res.AvgLatency < 0 {
		t.Errorf("expected non-negative latency, got %v", res.AvgLatency)
	}
}

func TestQUICProberTimeout(t *testing.T) {
	// Probe non-responsive port
	prober := NewQUICProber(WithQUICTimeout(50 * time.Millisecond), WithQUICPacketCount(2))
	res, err := prober.Probe(context.Background(), "127.0.0.1:65530")
	if err != nil {
		t.Fatalf("unexpected error on timeout probe: %v", err)
	}
	if res.Alive {
		t.Errorf("expected alive = false for dead endpoint")
	}
	if res.PacketLossRate != 1.0 {
		t.Errorf("expected 100%% packet loss, got %.2f", res.PacketLossRate)
	}
}
