package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"huntx-engine/benchmark"
	"huntx-engine/georoute"
	"huntx-engine/healing"
	"huntx-engine/stream"
)

var (
	version = "1.0.0-nextgen"
)

func main() {
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
		_ = fs.Parse(os.Args[2:])

		sp := stream.NewStreamParser(65536)
		var r *os.File
		var err error

		if *fileFlag != "" {
			r, err = os.Open(*fileFlag)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error opening file: %v\n", err)
				os.Exit(1)
			}
			defer r.Close()
		} else {
			r = os.Stdin
		}

		records, err := sp.ParseStream(r)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error parsing stream: %v\n", err)
			os.Exit(1)
		}

		out, _ := json.MarshalIndent(records, "", "  ")
		fmt.Println(string(out))

	case "benchmark":
		fs := flag.NewFlagSet("benchmark", flag.ExitOnError)
		targetsFlag := fs.String("targets", "", "Comma-separated host:port targets")
		concurrencyFlag := fs.Int("concurrency", 50, "Max concurrent TCP workers")
		timeoutFlag := fs.Duration("timeout", 2*time.Second, "Dial timeout duration")
		_ = fs.Parse(os.Args[2:])

		if *targetsFlag == "" {
			fmt.Fprintln(os.Stderr, "Error: --targets flag is required (e.g. --targets '1.1.1.1:443,8.8.8.8:53')")
			os.Exit(1)
		}

		targets := strings.Split(*targetsFlag, ",")
		bm := benchmark.NewBenchmarker(*timeoutFlag, *concurrencyFlag)

		ctx, cancel := context.WithTimeout(context.Background(), *timeoutFlag*2)
		defer cancel()

		results := bm.CheckBatch(ctx, targets)
		out, _ := json.MarshalIndent(results, "", "  ")
		fmt.Println(string(out))

	case "georoute":
		fs := flag.NewFlagSet("georoute", flag.ExitOnError)
		regionFlag := fs.String("region", "US", "ISO country code to filter by")
		_ = fs.Parse(os.Args[2:])

		engine := georoute.NewEngine()
		sp := stream.NewStreamParser(65536)
		records, _ := sp.ParseStream(os.Stdin)

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
		out, _ := json.MarshalIndent(filtered, "", "  ")
		fmt.Println(string(out))

	case "heal":
		daemon := healing.NewDaemon(nil)
		now := time.Now()
		daemon.RecordFailure("demo_hash", "vless://user@host:443", now)
		purged := daemon.PurgeStale(48*time.Hour, now)

		fmt.Printf("Self-Healing Daemon initialized. Purged stale nodes: %d\n", purged)

	default:
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n", command)
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
