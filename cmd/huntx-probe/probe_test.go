package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestProbeAgentCollectsTelemetry(t *testing.T) {
	agent := NewProbeAgent(
		WithRegionID("eu-central-fra"),
		WithVantageProvider("hetzner"),
		WithProbeTimeout(500*time.Millisecond),
	)

	if agent.RegionID != "eu-central-fra" || agent.Provider != "hetzner" {
		t.Errorf("unexpected agent configuration: %+v", agent)
	}

	// Hermetic: the report shape is under test, not the reachability of public
	// addresses, so a CI runner without outbound access behaves identically.
	agent.dial = stubDial(0, map[string]bool{"unreachable.invalid:443": true})
	targets := []string{"reachable.invalid:443", "unreachable.invalid:443"}
	report := agent.EvaluateTargets(context.Background(), targets)

	if report.RegionID != "eu-central-fra" {
		t.Errorf("expected report region eu-central-fra, got %s", report.RegionID)
	}
	if len(report.Observations) != 2 {
		t.Errorf("expected 2 observations, got %d", len(report.Observations))
	}
}

func TestProbeAgentHTTPDispatch(t *testing.T) {
	var receivedReport bool
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && r.URL.Path == "/api/vantage/report" {
			if got := r.Header.Get("Authorization"); got != "Bearer probe-token" {
				t.Fatalf("expected authorization header, got %q", got)
			}
			receivedReport = true
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ack"}`))
		}
	}))
	defer server.Close()

	agent := NewProbeAgent(
		WithOrchestratorEndpoint(server.URL+"/api/vantage/report"),
		WithOrchestratorBearerToken("probe-token"),
	)
	err := agent.SubmitReport(context.Background(), VantageReport{
		RegionID:  "us-east-iad",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	})
	if err != nil {
		t.Fatalf("unexpected submit error: %v", err)
	}
	if !receivedReport {
		t.Errorf("orchestrator server did not receive report")
	}
}

func TestProbeAgentRefusesPlaintextBearerToRemoteHost(t *testing.T) {
	cases := []struct {
		name      string
		url       string
		token     string
		wantError bool
	}{
		{"https remote with token", "https://orchestrator.example/api/vantage/report", "token", false},
		{"http loopback with token", "http://127.0.0.1:8080/api/vantage/report", "token", false},
		{"http localhost with token", "http://localhost:8080/api/vantage/report", "token", false},
		{"http remote with token", "http://orchestrator.example/api/vantage/report", "token", true},
		{"http remote without token", "http://orchestrator.example/api/vantage/report", "", false},
		{"https remote without token", "https://orchestrator.example/api/vantage/report", "", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			agent := NewProbeAgent(
				WithOrchestratorEndpoint(tc.url),
				WithOrchestratorBearerToken(tc.token),
			)
			err := agent.validateTransport()
			if tc.wantError && err == nil {
				t.Errorf("expected transport error for %q, got none", tc.url)
			}
			if !tc.wantError && err != nil {
				t.Errorf("unexpected transport error for %q: %v", tc.url, err)
			}
		})
	}
}

func TestSubmitReportBlocksPlaintextBearerBeforeAnyRequest(t *testing.T) {
	// Force a non-loopback host while keeping the plaintext scheme.
	agent := NewProbeAgent(
		WithOrchestratorEndpoint("http://orchestrator.example/api/vantage/report"),
		WithOrchestratorBearerToken("probe-token"),
	)
	err := agent.SubmitReport(context.Background(), VantageReport{
		RegionID:  "us-east-iad",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	})
	if err == nil {
		t.Fatalf("expected submit to fail closed, got success")
	}
}
