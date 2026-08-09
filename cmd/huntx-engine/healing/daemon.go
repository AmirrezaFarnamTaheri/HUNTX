package healing

import (
	"sync"
	"time"
)

type DegradedNode struct {
	UniqueHash    string
	RawURI        string
	FailCount     int
	FirstFailedAt time.Time
	NextCheckAt   time.Time
}

type Daemon struct {
	mu              sync.RWMutex
	degraded        map[string]*DegradedNode
	backoffSchedule []time.Duration
}

func NewDaemon(backoff []time.Duration) *Daemon {
	if len(backoff) == 0 {
		backoff = []time.Duration{
			5 * time.Minute,
			15 * time.Minute,
			1 * time.Hour,
			6 * time.Hour,
		}
	}
	return &Daemon{
		degraded:        make(map[string]*DegradedNode),
		backoffSchedule: backoff,
	}
}

func (d *Daemon) RecordFailure(hash, uri string, now time.Time) (int, time.Time) {
	d.mu.Lock()
	defer d.mu.Unlock()

	node, exists := d.degraded[hash]
	failCount := 1
	firstFailedAt := now

	if exists {
		failCount = node.FailCount + 1
		firstFailedAt = node.FirstFailedAt
	}

	idx := failCount - 1
	if idx >= len(d.backoffSchedule) {
		idx = len(d.backoffSchedule) - 1
	}
	nextCheck := now.Add(d.backoffSchedule[idx])

	d.degraded[hash] = &DegradedNode{
		UniqueHash:    hash,
		RawURI:        uri,
		FailCount:     failCount,
		FirstFailedAt: firstFailedAt,
		NextCheckAt:   nextCheck,
	}

	return failCount, nextCheck
}

func (d *Daemon) Reinstate(hash string) bool {
	d.mu.Lock()
	defer d.mu.Unlock()

	if _, exists := d.degraded[hash]; exists {
		delete(d.degraded, hash)
		return true
	}
	return false
}

func (d *Daemon) GetDueForRetest(now time.Time) []*DegradedNode {
	d.mu.RLock()
	defer d.mu.RUnlock()

	var due []*DegradedNode
	for _, n := range d.degraded {
		if !n.NextCheckAt.After(now) {
			due = append(due, n)
		}
	}
	return due
}

func (d *Daemon) PurgeStale(maxAge time.Duration, now time.Time) int {
	d.mu.Lock()
	defer d.mu.Unlock()

	cutoff := now.Add(-maxAge)
	purged := 0
	for hash, n := range d.degraded {
		if n.FirstFailedAt.Before(cutoff) {
			delete(d.degraded, hash)
			purged++
		}
	}
	return purged
}
