// Package subfeed owns bounded public subscription retrieval.
// Python keeps durable HUNTX state, while this Go-only network boundary handles
// HTTP conditional requests, redirect prevention, and DNS/IP safety.
package subfeed

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const MaxBodyBytes = 5 * 1024 * 1024

var hostAllowlist = map[string]bool{
	"raw.githubusercontent.com": true,
	"sub.iampedi5.live":         true,
	"sub.whitedns.one":          true,
	"key.zarazaex.xyz":          true,
}

var unsafeNetworks = []netip.Prefix{
	netip.MustParsePrefix("0.0.0.0/8"),
	netip.MustParsePrefix("100.64.0.0/10"),
	netip.MustParsePrefix("192.0.0.0/24"),
	netip.MustParsePrefix("192.0.2.0/24"),
	netip.MustParsePrefix("198.18.0.0/15"),
	netip.MustParsePrefix("198.51.100.0/24"),
	netip.MustParsePrefix("203.0.113.0/24"),
	netip.MustParsePrefix("224.0.0.0/4"),
	netip.MustParsePrefix("240.0.0.0/4"),
	netip.MustParsePrefix("2001:db8::/32"),
	netip.MustParsePrefix("2001::/32"),
	netip.MustParsePrefix("fe80::/10"),
}

type Result struct {
	Status       string `json:"status"`
	ContentB64   string `json:"content_b64,omitempty"`
	ETag         string `json:"etag,omitempty"`
	LastModified string `json:"last_modified,omitempty"`
	Bytes        int    `json:"bytes"`
}

func ValidateURL(raw string) (*url.URL, error) {
	u, err := url.Parse(raw)
	if err != nil || u == nil || u.Scheme != "https" ||
		!hostAllowlist[strings.ToLower(u.Hostname())] ||
		u.User != nil || u.Fragment != "" || u.Path == "" ||
		(u.Port() != "" && u.Port() != "443") || u.Opaque != "" {
		return nil, errors.New("unapproved public HTTPS feed")
	}
	return u, nil
}

func PublicAddress(ip netip.Addr) bool {
	if !ip.IsValid() {
		return false
	}
	ip = ip.Unmap()
	if !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() ||
		ip.IsLinkLocalUnicast() || ip.IsMulticast() || ip.IsUnspecified() {
		return false
	}
	// IsGlobalUnicast does not exclude several special-purpose ranges.
	if ip.Is6() && !netip.MustParsePrefix("2000::/3").Contains(ip) {
		return false
	}
	for _, prefix := range unsafeNetworks {
		if prefix.Contains(ip) {
			return false
		}
	}
	return true
}

func sanitizedValidator(value string) string {
	value = strings.TrimSpace(value)
	if len(value) > 512 || strings.IndexFunc(value, func(c rune) bool { return c == 0 || c == 10 || c == 13 }) >= 0 {
		return ""
	}
	return value
}

func newClient(timeout time.Duration) *http.Client {
	dialer := &net.Dialer{Timeout: timeout, KeepAlive: 15 * time.Second}
	transport := &http.Transport{
		Proxy:               nil,
		ForceAttemptHTTP2:   true,
		MaxIdleConns:        3,
		MaxIdleConnsPerHost: 1,
		IdleConnTimeout:     10 * time.Second,
		TLSHandshakeTimeout: timeout,
		DisableCompression:  true,
		DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
			host, port, err := net.SplitHostPort(address)
			if err != nil || !hostAllowlist[strings.ToLower(host)] {
				return nil, errors.New("dial outside public source allowlist")
			}
			number, err := strconv.Atoi(port)
			if err != nil || number != 443 {
				return nil, errors.New("unexpected remote feed port")
			}
			ips, err := net.DefaultResolver.LookupNetIP(ctx, "ip", host)
			if err != nil {
				return nil, fmt.Errorf("feed DNS lookup failed: %w", err)
			}
			var dialErr error
			for _, ip := range ips {
				if !PublicAddress(ip) {
					continue
				}
				c, err := dialer.DialContext(ctx, "tcp", net.JoinHostPort(ip.String(), port))
				if err == nil {
					return c, nil
				}
				dialErr = err
			}
			if dialErr != nil {
				return nil, fmt.Errorf("public feed endpoints unavailable: %w", dialErr)
			}
			return nil, errors.New("feed DNS returned no permitted public IPs")
		},
	}
	return &http.Client{
		Timeout:   timeout,
		Transport: transport,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

// Fetch never logs the credential-bearing body or query string. Callers may
// send conditional validators only when a verified cached body exists.
func Fetch(ctx context.Context, rawURL, etag, lastModified string, timeout time.Duration) (Result, error) {
	u, err := ValidateURL(rawURL)
	if err != nil {
		return Result{}, err
	}
	if timeout < time.Second || timeout > 40*time.Second {
		return Result{}, errors.New("feed timeout is outside 1-40 seconds")
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return Result{}, errors.New("cannot construct feed HTTP request")
	}
	req.Header.Set("User-Agent", "HUNTX-source-investigation/1")
	req.Header.Set("Accept", "text/plain, application/json, application/yaml, */*;q=0.4")
	req.Header.Set("Accept-Encoding", "identity")
	if etag = sanitizedValidator(etag); etag != "" {
		req.Header.Set("If-None-Match", etag)
	}
	if lastModified = sanitizedValidator(lastModified); lastModified != "" {
		req.Header.Set("If-Modified-Since", lastModified)
	}
	client := newClient(timeout)
	res, err := client.Do(req)
	if err != nil {
		return Result{}, fmt.Errorf("upstream fetch failed: %w", err)
	}
	defer res.Body.Close()

	result := Result{
		ETag:         sanitizedValidator(res.Header.Get("ETag")),
		LastModified: sanitizedValidator(res.Header.Get("Last-Modified")),
	}
	if res.StatusCode == http.StatusNotModified {
		result.Status = "not_modified"
		return result, nil
	}
	if res.StatusCode != http.StatusOK {
		return Result{}, fmt.Errorf("upstream returned HTTP %d", res.StatusCode)
	}
	if res.ContentLength > MaxBodyBytes {
		return Result{}, errors.New("upstream feed exceeds maximum bytes")
	}
	body, err := io.ReadAll(io.LimitReader(res.Body, MaxBodyBytes+1))
	if err != nil {
		return Result{}, fmt.Errorf("cannot read feed response: %w", err)
	}
	if len(body) == 0 || len(body) > MaxBodyBytes {
		return Result{}, errors.New("upstream feed is empty or too large")
	}
	result.Status = "ok"
	result.ContentB64 = base64.StdEncoding.EncodeToString(body)
	result.Bytes = len(body)
	return result, nil
}
