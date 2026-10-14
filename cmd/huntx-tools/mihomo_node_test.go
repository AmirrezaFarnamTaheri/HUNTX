package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestMihomoNodeCliRequiresPrivateTokenAndOnlyExplicitLeaf(t *testing.T) {
	for _, args := range [][]string{
		{"--controller", "http://example.com:9090", "--token-file", "/dev/null", "--node", "a"},
		{"--controller", "http://127.0.0.1:9090", "--node", "a"},
		{"--controller", "http://127.0.0.1:9090", "--token-file", "/dev/null", "--node", "a", "--attempts", "100"},
		{"--controller", "http://127.0.0.1:9090", "--token-file", "/dev/null", "--node", ".."},
		{"--controller", "http://127.0.0.1:9090", "--token-file", "/dev/null", "--node", "a", "unexpected-extra"},
	} {
		var out bytes.Buffer
		if err := mihomoNode(args, &out); err == nil {
			t.Errorf("accepted invalid args %v", args)
		}
		if out.Len() != 0 {
			t.Errorf("invalid args produced output %q", out.String())
		}
	}
}

func TestMihomoCliRecordsControllerAttestedEvidenceButNotIndependentRecovery(t *testing.T) {
	const token = "secret-from-private-file"
	dir := t.TempDir()
	secret := filepath.Join(dir, "mihomo.secret")
	if err := os.WriteFile(secret, []byte(token+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	var calls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+token {
			t.Errorf("missing bearer header")
			http.Error(w, "unauthorized", 401)
			return
		}
		if r.URL.Path == "/proxies/test-node" {
			_, _ = w.Write([]byte(`{"type":"VLESS","name":"test-node"}`))
			return
		}
		if r.URL.Path == "/proxies/test-node/delay" {
			calls++
			_, _ = w.Write([]byte(`{"delay":24}`))
			return
		}
		http.NotFound(w, r)
	}))
	defer server.Close()
	var out bytes.Buffer
	err := mihomoNode([]string{"--controller", server.URL, "--token-file", secret, "--node", "test-node", "--json", "--attempts", "2"}, &out)
	if err != nil {
		t.Fatal(err)
	}
	var result struct {
		Evidence                 string `json:"evidence"`
		NativeTestPassed         bool   `json:"native_test_passed"`
		NodeAttributed           bool   `json:"node_attributed"`
		OriginalRecovered        bool   `json:"original_recovered"`
		TLSIndependentlyVerified bool   `json:"tls_independently_verified"`
		Successes                int    `json:"successes"`
	}
	if err := json.Unmarshal(out.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if !result.NativeTestPassed || !result.NodeAttributed || result.OriginalRecovered || result.TLSIndependentlyVerified || result.Successes != 2 || calls != 2 {
		t.Fatalf("incorrect classification: %+v calls=%d", result, calls)
	}
	if strings.Contains(out.String(), token) || strings.Contains(out.String(), "test-node") || strings.Contains(out.String(), server.URL) {
		t.Fatal("sensitive information leaked into report")
	}
}

func TestMihomoCliFailureIsInconclusiveWithNonzeroExit(t *testing.T) {
	dir := t.TempDir()
	secret := filepath.Join(dir, "mihomo.secret")
	_ = os.WriteFile(secret, []byte("valid-secret-123456"), 0600)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"name":"GROUP","type":"Selector","all":["x"]}`))
	}))
	defer server.Close()
	var out bytes.Buffer
	err := mihomoNode([]string{"--controller", server.URL, "--token-file", secret, "--node", "GROUP", "--json"}, &out)
	if err == nil {
		t.Fatal("native diagnostic incorrectly exited successfully")
	}
	if !strings.Contains(out.String(), "not-leaf") || !strings.Contains(out.String(), `"native_test_passed":false`) {
		t.Errorf("unexpected evidence: %q", out.String())
	}
	if strings.Contains(err.Error(), "GROUP") || strings.Contains(err.Error(), "secret") {
		t.Errorf("error leaked node name or token: %v", err)
	}
}
