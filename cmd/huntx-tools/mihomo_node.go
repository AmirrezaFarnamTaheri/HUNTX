package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/localmihomo"
)

func runMihomoNode(args []string) error { return mihomoNode(args, os.Stdout) }

// mihomoNode intentionally accepts secrets only from a protected file, never
// through CLI flags or environment variables, and never starts a local server.
func mihomoNode(args []string, out io.Writer) error {
	flags := flag.NewFlagSet("mihomo-node", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	controller := flags.String("controller", "", "explicit localhost Mihomo controller URL")
	secretFile := flags.String("token-file", "", "private controller token file (0600)")
	name := flags.String("node", "", "existing named Mihomo leaf proxy")
	attempts := flags.Int("attempts", 3, "sequential tests, 1-3")
	timeout := flags.Duration("timeout", 8*time.Second, "per-test budget, 1-15s")
	asJSON := flags.Bool("json", false, "emit privacy-safe JSON evidence")
	if err := flags.Parse(args); err != nil || flags.NArg() != 0 {
		return errors.New("invalid mihomo-node options")
	}
	if *controller == "" || *secretFile == "" || *name == "" {
		return errors.New("--controller, --token-file and --node are required")
	}
	if *attempts < 1 || *attempts > 3 || *timeout < time.Second || *timeout > 15*time.Second {
		return errors.New("invalid bounded test budget")
	}
	token, err := localmihomo.ReadTokenFile(*secretFile)
	if err != nil {
		return err
	}
	client, err := localmihomo.New(*controller, token)
	if err != nil {
		return err
	}
	outcome := client.Probe(context.Background(), *name, *timeout, *attempts)
	if *asJSON {
		if err := json.NewEncoder(out).Encode(outcome); err != nil {
			return err
		}
	} else {
		if outcome.NativeTestPassed {
			_, err = fmt.Fprintf(out, "Selected Mihomo leaf: %d/%d controller-attested HTTPS URL tests passed (median %d ms). Independent TLS/node repair: unverified.\n", outcome.Successes, outcome.Attempts, outcome.MedianDelayMS)
		} else {
			_, err = fmt.Fprintf(out, "Selected Mihomo leaf: inconclusive (%s, %d/%d passes). No recovery verified.\n", outcome.ErrorClass, outcome.Successes, outcome.Attempts)
		}
		if err != nil {
			return err
		}
	}
	if !outcome.NativeTestPassed {
		return errors.New("Mihomo native node check did not pass")
	}
	return nil
}
