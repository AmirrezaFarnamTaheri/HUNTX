package healing

import (
	"testing"
	"time"
)

func TestDaemonBackoffAndPurge(t *testing.T) {
	d := NewDaemon([]time.Duration{10 * time.Second, 30 * time.Second})
	now := time.Now()

	failCount, nextCheck := d.RecordFailure("h1", "vless://u@h1:443", now)
	if failCount != 1 {
		t.Errorf("Expected fail count 1, got %d", failCount)
	}
	if !nextCheck.Equal(now.Add(10 * time.Second)) {
		t.Errorf("Expected next check in 10s")
	}

	due := d.GetDueForRetest(now.Add(5 * time.Second))
	if len(due) != 0 {
		t.Errorf("Expected 0 due, got %d", len(due))
	}

	due = d.GetDueForRetest(now.Add(10 * time.Second))
	if len(due) != 1 {
		t.Errorf("Expected 1 due, got %d", len(due))
	}

	d.RecordFailure("h2", "vmess://u@h2:443", now.Add(-49*time.Hour))
	purged := d.PurgeStale(48*time.Hour, now)
	if purged != 1 {
		t.Errorf("Expected 1 purged, got %d", purged)
	}
}

func TestDueNodesAreDefensiveCopies(t *testing.T) {
	d := NewDaemon([]time.Duration{time.Second})
	now := time.Now()
	d.RecordFailure("h1", "vless://original@host:443", now)

	due := d.GetDueForRetest(now.Add(time.Second))
	if len(due) != 1 {
		t.Fatalf("expected one due node, got %d", len(due))
	}
	due[0].RawURI = "mutated"
	due[0].FailCount = 999

	again := d.GetDueForRetest(now.Add(time.Second))
	if len(again) != 1 {
		t.Fatalf("expected one due node, got %d", len(again))
	}
	if again[0].RawURI != "vless://original@host:443" || again[0].FailCount != 1 {
		t.Fatalf("caller mutation leaked into daemon state: %#v", again[0])
	}
}

func TestInvalidBackoffCannotCreateBusyLoop(t *testing.T) {
	now := time.Now()
	d := NewDaemon([]time.Duration{0, -time.Second})
	_, next := d.RecordFailure("h1", "vless://u@h1:443", now)
	if !next.After(now) {
		t.Fatalf("expected a positive fallback backoff, got %s", next.Sub(now))
	}
}

func TestNonPositivePurgeAgeIsNoOp(t *testing.T) {
	now := time.Now()
	d := NewDaemon([]time.Duration{time.Second})
	d.RecordFailure("h1", "vless://u@h1:443", now.Add(-24*time.Hour))

	if purged := d.PurgeStale(0, now); purged != 0 {
		t.Fatalf("zero max age should not purge everything, got %d", purged)
	}
	if due := d.GetDueForRetest(now); len(due) != 1 {
		t.Fatalf("node should remain after no-op purge, got %d", len(due))
	}
}

func ExampleDaemon_PurgeStale() {
	daemon := NewDaemon(nil)
	now := time.Now()
	daemon.RecordFailure("node_abc", "vless://u@node.example:443#DE", now.Add(-72*time.Hour))
	_ = daemon.PurgeStale(48*time.Hour, now) // Returns 1
}
