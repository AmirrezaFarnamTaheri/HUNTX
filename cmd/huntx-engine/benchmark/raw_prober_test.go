package benchmark

import (
	"context"
	"net"
	"testing"
	"time"
)

func TestFastTCPProber(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	defer ln.Close()

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	prober := NewFastTCPProber(200 * time.Millisecond)
	res, err := prober.ProbeTarget(context.Background(), ln.Addr().String())
	if err != nil {
		t.Fatalf("unexpected probe error: %v", err)
	}
	if !res.Alive {
		t.Errorf("expected target to be alive")
	}
	if res.Latency <= 0 {
		t.Errorf("expected positive latency")
	}
}
