// Package dns implements concurrent hybrid DNS resolution with DoH racing and dual-layer caching.
// Source: https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/ (Cloudflare DoH JSON API)
// Source: https://developers.google.com/speed/public-dns/docs/doh/json (Google DoH JSON API)
package dns

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// DefaultDoHServers provides high-availability DoH endpoints for DNS racing.
var DefaultDoHServers = []string{
	"https://cloudflare-dns.com/dns-query?name=%s&type=A",
	"https://cloudflare-dns.com/dns-query?name=%s&type=AAAA",
	"https://dns.google/resolve?name=%s&type=A",
	"https://dns.google/resolve?name=%s&type=AAAA",
}

// Config specifies customization options for the HyperResolver.
type Config struct {
	DoHServers []string
	Timeout    time.Duration
	DefaultTTL time.Duration
	HTTPClient *http.Client
}

// CacheEntry represents an in-memory cached DNS record.
type CacheEntry struct {
	IP     string
	Expiry time.Time
}

// HyperResolver manages concurrent DNS resolution across native UDP and DoH servers.
type HyperResolver struct {
	config     Config
	cache      sync.Map // map[string]CacheEntry
	httpClient *http.Client
}

// dohResponse represents the standard RFC-8427 JSON DNS response.
type dohResponse struct {
	Status int `json:"Status"`
	Answer []struct {
		Name string `json:"name"`
		Type int    `json:"type"`
		TTL  int    `json:"TTL"`
		Data string `json:"data"`
	} `json:"Answer"`
}

// validatedDNSName rejects injected query delimiters and malformed DNS labels.
// The returned ASCII hostname is also safe for URL-escaped DoH queries.
func validatedDNSName(raw string) (string, error) {
	host := strings.TrimSuffix(strings.ToLower(strings.TrimSpace(raw)), ".")
	if host == "" || len(host) > 253 {
		return "", errors.New("dns: invalid hostname")
	}
	for _, label := range strings.Split(host, ".") {
		if len(label) == 0 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return "", errors.New("dns: invalid hostname label")
		}
		for _, char := range label {
			if !(char >= 'a' && char <= 'z' || char >= '0' && char <= '9' || char == '-') {
				return "", errors.New("dns: invalid hostname label")
			}
		}
	}
	return host, nil
}

// trustedDoHAnswer accepts only NOERROR records for the actual queried name,
// or its bounded CNAME chain. This prevents unrelated records in the JSON
// response from poisoning the shared resolver cache.
func trustedDoHAnswer(host string, response dohResponse) (string, time.Duration, bool) {
	if response.Status != 0 {
		return "", 0, false
	}
	owners := map[string]bool{host: true}
	for depth := 0; depth < 8; depth++ {
		added := false
		for _, answer := range response.Answer {
			if answer.Type != 5 {
				continue
			}
			owner, ownerErr := validatedDNSName(answer.Name)
			alias, aliasErr := validatedDNSName(answer.Data)
			if ownerErr != nil || aliasErr != nil || !owners[owner] || owners[alias] {
				continue
			}
			owners[alias] = true
			added = true
		}
		if !added {
			break
		}
	}
	for _, answer := range response.Answer {
		owner, err := validatedDNSName(answer.Name)
		if err != nil || !owners[owner] {
			continue
		}
		ip := net.ParseIP(answer.Data)
		if ip == nil {
			continue
		}
		if answer.Type != 1 && answer.Type != 28 {
			continue
		}
		if answer.Type == 1 && ip.To4() == nil || answer.Type == 28 && ip.To4() != nil {
			continue
		}
		ttlSeconds := answer.TTL
		if ttlSeconds < 0 {
			ttlSeconds = 0
		}
		if ttlSeconds > 86400 {
			ttlSeconds = 86400
		}
		return ip.String(), time.Duration(ttlSeconds) * time.Second, true
	}
	return "", 0, false
}

