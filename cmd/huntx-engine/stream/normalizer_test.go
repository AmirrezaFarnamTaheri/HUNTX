// Package stream_test validates high-throughput proxy ingestion normalization and deduplication.
// Source: HUNTX Master Porting Compendium §4 & §8
package stream_test

import (
	"bytes"
	"context"
	"strings"
	"testing"
	"time"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
)

func TestNormalizeURI_Vless(t *testing.T) {
	raw := "vless://a1b2c3d4-e5f6-7890-abcd-ef1234567890@198.51.100.1:443?encryption=none&security=reality&sni=speed.cloudflare.com&fp=chrome&pbk=1234567890abcdef1234567890abcdef1234567890a&sid=12345678&type=grpc&serviceName=grpc-sub#%F0%9F%87%A9%F0%9F%87%AA%20DE%20%7C%20Join%20%40free_proxy_channel"
	node, err := stream.NormalizeURI(raw)
	if err != nil {
		t.Fatalf("unexpected error normalizing vless URI: %v", err)
	}

	if node.Protocol != "vless" {
		t.Errorf("expected protocol vless, got %s", node.Protocol)
	}
	if node.Host != "198.51.100.1" {
		t.Errorf("expected host 198.51.100.1, got %s", node.Host)
	}
	if node.Port != 443 {
		t.Errorf("expected port 443, got %d", node.Port)
	}
	if node.UUID != "a1b2c3d4-e5f6-7890-abcd-ef1234567890" {
		t.Errorf("expected uuid, got %s", node.UUID)
	}
	if node.Security != "reality" {
		t.Errorf("expected security reality, got %s", node.Security)
	}
	if node.SNI != "speed.cloudflare.com" {
		t.Errorf("expected sni speed.cloudflare.com, got %s", node.SNI)
	}
	if node.Network != "grpc" {
		t.Errorf("expected network grpc, got %s", node.Network)
	}
	if node.ServiceName != "grpc-sub" {
		t.Errorf("expected serviceName grpc-sub, got %s", node.ServiceName)
	}
	if strings.Contains(node.Remark, "@free_proxy_channel") {
		t.Errorf("expected remark to be sanitized of channel spam, got %s", node.Remark)
	}
}

func TestNormalizeURI_VMessBase64(t *testing.T) {
	// Base64 JSON for {"v":"2","ps":"🚀 Frankfurt High Speed @channel","add":"198.51.100.2","port":"8443","id":"b2c3d4e5-f6a7-8901-bcde-f12345678901","aid":"0","net":"ws","path":"/vmess-ws","tls":"tls","sni":"vmess.example.com"}
	raw := "vmess://eyJ2IjoiMiIsInBzIjoi8J+agCBGcmFua2Z1cnQgSGlnaCBTcGVlZCBAY2hhbm5lbCIsImFkZCI6IjE5OC41MS4xMDAuMiIsInBvcnQiOiI4NDQzIiwiaWQiOiJiMmMzZDRlNS1mNmE3LTg5MDEtYmNkZS1mMTIzNDU2Nzg5MDEiLCJhaWQiOiIwIiwibmV0Ijoid3MiLCJwYXRoIjoiL3ZtZXNzLXdzIiwidGxzIjoidGxzIiwic25pIjoidm1lc3MuZXhhbXBsZS5jb20ifQ=="
	node, err := stream.NormalizeURI(raw)
	if err != nil {
		t.Fatalf("unexpected error normalizing vmess URI: %v", err)
	}

	if node.Protocol != "vmess" {
		t.Errorf("expected protocol vmess, got %s", node.Protocol)
	}
	if node.Host != "198.51.100.2" {
		t.Errorf("expected host 198.51.100.2, got %s", node.Host)
	}
	if node.Port != 8443 {
		t.Errorf("expected port 8443, got %d", node.Port)
	}
	if node.UUID != "b2c3d4e5-f6a7-8901-bcde-f12345678901" {
		t.Errorf("expected uuid, got %s", node.UUID)
	}
	if node.Network != "ws" {
		t.Errorf("expected network ws, got %s", node.Network)
	}
	if node.Path != "/vmess-ws" {
		t.Errorf("expected path /vmess-ws, got %s", node.Path)
	}
	if node.Security != "tls" {
		t.Errorf("expected security tls, got %s", node.Security)
	}
	if node.SNI != "vmess.example.com" {
		t.Errorf("expected sni vmess.example.com, got %s", node.SNI)
	}
	if strings.Contains(node.Remark, "@channel") {
		t.Errorf("expected remark to be sanitized of channel spam, got %s", node.Remark)
	}
}

