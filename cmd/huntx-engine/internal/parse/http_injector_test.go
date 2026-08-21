// Package parse implements multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/golang.org/x/crypto/argon2 (Argon2id KDF specifications)
// Source: https://pkg.go.dev/golang.org/x/crypto/chacha20poly1305 (XChaCha20-Poly1305 specifications)
// Source: https://en.wikipedia.org/wiki/XXTEA (XXTEA block cipher specifications)
package parse_test

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/parse"
)

func TestHTTPInjector_NativeXXTEA(t *testing.T) {
	key := []byte("null=V5kU5+FFrY\x00")
	plaintext := []byte("huntx-secure-ehi-payload-stream-12345678")

	encrypted, err := parse.NativeXXTEAEncrypt(plaintext, key)
	if err != nil {
		t.Fatalf("XXTEA Encrypt failed: %v", err)
	}

	decrypted, err := parse.NativeXXTEADecrypt(encrypted, key)
	if err != nil {
		t.Fatalf("XXTEA Decrypt failed: %v", err)
	}

	// Trim trailing null bytes if length was padded to 4-byte boundaries
	decryptedTrimmed := bytes.TrimRight(decrypted, "\x00")
	if !bytes.Equal(decryptedTrimmed, plaintext) {
		t.Errorf("XXTEA roundtrip mismatch: expected %s, got %s", plaintext, decryptedTrimmed)
	}
}

func TestHTTPInjector_FullStackDecrypt_Success(t *testing.T) {
	// Construct a synthetic EHI payload with nested v2rRawJson
	configMap := map[string]interface{}{
		"v2rRawJson": `{"outbounds":[{"protocol":"vmess","settings":{"vnext":[{"address":"8.8.8.8","port":443}]}}]}`,
		"configSalt": "EVZJNI",
	}
	rawJSON, err := json.Marshal(configMap)
	if err != nil {
		t.Fatalf("marshal config failed: %v", err)
	}

	// 1. XXTEA Encrypt
	xxteaKey := []byte("null=V5kU5+FFrY\x00")
	xxteaEncrypted, err := parse.NativeXXTEAEncrypt(rawJSON, xxteaKey)
	if err != nil {
		t.Fatalf("xxtea encrypt failed: %v", err)
	}

	// 2. Layer 2 AES-128-CBC Encrypt
	l2Key := []byte{0xb2, 0xbc, 0x61, 0x7c, 0x32, 0xd8, 0xb9, 0xeb, 0x19, 0x43, 0xa5, 0xff, 0xa8, 0x05, 0x1e, 0xea}
	iv2 := []byte{0x2c, 0x5d, 0x11, 0x47, 0xbb, 0xad, 0x42, 0x2b, 0x3b, 0x33, 0x4d, 0x4d, 0x23, 0x5f, 0x1a, 0x53}

	padLen := aes.BlockSize - (len(xxteaEncrypted) % aes.BlockSize)
	paddedL2 := append(xxteaEncrypted, bytes.Repeat([]byte{byte(padLen)}, padLen)...)

	blockL2, err := aes.NewCipher(l2Key)
	if err != nil {
		t.Fatalf("cipher l2 failed: %v", err)
	}
	encryptedL2 := make([]byte, len(paddedL2))
	modeL2 := cipher.NewCBCEncrypter(blockL2, iv2)
	modeL2.CryptBlocks(encryptedL2, paddedL2)

	// 3. Colon-separated payload: token0 (iv2 b64) : token1 (garbage/salt) : token2 (encryptedL2 b64)
	token0B64 := base64.StdEncoding.EncodeToString(iv2)
	token1B64 := "DUMMY_SALT_EXTRA_PADDING_12345"
	token2B64 := base64.StdEncoding.EncodeToString(encryptedL2)
	colonFormatted := fmt.Sprintf("%s:%s:%s", token0B64, token1B64, token2B64)

	// 4. Layer 1 AES-256-CBC Encrypt
	l1Key := []byte{0x7e, 0x12, 0x10, 0xf7, 0xaa, 0xb9, 0x56, 0xf7, 0xa6, 0x68, 0xbd, 0xa6, 0xe5, 0x7f, 0xed, 0xdb, 0x7f, 0x84, 0xad, 0x84, 0x0a, 0xef, 0x8d, 0x27, 0xb1, 0xb9, 0x69, 0x95, 0x9b, 0xe3, 0xab, 0x6c}
	standardIV := []byte{0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}

	padLen1 := aes.BlockSize - (len(colonFormatted) % aes.BlockSize)
	paddedL1 := append([]byte(colonFormatted), bytes.Repeat([]byte{byte(padLen1)}, padLen1)...)

	blockL1, err := aes.NewCipher(l1Key)
	if err != nil {
		t.Fatalf("cipher l1 failed: %v", err)
	}
	encryptedL1 := make([]byte, len(paddedL1))
	modeL1 := cipher.NewCBCEncrypter(blockL1, standardIV)
	modeL1.CryptBlocks(encryptedL1, paddedL1)

	// Decrypt using HUNTX HTTP Injector decrypter
	result, err := parse.DecryptHTTPInjector(encryptedL1)
	if err != nil {
		t.Fatalf("DecryptHTTPInjector failed: %v", err)
	}

	if !bytes.Contains([]byte(result), []byte("8.8.8.8")) {
		t.Errorf("expected result to contain 8.8.8.8, got %s", result)
	}
}

func TestHTTPInjector_InvalidInputs(t *testing.T) {
	tests := []struct {
		name string
		data []byte
	}{
		{"NilData", nil},
		{"EmptyData", []byte{}},
		{"TooShort", []byte("short")},
		{"NonBlockAligned", []byte("12345678901234567")},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := parse.DecryptHTTPInjector(tt.data)
			if err == nil {
				t.Errorf("expected error for %s, got nil", tt.name)
			}
		})
	}
}
