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

	// Test report generation on targets
	targets := []string{"1.1.1.1:443", "8.8.8.8:443"}
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
