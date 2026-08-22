// Package subsync_test benchmarks proxy outbound compiling for Sing-box and Clash Meta.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package subsync_test

import (
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/subsync"
)

func BenchmarkCompileSingBox_VlessReality(b *testing.B) {
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
		EnableFragment: true,
	}

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_, _ = subsync.CompileSingBox(node, opts)
	}
}

func BenchmarkCompileClashMeta_VlessReality(b *testing.B) {
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

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_, _ = subsync.CompileClashMeta(node, opts)
	}
}

func BenchmarkBuildXrayFragmentOutbound(b *testing.B) {
	node := stream.NormalizedNode{
		Protocol: "vless",
		Host:     "198.51.100.1",
		Port:     443,
	}
	fragCfg := subsync.FragmentConfig{
		Packets:  "tlshello",
		Length:   "10-20",
		Interval: "10-20",
	}

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_, _ = subsync.BuildXrayFragmentOutbound(node, fragCfg)
	}
}
