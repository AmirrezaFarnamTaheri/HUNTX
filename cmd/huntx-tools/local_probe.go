package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"sort"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/localprobe"
)

// LocalProbeSummary is intentionally credential-free. It confirms only a
// working HTTPS path through the configured local client, never node identity.
type LocalProbeSummary struct {
	Evidence          string         `json:"evidence"`
	Attempts          int            `json:"attempts"`
	Successes         int            `json:"successes"`
	ClientPathUsable  bool           `json:"client_path_usable"`
	NodeAttributed    bool           `json:"node_attributed"`
	OriginalRecovered bool           `json:"original_recovered"`
	TargetTLSVerified bool           `json:"target_tls_verified"`
	MedianLatencyMS   *int64         `json:"median_latency_ms,omitempty"`
	ErrorClasses      map[string]int `json:"error_classes,omitempty"`
}

func runLocalProbe(args []string) error {
	return localProbe(args, os.Stdout, localprobe.Check)
}

func localProbe(args []string, out io.Writer, probe func(context.Context, string, time.Duration) localprobe.Result) error {
	flags := flag.NewFlagSet("local-probe", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	address := flags.String("proxy", "", "loopback HTTP/SOCKS5 client URL, without credentials")
	attempts := flags.Int("attempts", 3, "number of sequential HTTPS checks (1-3)")
	timeout := flags.Duration("timeout", 8*time.Second, "per-check budget (1-15s)")
	asJSON := flags.Bool("json", false, "print privacy-safe JSON evidence")
	if err := flags.Parse(args); err != nil || flags.NArg() != 0 {
		return errors.New("invalid local-probe options")
	}
	if *address == "" {
		return errors.New("--proxy is required (loopback URL only)")
	}
	if err := localprobe.ValidateLocalProxy(*address); err != nil {
		return err
	}
	if *attempts < 1 || *attempts > 3 {
		return errors.New("--attempts must be between 1 and 3")
	}
	if *timeout < time.Second || *timeout > 15*time.Second {
		return errors.New("--timeout must be between 1s and 15s")
	}

	summary := LocalProbeSummary{
		Evidence:     "HTTPS-through-local-client",
		Attempts:     *attempts,
		ErrorClasses: make(map[string]int),
	}
	latencies := make([]int64, 0, *attempts)
	for i := 0; i < *attempts; i++ {
		result := probe(context.Background(), *address, *timeout)
		if result.ClientPathUsable && result.TargetTLSVerified {
			summary.Successes++
			latencies = append(latencies, result.LatencyMS)
		} else {
			kind := result.ErrorClass
			if kind == "" {
				kind = "unattributed-failure"
			}
			summary.ErrorClasses[kind]++
		}
	}
	if len(latencies) > 0 {
		sort.Slice(latencies, func(i, j int) bool { return latencies[i] < latencies[j] })
		mid := len(latencies) / 2
		median := latencies[mid]
		if len(latencies)%2 == 0 {
			median = (latencies[mid-1] + latencies[mid]) / 2
		}
		summary.MedianLatencyMS = &median
	}
	// Never claim the original node was revived: the local client may route
	// through a fallback or DIRECT group, which this CLI cannot attribute.
	summary.ClientPathUsable = summary.Successes == summary.Attempts
	summary.TargetTLSVerified = summary.ClientPathUsable
	if len(summary.ErrorClasses) == 0 {
		summary.ErrorClasses = nil
	}
	if *asJSON {
		return json.NewEncoder(out).Encode(summary)
	}
	status := "inconclusive"
	if summary.ClientPathUsable {
		status = "client HTTPS path usable"
	}
	_, err := fmt.Fprintf(out, "%s: %d/%d HTTPS checks passed through the local client; original node not attributed or recovered.\n", status, summary.Successes, summary.Attempts)
	return err
}
