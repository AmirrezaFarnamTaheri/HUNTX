package benchmark

import (
	"context"
	"fmt"
	"net"
	"strconv"
	"sync"
	"time"
)

type CheckResult struct {
	Target  string
	Latency time.Duration
	Alive   bool
	Err     error
}

type Benchmarker struct {
	Timeout     time.Duration
	Concurrency int
}

var blockedNetworks = mustNetworks(
	"0.0.0.0/8",
	"10.0.0.0/8",
	"100.64.0.0/10",
	"127.0.0.0/8",
	"169.254.0.0/16",
	"172.16.0.0/12",
	"192.0.0.0/24",
	"192.0.2.0/24",
	"192.168.0.0/16",
	"198.18.0.0/15",
	"198.51.100.0/24",
	"203.0.113.0/24",
	"224.0.0.0/4",
	"240.0.0.0/4",
	"::/128",
	"::1/128",
	"fc00::/7",
	"fe80::/10",
	"ff00::/8",
	"2001:db8::/32",
)

func mustNetworks(cidrs ...string) []*net.IPNet {
	networks := make([]*net.IPNet, 0, len(cidrs))
	for _, cidr := range cidrs {
		_, network, err := net.ParseCIDR(cidr)
		if err != nil {
			panic(err)
		}
		networks = append(networks, network)
	}
	return networks
}

func isPublicIP(ip net.IP) bool {
	if ip == nil || !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() ||
		ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsMulticast() ||
		ip.IsUnspecified() {
		return false
	}
	for _, network := range blockedNetworks {
		if network.Contains(ip) {
			return false
		}
	}
	return true
}

func resolvePublicTargets(ctx context.Context, target string) ([]string, error) {
	host, portText, err := net.SplitHostPort(target)
	if err != nil {
		return nil, fmt.Errorf("target must be host:port: %w", err)
	}
	port, err := strconv.Atoi(portText)
	if err != nil || port < 1 || port > 65535 {
		return nil, fmt.Errorf("invalid target port %q", portText)
	}

	if literal := net.ParseIP(host); literal != nil {
		if !isPublicIP(literal) {
			return nil, fmt.Errorf("refusing non-public benchmark target %s", host)
		}
		return []string{net.JoinHostPort(literal.String(), portText)}, nil
	}

	addresses, err := net.DefaultResolver.LookupIPAddr(ctx, host)
	if err != nil {
		return nil, fmt.Errorf("resolve %s: %w", host, err)
	}
	seen := make(map[string]struct{})
	resolved := make([]string, 0, len(addresses))
	for _, address := range addresses {
		if !isPublicIP(address.IP) {
			continue
		}
		endpoint := net.JoinHostPort(address.IP.String(), portText)
		if _, exists := seen[endpoint]; exists {
			continue
		}
		seen[endpoint] = struct{}{}
		resolved = append(resolved, endpoint)
	}
	if len(resolved) == 0 {
		return nil, fmt.Errorf("target %s resolved only to non-public addresses", host)
	}
	return resolved, nil
}

func NewBenchmarker(timeout time.Duration, concurrency int) *Benchmarker {
	if timeout <= 0 {
		timeout = 3 * time.Second
	}
	if concurrency <= 0 {
		concurrency = 100
	}
	return &Benchmarker{
		Timeout:     timeout,
		Concurrency: concurrency,
	}
}

func (b *Benchmarker) CheckTarget(ctx context.Context, target string) CheckResult {
	ctxTimeout, cancel := context.WithTimeout(ctx, b.Timeout)
	defer cancel()

	endpoints, err := resolvePublicTargets(ctxTimeout, target)
	if err != nil {
		return CheckResult{Target: target, Alive: false, Err: err}
	}

	var lastErr error
	for _, endpoint := range endpoints {
		start := time.Now()
		dialer := &net.Dialer{Timeout: b.Timeout}
		conn, dialErr := dialer.DialContext(ctxTimeout, "tcp", endpoint)
		if dialErr != nil {
			lastErr = dialErr
			continue
		}
		_ = conn.Close()
		return CheckResult{
			Target:  target,
			Latency: time.Since(start),
			Alive:   true,
			Err:     nil,
		}
	}
	return CheckResult{Target: target, Alive: false, Err: lastErr}
}

func (b *Benchmarker) CheckBatch(ctx context.Context, targets []string) []CheckResult {
	results := make([]CheckResult, len(targets))
	if len(targets) == 0 {
		return results
	}
	targetChan := make(chan struct {
		index  int
		target string
	}, len(targets))

	for i, target := range targets {
		targetChan <- struct {
			index  int
			target string
		}{index: i, target: target}
	}
	close(targetChan)

	var wg sync.WaitGroup
	workers := b.Concurrency
	if workers < 1 {
		workers = 1
	}
	if workers > len(targets) {
		workers = len(targets)
	}

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range targetChan {
				select {
				case <-ctx.Done():
					results[item.index] = CheckResult{
						Target: item.target,
						Alive:  false,
						Err:    ctx.Err(),
					}
				default:
					results[item.index] = b.CheckTarget(ctx, item.target)
				}
			}
		}()
	}

	wg.Wait()
	return results
}
