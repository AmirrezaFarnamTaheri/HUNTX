// Package parse implements multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/crypto/cipher#NewCFBDecrypter (Go standard library AES-CFB)
// Source: https://github.com/vmihailenco/msgpack (MessagePack deserialization)
package parse

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/vmihailenco/msgpack"
)

var (
	// DarkTunnelKey256 is the outer AES-256-CFB decryption key.
	DarkTunnelKey256 = []byte("$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd")

	// DarkTunnelKey192 is the inner AES-192-CFB decryption key.
	DarkTunnelKey192 = []byte("F)J@NcRfUjXn2r4u7x!A%D*G")

	// DarkTunnelIVHex is the static 16-byte initialization vector in hexadecimal.
	DarkTunnelIVHex = "232e39185523184a5723586242200e05"
)

// DarkTunnelPayload represents the outer JSON structure of a .dark config.
type DarkTunnelPayload struct {
	EncryptedLockedConfig []byte `json:"encryptedLockedConfig"`
}

// DecryptDarkTunnel decrypts a DarkTunnel .dark JSON payload and extracts the plaintext configuration.
func DecryptDarkTunnel(payload string) (string, error) {
	if payload == "" {
		return "", errors.New("darktunnel: empty payload")
	}

	var outer DarkTunnelPayload
	if err := json.Unmarshal([]byte(payload), &outer); err != nil {
		return "", fmt.Errorf("darktunnel: invalid outer json: %w", err)
	}

	if len(outer.EncryptedLockedConfig) == 0 {
		return "", errors.New("darktunnel: missing encryptedLockedConfig in payload")
	}

	iv, err := hex.DecodeString(DarkTunnelIVHex)
	if err != nil {
		return "", fmt.Errorf("darktunnel: invalid iv hex: %w", err)
	}

	// 1. Outer Decryption (AES-256-CFB)
	outerPlaintext, err := decryptAESCFB(outer.EncryptedLockedConfig, DarkTunnelKey256, iv)
	if err != nil {
		return "", fmt.Errorf("darktunnel: outer decryption failed: %w", err)
	}

	// 2. MessagePack Unpacking
	var unpackedMap map[string]interface{}
	if err := msgpack.Unmarshal(outerPlaintext, &unpackedMap); err != nil {
		// Fallback: Check if outer plaintext is already direct JSON or text
		if json.Valid(outerPlaintext) {
			return string(outerPlaintext), nil
		}
		return "", fmt.Errorf("darktunnel: msgpack unpack failed: %w", err)
	}

	// 3. Inner Decryption (AES-192-CFB if nested encrypted config exists)
	if encryptedInner, ok := unpackedMap["EncryptedLockedConfig"].([]byte); ok && len(encryptedInner) > 0 {
		innerPlaintext, err := decryptAESCFB(encryptedInner, DarkTunnelKey192, iv)
		if err == nil && len(innerPlaintext) > 0 {
			unpackedMap["DecryptedConfig"] = string(innerPlaintext)
		}
	}

	// Format final output as indented JSON
	resultBytes, err := json.MarshalIndent(unpackedMap, "", "  ")
	if err != nil {
		return "", fmt.Errorf("darktunnel: marshal result failed: %w", err)
	}

	return string(resultBytes), nil
}

func decryptAESCFB(ciphertext, key, iv []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("aes.NewCipher failed: %w", err)
	}

	if len(iv) != block.BlockSize() {
		return nil, fmt.Errorf("invalid iv size: expected %d, got %d", block.BlockSize(), len(iv))
	}

	plaintext := make([]byte, len(ciphertext))
	stream := cipher.NewCFBDecrypter(block, iv)
	stream.XORKeyStream(plaintext, ciphertext)
	return plaintext, nil
}
