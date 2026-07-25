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

	"huntx-engine/benchmark"
	"huntx-engine/georoute"
	"huntx-engine/healing"
	"huntx-engine/internal/parse"
	"huntx-engine/stream"
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
		bm := benchmark.NewBenchmarker(*timeoutFlag, *concurrencyFlag)

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
  version                 Print engine version
  parse [--file PATH]     Parse base64 or raw subscription stream into JSON records
  benchmark --targets CSV High-concurrency TCP/TLS latency benchmark across targets
  georoute [--region ISO] Tag and filter proxy stream by ISO country code
  heal                    Run self-healing daemon status check`)
}
