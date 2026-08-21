// Package telemetry provides statistical latency anomaly detection and jitter analysis for HUNTX engine probers.
package telemetry

import (
	"math"
	"testing"
	"time"
)

func TestOnlineStatsAccumulator(t *testing.T) {
	acc := NewStatsAccumulator()

	samples := []time.Duration{
		10 * time.Millisecond,
		20 * time.Millisecond,
		30 * time.Millisecond,
		40 * time.Millisecond,
		50 * time.Millisecond,
	}

	for _, s := range samples {
		acc.AddSample(s)
	}

	if acc.Count() != 5 {
		t.Fatalf("expected count 5, got %d", acc.Count())
	}

	expectedMean := 30.0 // ms
	if math.Abs(acc.MeanMs()-expectedMean) > 1e-4 {
		t.Errorf("expected mean %.2f, got %.2f", expectedMean, acc.MeanMs())
	}

	// Sample variance of [10, 20, 30, 40, 50] is 250, stddev = sqrt(250) ≈ 15.811
	expectedStdDev := math.Sqrt(250.0)
	if math.Abs(acc.StdDevMs()-expectedStdDev) > 1e-2 {
		t.Errorf("expected stddev %.2f, got %.2f", expectedStdDev, acc.StdDevMs())
	}
}

func TestAnomalyClassification(t *testing.T) {
	acc := NewStatsAccumulator()

	// Train baseline around 50ms +/- 5ms
	for i := 0; i < 20; i++ {
		acc.AddSample(time.Duration(48+i%5) * time.Millisecond)
	}

	// 50ms should not be anomaly
	if acc.IsAnomaly(50*time.Millisecond, 3.0) {
		t.Errorf("50ms should not be an anomaly")
	}

	// 500ms should definitely be an anomaly (Z-score >> 3.0)
	if !acc.IsAnomaly(500*time.Millisecond, 3.0) {
		t.Errorf("500ms should be flagged as an anomaly")
	}
}

func TestRFC3550JitterCalculation(t *testing.T) {
	j := NewRFC3550JitterEstimator()

	// Packet 1: Transit time = 100ms
	j.Update(100*time.Millisecond, 100*time.Millisecond)
	if j.JitterMs() != 0 {
		t.Errorf("first packet jitter should be 0, got %.2f", j.JitterMs())
	}

	// Packet 2: Transit time = 120ms (diff = 20ms) -> Jitter = (0*15 + 20)/16 = 1.25ms
	j.Update(200*time.Millisecond, 220*time.Millisecond)
	expected := 20.0 / 16.0
	if math.Abs(j.JitterMs()-expected) > 1e-4 {
		t.Errorf("expected jitter %.4f, got %.4f", expected, j.JitterMs())
	}
}
