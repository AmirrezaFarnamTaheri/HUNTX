// Package main provides a lightweight, resilient proxy management daemon.
//
// Authority:
//
//	Proxy Auto-Config (PAC) Specification: https://developer.mozilla.org/en-US/docs/Web/HTTP/Proxy_servers_and_tunneling/Proxy_Auto-Configuration_PAC_file
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

// HealthCheck evaluates one node and returns its observed latency.
type HealthCheck func(context.Context, DaemonNode) (time.Duration, error)

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

func (d *Daemon) pacDirective(node DaemonNode) (string, error) {
	address := net.JoinHostPort(node.Server, strconv.Itoa(node.Port))
	switch strings.ToLower(node.Protocol) {
	case "http", "https":
		return "PROXY " + address, nil
	case "socks5":
		return "SOCKS5 " + address, nil
	default:
		return "", fmt.Errorf("unsupported PAC protocol %q", node.Protocol)
	}
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
	for index, node := range d.nodes {
		if node.Alive {
			d.activeIdx = index
			break
		}
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
	for offset := 1; offset <= len(d.nodes); offset++ {
		idx := (d.activeIdx + offset) % len(d.nodes)
		if d.nodes[idx].Alive {
			d.activeIdx = idx
			d.failoverCount++
			return d.nodes[idx]
		}
	}
	return DaemonNode{ID: "none", Alive: false}
}

// StartHealthChecks continuously refreshes node health and automatically moves
// away from a failed active node. The goroutine ends with ctx.
func (d *Daemon) StartHealthChecks(ctx context.Context, check HealthCheck) {
	if check == nil {
		return
	}
	interval := d.checkInterval
	if interval <= 0 {
		interval = 30 * time.Second
	}

	run := func() {
		d.mu.RLock()
		nodes := append([]DaemonNode(nil), d.nodes...)
		d.mu.RUnlock()
		for index, node := range nodes {
			latency, err := check(ctx, node)
			d.mu.Lock()
			if index < len(d.nodes) && d.nodes[index].ID == node.ID {
				d.nodes[index].Alive = err == nil
				if err == nil {
					d.nodes[index].Latency = latency
				}
			}
			d.mu.Unlock()
		}
		if !d.ActiveNode().Alive {
			d.RotateNode()
		}
	}

	go func() {
		run()
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				run()
			}
		}
	}()
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

	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		if !d.ActiveNode().Alive {
			http.Error(w, "No live proxy node available", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

	mux.HandleFunc("/rotate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		token := os.Getenv("HUNTX_DAEMON_CONTROL_TOKEN")
		if token == "" || r.Header.Get("Authorization") != "Bearer "+token {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		newActive := d.RotateNode()
		if !newActive.Alive {
			http.Error(w, "No live proxy node available", http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status": "rotated",
			"active": newActive,
		})
	})

	mux.HandleFunc("/proxy.pac", func(w http.ResponseWriter, r *http.Request) {
		active := d.ActiveNode()
		if !active.Alive {
			http.Error(w, "No live proxy node available", http.StatusServiceUnavailable)
			return
		}
		directive, err := d.pacDirective(active)
		if err != nil {
			http.Error(w, err.Error(), http.StatusServiceUnavailable)
			return
		}
		pacScript := fmt.Sprintf(`function FindProxyForURL(url, host) {
    if (shExpMatch(host, "*.local") || isInNet(dnsResolve(host), "10.0.0.0", "255.0.0.0") || isInNet(dnsResolve(host), "192.168.0.0", "255.255.0.0")) {
        return "DIRECT";
    }
    return %s;
}`, strconv.Quote(directive))
		w.Header().Set("Content-Type", "application/x-ns-proxy-autoconfig")
		_, _ = w.Write([]byte(pacScript))
	})

	return mux
}
