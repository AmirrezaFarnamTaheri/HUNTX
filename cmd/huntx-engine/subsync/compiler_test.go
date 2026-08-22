// Package subsync_test validates universal subscription compiling for Sing-box, Clash Meta, and Xray.
// Source: HUNTX Master Porting Compendium §4 & §8
package subsync_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/subsync"
)

func TestCompileSingBox_VlessReality(t *testing.T) {
	node := stream.NormalizedNode{
		Protocol:    "vless",
		Host:        "198.51.100.1",
		Port:        443,
		UUID:        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
		Security:    "reality",
		SNI:         "speed.cloudflare.com",
		Fingerprint: "chrome",
		PublicKey:   "abcdef1234567890abcdef1234567890abcdef12345",
		ShortID:     "12345678",
		Network:     "grpc",
		ServiceName: "grpc-service",
		Remark:      "Singbox-Reality-Node",
	}

	opts := subsync.CompileOptions{
		EnableFragment:   true,
		FragmentLength:   "10-20",
		FragmentInterval: "10-20",
	}

	outbound, err := subsync.CompileSingBox(node, opts)
	if err != nil {
		t.Fatalf("unexpected error compiling sing-box: %v", err)
	}

	data, err := json.Marshal(outbound)
	if err != nil {
		t.Fatalf("failed to marshal sing-box json: %v", err)
	}
	jsonStr := string(data)

	if !strings.Contains(jsonStr, `"type":"vless"`) {
		t.Errorf("expected type vless, got %s", jsonStr)
	}
	if !strings.Contains(jsonStr, `"server":"198.51.100.1"`) {
		t.Errorf("expected server 198.51.100.1, got %s", jsonStr)
	}
	if !strings.Contains(jsonStr, `"public_key":"abcdef1234567890abcdef1234567890abcdef12345"`) {
		t.Errorf("expected reality public_key, got %s", jsonStr)
	}
	if !strings.Contains(jsonStr, `"service_name":"grpc-service"`) {
		t.Errorf("expected grpc service_name, got %s", jsonStr)
	}
}

func TestCompileClashMeta_VlessReality(t *testing.T) {
	node := stream.NormalizedNode{
		Protocol:    "vless",
		Host:        "198.51.100.1",
		Port:        443,
		UUID:        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
		Security:    "reality",
		SNI:         "speed.cloudflare.com",
		Fingerprint: "chrome",
		PublicKey:   "abcdef1234567890abcdef1234567890abcdef12345",
		ShortID:     "12345678",
		Network:     "grpc",
		ServiceName: "grpc-service",
		Remark:      "Clash-Reality-Node",
	}

	opts := subsync.CompileOptions{
		EnableFragment: true,
	}

	yamlMap, err := subsync.CompileClashMeta(node, opts)
	if err != nil {
		t.Fatalf("unexpected error compiling clash meta: %v", err)
	}

	if yamlMap["name"] != "Clash-Reality-Node" {
		t.Errorf("expected name Clash-Reality-Node, got %v", yamlMap["name"])
	}
	if yamlMap["type"] != "vless" {
		t.Errorf("expected type vless, got %v", yamlMap["type"])
	}
	if yamlMap["server"] != "198.51.100.1" {
		t.Errorf("expected server 198.51.100.1, got %v", yamlMap["server"])
	}
	if yamlMap["uuid"] != "a1b2c3d4-e5f6-7890-abcd-ef1234567890" {
		t.Errorf("expected uuid, got %v", yamlMap["uuid"])
	}
	if yamlMap["network"] != "grpc" {
		t.Errorf("expected network grpc, got %v", yamlMap["network"])
	}

	realityOpts, ok := yamlMap["reality-opts"].(map[string]interface{})
	if !ok || realityOpts["public-key"] != "abcdef1234567890abcdef1234567890abcdef12345" {
		t.Errorf("expected reality-opts public-key, got %v", yamlMap["reality-opts"])
	}
}

func TestCompileClashMeta_VMessWS(t *testing.T) {
	node := stream.NormalizedNode{
		Protocol:   "vmess",
		Host:       "198.51.100.2",
		Port:       8443,
		UUID:       "b2c3d4e5-f6a7-8901-bcde-f12345678901",
		Security:   "tls",
		SNI:        "vmess.sni.com",
		Network:    "ws",
		Path:       "/vmess-path",
		HostHeader: "vmess.sni.com",
		Remark:     "VMess-WS-Node",
	}

	opts := subsync.CompileOptions{
		EnableEarlyData: true,
	}

	yamlMap, err := subsync.CompileClashMeta(node, opts)
	if err != nil {
		t.Fatalf("unexpected error compiling clash vmess: %v", err)
	}

	if yamlMap["type"] != "vmess" {
		t.Errorf("expected type vmess, got %v", yamlMap["type"])
	}
	wsOpts, ok := yamlMap["ws-opts"].(map[string]interface{})
	if !ok {
		t.Fatalf("missing ws-opts")
	}
	pathStr, _ := wsOpts["path"].(string)
	if !strings.Contains(pathStr, "ed=2560") {
		t.Errorf("expected early data ?ed=2560 in path, got %s", pathStr)
	}
}