func TestNormalizeURI_Trojan(t *testing.T) {
	raw := "trojan://trojan-password-1234@198.51.100.3:443?security=tls&sni=trojan.sni.com&type=tcp#Trojan-Node-1"
	node, err := stream.NormalizeURI(raw)
	if err != nil {
		t.Fatalf("unexpected error normalizing trojan URI: %v", err)
	}

	if node.Protocol != "trojan" {
		t.Errorf("expected protocol trojan, got %s", node.Protocol)
	}
	if node.Host != "198.51.100.3" {
		t.Errorf("expected host 198.51.100.3, got %s", node.Host)
	}
	if node.Password != "trojan-password-1234" {
		t.Errorf("expected password trojan-password-1234, got %s", node.Password)
	}
}

func TestNormalizeURI_ShadowsocksSIP002(t *testing.T) {
	// Base64("chacha20-ietf-poly1305:secretpassword") = "Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpzZWNyZXRwYXNzd29yZA=="
	raw := "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpzZWNyZXRwYXNzd29yZA==@198.51.100.4:8388#SS-Node"
	node, err := stream.NormalizeURI(raw)
	if err != nil {
		t.Fatalf("unexpected error normalizing ss URI: %v", err)
	}

	if node.Protocol != "shadowsocks" {
		t.Errorf("expected protocol shadowsocks, got %s", node.Protocol)
	}
	if node.Host != "198.51.100.4" {
		t.Errorf("expected host 198.51.100.4, got %s", node.Host)
	}
	if node.Cipher != "chacha20-ietf-poly1305" {
		t.Errorf("expected cipher chacha20-ietf-poly1305, got %s", node.Cipher)
	}
	if node.Password != "secretpassword" {
		t.Errorf("expected password secretpassword, got %s", node.Password)
	}
}

func TestNormalizeURI_Hysteria2(t *testing.T) {
	raw := "hysteria2://auth-token-1234@hy2.example.com:443/?sni=hy2.example.com&insecure=1#Hy2-Test"
	node, err := stream.NormalizeURI(raw)
	if err != nil {
		t.Fatalf("unexpected error normalizing hy2 URI: %v", err)
	}

	if node.Protocol != "hysteria2" {
		t.Errorf("expected protocol hysteria2, got %s", node.Protocol)
	}
	if node.Host != "hy2.example.com" {
		t.Errorf("expected host hy2.example.com, got %s", node.Host)
	}
	if node.Password != "auth-token-1234" {
		t.Errorf("expected password auth-token-1234, got %s", node.Password)
	}
}

func TestNormalizeURI_TUIC(t *testing.T) {
	raw := "tuic://uuid-user:pass-token@tuic.example.com:8443?congestion_control=bbr&alpn=h3&sni=tuic.example.com#TUIC-Node"
	node, err := stream.NormalizeURI(raw)
	if err != nil {
		t.Fatalf("unexpected error normalizing tuic URI: %v", err)
	}

	if node.Protocol != "tuic" {
		t.Errorf("expected protocol tuic, got %s", node.Protocol)
	}
	if node.Host != "tuic.example.com" {
		t.Errorf("expected host tuic.example.com, got %s", node.Host)
	}
	if node.UUID != "uuid-user" {
		t.Errorf("expected uuid uuid-user, got %s", node.UUID)
	}
	if node.Password != "pass-token" {
		t.Errorf("expected password pass-token, got %s", node.Password)
	}
}

func TestSanitizeRemark(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"🇩🇪 DE | Free VPN @tg_vpn_channel http://t.me/vpn", "DE | Free VPN"},
		{"[Fast] 🚀 US Premium (50MB/s) @proxy_free", "[Fast] US Premium (50MB/s)"},
		{"   Clean Name   ", "Clean Name"},
		{"", "HUNTX-Node"},
	}

	for _, tt := range tests {
		got := stream.SanitizeRemark(tt.input)
		if got != tt.expected {
			t.Errorf("SanitizeRemark(%q) = %q; want %q", tt.input, got, tt.expected)
		}
	}
}

