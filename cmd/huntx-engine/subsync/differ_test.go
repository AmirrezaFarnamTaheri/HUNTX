// Package subsync provides real-time 3-way cryptographic hash diff synchronization for subscriptions.
package subsync

import (
	"testing"
)

func TestSubscriptionDifferAddedRemovedUnchanged(t *testing.T) {
	differ := NewSubscriptionDiffer()

	baseline := []string{
		"vless://uuid-1@server1.com:443?type=ws#US-1",
		"vless://uuid-2@server2.com:443?type=tcp#US-2",
		"vless://uuid-3@server3.com:443?type=grpc#US-3",
	}

	incoming := []string{
		"vless://uuid-1@server1.com:443?type=ws#US-1",        // Unchanged
		"vless://uuid-2@server2.com:443?type=ws#US-2-Mutated", // Mutated / New hash
		"vless://uuid-4@server4.com:443?type=reality#US-4",   // Added
	}

	diff := differ.ComputeDiff(baseline, incoming)

	if len(diff.Unchanged) != 1 {
		t.Errorf("expected 1 unchanged, got %d", len(diff.Unchanged))
	}
	if len(diff.Added) != 2 { // US-4 and US-2-Mutated are new
		t.Errorf("expected 2 added, got %d", len(diff.Added))
	}
	if len(diff.Removed) != 2 { // US-2 and US-3 removed
		t.Errorf("expected 2 removed, got %d", len(diff.Removed))
	}
}

func TestSubscriptionDifferEmptyCases(t *testing.T) {
	differ := NewSubscriptionDiffer()

	diff := differ.ComputeDiff([]string{}, []string{"vless://a@b:443"})
	if len(diff.Added) != 1 || len(diff.Removed) != 0 || len(diff.Unchanged) != 0 {
		t.Errorf("unexpected diff on empty baseline: %+v", diff)
	}

	diff2 := differ.ComputeDiff([]string{"vless://a@b:443"}, []string{})
	if len(diff2.Removed) != 1 || len(diff2.Added) != 0 || len(diff2.Unchanged) != 0 {
		t.Errorf("unexpected diff on empty incoming: %+v", diff2)
	}
}
