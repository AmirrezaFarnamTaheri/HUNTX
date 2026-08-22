// Package parse implements multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/crypto/rsa (RSA PKCS#1 v1.5 specifications)
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

func TestHTTPCustom_RSA1024_Crypt_Success(t *testing.T) {
	// Parse private key for crypt (RSA-1024)
	derBytes, err := base64.StdEncoding.DecodeString(parse.HTTPCustomPKCS1KeysB64[0])
	if err != nil {
		t.Fatalf("decode b64 key failed: %v", err)
	}
	privKey, err := x509.ParsePKCS1PrivateKey(derBytes)
	if err != nil {
		t.Fatalf("parse pkcs1 key failed: %v", err)
	}

	payload := "vless://user-uuid-12345@1.1.1.1:443?security=tls&type=ws#Sample-Node"

	// Encrypt in chunks (max plaintext chunk size for RSA-1024 PKCS#1 v1.5 is 128 - 11 = 117 bytes)
	var cipherBytes []byte
	chunkSize := 50
	for i := 0; i < len(payload); i += chunkSize {
		end := i + chunkSize
		if end > len(payload) {
			end = len(payload)
		}
		chunk := []byte(payload[i:end])
		encryptedChunk, err := rsa.EncryptPKCS1v15(rand.Reader, &privKey.PublicKey, chunk)
		if err != nil {
			t.Fatalf("encrypt rsa failed: %v", err)
		}
		cipherBytes = append(cipherBytes, encryptedChunk...)
	}

	b64Payload := base64.StdEncoding.EncodeToString(cipherBytes)
	link := fmt.Sprintf("happ://crypt/%s", b64Payload)

	decrypted, err := parse.DecryptHTTPCustom(link)
	if err != nil {
		t.Fatalf("DecryptHTTPCustom failed: %v", err)
	}

	if decrypted != payload {
		t.Errorf("decrypted payload mismatch: expected %s, got %s", payload, decrypted)
	}
}

func TestHTTPCustom_RSA4096_Crypt2_Success(t *testing.T) {
	// Parse private key for crypt2 (RSA-4096)
	derBytes, err := base64.StdEncoding.DecodeString(parse.HTTPCustomPKCS1KeysB64[1])
	if err != nil {
		t.Fatalf("decode b64 key failed: %v", err)
	}
	privKey, err := x509.ParsePKCS1PrivateKey(derBytes)
	if err != nil {
		t.Fatalf("parse pkcs1 key failed: %v", err)
	}

	payload := "vmess://eyJhZGQiOiIxLjIuMy40IiwicG9ydCI6NDQzLCJpZCI6IjEyMzQ1In0="

	var cipherBytes []byte
	chunkSize := 100
	for i := 0; i < len(payload); i += chunkSize {
		end := i + chunkSize
		if end > len(payload) {
			end = len(payload)
		}
		chunk := []byte(payload[i:end])
		encryptedChunk, err := rsa.EncryptPKCS1v15(rand.Reader, &privKey.PublicKey, chunk)
		if err != nil {
			t.Fatalf("encrypt rsa failed: %v", err)
		}
		cipherBytes = append(cipherBytes, encryptedChunk...)
	}

	b64Payload := base64.StdEncoding.EncodeToString(cipherBytes)
	link := fmt.Sprintf("happ://crypt2/%s", b64Payload)

	decrypted, err := parse.DecryptHTTPCustom(link)
	if err != nil {
		t.Fatalf("DecryptHTTPCustom failed: %v", err)
	}

	if decrypted != payload {
		t.Errorf("decrypted payload mismatch: expected %s, got %s", payload, decrypted)
	}
}

func TestHTTPCustom_InvalidLinks(t *testing.T) {
	tests := []struct {
		name string
		link string
	}{
		{"EmptyLink", ""},
		{"InvalidPrefix", "custom://unknown/12345"},
		{"CorruptBase64", "happ://crypt/%%%invalid_b64%%%"},
		{"UnalignedBytes", "happ://crypt/QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo="},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := parse.DecryptHTTPCustom(tt.link)
			if err == nil {
				t.Errorf("expected error for link %s, got nil", tt.name)
			}
		})
	}
}
