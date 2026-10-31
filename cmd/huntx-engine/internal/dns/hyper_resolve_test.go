// Package dns implements concurrent hybrid DNS resolution with DoH racing and dual-layer caching.
// Source: https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/ (Cloudflare DoH JSON API)
// Source: https://developers.google.com/speed/public-dns/docs/doh/json (Google DoH JSON API)
package dns_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/dns"
)

func TestHyperResolve_DirectIP(t *testing.T) {
	resolver := dns.NewHyperResolver(nil)

	ip, err := resolver.Resolve(context.Background(), "1.1.1.1")
	if err != nil {
		t.Fatalf("expected direct IP return without error, got %v", err)
	}
	if ip != "1.1.1.1" {
		t.Errorf("expected 1.1.1.1, got %s", ip)
	}

	ipv6, err := resolver.Resolve(context.Background(), "2606:4700:4700::1111")
	if err != nil {
		t.Fatalf("expected direct IPv6 return without error, got %v", err)
	}
	if ipv6 != "2606:4700:4700::1111" {
		t.Errorf("expected 2606:4700:4700::1111, got %s", ipv6)
	}
}

func TestHyperResolve_MemoryCache(t *testing.T) {
	resolver := dns.NewHyperResolver(nil)

	// Inject a pre-cached entry
	resolver.SetCache("huntx.internal.test", "10.0.0.1", 5*time.Minute)

	ip, err := resolver.Resolve(context.Background(), "huntx.internal.test")
	if err != nil {
		t.Fatalf("expected cache hit, got %v", err)
	}
	if ip != "10.0.0.1" {
		t.Errorf("expected 10.0.0.1 from cache, got %s", ip)
	}
}

func TestHyperResolve_MockDoHRacing(t *testing.T) {
	// Create mock DoH server responding with standard DNS JSON format
	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		name := r.URL.Query().Get("name")
		if name == "mock.huntx.domain" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"Status":0,"Answer":[{"name":"mock.huntx.domain","type":1,"TTL":300,"data":"192.0.2.1"}]}`))
			return
		}
		http.NotFound(w, r)
	}))
	defer mockServer.Close()

	resolver := dns.NewHyperResolver(&dns.Config{
		DoHServers: []string{mockServer.URL + "?name=%s&type=A"},
		Timeout:    2 * time.Second,
	})

	ip, err := resolver.Resolve(context.Background(), "mock.huntx.domain")
	if err != nil {
		t.Fatalf("expected DoH resolution, got error: %v", err)
	}
	if ip != "192.0.2.1" {
		t.Errorf("expected 192.0.2.1, got %s", ip)
	}

	// Verify it is now cached in memory
	cachedIP, found := resolver.GetCached("mock.huntx.domain")
	if !found || cachedIP != "192.0.2.1" {
		t.Errorf("expected cached IP 192.0.2.1, got %s (found: %v)", cachedIP, found)
	}
}

func TestHyperResolve_InvalidDomain(t *testing.T) {
	resolver := dns.NewHyperResolver(&dns.Config{
		Timeout: 500 * time.Millisecond,
	})

	_, err := resolver.Resolve(context.Background(), "invalid.unresolvable.huntx-nonexistent-domain-12345.xyz")
	if err == nil {
		t.Error("expected error resolving non-existent domain, got nil")
	}
}


func TestDoHRejectsNXDomainSpoofedOrWrongFamilyAnswers(t *testing.T) {
	cases := []struct{ name, payload string }{
		{"nxdomain_with_address", `{"Status":3,"Answer":[{"name":"hardened.invalid.","type":1,"TTL":300,"data":"9.9.9.9"}]}`},
		{"unrelated_owner", `{"Status":0,"Answer":[{"name":"attacker.invalid.","type":1,"TTL":300,"data":"9.9.9.9"}]}`},
		{"ipv6_address_disguised_as_A", `{"Status":0,"Answer":[{"name":"hardened.invalid.","type":1,"TTL":300,"data":"2606:4700:4700::1111"}]}`},
		{"ipv4_address_disguised_as_AAAA", `{"Status":0,"Answer":[{"name":"hardened.invalid.","type":28,"TTL":300,"data":"9.9.9.9"}]}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("Content-Type", "application/dns-json")
				_, _ = w.Write([]byte(tc.payload))
			}))
			defer server.Close()
			resolver := dns.NewHyperResolver(&dns.Config{
				DoHServers: []string{server.URL + "?name=%s&type=A"},
				Timeout:    500 * time.Millisecond,
			})
			_, err := resolver.Resolve(context.Background(), "hardened.invalid")
			if err == nil {
				t.Fatal("untrusted DoH record was accepted as a resolved address")
			}
			if ip, ok := resolver.GetCached("hardened.invalid"); ok {
				t.Errorf("untrusted response poisoned cache with %s", ip)
			}
		})
	}
}

func TestDoHRejectsQueryParameterInjectionInHostname(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"Status":0,"Answer":[{"name":"hardened.invalid","type":1,"TTL":300,"data":"9.9.9.9"}]}`))
	}))
	defer server.Close()
	resolver := dns.NewHyperResolver(&dns.Config{
		DoHServers: []string{server.URL + "?name=%s&type=A"},
		Timeout:    500 * time.Millisecond,
	})
	if _, err := resolver.Resolve(context.Background(), "hardened.invalid&type=AAAA"); err == nil {
		t.Fatal("DNS query manipulation was accepted")
	}
}

func TestDoHAcceptsOwnerBoundValidCNAMEAnswer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"Status":0,"Answer":[{"name":"alias.invalid.","type":5,"TTL":60,"data":"edge.invalid."},{"name":"edge.invalid.","type":1,"TTL":120,"data":"9.9.9.9"}]}`))
	}))
	defer server.Close()
	resolver := dns.NewHyperResolver(&dns.Config{
		DoHServers: []string{server.URL + "?name=%s&type=A"},
		Timeout:    500 * time.Millisecond,
	})
	got, err := resolver.Resolve(context.Background(), "alias.invalid")
	if err != nil || got != "9.9.9.9" {
		t.Fatalf("valid CNAME chain rejected: ip=%q err=%v", got, err)
	}
}