func TestStreamDeduplicator(t *testing.T) {
	dedup := stream.NewStreamDeduplicator(1000)

	node1, _ := stream.NormalizeURI("vless://a1b2c3d4-e5f6-7890-abcd-ef1234567890@198.51.100.1:443?security=reality#Node1")
	node2, _ := stream.NormalizeURI("vless://a1b2c3d4-e5f6-7890-abcd-ef1234567890@198.51.100.1:443?security=reality#Node1-DifferentRemark")
	node3, _ := stream.NormalizeURI("vless://diff-uuid-000000000000000000000000000000@198.51.100.1:443?security=reality#Node3")

	if dedup.IsDuplicate(node1) {
		t.Errorf("expected node1 to be fresh, reported duplicate")
	}

	// Adding node1
	if !dedup.Add(node1) {
		t.Errorf("expected node1 to be added")
	}

	// node2 has same identity key (uuid + host + port), should be duplicate
	if !dedup.IsDuplicate(node2) {
		t.Errorf("expected node2 to be duplicate of node1")
	}

	// Adding node2 should return false (already present)
	if dedup.Add(node2) {
		t.Errorf("expected Add(node2) to return false for duplicate")
	}

	// node3 is different
	if dedup.IsDuplicate(node3) {
		t.Errorf("expected node3 to be fresh")
	}
	if !dedup.Add(node3) {
		t.Errorf("expected node3 to be added")
	}

	if dedup.Count() != 2 {
		t.Errorf("expected dedup count 2, got %d", dedup.Count())
	}
}

func TestStreamIngest(t *testing.T) {
	rawInput := `
vless://uuid-1@198.51.100.1:443?security=tls#Node-1
vmess://eyJ2IjoiMiIsInBzIjoiTm9kZS0yIiwiYWRkIjoiMTk4LjUxLjEwMC4yIiwicG9ydCI6IjQ0MyIsImlkIjoidXVpZC0yIiwibmV0Ijoid3MifQ==
trojan://pass-3@198.51.100.3:443#Node-3
invalid-garbage-line-to-skip
vless://uuid-1@198.51.100.1:443?security=tls#Node-1-Duplicate
`
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	reader := bytes.NewReader([]byte(rawInput))
	ch := stream.Ingest(ctx, reader, 100)

	var nodes []stream.NormalizedNode
	for node := range ch {
		nodes = append(nodes, node)
	}

	// Expect 3 unique valid nodes (Node 1, Node 2, Node 3)
	if len(nodes) != 3 {
		t.Fatalf("expected 3 unique normalized nodes, got %d", len(nodes))
	}

	if nodes[0].Protocol != "vless" || nodes[0].Host != "198.51.100.1" {
		t.Errorf("unexpected node[0]: %+v", nodes[0])
	}
	if nodes[1].Protocol != "vmess" || nodes[1].Host != "198.51.100.2" {
		t.Errorf("unexpected node[1]: %+v", nodes[1])
	}
	if nodes[2].Protocol != "trojan" || nodes[2].Host != "198.51.100.3" {
		t.Errorf("unexpected node[2]: %+v", nodes[2])
	}
}

func TestFormatEnrichedRemark(t *testing.T) {
	node := stream.NormalizedNode{
		Protocol: "vless",
		Host:     "speed.cloudflare.com",
		Port:     443,
		Security: "reality",
		Network:  "grpc",
		SNI:      "speed.cloudflare.com",
	}

	opts := stream.EnrichedRemarkOptions{
		Country:      "DE",
		Operator:     "CF",
		LatencyMs:    38,
		HealthScore:  95.0,
		HealthGrade:  "A+",
		Index:        1,
		IncludeStats: true,
	}

	remark := stream.FormatEnrichedRemark(node, opts)
	if !strings.Contains(remark, "DE-CF") {
		t.Errorf("expected remark to contain DE-CF, got %q", remark)
	}
	if !strings.Contains(remark, "VLESS-REALITY-GRPC") {
		t.Errorf("expected remark to contain VLESS-REALITY-GRPC, got %q", remark)
	}
	if !strings.Contains(remark, "⚡38ms") {
		t.Errorf("expected remark to contain ⚡38ms, got %q", remark)
	}
	if !strings.Contains(remark, "⭐A+") {
		t.Errorf("expected remark to contain ⭐A+, got %q", remark)
	}
	if !strings.Contains(remark, "#001") {
		t.Errorf("expected remark to contain #001, got %q", remark)
	}
}

func TestEnrichURI(t *testing.T) {
	rawVless := "vless://uuid-1@198.51.100.1:443?security=reality&type=grpc#OldSpam"
	opts := stream.EnrichedRemarkOptions{
		Country:     "NL",
		LatencyMs:   45,
		HealthGrade: "A",
		Index:       5,
	}

	enriched, err := stream.EnrichURI(rawVless, opts)
	if err != nil {
		t.Fatalf("unexpected error enriching URI: %v", err)
	}
	if !strings.Contains(enriched, "vless://uuid-1@198.51.100.1:443") {
		t.Errorf("expected base URI preserved, got %q", enriched)
	}
	if strings.Contains(enriched, "OldSpam") {
		t.Errorf("expected old remark replaced, got %q", enriched)
	}
}
