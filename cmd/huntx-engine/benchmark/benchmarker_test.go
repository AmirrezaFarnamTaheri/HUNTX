package benchmark

import (
	"context"
	"net"
	"testing"
	"time"
)

func testServer(t *testing.T) (string, func()) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("Failed to listen: %v", err)
	}

	go func() {
		for {
			conn, err := l.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	return l.Addr().String(), func() { l.Close() }
}

func TestBenchmarkerCheckBatch(t *testing.T) {
	addr, cleanup := testServer(t)
	defer cleanup()

	targets := []string{addr, "127.0.0.1:59999"} // 1 alive, 1 dead
	bm := NewBenchmarker(500*time.Millisecond, 2)

	results := bm.CheckBatch(context.Background(), targets)
	if len(results) != 2 {
		t.Fatalf("Expected 2 results, got %d", len(results))
	}

	if !results[0].Alive {
		t.Errorf("Expected target %s to be alive", addr)
	}

	if results[1].Alive {
		t.Errorf("Expected target 127.0.0.1:59999 to be dead")
	}
}
