// Package subsync_test validates TLS Hello packet fragmentation and evasion strategies.
// Source: HUNTX Master Porting Compendium §4 & §8
package subsync_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/subsync"
)

func TestBuildXrayFragmentConfig(t *testing.T) {
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
		Remark:      "Xray-Fragment-Node",
	}

	fragCfg := subsync.FragmentConfig{
		Packets:  "tlshello",
		Length:   "10-20",
		Interval: "10-20",
	}

	xrayJSON, err := subsync.BuildXrayFragmentOutbound(node, fragCfg)
	if err != nil {
		t.Fatalf("unexpected error building xray config: %v", err)
	}

	data, err := json.Marshal(xrayJSON)
	if err != nil {
		t.Fatalf("failed to marshal xray json: %v", err)
	}
	raw := string(data)

	if !strings.Contains(raw, `"packets":"tlshello"`) {
		t.Errorf("expected packets tlshello, got %s", raw)
	}
	if !strings.Contains(raw, `"length":"10-20"`) {
		t.Errorf("expected length 10-20, got %s", raw)
	}
	if !strings.Contains(raw, `"dialerProxy":"fragment"`) {
		t.Errorf("expected sockopt dialerProxy fragment, got %s", raw)
	}
}

func TestApplyEarlyData(t *testing.T) {
	path1 := "/my-ws-path"
	modified1 := subsync.ApplyEarlyData(path1, 2560)
	if modified1 != "/my-ws-path?ed=2560" {
		t.Errorf("expected /my-ws-path?ed=2560, got %s", modified1)
	}

	path2 := "/ws?mode=fast"
	modified2 := subsync.ApplyEarlyData(path2, 2560)
	if modified2 != "/ws?mode=fast&ed=2560" {
		t.Errorf("expected /ws?mode=fast&ed=2560, got %s", modified2)
	}
}
