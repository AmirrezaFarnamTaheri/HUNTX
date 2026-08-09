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

	// Purge stale
	d.RecordFailure("h2", "vmess://u@h2:443", now.Add(-49*time.Hour))
	purged := d.PurgeStale(48*time.Hour, now)
	if purged != 1 {
		t.Errorf("Expected 1 purged, got %d", purged)
	}
}
