// Package telemetry provides statistical latency anomaly detection and jitter analysis for HUNTX engine probers.
//
// Authority:
//   Welford, B. P. (1962). "Note on a method for calculating corrected sums of squares and products".
//   RFC 3550 (RTP: Jitter Calculation): https://datatracker.ietf.org/doc/html/rfc3550#section-6.4.1
package telemetry

import (
	"math"
	"sync"
	"time"
)

// StatsAccumulator computes streaming online mean and standard deviation using Welford's algorithm.
type StatsAccumulator struct {
	mu    sync.RWMutex
	count int64
	mean  float64
	m2    float64
}

// NewStatsAccumulator initializes an empty statistical accumulator.
func NewStatsAccumulator() *StatsAccumulator {
	return &StatsAccumulator{}
}

// AddSample records a latency duration sample into the accumulator.
func (a *StatsAccumulator) AddSample(d time.Duration) {
	a.mu.Lock()
	defer a.mu.Unlock()

	a.count++
	valMs := float64(d.Microseconds()) / 1000.0
	delta := valMs - a.mean
	a.mean += delta / float64(a.count)
	delta2 := valMs - a.mean
	a.m2 += delta * delta2
}

// Count returns the total number of samples collected.
func (a *StatsAccumulator) Count() int64 {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.count
}

// MeanMs returns the running arithmetic mean in milliseconds.
func (a *StatsAccumulator) MeanMs() float64 {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.mean
}

// StdDevMs returns the sample standard deviation in milliseconds.
func (a *StatsAccumulator) StdDevMs() float64 {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.count < 2 {
		return 0.0
	}
	variance := a.m2 / float64(a.count-1)
	if variance <= 0 {
		return 0.0
	}
	return math.Sqrt(variance)
}

// IsAnomaly returns true if the sample exceeds threshold Z-scores from the mean.
func (a *StatsAccumulator) IsAnomaly(d time.Duration, zThreshold float64) bool {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.count < 5 {
		return false
	}
	stdDev := a.StdDevMs()
	if stdDev < 1e-4 {
		return false
	}
	valMs := float64(d.Microseconds()) / 1000.0
	zScore := math.Abs(valMs-a.mean) / stdDev
	return zScore > zThreshold
}

// RFC3550JitterEstimator tracks network packet transit time variance per RFC 3550.
type RFC3550JitterEstimator struct {
	mu           sync.RWMutex
	jitter       float64 // in milliseconds
	hasPrev      bool
	prevTransit  float64 // in milliseconds
}

// NewRFC3550JitterEstimator creates a new RFC 3550 compliant jitter calculator.
func NewRFC3550JitterEstimator() *RFC3550JitterEstimator {
	return &RFC3550JitterEstimator{}
}

// Update records a new packet with send and receive timestamps.
func (j *RFC3550JitterEstimator) Update(sendTime, recvTime time.Duration) {
	j.mu.Lock()
	defer j.mu.Unlock()

	transit := float64((recvTime - sendTime).Microseconds()) / 1000.0
	if !j.hasPrev {
		j.hasPrev = true
		j.prevTransit = transit
		j.jitter = 0.0
		return
	}

	diff := math.Abs(transit - j.prevTransit)
	j.prevTransit = transit
	j.jitter += (diff - j.jitter) / 16.0
}

// JitterMs returns the smoothed statistical jitter in milliseconds.
func (j *RFC3550JitterEstimator) JitterMs() float64 {
	j.mu.RLock()
	defer j.mu.RUnlock()
	return j.jitter
}
