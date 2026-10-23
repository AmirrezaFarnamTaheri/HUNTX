// Package localprobe checks HTTPS traffic through an explicitly selected local
// HTTP or SOCKS5 proxy client. It never claims to identify the remote node.
package localprobe

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// DefaultTarget is a small, fixed HTTPS request. It is not a universal proxy
// health oracle: an unavailable test target must not condemn the remote node.
const DefaultTarget = "https://www.gstatic.com/generate_204"

// Result is intentionally credential-free and does not attest the selected node.
type Result struct {
	Evidence          string `json:"evidence"`
	ClientPathUsable  bool   `json:"client_path_usable"`
	NodeAttributed    bool   `json:"node_attributed"`
	OriginalRecovered bool   `json:"original_recovered"`
	TargetTLSVerified bool   `json:"target_tls_verified"`
	HTTPStatus        int    `json:"http_status,omitempty"`
	LatencyMS         int64  `json:"latency_ms,omitempty"`
	ErrorClass        string `json:"error_class,omitempty"`
}

// ValidateLocalProxy rejects non-loopback destinations, credentials, paths and
// query parameters. This command never accepts remote controllers or secrets.
func ValidateLocalProxy(raw string) error {
	_, err := parseLocalProxy(raw)
	return err
}

func parseLocalProxy(raw string) (*url.URL, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return nil, errors.New("invalid local proxy address")
	}
	switch strings.ToLower(u.Scheme) {
	case "http", "socks5", "socks5h":
	default:
		return nil, errors.New("unsupported local proxy scheme")
	}
	if u.User != nil || u.RawQuery != "" || u.Fragment != "" || u.Path != "" || u.Opaque != "" {
		return nil, errors.New("local proxy must not contain credentials, paths or query parameters")
	}
	host := u.Hostname()
	ip := net.ParseIP(host)
	if !(strings.EqualFold(host, "localhost") || (ip != nil && ip.IsLoopback())) {
		return nil, errors.New("local proxy must use a loopback address")
	}
	port, err := strconv.Atoi(u.Port())
	if err != nil || port < 1 || port > 65535 {
		return nil, errors.New("local proxy port must be between 1 and 65535")
	}
	if strings.EqualFold(host, "localhost") {
		// Pin the proxy to numeric loopback so an unexpected hosts/DNS entry
		// cannot redirect the diagnostic connection to a remote controller.
		u.Host = net.JoinHostPort("127.0.0.1", u.Port())
	}
	return u, nil
}

// Check tests the local client path, not the identity or health of an individual
// VLESS, VMess, Trojan, or Shadowsocks node. No direct fallback is permitted.
func Check(ctx context.Context, proxyAddress string, timeout time.Duration) Result {
	return check(ctx, proxyAddress, DefaultTarget, timeout, nil)
}

func check(ctx context.Context, proxyAddress, target string, timeout time.Duration, roots *x509.CertPool) Result {
	result := Result{Evidence: "client-https-path"}
	if timeout < time.Second || timeout > 15*time.Second {
		result.ErrorClass = "invalid-budget"
		return result
	}
	proxyURL, err := parseLocalProxy(proxyAddress)
	if err != nil {
		result.ErrorClass = "invalid-proxy"
		return result
	}
	targetURL, err := url.Parse(target)
	if err != nil || targetURL.Scheme != "https" || targetURL.Hostname() == "" || targetURL.User != nil {
		result.ErrorClass = "invalid-target"
		return result
	}
	transport := &http.Transport{
		Proxy:                 http.ProxyURL(proxyURL),
		DialContext:           (&net.Dialer{Timeout: timeout}).DialContext,
		TLSClientConfig:       &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12},
		TLSHandshakeTimeout:   timeout,
		ResponseHeaderTimeout: timeout,
		DisableKeepAlives:     true,
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{
		Timeout:       timeout,
		Transport:     transport,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}
	if ctx == nil {
		ctx = context.Background()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		result.ErrorClass = "invalid-target"
		return result
	}
	req.Header.Set("User-Agent", "HUNTX-local-probe/1")
	start := time.Now()
	response, err := client.Do(req)
	result.LatencyMS = time.Since(start).Milliseconds()
	if err != nil {
		result.ErrorClass = classifyError(err)
		return result
	}
	defer response.Body.Close()
	result.HTTPStatus = response.StatusCode
	result.TargetTLSVerified = response.TLS != nil && response.TLS.HandshakeComplete
	if !result.TargetTLSVerified {
		result.ErrorClass = "tls-not-established"
	} else if response.StatusCode < 200 || response.StatusCode >= 300 {
		result.ErrorClass = "target-http"
	} else {
		result.ClientPathUsable = true
	}
	return result
}

func classifyError(err error) string {
	var unknown x509.UnknownAuthorityError
	var invalid x509.CertificateInvalidError
	var hostname x509.HostnameError
	if errors.As(err, &unknown) || errors.As(err, &invalid) || errors.As(err, &hostname) {
		return "tls-validation"
	}
	var timeout net.Error
	if errors.Is(err, context.DeadlineExceeded) || (errors.As(err, &timeout) && timeout.Timeout()) {
		return "timeout"
	}
	return "client-path-error"
}
