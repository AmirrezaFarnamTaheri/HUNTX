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
	"huntx-engine/internal/parse"
	"huntx-engine/stream"
)

var version = "1.0.0-nextgen"

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
	slog.SetDefault(logger)

	if len(os.Args) < 2 {
		printUsage()
		os.Exit(0)
	}

	switch os.Args[1] {
	case "version":
		fmt.Printf("HUNTX Next-Gen Go Engine v%s\n", version)
	case "parse":
		fs := flag.NewFlagSet("parse", flag.ExitOnError)
		fileFlag := fs.String("file", "", "Path to subscription file or raw payload")
		if err := fs.Parse(os.Args[2:]); err != nil {
			os.Exit(1)
		}
		var records []stream.Record
		var err error
		if *fileFlag != "" {
			records, err = parse.ParseFile(*fileFlag)
		} else {
			records, err = parse.ParseReader(os.Stdin)
		}
		if err != nil {
			slog.Error("failed to parse stream", "error", err)
			os.Exit(1)
		}
		out, _ := json.MarshalIndent(records, "", "  ")
		fmt.Println(string(out))
	case "benchmark":
		fs := flag.NewFlagSet("benchmark", flag.ExitOnError)
		targetsFlag := fs.String("targets", "", "Comma-separated host:port targets")
		concurrencyFlag := fs.Int("concurrency", 50, "Max concurrent TCP workers")
		timeoutFlag := fs.Duration("timeout", 2*time.Second, "Dial timeout duration")
		if err := fs.Parse(os.Args[2:]); err != nil {
			os.Exit(1)
		}
		targets, err := parseBenchmarkTargets(*targetsFlag)
		if err != nil {
			slog.Error("invalid benchmark targets", "error", err)
			os.Exit(1)
		}

		bm := benchmark.NewBenchmarker(*timeoutFlag, *concurrencyFlag)
		workers := *concurrencyFlag
		if workers <= 0 || workers > len(targets) {
			workers = len(targets)
		}
		batches := 1
		if workers > 0 {
			batches = (len(targets) + workers - 1) / workers
		}
		ctx, cancel := context.WithTimeout(context.Background(), time.Duration(batches)*(*timeoutFlag)+(*timeoutFlag))
		defer cancel()

		results := bm.CheckBatch(ctx, targets)
		out, _ := json.MarshalIndent(results, "", "  ")
		fmt.Println(string(out))
	case "georoute":
		fs := flag.NewFlagSet("georoute", flag.ExitOnError)
		regionFlag := fs.String("region", "US", "ISO country code to filter by")
		if err := fs.Parse(os.Args[2:]); err != nil {
			os.Exit(1)
		}
		engine := georoute.NewEngine()
		sp := stream.NewStreamParser(65536)
		records, err := sp.ParseStream(os.Stdin)
		if err != nil {
			slog.Error("failed to parse stream", "error", err)
			os.Exit(1)
		}
		classified := make([]georoute.ProxyRecord, 0, len(records))
		for _, rec := range records {
			classified = append(classified, engine.Classify(georoute.ProxyRecord{UniqueHash: rec.UniqueHash, RawURI: rec.RawURI, Protocol: rec.Protocol}))
		}
		out, _ := json.MarshalIndent(georoute.FilterByRegion(classified, *regionFlag), "", "  ")
		fmt.Println(string(out))
	default:
		slog.Error("unknown command", "command", os.Args[1])
		printUsage()
		os.Exit(1)
	}
}

func parseBenchmarkTargets(raw string) ([]string, error) {
	if strings.TrimSpace(raw) == "" {
		return nil, fmt.Errorf("--targets is required")
	}
	parts := strings.Split(raw, ",")
	targets := make([]string, 0, len(parts))
	for _, part := range parts {
		target := strings.TrimSpace(part)
		if target == "" {
			return nil, fmt.Errorf("--targets must not contain empty entries")
		}
		targets = append(targets, target)
	}
	return targets, nil
}

func printUsage() {
	fmt.Println("Usage: huntx-engine <version|parse|benchmark|georoute> [options]")
	fmt.Println("  version                         Print the engine version")
	fmt.Println("  parse [-file PATH]              Parse a file or stdin subscription stream")
	fmt.Println("  benchmark --targets HOST:PORT   Benchmark comma-separated TCP targets")
	fmt.Println("  georoute [-region ISO]          Classify stdin records and filter by region")
}
