// Package parse implements multi-protocol proxy subscription and tunnel decoders.
// Source: https://github.com/vmihailenco/msgpack (MessagePack specs)
// Source: https://pkg.go.dev/crypto/cipher#NewCFBDecrypter (Go crypto/cipher CFB specification)
package parse_test

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"encoding/json"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/parse"
	"github.com/vmihailenco/msgpack"
)

func TestDarkTunnelDecrypt_Success(t *testing.T) {
	// Prepare synthetic inner DarkTunnel payload
	rawV2RayJSON := `{"outbounds":[{"protocol":"vless","settings":{"vnext":[{"address":"1.1.1.1","port":443}]}}]}`

	key192 := []byte("F)J@NcRfUjXn2r4u7x!A%D*G")
	ivBytes, _ := hex.DecodeString("232e39185523184a5723586242200e05")

	// Encrypt inner V2Ray payload using AES-192-CFB
	block192, err := aes.NewCipher(key192)
	if err != nil {
		t.Fatalf("failed to create inner cipher: %v", err)
	}
	innerEncrypted := make([]byte, len(rawV2RayJSON))
	stream192 := cipher.NewCFBEncrypter(block192, ivBytes)
	stream192.XORKeyStream(innerEncrypted, []byte(rawV2RayJSON))

	// Pack into DarkConfig struct for msgpack
	innerMap := map[string]interface{}{
		"EncryptedLockedConfig": innerEncrypted,
		"ConfigName":            "TestDarkTunnel",
		"Protocol":              "v2ray",
	}
	packedBytes, err := msgpack.Marshal(innerMap)
	if err != nil {
		t.Fatalf("failed to msgpack marshal: %v", err)
	}

	// Encrypt outer payload using AES-256-CFB
	key256 := []byte("$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd")
	block256, err := aes.NewCipher(key256)
	if err != nil {
		t.Fatalf("failed to create outer cipher: %v", err)
	}
	outerEncrypted := make([]byte, len(packedBytes))
	stream256 := cipher.NewCFBEncrypter(block256, ivBytes)
	stream256.XORKeyStream(outerEncrypted, packedBytes)

	// Wrap in outer JSON
	outerJSON, err := json.Marshal(map[string]interface{}{
		"encryptedLockedConfig": outerEncrypted,
	})
	if err != nil {
		t.Fatalf("failed to json marshal: %v", err)
	}

	// Decrypt using HUNTX parser
	decrypted, err := parse.DecryptDarkTunnel(string(outerJSON))
	if err != nil {
		t.Fatalf("DecryptDarkTunnel failed: %v", err)
	}

	if !bytes.Contains([]byte(decrypted), []byte("1.1.1.1")) {
		t.Errorf("expected decrypted payload to contain 1.1.1.1, got %s", decrypted)
	}
}

func TestDarkTunnelDecrypt_InvalidInputs(t *testing.T) {
	tests := []struct {
		name    string
		payload string
	}{
		{"EmptyString", ""},
		{"MalformedJSON", "{not-valid-json"},
		{"MissingField", `{"otherField": "abc"}`},
		{"CorruptedCiphertext", `{"encryptedLockedConfig": [1, 2, 3]}`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := parse.DecryptDarkTunnel(tt.payload)
			if err == nil {
				t.Errorf("expected error for %s, got nil", tt.name)
			}
		})
	}
}
