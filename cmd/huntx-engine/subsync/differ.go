// Package subsync provides real-time 3-way cryptographic hash diff synchronization for subscriptions.
//
// Authority:
//   FIPS 180-4 (SHA-256): https://csrc.nist.gov/publications/detail/fips/180/4/final
package subsync

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"sync"
)

// SyncDiff holds categorized diff sets between subscription states.
type SyncDiff struct {
	Added     []string `json:"added"`
	Removed   []string `json:"removed"`
	Unchanged []string `json:"unchanged"`
}

// SubscriptionDiffer computes incremental state transitions.
type SubscriptionDiffer struct {
	mu sync.RWMutex
}

// NewSubscriptionDiffer creates a new differ instance.
func NewSubscriptionDiffer() *SubscriptionDiffer {
	return &SubscriptionDiffer{}
}

func computeHash(uri string) string {
	h := sha256.Sum256([]byte(strings.TrimSpace(uri)))
	return hex.EncodeToString(h[:])
}

// ComputeDiff calculates Added, Removed, and Unchanged sets between baseline and incoming.
func (d *SubscriptionDiffer) ComputeDiff(baseline, incoming []string) SyncDiff {
	d.mu.RLock()
	defer d.mu.RUnlock()

	baseMap := make(map[string]string, len(baseline)) // hash -> uri
	for _, u := range baseline {
		clean := strings.TrimSpace(u)
		if clean != "" {
			baseMap[computeHash(clean)] = clean
		}
	}

	incMap := make(map[string]string, len(incoming)) // hash -> uri
	for _, u := range incoming {
		clean := strings.TrimSpace(u)
		if clean != "" {
			incMap[computeHash(clean)] = clean
		}
	}

	diff := SyncDiff{
		Added:     make([]string, 0),
		Removed:   make([]string, 0),
		Unchanged: make([]string, 0),
	}

	for hash, uri := range incMap {
		if _, exists := baseMap[hash]; exists {
			diff.Unchanged = append(diff.Unchanged, uri)
		} else {
			diff.Added = append(diff.Added, uri)
		}
	}

	for hash, uri := range baseMap {
		if _, exists := incMap[hash]; !exists {
			diff.Removed = append(diff.Removed, uri)
		}
	}

	return diff
}
