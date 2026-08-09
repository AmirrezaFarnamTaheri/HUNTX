package benchmark

import (
	"context"
	"net"
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
	start := time.Now()
	dialer := &net.Dialer{
		Timeout: b.Timeout,
	}

	ctxTimeout, cancel := context.WithTimeout(ctx, b.Timeout)
	defer cancel()

	conn, err := dialer.DialContext(ctxTimeout, "tcp", target)
	if err != nil {
		return CheckResult{
			Target:  target,
			Latency: 0,
			Alive:   false,
			Err:     err,
		}
	}
	_ = conn.Close()

	return CheckResult{
		Target:  target,
		Latency: time.Since(start),
		Alive:   true,
		Err:     nil,
	}
}

func (b *Benchmarker) CheckBatch(ctx context.Context, targets []string) []CheckResult {
	results := make([]CheckResult, len(targets))
	targetChan := make(chan struct {
		index  int
		target string
	}, len(targets))

	for i, t := range targets {
		targetChan <- struct {
			index  int
			target string
		}{index: i, target: t}
	}
	close(targetChan)

	var wg sync.WaitGroup
	workers := b.Concurrency
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
