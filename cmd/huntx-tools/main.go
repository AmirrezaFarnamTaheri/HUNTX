package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/outputverify"
	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/releasemanifest"
	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/runtimegen"
	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/sitegen"
)

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "huntx-tools:", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	if len(args) == 0 {
		return errors.New("subcommand required: runtime-generation, release-manifest, verify-output, or site-data")
	}
	switch args[0] {
	case "runtime-generation":
		return runRuntimeGeneration(args[1:])
	case "release-manifest":
		return runReleaseManifest(args[1:])
	case "verify-output":
		return runVerifyOutput(args[1:])
	case "site-data":
		return runSiteData(args[1:])
	default:
		return fmt.Errorf("unsupported subcommand: %s", args[0])
	}
}

func runRuntimeGeneration(args []string) error {
	if len(args) == 0 {
		return errors.New("runtime-generation operation required: build, verify, or validate-pointer")
	}
	switch args[0] {
	case "build":
		flags := flag.NewFlagSet("runtime-generation build", flag.ContinueOnError)
		root := flags.String("root", "", "generation payload root")
		generation := flags.String("generation", "", "generation identifier")
		manifestPath := flags.String("manifest", "", "manifest output path")
		pointerPath := flags.String("pointer", "", "pointer output path")
		if err := flags.Parse(args[1:]); err != nil {
			return err
		}
		if *root == "" || *generation == "" || *manifestPath == "" || *pointerPath == "" {
			return errors.New("--root, --generation, --manifest, and --pointer are required")
		}
		manifest, err := runtimegen.Build(*root, *generation)
		if err != nil {
			return err
		}
		pointer, err := runtimegen.BuildPointer(*generation, manifest)
		if err != nil {
			return err
		}
		if err := runtimegen.WriteAtomic(*manifestPath, manifest); err != nil {
			return err
		}
		return runtimegen.WriteAtomic(*pointerPath, pointer)
	case "verify":
		flags := flag.NewFlagSet("runtime-generation verify", flag.ContinueOnError)
		root := flags.String("root", "", "generation payload root")
		manifestPath := flags.String("manifest", "", "manifest path")
		if err := flags.Parse(args[1:]); err != nil {
			return err
		}
		if *root == "" || *manifestPath == "" {
			return errors.New("--root and --manifest are required")
		}
		manifest, err := runtimegen.ReadManifest(*manifestPath)
		if err != nil {
			return err
		}
		return runtimegen.Verify(*root, manifest)
	case "validate-pointer":
		flags := flag.NewFlagSet("runtime-generation validate-pointer", flag.ContinueOnError)
		pointerPath := flags.String("pointer", "", "pointer path")
		manifestPath := flags.String("manifest", "", "optional manifest path")
		if err := flags.Parse(args[1:]); err != nil {
			return err
		}
		if *pointerPath == "" {
			return errors.New("--pointer is required")
		}
		pointer, err := runtimegen.ReadPointer(*pointerPath)
		if err != nil {
			return err
		}
		var manifest *runtimegen.Manifest
		if *manifestPath != "" {
			loaded, err := runtimegen.ReadManifest(*manifestPath)
			if err != nil {
				return err
			}
			manifest = &loaded
		}
		generation, err := runtimegen.ValidatePointer(pointer, manifest)
		if err != nil {
			return err
		}
		fmt.Println(generation)
		return nil
	default:
		return fmt.Errorf("unsupported runtime-generation operation: %s", args[0])
	}
}

func runReleaseManifest(args []string) error {
	flags := flag.NewFlagSet("release-manifest", flag.ContinueOnError)
	root := flags.String("root", "", "release root")
	manifestPath := flags.String("manifest", "", "manifest output path")
	jsonSummary := flags.Bool("json", false, "emit machine-readable summary")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *root == "" {
		return errors.New("--root is required")
	}
	if *manifestPath == "" {
		*manifestPath = filepath.Join(*root, "manifest.json")
	}
	candidates, err := releasemanifest.Discover(*root, *manifestPath)
	if err != nil {
		return err
	}
	manifest, err := releasemanifest.Build(*root, candidates)
	if err != nil {
		return err
	}
	if err := releasemanifest.WriteAtomic(*manifestPath, manifest); err != nil {
		return err
	}
	loaded, err := releasemanifest.Read(*manifestPath)
	if err != nil {
		return err
	}
	if err := releasemanifest.Verify(*root, loaded); err != nil {
		return err
	}
	if *jsonSummary {
		payload, err := json.Marshal(loaded)
		if err != nil {
			return err
		}
		fmt.Println(string(payload))
	} else {
		fmt.Printf("Validated %d release artifacts\n", loaded.ArtifactCount)
	}
	return nil
}

func runVerifyOutput(args []string) error {
	flags := flag.NewFlagSet("verify-output", flag.ContinueOnError)
	dataDir := flags.String("data-dir", "", "HUNTX data directory")
	jsonSummary := flags.Bool("json", false, "emit machine-readable summary")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *dataDir == "" {
		*dataDir = os.Getenv("HUNTX_DATA_DIR")
	}
	if *dataDir == "" {
		*dataDir = "persist/data"
	}
	summary, err := outputverify.Verify(*dataDir)
	if err != nil {
		return err
	}
	if *jsonSummary {
		payload, err := json.Marshal(summary)
		if err != nil {
			return err
		}
		fmt.Println(string(payload))
	} else {
		fmt.Printf("Verified %d output files (%d bytes); vmess outbounds=%d\n", summary.Files, summary.TotalSize, summary.VmessCount)
	}
	return nil
}

func runSiteData(args []string) error {
	flags := flag.NewFlagSet("site-data", flag.ContinueOnError)
	dataDir := flags.String("data-dir", "", "HUNTX data directory")
	docsDir := flags.String("docs-dir", "docs", "site documentation directory")
	generatedAt := flags.String("generated-at", "", "RFC3339 timestamp override for reproducible testing")
	jsonSummary := flags.Bool("json", false, "emit machine-readable catalog")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *dataDir == "" {
		*dataDir = os.Getenv("HUNTX_DATA_DIR")
	}
	if *dataDir == "" {
		*dataDir = "persist/data"
	}
	timestamp := time.Now().UTC()
	if *generatedAt != "" {
		parsed, err := time.Parse(time.RFC3339Nano, *generatedAt)
		if err != nil {
			return fmt.Errorf("invalid --generated-at: %w", err)
		}
		timestamp = parsed
	}
	catalog, err := sitegen.Generate(*dataDir, *docsDir, timestamp)
	if err != nil {
		return err
	}
	if err := sitegen.ValidateCatalog(catalog); err != nil {
		return err
	}
	if *jsonSummary {
		payload, err := json.Marshal(catalog)
		if err != nil {
			return err
		}
		fmt.Println(string(payload))
	} else {
		fmt.Printf("Catalog written to %s with %d verified artifacts\n", filepath.Join(*docsDir, "catalog.json"), catalog.TotalFiles)
	}
	return nil
}
