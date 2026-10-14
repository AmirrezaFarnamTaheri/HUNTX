package main

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/localprobe"
)

func TestLocalProbeRequiresExplicitLoopbackAndBoundedAttempts(t *testing.T) {
	for _, args := range [][]string{
		{"--proxy", "http://example.com:7890"},
		{"--proxy", "http://127.0.0.1:7890", "--attempts", "0"},
		{"--proxy", "http://127.0.0.1:7890", "--attempts", "1000"},
		{"--proxy", "http://127.0.0.1:7890", "--timeout", "30s"},
	} {
		var out bytes.Buffer
		called := false
		err := localProbe(args, &out, func(context.Context, string, time.Duration) localprobe.Result {
			called = true
			return localprobe.Result{ClientPathUsable: true}
		})
		if err == nil || called || out.Len() != 0 {
			t.Errorf("unsafe invocation was not rejected: %v, called=%v", args, called)
		}
	}
}

func TestLocalProbeOnlyCallsBoundedLocalChecksAndNeverClaimsOriginalRecovered(t *testing.T) {
	var out bytes.Buffer
	calls := 0
	err := localProbe([]string{"--proxy", "http://127.0.0.1:7890", "--attempts", "3", "--json"}, &out,
		func(ctx context.Context, address string, timeout time.Duration) localprobe.Result {
			calls++
			if address != "http://127.0.0.1:7890" || timeout != 8*time.Second {
				t.Fatalf("unexpected probe inputs")
			}
			if calls == 3 {
				return localprobe.Result{ErrorClass: "timeout"}
			}
			return localprobe.Result{ClientPathUsable: true, TargetTLSVerified: true, HTTPStatus: 204, LatencyMS: int64(calls * 10)}
		})
	if err != nil {
		t.Fatal(err)
	}
	if calls != 3 {
		t.Fatalf("expected 3 checks, got %d", calls)
	}
	var summary LocalProbeSummary
	if err := json.Unmarshal(out.Bytes(), &summary); err != nil {
		t.Fatal(err)
	}
	if summary.ClientPathUsable || summary.NodeAttributed || summary.OriginalRecovered {
		t.Fatalf("partial success was promoted to verified recovery: %+v", summary)
	}
	if summary.Successes != 2 || summary.Attempts != 3 || summary.MedianLatencyMS == nil || *summary.MedianLatencyMS != 15 {
		t.Fatalf("incorrect bounded summary: %+v", summary)
	}
	if strings.Contains(out.String(), "127.0.0.1") || strings.Contains(out.String(), "7890") {
		t.Fatalf("local endpoint leaked into report: %s", out.String())
	}
}

func TestLocalProbeAllSuccessfulChecksOnlyVerifyClientPath(t *testing.T) {
	var out bytes.Buffer
	err := localProbe([]string{"--proxy", "socks5h://localhost:1080", "--attempts", "1", "--json"}, &out,
		func(context.Context, string, time.Duration) localprobe.Result {
			return localprobe.Result{ClientPathUsable: true, TargetTLSVerified: true, HTTPStatus: 204, LatencyMS: 42}
		})
	if err != nil {
		t.Fatal(err)
	}
	var summary LocalProbeSummary
	if err := json.Unmarshal(out.Bytes(), &summary); err != nil {
		t.Fatal(err)
	}
	if !summary.ClientPathUsable || summary.NodeAttributed || summary.OriginalRecovered || !summary.TargetTLSVerified {
		t.Fatalf("wrong evidence boundary: %+v", summary)
	}
}
