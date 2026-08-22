// Package dns implements concurrent hybrid DNS resolution with DoH racing and dual-layer caching.
// Source: https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/ (Cloudflare DoH JSON API)
// Source: https://developers.google.com/speed/public-dns/docs/doh/json (Google DoH JSON API)
package dns

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
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
			targetURL := fmt.Sprintf(template, host)
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
			if err := json.NewDecoder(resp.Body).Decode(&dohResp); err != nil {
				ch <- queryResult{err: err}
				return
			}

			for _, ans := range dohResp.Answer {
				// Type 1 (A) or Type 28 (AAAA)
				if (ans.Type == 1 || ans.Type == 28) && net.ParseIP(ans.Data) != nil {
					ttlDuration := time.Duration(ans.TTL) * time.Second
					if ttlDuration < 30*time.Second {
						ttlDuration = r.config.DefaultTTL
					}
					ch <- queryResult{ip: ans.Data, ttl: ttlDuration, err: nil}
					return
				}
			}

			ch <- queryResult{err: errors.New("doh: no valid A or AAAA answer found")}
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
