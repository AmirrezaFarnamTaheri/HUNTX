// Package stream_test benchmarks URI normalization, deduplication, and streaming ingestion.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package stream_test

import (
	"bytes"
	"context"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
)

func BenchmarkNormalizeURI_Vless(b *testing.B) {
	raw := "vless://a1b2c3d4-e5f6-7890-abcd-ef1234567890@198.51.100.1:443?encryption=none&security=reality&sni=speed.cloudflare.com&fp=chrome&pbk=1234567890abcdef1234567890abcdef1234567890a&sid=12345678&type=grpc&serviceName=grpc-sub#DE-Node"

	b.ReportAllocs()
	b.SetBytes(int64(len(raw)))
	b.ResetTimer()

	for b.Loop() {
		_, _ = stream.NormalizeURI(raw)
	}
}

func BenchmarkNormalizeURI_VMess(b *testing.B) {
	raw := "vmess://eyJ2IjoiMiIsInBzIjoi8J+agCBGcmFua2Z1cnQgSGlnaCBTcGVlZCBAY2hhbm5lbCIsImFkZCI6IjE5OC41MS4xMDAuMiIsInBvcnQiOiI4NDQzIiwiaWQiOiJiMmMzZDRlNS1mNmE3LTg5MDEtYmNkZS1mMTIzNDU2Nzg5MDEiLCJhaWQiOiIwIiwibmV0Ijoid3MiLCJwYXRoIjoiL3ZtZXNzLXdzIiwidGxzIjoidGxzIiwic25pIjoidm1lc3MuZXhhbXBsZS5jb20ifQ=="

	b.ReportAllocs()
	b.SetBytes(int64(len(raw)))
	b.ResetTimer()

	for b.Loop() {
		_, _ = stream.NormalizeURI(raw)
	}
}

func BenchmarkSanitizeRemark(b *testing.B) {
	raw := "🇩🇪 DE | Free VPN @tg_vpn_channel http://t.me/vpn [50MB/s]"

	b.ReportAllocs()
	b.SetBytes(int64(len(raw)))
	b.ResetTimer()

	for b.Loop() {
		_ = stream.SanitizeRemark(raw)
	}
}

func BenchmarkStreamDeduplicator_Add(b *testing.B) {
	dedup := stream.NewStreamDeduplicator(100000)
	node, _ := stream.NormalizeURI("vless://a1b2c3d4-e5f6-7890-abcd-ef1234567890@198.51.100.1:443?security=reality#BenchmarkNode")

	b.ReportAllocs()
	b.ResetTimer()

	for b.Loop() {
		_ = dedup.Add(node)
	}
}

func BenchmarkStreamIngest_1000Nodes(b *testing.B) {
	var buf bytes.Buffer
	for i := 0; i < 1000; i++ {
		buf.WriteString("vless://a1b2c3d4-e5f6-7890-abcd-ef1234567890@198.51.100.1:443?security=reality#BenchmarkNode\n")
	}
	data := buf.Bytes()

	b.ReportAllocs()
	b.SetBytes(int64(len(data)))
	b.ResetTimer()

	for b.Loop() {
		ctx := context.Background()
		r := bytes.NewReader(data)
		ch, errs := stream.Ingest(ctx, r, 256)
		for range ch {
		}
		for range errs {
		}
	}
}
