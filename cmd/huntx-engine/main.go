package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"strings"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/benchmark"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/chain"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/georoute"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/healing"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/parse"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/tlsdiag"
)

var (
	version = "1.0.0-nextgen"
)

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
	slog.SetDefault(logger)

	if len(os.Args) < 2 {
		printUsage()
		os.Exit(0)
	}

	command := os.Args[1]
	switch command {
	case "version":
		fmt.Printf("HUNTX Next-Gen Go Engine v%s\n", version)

	case "parse":
		fs := flag.NewFlagSet("parse", flag.ExitOnError)
		fileFlag := fs.String("file", "", "Path to subscription file or raw payload")
		if err := fs.Parse(os.Args[2:]); err != nil {
			slog.Error("failed to parse flags", "error", err)
			os.Exit(1)
		}

		var (
			records []stream.Record
			err     error
		)
		if *fileFlag != "" {
			records, err = parse.ParseFile(*fileFlag)
		} else {
			records, err = parse.ParseReader(os.Stdin)
		}
		if err != nil {
			slog.Error("failed to parse stream", "error", err)
			os.Exit(1)
		}

		out, err := json.MarshalIndent(records, "", "  ")
		if err != nil {
			slog.Error("failed to marshal json records", "error", err)
			os.Exit(1)
		}
		fmt.Println(string(out))

	case "benchmark":
		fs := flag.NewFlagSet("benchmark", flag.ExitOnError)
		targetsFlag := fs.String("targets", "", "Comma-separated host:port targets")
		concurrencyFlag := fs.Int("concurrency", 50, "Max concurrent TCP workers")
		timeoutFlag := fs.Duration("timeout", 2*time.Second, "Dial timeout duration")
		if err := fs.Parse(os.Args[2:]); err != nil {
			slog.Error("failed to parse flags", "error", err)
			os.Exit(1)
		}

		if *targetsFlag == "" {
			slog.Error("missing required flag", "flag", "--targets")
			os.Exit(1)
		}

		targets := strings.Split(*targetsFlag, ",")
		bm := benchmark.New(
			benchmark.WithTimeout(*timeoutFlag),
			benchmark.WithConcurrency(*concurrencyFlag),
		)

		ctx, cancel := context.WithTimeout(context.Background(), *timeoutFlag*2)
		defer cancel()

		results := bm.CheckBatch(ctx, targets)
		out, err := json.MarshalIndent(results, "", "  ")
		if err != nil {
			slog.Error("failed to marshal benchmark results", "error", err)
			os.Exit(1)
		}
		fmt.Println(string(out))

	case "georoute":
		fs := flag.NewFlagSet("georoute", flag.ExitOnError)
		regionFlag := fs.String("region", "US", "ISO country code to filter by")
		if err := fs.Parse(os.Args[2:]); err != nil {
			slog.Error("failed to parse flags", "error", err)
			os.Exit(1)
		}

		engine := georoute.NewEngine()
		sp := stream.NewStreamParser(65536)
		records, err := sp.ParseStream(os.Stdin)
		if err != nil {
			slog.Error("failed to parse stdin stream for georoute", "error", err)
			os.Exit(1)
		}

		var classified []georoute.ProxyRecord
		for _, rec := range records {
			c := engine.Classify(georoute.ProxyRecord{
				UniqueHash: rec.UniqueHash,
				RawURI:     rec.RawURI,
				Protocol:   rec.Protocol,
			})
			classified = append(classified, c)
		}

		filtered := georoute.FilterByRegion(classified, *regionFlag)
		out, err := json.MarshalIndent(filtered, "", "  ")
		if err != nil {
			slog.Error("failed to marshal georoute results", "error", err)
			os.Exit(1)
		}
		fmt.Println(string(out))

	case "chain":
		fs := flag.NewFlagSet("chain", flag.ExitOnError)
		domesticFlag := fs.String("domestic", "IR", "Domestic ISO country code for entry relays")
		maxLatencyFlag := fs.Duration("max-latency", 800*time.Millisecond, "Maximum composite RTT ceiling")
		maxChainsFlag := fs.Int("max-chains", 20, "Maximum number of chains to synthesize")
		if err := fs.Parse(os.Args[2:]); err != nil {
			slog.Error("failed to parse flags", "error", err)
			os.Exit(1)
		}

		synthesizer := chain.New(
			chain.WithStrategy(chain.StrategyDomesticRelayInternationalExit),
			chain.WithDomesticCountry(*domesticFlag),
			chain.WithMaxLatencyCeiling(*maxLatencyFlag),
			chain.WithMaxChains(*maxChainsFlag),
		)

		var pool []chain.Node
		dec := json.NewDecoder(os.Stdin)
		if err := dec.Decode(&pool); err != nil {
			slog.Error("failed to decode node pool from stdin JSON", "error", err)
			os.Exit(1)
		}

		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		chains, err := synthesizer.Synthesize(ctx, pool)
		if err != nil {
			slog.Error("chain synthesis failed", "error", err)
			os.Exit(1)
		}

		out, err := json.MarshalIndent(chains, "", "  ")
		if err != nil {
			slog.Error("failed to marshal synthesized chains", "error", err)
			os.Exit(1)
		}
		fmt.Println(string(out))

	case "tlsdiag":
		fs := flag.NewFlagSet("tlsdiag", flag.ExitOnError)
		targetFlag := fs.String("target", "", "Target endpoint host:port (e.g. 1.1.1.1:443)")
		sniFlag := fs.String("sni", "cloudflare.com", "Server Name Indication (SNI)")
		timeoutFlag := fs.Duration("timeout", 3*time.Second, "TLS handshake timeout")
		if err := fs.Parse(os.Args[2:]); err != nil {
			slog.Error("failed to parse flags", "error", err)
			os.Exit(1)
		}

		if *targetFlag == "" {
			slog.Error("missing required flag", "flag", "--target")
			os.Exit(1)
		}

		classifier := tlsdiag.NewClassifier(
			tlsdiag.WithTimeout(*timeoutFlag),
			tlsdiag.WithInsecureSkipVerify(true),
		)

		ctx, cancel := context.WithTimeout(context.Background(), *timeoutFlag*2)
		defer cancel()

		report := classifier.Probe(ctx, *targetFlag, *sniFlag)
		out, err := json.MarshalIndent(report, "", "  ")
		if err != nil {
			slog.Error("failed to marshal TLS diagnostic report", "error", err)
			os.Exit(1)
		}
		fmt.Println(string(out))

	case "heal":
		daemon := healing.NewDaemon(nil)
		now := time.Now()
		daemon.RecordFailure("demo_hash", "vless://user@host:443", now)
		purged := daemon.PurgeStale(48*time.Hour, now)

		slog.Info("self-healing daemon status check", "purged_stale_nodes", purged)

	default:
		slog.Error("unknown command", "command", command)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println(`HUNTX Next-Gen Go High-Performance Engine

Usage:
  huntx-engine <command> [flags]

Commands:
  version                   Print engine version
  parse [--file PATH]       Parse base64 or raw subscription stream into JSON records
  benchmark --targets CSV   High-concurrency TCP/TLS latency benchmark across targets
  georoute [--region ISO]   Tag and filter proxy stream by ISO country code
  chain [--domestic ISO]    Synthesize multi-hop relay-to-exit proxy chains from stdin JSON
  tlsdiag --target HOST:PORT Active TLS handshake probe, ALPN check, and JA4 fingerprint
  heal                      Run self-healing daemon status check`)
}
