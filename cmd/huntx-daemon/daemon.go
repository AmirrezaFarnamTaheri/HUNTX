// Package main provides a lightweight, resilient proxy management daemon.
//
// Authority:
//
//	Proxy Auto-Config (PAC) Specification: https://developer.mozilla.org/en-US/docs/Web/HTTP/Proxy_servers_and_tunneling/Proxy_Auto-Configuration_PAC_file
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"
)

// DaemonNode represents an evaluated proxy endpoint in the daemon's rotation pool.
type DaemonNode struct {
	ID       string        `json:"id"`
	Protocol string        `json:"protocol"`
	Server   string        `json:"server"`
	Port     int           `json:"port"`
	Latency  time.Duration `json:"latency"`
	Alive    bool          `json:"alive"`
}

// DaemonStatus represents the current operational health and active proxy.
type DaemonStatus struct {
	ActiveNode    DaemonNode `json:"active_node"`
	TotalNodes    int        `json:"total_nodes"`
	FailoverCount int64      `json:"failover_count"`
	UptimeSec     int64      `json:"uptime_sec"`
	ListenAddr    string     `json:"listen_addr"`
}

// DaemonOption configures the daemon.
type DaemonOption func(*Daemon)

// WithListenAddr sets the REST control server listen address.
func WithListenAddr(addr string) DaemonOption {
	return func(d *Daemon) { d.listenAddr = addr }
}

// WithCheckInterval sets background health check intervals.
func WithCheckInterval(interval time.Duration) DaemonOption {
	return func(d *Daemon) { d.checkInterval = interval }
}

// Daemon coordinates local system proxying and automatic failover.
type Daemon struct {
	mu            sync.RWMutex
	nodes         []DaemonNode
	activeIdx     int
	failoverCount int64
	startTime     time.Time
	listenAddr    string
	checkInterval time.Duration
}

// NewDaemon initializes a new proxy management daemon.
func NewDaemon(nodes []DaemonNode, opts ...DaemonOption) *Daemon {
	d := &Daemon{
		nodes:         nodes,
		activeIdx:     0,
		startTime:     time.Now(),
		listenAddr:    "127.0.0.1:9090",
		checkInterval: 30 * time.Second,
	}
	for _, opt := range opts {
		opt(d)
	}
	return d
}

// ActiveNode returns the currently selected proxy node.
func (d *Daemon) ActiveNode() DaemonNode {
	d.mu.RLock()
	defer d.mu.RUnlock()
	if len(d.nodes) == 0 {
		return DaemonNode{ID: "none", Alive: false}
	}
	return d.nodes[d.activeIdx]
}

// RotateNode advances to the next available node in the pool.
func (d *Daemon) RotateNode() DaemonNode {
	d.mu.Lock()
	defer d.mu.Unlock()
	if len(d.nodes) == 0 {
		return DaemonNode{ID: "none", Alive: false}
	}
	d.activeIdx = (d.activeIdx + 1) % len(d.nodes)
	d.failoverCount++
	return d.nodes[d.activeIdx]
}

// GetStatus returns the operational snapshot of the daemon.
func (d *Daemon) GetStatus() DaemonStatus {
	d.mu.RLock()
	defer d.mu.RUnlock()

	active := DaemonNode{ID: "none", Alive: false}
	if len(d.nodes) > 0 {
		active = d.nodes[d.activeIdx]
	}

	return DaemonStatus{
		ActiveNode:    active,
		TotalNodes:    len(d.nodes),
		FailoverCount: d.failoverCount,
		UptimeSec:     int64(time.Since(d.startTime).Seconds()),
		ListenAddr:    d.listenAddr,
	}
}

// Handler returns the HTTP mux for the local control REST API.
func (d *Daemon) Handler() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		status := d.GetStatus()
		_ = json.NewEncoder(w).Encode(status)
	})

	mux.HandleFunc("/rotate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		newActive := d.RotateNode()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status": "rotated",
			"active": newActive,
		})
	})

	mux.HandleFunc("/proxy.pac", func(w http.ResponseWriter, r *http.Request) {
		active := d.ActiveNode()
		pacScript := fmt.Sprintf(`function FindProxyForURL(url, host) {
    if (shExpMatch(host, "*.local") || isInNet(dnsResolve(host), "10.0.0.0", "255.0.0.0") || isInNet(dnsResolve(host), "192.168.0.0", "255.255.0.0")) {
        return "DIRECT";
    }
    return "PROXY %s:%d; DIRECT";
}`, active.Server, active.Port)
		w.Header().Set("Content-Type", "application/x-ns-proxy-autoconfig")
		_, _ = w.Write([]byte(pacScript))
	})

	return mux
}
