// Package geoip implements high-performance IP geolocation, ASN lookup, and reverse geographic inference.
// Source: https://www.iana.org/assignments/ipv4-address-space/ipv4-address-space.xhtml (IANA IPv4 address assignments)
// Source: https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2 (ISO 3166-1 alpha-2 country codes)
package geoip_test

import (
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/geoip"
)

func TestGeoIP_KnownPublicIPs(t *testing.T) {
	provider := geoip.NewGeoIPProvider(nil)

	// Cloudflare DNS 1.1.1.1
	res1, err := provider.LookupIP("1.1.1.1")
	if err != nil {
		t.Fatalf("lookup 1.1.1.1 failed: %v", err)
	}
	if res1.CountryCode != "US" && res1.CountryCode != "AU" {
		t.Errorf("expected US or AU for 1.1.1.1, got %s", res1.CountryCode)
	}
	if res1.ASN == 0 {
		t.Errorf("expected non-zero ASN for 1.1.1.1, got %d", res1.ASN)
	}

	// Google DNS 8.8.8.8
	res2, err := provider.LookupIP("8.8.8.8")
	if err != nil {
		t.Fatalf("lookup 8.8.8.8 failed: %v", err)
	}
	if res2.CountryCode != "US" {
		t.Errorf("expected US for 8.8.8.8, got %s", res2.CountryCode)
	}
	if res2.ASN != 15169 {
		t.Errorf("expected AS15169 for 8.8.8.8, got %d", res2.ASN)
	}
}

func TestGeoIP_PrivateAndLocalIPs(t *testing.T) {
	provider := geoip.NewGeoIPProvider(nil)

	tests := []string{"127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "::1"}
	for _, ip := range tests {
		res, err := provider.LookupIP(ip)
		if err != nil {
			t.Fatalf("lookup private IP %s failed: %v", ip, err)
		}
		if res.CountryCode != "LAN" {
			t.Errorf("expected LAN for %s, got %s", ip, res.CountryCode)
		}
		if !res.IsPrivate {
			t.Errorf("expected IsPrivate=true for %s", ip)
		}
	}
}

func TestGeoIP_InferCountryFromDomain(t *testing.T) {
	provider := geoip.NewGeoIPProvider(nil)

	tests := []struct {
		domain   string
		expected string
	}{
		{"vpn.server.de", "DE"},
		{"node1.ams.nl", "NL"},
		{"proxy.tokyo.jp", "JP"},
		{"gw.tehran.ir", "IR"},
		{"london.uk.co", "GB"},
		{"unknown-server.com", "XX"},
	}

	for _, tt := range tests {
		code := provider.InferCountryFromDomain(tt.domain)
		if code != tt.expected {
			t.Errorf("domain %s: expected country %s, got %s", tt.domain, tt.expected, code)
		}
	}
}
