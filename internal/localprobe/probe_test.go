package localprobe

import (
	"context"
	"crypto/x509"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestRejectNonLoopbackAndCredentialedProxy(t *testing.T) {
	cases := []string{
		"http://example.com:7890", "http://localhost.evil:7890", "http://10.0.0.2:7890",
		"http://user:pass@127.0.0.1:7890", "http://127.0.0.1:7890/extra",
		"http://127.0.0.1:7890?token=abc", "file:///tmp/proxy", "http://127.0.0.1:0",
	}
	for _, raw := range cases {
		if err := ValidateLocalProxy(raw); err == nil {
			t.Errorf("expected rejection for %q", raw)
		}
	}
	for _, raw := range []string{"http://127.0.0.1:7890", "socks5://[::1]:1080", "socks5h://localhost:1080"} {
		if err := ValidateLocalProxy(raw); err != nil {
			t.Errorf("expected safe local proxy %q: %v", raw, err)
		}
	}
}

func TestRealHTTPSRequestMustTravelThroughSelectedLocalClient(t *testing.T) {
	var targetCalls atomic.Int32
	target := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		targetCalls.Add(1)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer target.Close()
	roots := x509.NewCertPool()
	roots.AddCert(target.Certificate())

	var proxyConnects atomic.Int32
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		proxyConnects.Add(1)
		if r.Method != http.MethodConnect {
			http.Error(w, "CONNECT required", http.StatusMethodNotAllowed)
			return
		}
		upstream, err := net.DialTimeout("tcp", target.Listener.Addr().String(), time.Second)
		if err != nil {
			http.Error(w, "upstream unavailable", http.StatusBadGateway)
			return
		}
		client, _, err := w.(http.Hijacker).Hijack()
		if err != nil {
			upstream.Close()
			return
		}
		_, _ = io.WriteString(client, "HTTP/1.1 200 Connection Established\r\n\r\n")
		go func() { _, _ = io.Copy(upstream, client); upstream.Close() }()
		go func() { _, _ = io.Copy(client, upstream); client.Close() }()
	}))
	defer proxy.Close()

	result := check(context.Background(), proxy.URL, target.URL, 3*time.Second, roots)
	if !result.ClientPathUsable || result.NodeAttributed || result.OriginalRecovered || !result.TargetTLSVerified {
		t.Fatalf("unexpected evidence classification: %+v", result)
	}
	if result.HTTPStatus != 204 || result.ErrorClass != "" {
		t.Fatalf("unexpected HTTP result: %+v", result)
	}
	if proxyConnects.Load() != 1 || targetCalls.Load() != 1 {
		t.Fatalf("request did not traverse local proxy: connects=%d target=%d", proxyConnects.Load(), targetCalls.Load())
	}
}

func TestProxyFailureDoesNotFallBackToDirectTarget(t *testing.T) {
	var directCalls atomic.Int32
	target := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		directCalls.Add(1)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer target.Close()
	roots := x509.NewCertPool()
	roots.AddCert(target.Certificate())
	result := check(context.Background(), "http://127.0.0.1:1", target.URL, time.Second, roots)
	if result.ClientPathUsable || result.OriginalRecovered || result.NodeAttributed {
		t.Fatalf("proxy failure was incorrectly promoted to success: %+v", result)
	}
	if directCalls.Load() != 0 {
		t.Fatalf("direct fallback occurred: %d", directCalls.Load())
	}
	if result.ErrorClass == "" || strings.Contains(result.ErrorClass, "127.0.0.1") {
		t.Fatalf("error class should be generic and privacy-safe: %+v", result)
	}
}

func TestBadTargetTLSIsNeverMarkedUsable(t *testing.T) {
	target := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	defer target.Close()
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstream, err := net.DialTimeout("tcp", target.Listener.Addr().String(), time.Second)
		if err != nil {
			http.Error(w, "unavailable", http.StatusBadGateway)
			return
		}
		client, _, err := w.(http.Hijacker).Hijack()
		if err != nil {
			upstream.Close()
			return
		}
		_, _ = io.WriteString(client, "HTTP/1.1 200 Connection Established\r\n\r\n")
		go func() { _, _ = io.Copy(upstream, client); upstream.Close() }()
		go func() { _, _ = io.Copy(client, upstream); client.Close() }()
	}))
	defer proxy.Close()
	result := check(context.Background(), proxy.URL, target.URL, 3*time.Second, nil)
	if result.ClientPathUsable || result.TargetTLSVerified || result.OriginalRecovered {
		t.Fatalf("untrusted certificate was treated as recovered: %+v", result)
	}
	if result.ErrorClass != "tls-validation" {
		t.Fatalf("expected TLS validation error class, got %+v", result)
	}
}

func TestInvalidProbeBudgetRejectedBeforeNetworking(t *testing.T) {
	for _, budget := range []time.Duration{0, -time.Second, 16 * time.Second} {
		result := check(context.Background(), "http://127.0.0.1:7890", "https://example.com", budget, nil)
		if result.ErrorClass != "invalid-budget" || result.ClientPathUsable {
			t.Errorf("invalid budget %s was not rejected: %+v", budget, result)
		}
	}
}

func TestLocalhostIsPinnedToNumericLoopbackBeforeDial(t *testing.T) {
	u, err := parseLocalProxy("http://localhost:7890")
	if err != nil {
		t.Fatal(err)
	}
	if u.Host != "127.0.0.1:7890" {
		t.Fatalf("localhost must not rely on external DNS: %q", u.Host)
	}
}
