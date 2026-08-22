// Package main provides the WebAssembly compilation target for HUNTX client-side browser execution.
package main

import (
	"encoding/json"
	"testing"
)

func TestWasmDecodeBase64Subscription(t *testing.T) {
	rawSubscription := "dm1lc3M6Ly9leGFtcGxlCg==" // vmess://example in base64
	lines, err := decodeBase64Subscription(rawSubscription)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(lines) != 1 || lines[0] != "vmess://example" {
		t.Errorf("unexpected decoded lines: %v", lines)
	}
}

func TestWasmDecodeBase64RawAndEmpty(t *testing.T) {
	lines, err := decodeBase64Subscription("   ")
	if err != nil {
		t.Fatalf("unexpected error on empty: %v", err)
	}
	if len(lines) != 0 {
		t.Errorf("expected 0 lines, got %d", len(lines))
	}
}

func TestWasmProcessNodesJSON(t *testing.T) {
	nodeJSON := `[{"server":"8.8.8.8","port":443,"protocol":"vless","tag":"Google DNS"}]`
	resJSON, err := processNodesJSON(nodeJSON)
	if err != nil {
		t.Fatalf("process error: %v", err)
	}
	var res []map[string]any
	if err := json.Unmarshal([]byte(resJSON), &res); err != nil {
		t.Fatalf("json parse error: %v", err)
	}
	if len(res) != 1 {
		t.Errorf("expected 1 node, got %d", len(res))
	}
}
