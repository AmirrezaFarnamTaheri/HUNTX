package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestE2EDaemonLifecycleAndLivePACServing(t *testing.T) {
	t.Setenv("HUNTX_DAEMON_CONTROL_TOKEN", "test-control-token")
	// 1. Ingest initial evaluated proxy nodes
	initialNodes := []DaemonNode{
		{ID: "ir-relay-01", Protocol: "vless", Server: "185.10.10.1", Port: 443, Latency: 22 * time.Millisecond, Alive: true},
		{ID: "de-exit-02", Protocol: "hysteria2", Server: "95.216.1.1", Port: 8443, Latency: 65 * time.Millisecond, Alive: true},
		{ID: "us-exit-03", Protocol: "trojan", Server: "104.20.0.1", Port: 443, Latency: 120 * time.Millisecond, Alive: true},
	}

	daemon := NewDaemon(initialNodes, WithListenAddr("127.0.0.1:0"), WithCheckInterval(50*time.Millisecond))
	handler := daemon.Handler()

	// 2. Validate initial status & active proxy
	reqStatus := httptest.NewRequest(http.MethodGet, "/status", nil)
	recStatus := httptest.NewRecorder()
	handler.ServeHTTP(recStatus, reqStatus)

	if recStatus.Code != http.StatusOK {
		t.Fatalf("expected 200 on /status, got %d", recStatus.Code)
	}

	var status DaemonStatus
	if err := json.NewDecoder(recStatus.Body).Decode(&status); err != nil {
		t.Fatalf("failed to decode daemon status: %v", err)
	}
	if status.ActiveNode.ID != "ir-relay-01" {
		t.Errorf("expected active node ir-relay-01, got %s", status.ActiveNode.ID)
	}
	if status.TotalNodes != 3 {
		t.Errorf("expected 3 total nodes, got %d", status.TotalNodes)
	}

	// 3. Validate PAC generation for initial node
	reqPac1 := httptest.NewRequest(http.MethodGet, "/proxy.pac", nil)
	recPac1 := httptest.NewRecorder()
	handler.ServeHTTP(recPac1, reqPac1)

	pacBody1 := recPac1.Body.String()
	if !strings.Contains(pacBody1, "PROXY 185.10.10.1:443") {
		t.Errorf("expected PAC to point to 185.10.10.1:443, got: %s", pacBody1)
	}

	// 4. Trigger node rotation / failover
	reqRotate := authorizedRequest(http.MethodPost, "/rotate")
	recRotate := httptest.NewRecorder()
	handler.ServeHTTP(recRotate, reqRotate)

	if recRotate.Code != http.StatusOK {
		t.Fatalf("expected 200 on /rotate, got %d", recRotate.Code)
	}

	// 5. Verify PAC has dynamically updated to de-exit-02
	reqPac2 := httptest.NewRequest(http.MethodGet, "/proxy.pac", nil)
	recPac2 := httptest.NewRecorder()
	handler.ServeHTTP(recPac2, reqPac2)

	pacBody2 := recPac2.Body.String()
	if !strings.Contains(pacBody2, "PROXY 95.216.1.1:8443") {
		t.Errorf("expected PAC to point to 95.216.1.1:8443 after rotation, got: %s", pacBody2)
	}

	// 6. Verify failover counter
	statusAfter := daemon.GetStatus()
	if statusAfter.FailoverCount != 1 {
		t.Errorf("expected failover count 1, got %d", statusAfter.FailoverCount)
	}
}
