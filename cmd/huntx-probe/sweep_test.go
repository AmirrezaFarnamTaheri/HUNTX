package main

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

// stubConn satisfies net.Conn for dial stubs; nothing reads or writes it.
type stubConn struct{ net.Conn }

func (stubConn) Close() error { return nil }

func stubDial(delay time.Duration, failing map[string]bool) func(context.Context, string, string) (net.Conn, error) {
	return func(ctx context.Context, _, address string) (net.Conn, error) {
		select {
		case <-time.After(delay):
		case <-ctx.Done():
			return nil, ctx.Err()
		}
		if failing[address] {
			return nil, errors.New("connection refused")
		}
		return stubConn{}, nil
	}
}

func TestSweepPreservesTargetOrderUnderConcurrency(t *testing.T) {
	agent := NewProbeAgent()
	agent.dial = stubDial(5*time.Millisecond, map[string]bool{"t3:1": true, "t7:1": true})

	targets := make([]string, 12)
	for i := range targets {
		targets[i] = fmt.Sprintf("t%d:1", i)
	}
	report := agent.EvaluateTargets(context.Background(), targets)

	if len(report.Observations) != len(targets) {
		t.Fatalf("expected %d observations, got %d", len(targets), len(report.Observations))
	}
	for i, obs := range report.Observations {
		if obs.Target != targets[i] {
			t.Fatalf("observation %d is for %q, want %q: order was not preserved", i, obs.Target, targets[i])
		}
		wantAlive := targets[i] != "t3:1" && targets[i] != "t7:1"
		if obs.Alive != wantAlive {
			t.Errorf("%s: alive=%v, want %v", obs.Target, obs.Alive, wantAlive)
		}
	}
}

func TestSweepCostIsBoundedNotLinearInTargets(t *testing.T) {
	const perDial = 100 * time.Millisecond
	agent := NewProbeAgent()
	agent.dial = stubDial(perDial, nil)

	targets := make([]string, 32)
	for i := range targets {
		targets[i] = fmt.Sprintf("t%d:1", i)
	}
	start := time.Now()
	report := agent.EvaluateTargets(context.Background(), targets)
	elapsed := time.Since(start)

	if len(report.Observations) != len(targets) {
		t.Fatalf("expected %d observations, got %d", len(targets), len(report.Observations))
	}
	// Sequential would take 32 x 100ms = 3.2s. With a fan-out of 16 it is two
	// waves, ~200ms. Anything under one second proves the sweep is concurrent
	// without being sensitive to a loaded CI runner.
	if elapsed > time.Second {
		t.Fatalf("sweep of %d targets took %v; dialling looks sequential", len(targets), elapsed)
	}
}

func TestSweepNeverExceedsTheConcurrencyBound(t *testing.T) {
	var inFlight, peak int32
	agent := NewProbeAgent()
	agent.dial = func(ctx context.Context, _, _ string) (net.Conn, error) {
		n := atomic.AddInt32(&inFlight, 1)
		for {
			old := atomic.LoadInt32(&peak)
			if n <= old || atomic.CompareAndSwapInt32(&peak, old, n) {
				break
			}
		}
		time.Sleep(20 * time.Millisecond)
		atomic.AddInt32(&inFlight, -1)
		return stubConn{}, nil
	}
	targets := make([]string, 64)
	for i := range targets {
		targets[i] = fmt.Sprintf("t%d:1", i)
	}
	agent.EvaluateTargets(context.Background(), targets)
	if got := atomic.LoadInt32(&peak); got > maxConcurrentProbes {
		t.Fatalf("peak concurrency %d exceeds bound %d", got, maxConcurrentProbes)
	}
}

func TestSweepDoesNotFabricateResultsForCancelledTargets(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	agent := NewProbeAgent()
	agent.dial = func(ctx context.Context, _, _ string) (net.Conn, error) {
		cancel() // the first dial cancels the sweep
		return stubConn{}, nil
	}
	targets := make([]string, 200)
	for i := range targets {
		targets[i] = fmt.Sprintf("t%d:1", i)
	}
	report := agent.EvaluateTargets(ctx, targets)
	if len(report.Observations) >= len(targets) {
		t.Fatalf("cancelled sweep reported all %d targets", len(report.Observations))
	}
	for _, obs := range report.Observations {
		if obs.Protocol != "tcp" {
			t.Errorf("observation %q has protocol %q, want tcp", obs.Target, obs.Protocol)
		}
	}
}

func TestEveryObservationCarriesItsProtocol(t *testing.T) {
	agent := NewProbeAgent()
	agent.dial = stubDial(0, map[string]bool{"down:1": true})
	report := agent.EvaluateTargets(context.Background(), []string{"up:1", "down:1"})
	for _, obs := range report.Observations {
		if obs.Protocol != "tcp" {
			t.Errorf("%s: protocol %q, want tcp (both alive and dead observations)", obs.Target, obs.Protocol)
		}
	}
}

func TestEmptyTargetListYieldsAnEmptyNotNullArray(t *testing.T) {
	report := NewProbeAgent().EvaluateTargets(context.Background(), nil)
	if report.Observations == nil {
		t.Fatal("Observations must be an empty slice so it serializes as [] rather than null")
	}
}

func TestSubmitReportDoesNotFollowRedirectsWithTheToken(t *testing.T) {
	var leaked atomic.Bool
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "" {
			leaked.Store(true)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer target.Close()
	redirector := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, target.URL, http.StatusTemporaryRedirect)
	}))
	defer redirector.Close()

	agent := NewProbeAgent(
		WithOrchestratorEndpoint(redirector.URL),
		WithOrchestratorBearerToken("probe-token"),
	)
	err := agent.SubmitReport(context.Background(), VantageReport{})
	if err == nil {
		t.Fatal("a redirect response must be reported as a failed submission")
	}
	if leaked.Load() {
		t.Fatal("the bearer token was replayed to the redirect target")
	}
}
