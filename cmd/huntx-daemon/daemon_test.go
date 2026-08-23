package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func authorizedRequest(method, target string) *http.Request {
	req := httptest.NewRequest(method, target, nil)
	req.Header.Set("Authorization", "Bearer test-control-token")
	return req
}

func TestDaemonInitializationAndStatus(t *testing.T) {
	nodes := []DaemonNode{
		{ID: "node-1", Protocol: "http", Server: "1.1.1.1", Port: 443, Latency: 35 * time.Millisecond, Alive: true},
		{ID: "node-2", Protocol: "socks5", Server: "8.8.8.8", Port: 8443, Latency: 60 * time.Millisecond, Alive: true},
	}

	d := NewDaemon(nodes, WithListenAddr("127.0.0.1:0"), WithCheckInterval(100*time.Millisecond))
	if d.ActiveNode().ID != "node-1" {
		t.Errorf("expected initial active node node-1, got %s", d.ActiveNode().ID)
	}

	status := d.GetStatus()
	if status.ActiveNode.ID != "node-1" || status.TotalNodes != 2 {
		t.Errorf("unexpected status: %+v", status)
	}
}

func TestDaemonRotateNode(t *testing.T) {
	nodes := []DaemonNode{
		{ID: "node-1", Protocol: "http", Server: "1.1.1.1", Port: 443, Latency: 35 * time.Millisecond, Alive: true},
		{ID: "node-2", Protocol: "socks5", Server: "8.8.8.8", Port: 8443, Latency: 60 * time.Millisecond, Alive: true},
	}

	d := NewDaemon(nodes)
	rotated := d.RotateNode()
	if rotated.ID != "node-2" {
		t.Errorf("expected rotated node node-2, got %s", rotated.ID)
	}
	if d.ActiveNode().ID != "node-2" {
		t.Errorf("active node should now be node-2")
	}
}

func TestDaemonHTTPHandlerEndpoints(t *testing.T) {
	t.Setenv("HUNTX_DAEMON_CONTROL_TOKEN", "test-control-token")
	nodes := []DaemonNode{
		{ID: "node-1", Protocol: "http", Server: "1.1.1.1", Port: 443, Latency: 35 * time.Millisecond, Alive: true},
		{ID: "node-2", Protocol: "socks5", Server: "8.8.8.8", Port: 8443, Latency: 60 * time.Millisecond, Alive: true},
	}
	d := NewDaemon(nodes)
	handler := d.Handler()

	// 1. Test /status
	req := httptest.NewRequest("GET", "/status", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 on /status, got %d", rr.Code)
	}
	var s DaemonStatus
	if err := json.NewDecoder(rr.Body).Decode(&s); err != nil {
		t.Fatalf("failed to decode status: %v", err)
	}
	if s.ActiveNode.ID != "node-1" {
		t.Errorf("expected node-1, got %s", s.ActiveNode.ID)
	}

	// 2. Test /rotate
	reqRot := authorizedRequest("POST", "/rotate")
	rrRot := httptest.NewRecorder()
	handler.ServeHTTP(rrRot, reqRot)
	if rrRot.Code != http.StatusOK {
		t.Fatalf("expected 200 on /rotate, got %d", rrRot.Code)
	}

	// 3. Test /proxy.pac
	reqPac := httptest.NewRequest("GET", "/proxy.pac", nil)
	rrPac := httptest.NewRecorder()
	handler.ServeHTTP(rrPac, reqPac)
	if rrPac.Code != http.StatusOK || rrPac.Header().Get("Content-Type") != "application/x-ns-proxy-autoconfig" {
		t.Errorf("unexpected pac response: code=%d, type=%s", rrPac.Code, rrPac.Header().Get("Content-Type"))
	}
}

func TestDaemonRotateSkipsDeadNodes(t *testing.T) {
	d := NewDaemon([]DaemonNode{{ID: "live-1", Alive: true}, {ID: "dead", Alive: false}, {ID: "live-2", Alive: true}})
	if got := d.RotateNode(); got.ID != "live-2" {
		t.Fatalf("expected live-2, got %#v", got)
	}
}

func TestDaemonReadinessRequiresLiveNode(t *testing.T) {
	d := NewDaemon([]DaemonNode{{ID: "dead", Server: "127.0.0.1", Port: 1, Alive: false}})
	rr := httptest.NewRecorder()
	d.Handler().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/ready", nil))
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected unavailable readiness, got %d", rr.Code)
	}
}

func TestDaemonHealthCheckRotatesAwayFromFailedActiveNode(t *testing.T) {
	d := NewDaemon(
		[]DaemonNode{{ID: "active", Alive: true}, {ID: "standby", Alive: true}},
		WithCheckInterval(time.Millisecond),
	)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	d.StartHealthChecks(ctx, func(_ context.Context, node DaemonNode) (time.Duration, error) {
		if node.ID == "active" {
			return 0, errors.New("dial failed")
		}
		return time.Millisecond, nil
	})

	deadline := time.After(time.Second)
	for d.ActiveNode().ID != "standby" {
		select {
		case <-deadline:
			t.Fatalf("expected standby after health failure, got %#v", d.ActiveNode())
		case <-time.After(time.Millisecond):
		}
	}
}
