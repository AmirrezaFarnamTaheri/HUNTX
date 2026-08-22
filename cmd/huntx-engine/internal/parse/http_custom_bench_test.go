// Package parse_test benchmarks multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
package parse_test

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"fmt"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/parse"
)

func BenchmarkDecryptHTTPCustom_RSA1024(b *testing.B) {
	derBytes, _ := base64.StdEncoding.DecodeString(parse.HTTPCustomPKCS1KeysB64[0])
	privKey, _ := x509.ParsePKCS1PrivateKey(derBytes)

	payload := "vless://user-uuid-12345@1.1.1.1:443?security=tls&type=ws#Benchmark-Node"
	var cipherBytes []byte
	chunkSize := 50
	for i := 0; i < len(payload); i += chunkSize {
		end := i + chunkSize
		if end > len(payload) {
			end = len(payload)
		}
		chunk := []byte(payload[i:end])
		encryptedChunk, _ := rsa.EncryptPKCS1v15(rand.Reader, &privKey.PublicKey, chunk)
		cipherBytes = append(cipherBytes, encryptedChunk...)
	}

	b64Payload := base64.StdEncoding.EncodeToString(cipherBytes)
	link := fmt.Sprintf("happ://crypt/%s", b64Payload)

	b.ReportAllocs()
	b.SetBytes(int64(len(link)))
	b.ResetTimer()

	for b.Loop() {
		res, err := parse.DecryptHTTPCustom(link)
		if err != nil || len(res) == 0 {
			b.Fatalf("decrypt failed: %v", err)
		}
	}
}

func BenchmarkDecryptHTTPCustom_RSA4096(b *testing.B) {
	derBytes, _ := base64.StdEncoding.DecodeString(parse.HTTPCustomPKCS1KeysB64[1])
	privKey, _ := x509.ParsePKCS1PrivateKey(derBytes)

	payload := "vmess://eyJhZGQiOiIxLjIuMy40IiwicG9ydCI6NDQzLCJpZCI6IjEyMzQ1In0="
	var cipherBytes []byte
	chunkSize := 100
	for i := 0; i < len(payload); i += chunkSize {
		end := i + chunkSize
		if end > len(payload) {
			end = len(payload)
		}
		chunk := []byte(payload[i:end])
		encryptedChunk, _ := rsa.EncryptPKCS1v15(rand.Reader, &privKey.PublicKey, chunk)
		cipherBytes = append(cipherBytes, encryptedChunk...)
	}

	b64Payload := base64.StdEncoding.EncodeToString(cipherBytes)
	link := fmt.Sprintf("happ://crypt2/%s", b64Payload)

	b.ReportAllocs()
	b.SetBytes(int64(len(link)))
	b.ResetTimer()

	for b.Loop() {
		res, err := parse.DecryptHTTPCustom(link)
		if err != nil || len(res) == 0 {
			b.Fatalf("decrypt failed: %v", err)
		}
	}
}
