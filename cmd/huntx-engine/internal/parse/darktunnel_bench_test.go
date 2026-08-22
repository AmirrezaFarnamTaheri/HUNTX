// Package parse_test benchmarks multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package parse_test

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"encoding/json"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/parse"
	"github.com/vmihailenco/msgpack"
)

func BenchmarkDecryptDarkTunnel(b *testing.B) {
	innerMap := map[string]interface{}{
		"ConfigName": "Benchmark-DarkTunnel-Node",
		"Server":     "198.51.100.1",
		"Port":       443,
		"Protocol":   "vmess",
		"UUID":       "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
	}

	packed, err := msgpack.Marshal(innerMap)
	if err != nil {
		b.Fatalf("setup msgpack marshal failed: %v", err)
	}

	iv, _ := hex.DecodeString(parse.DarkTunnelIVHex)
	block, err := aes.NewCipher(parse.DarkTunnelKey256)
	if err != nil {
		b.Fatalf("setup cipher failed: %v", err)
	}

	ciphertext := make([]byte, len(packed))
	stream := cipher.NewCFBEncrypter(block, iv)
	stream.XORKeyStream(ciphertext, packed)

	outer := parse.DarkTunnelPayload{
		EncryptedLockedConfig: ciphertext,
	}
	outerBytes, err := json.Marshal(outer)
	if err != nil {
		b.Fatalf("setup outer json marshal failed: %v", err)
	}
	payloadStr := string(outerBytes)

	b.ReportAllocs()
	b.SetBytes(int64(len(payloadStr)))
	b.ResetTimer()

	for b.Loop() {
		res, err := parse.DecryptDarkTunnel(payloadStr)
		if err != nil || len(res) == 0 {
			b.Fatalf("decrypt failed: %v", err)
		}
	}
}
