// Package exporter provides a Prometheus metrics exporter and security middleware for edge probes.
//
// Authority:
//   Prometheus Text-Based Exposition Format (0.0.4): https://prometheus.io/docs/instrumenting/exposition_formats/
package exporter

import (
	"crypto/subtle"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"
)

// ProbeMetricEntry stores telemetry state for a single probed endpoint.
type ProbeMetricEntry struct {
	ProbeID     string
	TargetID    string
	Latency     time.Duration
	JitterMS    float64
	LossRatio   float64
	IsAlive     bool
	LastChecked time.Time
}

// MetricsExporter provides Prometheus exposition and Bearer token security.
type MetricsExporter struct {
	mu        sync.RWMutex
	authToken string
	metrics   map[string]ProbeMetricEntry
}

// NewMetricsExporter initializes a metrics exporter.
func NewMetricsExporter(authToken string) *MetricsExporter {
	return &MetricsExporter{
		authToken: authToken,
		metrics:   make(map[string]ProbeMetricEntry),
	}
}

// RecordProbeResult records observed network characteristics for an edge target.
func (m *MetricsExporter) RecordProbeResult(probeID, targetID string, latency time.Duration, jitterMS, lossRatio float64, isAlive bool) {
	key := fmt.Sprintf("%s:%s", probeID, targetID)
	m.mu.Lock()
	m.metrics[key] = ProbeMetricEntry{
		ProbeID:     probeID,
		TargetID:    targetID,
		Latency:     latency,
		JitterMS:    jitterMS,
		LossRatio:   lossRatio,
		IsAlive:     isAlive,
		LastChecked: time.Now(),
	}
	m.mu.Unlock()
}

// Handler returns the authenticated HTTP handler serving Prometheus metrics.
func (m *MetricsExporter) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Enforce Bearer Token Authentication
		authHeader := r.Header.Get("Authorization")
		if m.authToken != "" {
			expected := "Bearer " + m.authToken
			if subtle.ConstantTimeCompare([]byte(authHeader), []byte(expected)) != 1 {
				http.Error(w, "Unauthorized", http.StatusUnauthorized)
				return
			}
		}

		w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
		
		var b strings.Builder
		b.WriteString("# HELP huntx_probe_latency_seconds Observed round-trip latency in seconds\n")
		b.WriteString("# TYPE huntx_probe_latency_seconds gauge\n")
		b.WriteString("# HELP huntx_probe_jitter_ms RFC3550 statistical latency jitter in milliseconds\n")
		b.WriteString("# TYPE huntx_probe_jitter_ms gauge\n")
		b.WriteString("# HELP huntx_probe_packet_loss_ratio Ratio of lost UDP/ICMP probe packets (0.0 - 1.0)\n")
		b.WriteString("# TYPE huntx_probe_packet_loss_ratio gauge\n")
		b.WriteString("# HELP huntx_probe_up 1 if endpoint responded to TCP/QUIC handshake, 0 otherwise\n")
		b.WriteString("# TYPE huntx_probe_up gauge\n")

		m.mu.RLock()
		for _, entry := range m.metrics {
			upVal := 0
			if entry.IsAlive {
				upVal = 1
			}
			b.WriteString(fmt.Sprintf("huntx_probe_latency_seconds{probe_id=%q,target_id=%q} %.6f\n",
				entry.ProbeID, entry.TargetID, entry.Latency.Seconds()))
			b.WriteString(fmt.Sprintf("huntx_probe_jitter_ms{probe_id=%q,target_id=%q} %.3f\n",
				entry.ProbeID, entry.TargetID, entry.JitterMS))
			b.WriteString(fmt.Sprintf("huntx_probe_packet_loss_ratio{probe_id=%q,target_id=%q} %.4f\n",
				entry.ProbeID, entry.TargetID, entry.LossRatio))
			b.WriteString(fmt.Sprintf("huntx_probe_up{probe_id=%q,target_id=%q} %d\n",
				entry.ProbeID, entry.TargetID, upVal))
		}
		m.mu.RUnlock()

		_, _ = w.Write([]byte(b.String()))
	})
}