// NewHyperResolver constructs a new HyperResolver with default or custom configuration.
func NewHyperResolver(cfg *Config) *HyperResolver {
	resolvedCfg := Config{
		DoHServers: DefaultDoHServers,
		Timeout:    3 * time.Second,
		DefaultTTL: 5 * time.Minute,
	}

	if cfg != nil {
		if len(cfg.DoHServers) > 0 {
			resolvedCfg.DoHServers = cfg.DoHServers
		}
		if cfg.Timeout > 0 {
			resolvedCfg.Timeout = cfg.Timeout
		}
		if cfg.DefaultTTL > 0 {
			resolvedCfg.DefaultTTL = cfg.DefaultTTL
		}
		if cfg.HTTPClient != nil {
			resolvedCfg.HTTPClient = cfg.HTTPClient
		}
	}

	if resolvedCfg.HTTPClient == nil {
		resolvedCfg.HTTPClient = &http.Client{
			Timeout: resolvedCfg.Timeout,
		}
	}

	return &HyperResolver{
		config:     resolvedCfg,
		httpClient: resolvedCfg.HTTPClient,
	}
}

// Resolve queries the in-memory cache, standard UDP DNS, and DoH servers concurrently, returning the fastest valid IP.
func (r *HyperResolver) Resolve(ctx context.Context, host string) (string, error) {
	host = strings.TrimSpace(host)
	if host == "" {
		return "", errors.New("dns: empty host")
	}

	// 1. Direct IP check
	if net.ParseIP(host) != nil {
		return host, nil
	}
	var nameErr error
	host, nameErr = validatedDNSName(host)
	if nameErr != nil {
		return "", nameErr
	}

	// 2. Memory Cache Check
	if ip, found := r.GetCached(host); found {
		return ip, nil
	}

	// 3. Concurrent Racing (UDP + DoH)
	ctx, cancel := context.WithTimeout(ctx, r.config.Timeout)
	defer cancel()

	type queryResult struct {
		ip  string
		ttl time.Duration
		err error
	}

	ch := make(chan queryResult, len(r.config.DoHServers)+1)
	activeWorkers := 0

	// Worker 1: Standard Go Resolver
	activeWorkers++
	go func() {
		ips, err := net.DefaultResolver.LookupHost(ctx, host)
		if err == nil && len(ips) > 0 {
			ch <- queryResult{ip: ips[0], ttl: r.config.DefaultTTL, err: nil}
			return
		}
		ch <- queryResult{err: err}
	}()

	// Workers 2..N: DoH Endpoints
	for _, dohTemplate := range r.config.DoHServers {
		activeWorkers++
		template := dohTemplate
		go func() {
			targetURL := fmt.Sprintf(template, url.QueryEscape(host))
			req, err := http.NewRequestWithContext(ctx, http.MethodGet, targetURL, nil)
			if err != nil {
				ch <- queryResult{err: err}
				return
			}
			req.Header.Set("Accept", "application/dns-json")

			resp, err := r.httpClient.Do(req)
			if err != nil {
				ch <- queryResult{err: err}
				return
			}
			defer resp.Body.Close()

			if resp.StatusCode != http.StatusOK {
				ch <- queryResult{err: fmt.Errorf("doh status %d", resp.StatusCode)}
				return
			}

			var dohResp dohResponse
			if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&dohResp); err != nil {
				ch <- queryResult{err: err}
				return
			}

			if ip, ttl, ok := trustedDoHAnswer(host, dohResp); ok {
				ch <- queryResult{ip: ip, ttl: ttl}
				return
			}
			ch <- queryResult{err: errors.New("doh: no owner-matched successful A or AAAA answer")}
		}()
	}

	var lastErr error
	for i := 0; i < activeWorkers; i++ {
		select {
		case res := <-ch:
			if res.err == nil && res.ip != "" {
				r.SetCache(host, res.ip, res.ttl)
				return res.ip, nil
			}
			lastErr = res.err
		case <-ctx.Done():
			return "", ctx.Err()
		}
	}

	if lastErr != nil {
		return "", fmt.Errorf("hyper_resolve: failed to resolve %s: %w", host, lastErr)
	}

	return "", fmt.Errorf("hyper_resolve: resolution failed for %s", host)
}

// GetCached returns the cached IP for a host if present and non-expired.
func (r *HyperResolver) GetCached(host string) (string, bool) {
	if v, ok := r.cache.Load(host); ok {
		entry := v.(CacheEntry)
		if time.Now().Before(entry.Expiry) {
			return entry.IP, true
		}
		r.cache.Delete(host)
	}
	return "", false
}

// SetCache injects or updates a host entry in the in-memory DNS cache.
func (r *HyperResolver) SetCache(host, ip string, ttl time.Duration) {
	r.cache.Store(host, CacheEntry{
		IP:     ip,
		Expiry: time.Now().Add(ttl),
	})
}
