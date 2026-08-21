package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestDaemonInitializationAndStatus(t *testing.T) {
	nodes := []DaemonNode{
		{ID: "node-1", Protocol: "vless", Server: "1.1.1.1", Port: 443, Latency: 35 * time.Millisecond, Alive: true},
		{ID: "node-2", Protocol: "hysteria2", Server: "8.8.8.8", Port: 8443, Latency: 60 * time.Millisecond, Alive: true},
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
		{ID: "node-1", Protocol: "vless", Server: "1.1.1.1", Port: 443, Latency: 35 * time.Millisecond, Alive: true},
		{ID: "node-2", Protocol: "hysteria2", Server: "8.8.8.8", Port: 8443, Latency: 60 * time.Millisecond, Alive: true},
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
	nodes := []DaemonNode{
		{ID: "node-1", Protocol: "vless", Server: "1.1.1.1", Port: 443, Latency: 35 * time.Millisecond, Alive: true},
		{ID: "node-2", Protocol: "hysteria2", Server: "8.8.8.8", Port: 8443, Latency: 60 * time.Millisecond, Alive: true},
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
	reqRot := httptest.NewRequest("POST", "/rotate", nil)
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
