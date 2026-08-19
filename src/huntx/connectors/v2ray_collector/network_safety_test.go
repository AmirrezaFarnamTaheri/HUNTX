package main

import (
	"encoding/base64"
	"net"
	"testing"
	"time"
)

func TestIsPublicProbeIPRejectsNonPublicRanges(t *testing.T) {
	rejected := []string{
		"127.0.0.1",
		"10.0.0.1",
		"100.64.0.1",
		"169.254.1.1",
		"172.16.0.1",
		"192.168.1.1",
		"192.0.2.1",
		"198.51.100.1",
		"203.0.113.1",
		"::1",
		"fc00::1",
		"fe80::1",
		"2001:db8::1",
	}
	for _, raw := range rejected {
		if isPublicProbeIP(net.ParseIP(raw)) {
			t.Fatalf("expected %s to be rejected as a probe target", raw)
		}
	}
}

func TestIsPublicProbeIPAllowsRepresentativePublicAddresses(t *testing.T) {
	accepted := []string{
		"1.1.1.1",
		"8.8.8.8",
		"2606:4700:4700::1111",
	}
	for _, raw := range accepted {
		if !isPublicProbeIP(net.ParseIP(raw)) {
			t.Fatalf("expected %s to be accepted as a public probe target", raw)
		}
	}
}

func TestResolveDomainToIPsRejectsLiteralPrivateAddress(t *testing.T) {
	ips, err := resolveDomainToIPs("127.0.0.1")
	if err == nil {
		t.Fatalf("expected private literal address to be rejected, got %v", ips)
	}
}

func TestCheckPortRejectsPrivateAddressBeforeDial(t *testing.T) {
	if checkPort("127.0.0.1", 80, time.Second) {
		t.Fatal("private loopback endpoint must never be probed")
	}
	if checkPort("10.0.0.1", 443, time.Second) {
		t.Fatal("private RFC1918 endpoint must never be probed")
	}
}

func TestExtractAddressPortSupportsCommonVMessStringPort(t *testing.T) {
	payload := `{"add":"example.com","port":"443"}`
	encoded := base64.RawStdEncoding.EncodeToString([]byte(payload))

	host, port, err := extractAddressPort("vmess://" + encoded)
	if err != nil {
		t.Fatalf("extractAddressPort failed: %v", err)
	}
	if host != "example.com" || port != 443 {
		t.Fatalf("unexpected VMess endpoint %s:%d", host, port)
	}
}

func TestExtractAddressPortRejectsInvalidVMessPort(t *testing.T) {
	payload := `{"add":"example.com","port":"70000"}`
	encoded := base64.StdEncoding.EncodeToString([]byte(payload))

	if _, _, err := extractAddressPort("vmess://" + encoded); err == nil {
		t.Fatal("expected out-of-range VMess port to be rejected")
	}
}
