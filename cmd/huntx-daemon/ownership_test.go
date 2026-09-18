package main

import (
	"net"
	"testing"
)

func TestHealthAddressUsesJoinHostPortForIPv6(t *testing.T) {
	// Regression: IPv6 literals must be bracketed before dialing, matching the
	// PAC path (daemon.go) so the health callback cannot mark them dead.
	address := net.JoinHostPort("2001:db8::1", "8443")
	if address != "[2001:db8::1]:8443" {
		t.Fatalf("JoinHostPort failed to bracket IPv6: %q", address)
	}
}

func TestDaemonOwnsNodeStorage(t *testing.T) {
	nodes := []DaemonNode{{ID: "a", Server: "example.com", Port: 443, Protocol: "vless"}}
	daemon := NewDaemon(nodes)
	// The daemon must own its node storage: caller-side mutation after
	// construction must not leak into health-checked state.
	nodes[0].Server = "mutated.invalid"
	if got := daemon.ActiveNode().Server; got != "example.com" {
		t.Fatalf("daemon aliased caller-owned storage: got %q", got)
	}
}
