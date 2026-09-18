// Package main implements a lightweight, stateless multi-region vantage probe agent.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
)

// maxConcurrentProbes bounds simultaneous dials in one sweep. Enough to finish a
// large target list inside a single reporting interval, few enough not to look
// like a scan or exhaust file descriptors on a small vantage host.
const maxConcurrentProbes = 16

// probeProtocol labels what an observation measured: a TCP handshake.
const probeProtocol = "tcp"

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

func WithOrchestratorBearerToken(token string) ProbeAgentOption {
	return func(a *ProbeAgent) { a.OrchestratorBearerToken = token }
}

// ProbeAgent runs telemetry sweeps and pushes metrics to the orchestrator.
type ProbeAgent struct {
	RegionID                string
	Provider                string
	Timeout                 time.Duration
	OrchestratorURL         string
	OrchestratorBearerToken string
	client                  *http.Client
	// dial opens the measured connection. It is a field so tests can inject
	// latency and failure without touching the network; production uses a
	// net.Dialer bounded by Timeout.
	dial func(ctx context.Context, network, address string) (net.Conn, error)
}

// NewProbeAgent initializes a new probe agent.
func NewProbeAgent(opts ...ProbeAgentOption) *ProbeAgent {
	a := &ProbeAgent{
		RegionID:        "default-vantage",
		Provider:        "generic",
		Timeout:         1000 * time.Millisecond,
		OrchestratorURL: "http://localhost:8080/api/vantage/report",
		client: &http.Client{
			Timeout: 5 * time.Second,
			// A report is a one-shot POST to a configured URL. Following a redirect
			// could replay the bearer token to a different scheme or path than the
			// one validateTransport approved.
			CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		},
	}
	for _, opt := range opts {
		opt(a)
	}
	if a.dial == nil {
		dialer := &net.Dialer{Timeout: a.Timeout}
		a.dial = dialer.DialContext
	}
	return a
}

// EvaluateTargets measures a TCP handshake to every target, concurrently but
// with a bounded fan-out, and returns the observations in target order.
//
// Sequential dialling made a sweep cost N x Timeout when targets were down, so
// a large list of dead endpoints outran the reporting interval and every
// report arrived late. Order is preserved because consumers correlate
// observations positionally with the configured target list.
func (a *ProbeAgent) EvaluateTargets(ctx context.Context, targets []string) VantageReport {
	report := VantageReport{
		RegionID:  a.RegionID,
		Provider:  a.Provider,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	}

	results := make([]Observation, len(targets))
	measured := make([]bool, len(targets))
	sem := make(chan struct{}, maxConcurrentProbes)
	var wg sync.WaitGroup

	for i, target := range targets {
		if ctx.Err() != nil {
			break
		}
		sem <- struct{}{}
		if ctx.Err() != nil {
			<-sem
			break
		}
		wg.Add(1)
		go func(i int, target string) {
			defer wg.Done()
			defer func() { <-sem }()
			results[i] = a.measure(ctx, target)
			measured[i] = true
		}(i, target)
	}
	wg.Wait()

	report.Observations = make([]Observation, 0, len(targets))
	for i, ok := range measured {
		// A target skipped because the context was cancelled has no
		// observation; reporting it as dead would be a fabricated result.
		if ok {
			report.Observations = append(report.Observations, results[i])
		}
	}
	return report
}

// measure times one TCP handshake.
func (a *ProbeAgent) measure(ctx context.Context, target string) Observation {
	start := time.Now()
	conn, err := a.dial(ctx, "tcp", target)
	if err != nil {
		return Observation{Target: target, Alive: false, LatencyMs: 0.0, Protocol: probeProtocol}
	}
	latency := time.Since(start)
	_ = conn.Close()
	return Observation{
		Target:    target,
		Alive:     true,
		LatencyMs: float64(latency.Microseconds()) / 1000.0,
		Protocol:  probeProtocol,
	}
}

// validateTransport fails closed when a bearer token would be sent over a
// plaintext remote connection. Loopback endpoints are permitted so local
// development and tests keep working; anything else must use https.
func (a *ProbeAgent) validateTransport() error {
	if a.OrchestratorBearerToken == "" {
		return nil
	}
	parsed, err := url.Parse(a.OrchestratorURL)
	if err != nil || parsed.Host == "" {
		return fmt.Errorf("invalid orchestrator url %q: %w", a.OrchestratorURL, err)
	}
	if parsed.Scheme == "https" {
		return nil
	}
	host, _, splitErr := net.SplitHostPort(parsed.Host)
	if splitErr != nil {
		host = parsed.Host
	}
	if host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "[::1]" {
		return nil
	}
	return fmt.Errorf(
		"refusing to send bearer token over plaintext scheme %q to %q; use https",
		parsed.Scheme, parsed.Host,
	)
}

// SubmitReport sends a JSON report to the central orchestrator.
func (a *ProbeAgent) SubmitReport(ctx context.Context, report VantageReport) error {
	payload, err := json.Marshal(report)
	if err != nil {
		return fmt.Errorf("failed to marshal report: %w", err)
	}

	if err := a.validateTransport(); err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, "POST", a.OrchestratorURL, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if a.OrchestratorBearerToken != "" {
		req.Header.Set("Authorization", "Bearer "+a.OrchestratorBearerToken)
	}

	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to submit report: %w", err)
	}
	defer resp.Body.Close()
	// Drain (bounded) so the keep-alive connection returns to the pool.
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 64<<10))

	// Redirects are not followed (see NewProbeAgent), so a 3xx means the
	// configured URL is wrong and the report was not accepted.
	if resp.StatusCode >= 300 {
		return fmt.Errorf("orchestrator returned status %d", resp.StatusCode)
	}
	return nil
}

func main() {
	region := os.Getenv("REGION")
	if region == "" {
		region = "default-vantage"
	}
	provider := os.Getenv("PROBE_ID")
	if provider == "" {
		provider = "generic"
	}
	endpoint := os.Getenv("ORCHESTRATOR_URL")
	if endpoint == "" {
		endpoint = "http://localhost:8080/api/vantage/report"
	}
	orchestratorToken := strings.TrimSpace(os.Getenv("ORCHESTRATOR_BEARER_TOKEN"))
	targets := strings.FieldsFunc(os.Getenv("PROBE_TARGETS"), func(r rune) bool { return r == ',' || r == ';' || r == ' ' })
	if len(targets) == 0 {
		targets = []string{"1.1.1.1:443"}
	}
	agent := NewProbeAgent(
		WithRegionID(region),
		WithVantageProvider(provider),
		WithOrchestratorEndpoint(endpoint),
		WithOrchestratorBearerToken(orchestratorToken),
	)
	fmt.Printf("[HUNTX-PROBE] Started vantage agent %s (%s)\n", agent.RegionID, agent.Provider)
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		report := agent.EvaluateTargets(ctx, targets)
		if err := agent.SubmitReport(ctx, report); err != nil {
			fmt.Fprintf(os.Stderr, "[HUNTX-PROBE] report submission failed: %v\n", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
