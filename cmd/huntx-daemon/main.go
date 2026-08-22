package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

func supportedProtocol(protocol string) bool {
	switch protocol {
	case "http", "https", "socks5":
		return true
	default:
		return false
	}
}

func validProxyHost(host string) bool {
	if net.ParseIP(host) != nil {
		return true
	}
	if len(host) == 0 || len(host) > 253 {
		return false
	}
	for _, label := range strings.Split(host, ".") {
		if len(label) == 0 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, char := range label {
			if !(char == '-' || char >= 'a' && char <= 'z' || char >= 'A' && char <= 'Z' || char >= '0' && char <= '9') {
				return false
			}
		}
	}
	return true
}

func loadNodes() ([]DaemonNode, error) {
	raw := os.Getenv("HUNTX_DAEMON_NODES_JSON")
	if raw == "" {
		return nil, fmt.Errorf("HUNTX_DAEMON_NODES_JSON is required; refusing to serve a demo proxy")
	}
	var nodes []DaemonNode
	if err := json.Unmarshal([]byte(raw), &nodes); err != nil {
		return nil, fmt.Errorf("parse HUNTX_DAEMON_NODES_JSON: %w", err)
	}
	if len(nodes) == 0 {
		return nil, fmt.Errorf("HUNTX_DAEMON_NODES_JSON must contain at least one node")
	}
	for _, node := range nodes {
		node.Protocol = strings.ToLower(strings.TrimSpace(node.Protocol))
		if node.ID == "" || !validProxyHost(node.Server) || node.Port < 1 || node.Port > 65535 || !supportedProtocol(node.Protocol) {
			return nil, fmt.Errorf("invalid daemon node %q", node.ID)
		}
	}
	return nodes, nil
}

func main() {
	nodes, err := loadNodes()
	if err != nil {
		fmt.Fprintf(os.Stderr, "[HUNTX-DAEMON] configuration error: %v\n", err)
		os.Exit(2)
	}
	listenAddr := os.Getenv("LISTEN_ADDR")
	if listenAddr == "" {
		listenAddr = "127.0.0.1:9090"
	}
	daemon := NewDaemon(nodes, WithListenAddr(listenAddr))
	healthCtx, cancelHealthChecks := context.WithCancel(context.Background())
	defer cancelHealthChecks()
	daemon.StartHealthChecks(healthCtx, func(ctx context.Context, node DaemonNode) (time.Duration, error) {
		start := time.Now()
		connection, err := (&net.Dialer{Timeout: 5 * time.Second}).DialContext(
			ctx, "tcp", fmt.Sprintf("%s:%d", node.Server, node.Port),
		)
		if err != nil {
			return 0, err
		}
		_ = connection.Close()
		return time.Since(start), nil
	})
	server := &http.Server{
		Addr:              listenAddr,
		Handler:           daemon.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	go func() {
		fmt.Printf("[HUNTX-DAEMON] Control API active on http://%s\n", listenAddr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			fmt.Fprintf(os.Stderr, "server error: %v\n", err)
		}
	}()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	fmt.Println("[HUNTX-DAEMON] Shutting down gracefully...")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		fmt.Fprintf(os.Stderr, "shutdown error: %v\n", err)
	}
}
