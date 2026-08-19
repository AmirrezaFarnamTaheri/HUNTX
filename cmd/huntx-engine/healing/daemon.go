package healing

import (
	"sort"
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
	clean := make([]time.Duration, 0, len(backoff))
	for _, delay := range backoff {
		if delay > 0 {
			clean = append(clean, delay)
		}
	}
	if len(clean) == 0 {
		clean = []time.Duration{5 * time.Minute}
	}
	return &Daemon{
		degraded:        make(map[string]*DegradedNode),
		backoffSchedule: clean,
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
	// Return defensive copies. Returning internal pointers after releasing the
	// mutex lets callers mutate daemon state without synchronization.
	d.mu.RLock()
	due := make([]*DegradedNode, 0)
	for _, n := range d.degraded {
		if !n.NextCheckAt.After(now) {
			copyNode := *n
			due = append(due, &copyNode)
		}
	}
	d.mu.RUnlock()

	// Stable ordering makes scheduler behavior/test output deterministic even
	// though the backing map iteration order is intentionally random.
	sort.Slice(due, func(i, j int) bool {
		if due[i].NextCheckAt.Equal(due[j].NextCheckAt) {
			return due[i].UniqueHash < due[j].UniqueHash
		}
		return due[i].NextCheckAt.Before(due[j].NextCheckAt)
	})
	return due
}

func (d *Daemon) PurgeStale(maxAge time.Duration, now time.Time) int {
	if maxAge <= 0 {
		return 0
	}
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
