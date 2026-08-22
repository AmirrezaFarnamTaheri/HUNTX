// Package parse implements multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/crypto/aes (AES-ECB, AES-GCM specifications)
// Source: https://pkg.go.dev/golang.org/x/crypto/pbkdf2 (PBKDF2 specifications)
package parse_test

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/parse"
	"golang.org/x/crypto/pbkdf2"
)

func TestHAT_Decrypt_Success(t *testing.T) {
	hasher := sha1.New()
	hasher.Write([]byte("8515D40BD04D8C97"))
	key := hasher.Sum(nil)[:16]

	payload := `{"server":"1.2.3.4","port":443,"protocol":"hat"}`
	padLen := aes.BlockSize - (len(payload) % aes.BlockSize)
	padded := append([]byte(payload), bytes.Repeat([]byte{byte(padLen)}, padLen)...)

	block, err := aes.NewCipher(key)
	if err != nil {
		t.Fatalf("cipher failed: %v", err)
	}

	encrypted := make([]byte, len(padded))
	for i := 0; i < len(padded); i += aes.BlockSize {
		block.Encrypt(encrypted[i:i+aes.BlockSize], padded[i:i+aes.BlockSize])
	}

	b64Payload := base64.StdEncoding.EncodeToString(encrypted)
	decrypted, err := parse.DecryptHAT(b64Payload)
	if err != nil {
		t.Fatalf("DecryptHAT failed: %v", err)
	}

	if !bytes.Contains([]byte(decrypted), []byte("1.2.3.4")) {
		t.Errorf("expected 1.2.3.4 in decrypted payload, got %s", decrypted)
	}
}

func TestNetMod_Decrypt_Success(t *testing.T) {
	key := []byte("_netsyna_netmod_")
	payload := "vless://uuid-12345@5.6.7.8:443?type=ws#NetModNode"

	// Pad to 16 bytes with nulls or pkcs
	padLen := (16 - (len(payload) % 16)) % 16
	padded := append([]byte(payload), make([]byte, padLen)...)

	block, err := aes.NewCipher(key)
	if err != nil {
		t.Fatalf("cipher failed: %v", err)
	}

	encrypted := make([]byte, len(padded))
	for i := 0; i < len(padded); i += aes.BlockSize {
		block.Encrypt(encrypted[i:i+aes.BlockSize], padded[i:i+aes.BlockSize])
	}

	b64Payload := base64.StdEncoding.EncodeToString(encrypted)
	decrypted, err := parse.DecryptNetMod("nm-vless", b64Payload)
	if err != nil {
		t.Fatalf("DecryptNetMod failed: %v", err)
	}

	if !bytes.Contains([]byte(decrypted), []byte("5.6.7.8")) {
		t.Errorf("expected 5.6.7.8 in decrypted NetMod, got %s", decrypted)
	}
}

func TestSlipNet_Decrypt_Success(t *testing.T) {
	keyHex := "214F052025B2F949605A5429EC3D5FA80C2022C168AD946E68852D447214DBD3"
	key, _ := hex.DecodeString(keyHex)

	rawProfile := "28|SSH|Node1|example.com|8.8.8.8|1|1|US|443|1.2.3.4|1|pk|user|pass|1|sshuser|sshpass|22|1|ssh.host|1|https://doh|udp|pwd|key64|pass64|tor|auth|9000|naiveusr|naivepass|0|hash|2027|1|dev1|0|res|0|1024|1080|1|A|255|100|30|1|10|10|16|1|sni|h|80|ch|1|/ws|1|ch|sshpayload|auto|1|vless-uuid|tls|ws|/vless|1.1.1.1|443|1|rand|50||1|1|1|64|decoy.com|1400|vless.sni.com|"

	block, err := aes.NewCipher(key)
	if err != nil {
		t.Fatalf("cipher failed: %v", err)
	}

	aesgcm, err := cipher.NewGCM(block)
	if err != nil {
		t.Fatalf("gcm failed: %v", err)
	}

	nonce := make([]byte, 12)
	rand.Read(nonce)

	ciphertext := aesgcm.Seal(nil, nonce, []byte(rawProfile), nil)
	blob := append([]byte{0x01}, nonce...)
	blob = append(blob, ciphertext...)

	b64Blob := base64.StdEncoding.EncodeToString(blob)
	decrypted, err := parse.DecryptSlipNet(b64Blob)
	if err != nil {
		t.Fatalf("DecryptSlipNet failed: %v", err)
	}

	if !bytes.Contains([]byte(decrypted), []byte("VLESS SNI")) || !bytes.Contains([]byte(decrypted), []byte("vless.sni.com")) {
		t.Errorf("expected parsed fields in SlipNet output, got %s", decrypted)
	}
}

func TestSlipNet_DecryptBundle_Success(t *testing.T) {
	password := "SecretPass123"
	salt := []byte("1234567890123456")
	iv := []byte("123456789012")
	derivedKey := pbkdf2.Key([]byte(password), salt, 600000, 32, sha256.New)

	block, err := aes.NewCipher(derivedKey)
	if err != nil {
		t.Fatalf("cipher failed: %v", err)
	}

	aesgcm, err := cipher.NewGCM(block)
	if err != nil {
		t.Fatalf("gcm failed: %v", err)
	}

	rawBundle := "vless://bundled-profile-data-12345"
	ciphertext := aesgcm.Seal(nil, iv, []byte(rawBundle), nil)

	blob := []byte{0x01} // FORMAT_VERSION = 1
	blob = append(blob, salt...)
	blob = append(blob, iv...)
	blob = append(blob, ciphertext...)

	b64Blob := base64.StdEncoding.EncodeToString(blob)
	decrypted, err := parse.DecryptSlipNetBundle(b64Blob, password)
	if err != nil {
		t.Fatalf("DecryptSlipNetBundle failed: %v", err)
	}

	if decrypted != rawBundle {
		t.Errorf("bundle decrypted mismatch: expected %s, got %s", rawBundle, decrypted)
	}
}
