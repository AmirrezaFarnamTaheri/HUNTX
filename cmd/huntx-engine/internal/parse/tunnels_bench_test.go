// Package parse_test benchmarks multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package parse_test

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha1"
	"encoding/base64"
	"encoding/hex"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/parse"
)

func BenchmarkDecryptHAT(b *testing.B) {
	hasher := sha1.New()
	hasher.Write([]byte("8515D40BD04D8C97"))
	key := hasher.Sum(nil)[:16]

	payload := `{"server":"198.51.100.10","port":443,"protocol":"hat"}`
	padLen := aes.BlockSize - (len(payload) % aes.BlockSize)
	padded := append([]byte(payload), bytes.Repeat([]byte{byte(padLen)}, padLen)...)

	block, _ := aes.NewCipher(key)
	encrypted := make([]byte, len(padded))
	for i := 0; i < len(padded); i += aes.BlockSize {
		block.Encrypt(encrypted[i:i+aes.BlockSize], padded[i:i+aes.BlockSize])
	}
	b64Payload := base64.StdEncoding.EncodeToString(encrypted)

	b.ReportAllocs()
	b.SetBytes(int64(len(b64Payload)))
	b.ResetTimer()

	for b.Loop() {
		_, _ = parse.DecryptHAT(b64Payload)
	}
}

func BenchmarkDecryptNetMod(b *testing.B) {
	key := []byte("_netsyna_netmod_")
	payload := "vless://uuid-12345@198.51.100.20:443?type=ws#BenchmarkNetMod"
	padLen := (16 - (len(payload) % 16)) % 16
	padded := append([]byte(payload), make([]byte, padLen)...)

	block, _ := aes.NewCipher(key)
	encrypted := make([]byte, len(padded))
	for i := 0; i < len(padded); i += aes.BlockSize {
		block.Encrypt(encrypted[i:i+aes.BlockSize], padded[i:i+aes.BlockSize])
	}
	b64Payload := base64.StdEncoding.EncodeToString(encrypted)

	b.ReportAllocs()
	b.SetBytes(int64(len(b64Payload)))
	b.ResetTimer()

	for b.Loop() {
		_, _ = parse.DecryptNetMod("nm-vless", b64Payload)
	}
}

func BenchmarkDecryptSlipNet(b *testing.B) {
	key, _ := hex.DecodeString(parse.SlipNetKeyHex)
	rawProfile := "28|SSH|Node1|example.com|8.8.8.8|1|1|US|443|1.2.3.4|1|pk|user|pass|1|sshuser|sshpass|22|1|ssh.host|1|https://doh|udp|pwd|key64|pass64|tor|auth|9000|naiveusr|naivepass|0|hash|2027|1|dev1|0|res|0|1024|1080|1|A|255|100|30|1|10|10|16|1|sni|h|80|ch|1|/ws|1|ch|sshpayload|auto|1|vless-uuid|tls|ws|/vless|1.1.1.1|443|1|rand|50||1|1|1|64|decoy.com|1400|vless.sni.com|"

	block, _ := aes.NewCipher(key)
	aesgcm, _ := cipher.NewGCM(block)
	nonce := make([]byte, 12)
	rand.Read(nonce)

	ciphertext := aesgcm.Seal(nil, nonce, []byte(rawProfile), nil)
	blob := append([]byte{0x01}, nonce...)
	blob = append(blob, ciphertext...)
	b64Blob := base64.StdEncoding.EncodeToString(blob)

	b.ReportAllocs()
	b.SetBytes(int64(len(b64Blob)))
	b.ResetTimer()

	for b.Loop() {
		_, _ = parse.DecryptSlipNet(b64Blob)
	}
}
