// Package main implements a lightweight, stateless multi-region vantage probe agent.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"time"
)

// Observation records an individual vantage probe target measurement.
type Observation struct {
	Target    string  `json:"target"`
	Alive     bool    `json:"alive"`
	LatencyMs float64 `json:"latency_ms"`
	Protocol  string  `json:"protocol"`
}

// VantageReport aggregates multiple target observations from a specific vantage region.
type VantageReport struct {
	RegionID     string        `json:"region_id"`
	Provider     string        `json:"provider"`
	Timestamp    string        `json:"timestamp"`
	Observations []Observation `json:"observations"`
}

// ProbeAgentOption configures the vantage probe agent.
type ProbeAgentOption func(*ProbeAgent)

func WithRegionID(region string) ProbeAgentOption {
	return func(a *ProbeAgent) { a.RegionID = region }
}

func WithVantageProvider(provider string) ProbeAgentOption {
	return func(a *ProbeAgent) { a.Provider = provider }
}

func WithProbeTimeout(d time.Duration) ProbeAgentOption {
	return func(a *ProbeAgent) { a.Timeout = d }
}

func WithOrchestratorEndpoint(url string) ProbeAgentOption {
	return func(a *ProbeAgent) { a.OrchestratorURL = url }
}

// ProbeAgent runs telemetry sweeps and pushes metrics to the orchestrator.
type ProbeAgent struct {
	RegionID        string
	Provider        string
	Timeout         time.Duration
	OrchestratorURL string
	client          *http.Client
}

// NewProbeAgent initializes a new probe agent.
func NewProbeAgent(opts ...ProbeAgentOption) *ProbeAgent {
	a := &ProbeAgent{
		RegionID:        "default-vantage",
		Provider:        "generic",
		Timeout:         1000 * time.Millisecond,
		OrchestratorURL: "http://localhost:8080/api/vantage/report",
		client:          &http.Client{Timeout: 5 * time.Second},
	}
	for _, opt := range opts {
		opt(a)
	}
	return a
}

// EvaluateTargets conducts non-blocking handshakes across target endpoints.
func (a *ProbeAgent) EvaluateTargets(ctx context.Context, targets []string) VantageReport {
	report := VantageReport{
		RegionID:     a.RegionID,
		Provider:     a.Provider,
		Timestamp:    time.Now().UTC().Format(time.RFC3339),
		Observations: make([]Observation, 0, len(targets)),
	}

	dialer := net.Dialer{Timeout: a.Timeout}
	for _, target := range targets {
		if ctx.Err() != nil {
			break
		}
		start := time.Now()
		conn, err := dialer.DialContext(ctx, "tcp", target)
		if err != nil {
			report.Observations = append(report.Observations, Observation{
				Target:    target,
				Alive:     false,
				LatencyMs: 0.0,
			})
			continue
		}
		latency := time.Since(start)
		_ = conn.Close()
		report.Observations = append(report.Observations, Observation{
			Target:    target,
			Alive:     true,
			LatencyMs: float64(latency.Microseconds()) / 1000.0,
		})
	}

	return report
}

// SubmitReport sends a JSON report to the central orchestrator.
func (a *ProbeAgent) SubmitReport(ctx context.Context, report VantageReport) error {
	payload, err := json.Marshal(report)
	if err != nil {
		return fmt.Errorf("failed to marshal report: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", a.OrchestratorURL, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to submit report: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("orchestrator returned status %d", resp.StatusCode)
	}
	return nil
}

func main() {
	agent := NewProbeAgent()
	fmt.Printf("[HUNTX-PROBE] Initialized vantage agent %s (%s)\n", agent.RegionID, agent.Provider)
}
