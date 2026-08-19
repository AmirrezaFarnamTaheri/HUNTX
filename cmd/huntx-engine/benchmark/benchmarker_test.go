package benchmark

import (
	"context"
	"net"
	"testing"
	"time"
)

func TestBenchmarkerRejectsPrivateTargets(t *testing.T) {
	bm := NewBenchmarker(100*time.Millisecond, 2)
	targets := []string{
		"127.0.0.1:80",
		"10.0.0.1:443",
		"192.168.1.1:22",
		"[::1]:443",
	}

	results := bm.CheckBatch(context.Background(), targets)
	if len(results) != len(targets) {
		t.Fatalf("expected %d results, got %d", len(targets), len(results))
	}
	for _, result := range results {
		if result.Alive {
			t.Fatalf("private target %s must never be benchmarked as alive", result.Target)
		}
		if result.Err == nil {
			t.Fatalf("private target %s should return an explicit rejection", result.Target)
		}
	}
}

func TestResolvePublicTargetsRejectsReservedDocumentationRanges(t *testing.T) {
	reserved := []string{
		"192.0.2.1:443",
		"198.51.100.1:443",
		"203.0.113.1:443",
		"[2001:db8::1]:443",
	}
	for _, target := range reserved {
		if endpoints, err := resolvePublicTargets(context.Background(), target); err == nil {
			t.Fatalf("expected %s to be rejected, got %v", target, endpoints)
		}
	}
}

func TestIsPublicIPAllowsRepresentativePublicAddresses(t *testing.T) {
	for _, raw := range []string{"1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"} {
		if !isPublicIP(net.ParseIP(raw)) {
			t.Fatalf("expected %s to be accepted as public", raw)
		}
	}
}

func TestResolvePublicTargetsValidatesPort(t *testing.T) {
	invalid := []string{"example.com", "example.com:0", "example.com:70000", "example.com:not-a-port"}
	for _, target := range invalid {
		if _, err := resolvePublicTargets(context.Background(), target); err == nil {
			t.Fatalf("expected invalid target %q to fail validation", target)
		}
	}
}

func TestCheckBatchEmptyInput(t *testing.T) {
	bm := NewBenchmarker(time.Second, 4)
	if results := bm.CheckBatch(context.Background(), nil); len(results) != 0 {
		t.Fatalf("expected empty results, got %v", results)
	}
}
