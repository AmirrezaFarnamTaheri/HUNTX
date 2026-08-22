// Package parse implements multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/crypto/aes (AES-ECB, AES-GCM specifications)
// Source: https://pkg.go.dev/golang.org/x/crypto/pbkdf2 (PBKDF2 key derivation)
package parse

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"golang.org/x/crypto/pbkdf2"
)

const (
	// HatImportKey is the static key seed for HA Tunnel Plus.
	HatImportKey = "8515D40BD04D8C97"

	// NetModKey is the static AES key for NetMod VPN client.
	NetModKey = "_netsyna_netmod_"

	// SlipNetKeyHex is the master 256-bit AES key for SlipNet configuration profiles.
	SlipNetKeyHex = "214F052025B2F949605A5429EC3D5FA80C2022C168AD946E68852D447214DBD3"

	slipNetFormatVersion = 0x01
	slipNetSaltLength    = 16
	slipNetIVLength      = 12
	slipNetPBKDF2Iter    = 600000
	slipNetKeySizeBytes  = 32
)

var (
	slipNetV1  = []string{"Version", "Tunnel Type/Mode", "Name", "Domain", "Resolvers", "AuthMode", "KeepAlive", "CC", "Port", "Host", "GSO"}
	slipNetV20 = append(slipNetV1,
		"DNSTT Public Key", "SOCKS Username", "SOCKS Password", "SSH Enabled", "SSH Username",
		"SSH Password", "SSH Port", "Forward DNS thru SSH", "SSH Host", "Use Server DNS",
		"DoH URL", "DNS Transport", "SSH Auth Type", "SSH Private Key (B64)", "SSH Key Passphrase (B64)",
		"Tor Bridge Lines (B64)", "DNSTT Authoritative", "Naive Port", "Naive Username", "Naive Password (B64)",
		"Is Locked", "Lock Password Hash", "Expiration Date", "Allow Sharing", "Bound Device ID",
		"Resolvers Hidden", "Hidden Resolvers", "NoizDNS Stealth", "DNS Payload Size", "SOCKS5 Server Port",
		"VayDNS DNSTT Compat", "VayDNS Record Type", "VayDNS Max Qname Len", "VayDNS RPS", "VayDNS Idle Timeout",
		"VayDNS Keepalive", "VayDNS UDP Timeout", "VayDNS Max Num Labels", "VayDNS Client Id Size",
	)
	slipNetV21 = append(slipNetV20,
		"SSH TLS Enabled", "SSH TLS SNI", "SSH HTTP Proxy Host", "SSH HTTP Proxy Port", "SSH HTTP Proxy Custom Host",
		"SSH WS Enabled", "SSH WS Path", "SSH WS Use TLS", "SSH WS Custom Host",
	)
	slipNetV22 = append(slipNetV21, "SSH Payload (B64)")
	slipNetV24 = append(slipNetV22, "Resolver Mode", "RR Spread Count")
	slipNetV25 = append(slipNetV24,
		"VLESS UUID", "VLESS Security", "VLESS Transport", "VLESS WS Path", "CDN IP",
		"CDN Port", "SNI Fragment Enabled", "SNI Fragment Strategy", "SNI Fragment Delay MS", "Legacy SNI (Empty)",
	)
	slipNetV27 = append(slipNetV25,
		"CH Padding Enabled", "WS Header Obfuscation", "WS Padding Enabled",
		"SNI Spoof TTL", "Fake Decoy Host", "TCP Max Seg",
	)
	slipNetV28     = append(slipNetV27, "VLESS SNI")
	slipNetSchemas = map[string][]string{
		"1": slipNetV1, "20": slipNetV20, "21": slipNetV21, "22": slipNetV22, "23": slipNetV24, "24": slipNetV24,
		"25": slipNetV25, "26": slipNetV27, "27": slipNetV27, "28": slipNetV28,
	}
)

// DecryptHAT decrypts an HA Tunnel Plus (.hat) base64 payload.
func DecryptHAT(payload string) (string, error) {
	if strings.TrimSpace(payload) == "" {
		return "", errors.New("hat: empty payload")
	}

	ciphertext, err := base64.StdEncoding.DecodeString(strings.TrimSpace(payload))
	if err != nil {
		return "", fmt.Errorf("hat: base64 decode failed: %w", err)
	}

	hasher := sha1.New()
	hasher.Write([]byte(HatImportKey))
	derivedKey := hasher.Sum(nil)[:16]

	plaintext, err := decryptAESECB(ciphertext, derivedKey)
	if err != nil {
		return "", fmt.Errorf("hat: aes-ecb decrypt failed: %w", err)
	}

	unpadded, err := pkcs7Unpad(plaintext, aes.BlockSize)
	if err != nil {
		return "", fmt.Errorf("hat: unpad failed: %w", err)
	}

	var prettyJSON bytes.Buffer
	if err := json.Indent(&prettyJSON, unpadded, "", "  "); err == nil {
		return prettyJSON.String(), nil
	}

	return string(unpadded), nil
}

// DecryptNetMod decrypts a NetMod (nm-*://) base64 payload.
func DecryptNetMod(proto, payload string) (string, error) {
	if strings.TrimSpace(payload) == "" {
		return "", errors.New("netmod: empty payload")
	}

	ciphertext, err := base64.StdEncoding.DecodeString(strings.TrimSpace(payload))
	if err != nil {
		return "", fmt.Errorf("netmod: base64 decode failed: %w", err)
	}

	plaintext, err := decryptAESECB(ciphertext, []byte(NetModKey))
	if err != nil {
		return "", fmt.Errorf("netmod: aes-ecb decrypt failed: %w", err)
	}

	cleanText := strings.TrimRight(string(plaintext), "\x00")
	if proto != "" {
		return proto + "://" + cleanText, nil
	}
	return cleanText, nil
}

// DecryptSlipNet decrypts a standard SlipNet encrypted profile (slipnet-enc://).
func DecryptSlipNet(payload string) (string, error) {
	if strings.TrimSpace(payload) == "" {
		return "", errors.New("slipnet: empty payload")
	}

	data, err := base64.StdEncoding.DecodeString(strings.TrimSpace(payload))
	if err != nil {
		return "", fmt.Errorf("slipnet: base64 decode failed: %w", err)
	}

	if len(data) < 13 {
		return "", errors.New("slipnet: blob too short")
	}

	key, err := hex.DecodeString(SlipNetKeyHex)
	if err != nil {
		return "", fmt.Errorf("slipnet: invalid master key hex: %w", err)
	}

	block, err := aes.NewCipher(key)
	if err != nil {
		return "", fmt.Errorf("slipnet: cipher init failed: %w", err)
	}

	aesgcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("slipnet: gcm init failed: %w", err)
	}

	nonce := data[1:13]
	ciphertext := data[13:]

	plaintext, err := aesgcm.Open(nil, nonce, ciphertext, nil)
	if err != nil {
		return "", fmt.Errorf("slipnet: gcm open failed: %w", err)
	}

	return parseSlipNetProfile(string(plaintext)), nil
}

// DecryptSlipNetBundle decrypts a password-protected SlipNet bundle profile.
func DecryptSlipNetBundle(payload, password string) (string, error) {
	if strings.TrimSpace(payload) == "" {
		return "", errors.New("slipnet_bundle: empty payload")
	}
	if strings.TrimSpace(password) == "" {
		return "", errors.New("slipnet_bundle: empty password")
	}

	cleaned := strings.NewReplacer("\n", "", "\r", "", " ", "").Replace(payload)
	data, err := base64.StdEncoding.DecodeString(cleaned)
	if err != nil {
		return "", fmt.Errorf("slipnet_bundle: base64 decode failed: %w", err)
	}

	minReq := 1 + slipNetSaltLength + slipNetIVLength + 16
	if len(data) < minReq {
		return "", errors.New("slipnet_bundle: data truncated")
	}

	if data[0] != slipNetFormatVersion {
		return "", fmt.Errorf("slipnet_bundle: unsupported version 0x%02x", data[0])
	}

	saltStart := 1
	ivStart := saltStart + slipNetSaltLength
	ciphertextStart := ivStart + slipNetIVLength

	salt := data[saltStart:ivStart]
	iv := data[ivStart:ciphertextStart]
	ciphertextWithTag := data[ciphertextStart:]

	derivedKey := pbkdf2.Key([]byte(password), salt, slipNetPBKDF2Iter, slipNetKeySizeBytes, sha256.New)

	block, err := aes.NewCipher(derivedKey)
	if err != nil {
		return "", fmt.Errorf("slipnet_bundle: cipher init failed: %w", err)
	}

	aesgcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("slipnet_bundle: gcm init failed: %w", err)
	}

	plaintext, err := aesgcm.Open(nil, iv, ciphertextWithTag, nil)
	if err != nil {
		return "", fmt.Errorf("slipnet_bundle: gcm open failed (wrong password or corrupt data): %w", err)
	}

	return string(plaintext), nil
}

func parseSlipNetProfile(decryptedText string) string {
	decryptedText = strings.TrimSuffix(decryptedText, "|")
	parts := strings.Split(decryptedText, "|")
	if len(parts) == 0 || parts[0] == "" {
		return "[!] Empty decrypted text"
	}

	verStr := parts[0]
	schema, exists := slipNetSchemas[verStr]

	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("\n[+] Detected Profile Version: %s\n", verStr))
	sb.WriteString(fmt.Sprintf("%-30s | %s\n", "FIELD", "VALUE"))
	sb.WriteString(strings.Repeat("-", 80) + "\n")

	for i, value := range parts {
		label := ""
		if exists && i < len(schema) {
			label = schema[i]
		} else {
			label = fmt.Sprintf("Field %d", i)
		}

		displayValue := value
		if displayValue == "" {
			displayValue = "(empty)"
		}

		switch label {
		case "Is Locked", "SSH TLS Enabled", "SSH WS Enabled", "SSH WS Use TLS",
			"SNI Fragment Enabled", "CH Padding Enabled", "WS Header Obfuscation", "WS Padding Enabled":
			if value == "1" {
				displayValue = "LOCK: YES"
			} else {
				displayValue = "LOCK: NO"
			}
		case "VayDNS DNSTT Compat", "Resolvers Hidden", "GSO", "DNSTT Authoritative",
			"SSH Enabled", "Forward DNS thru SSH", "Use Server DNS", "Allow Sharing", "NoizDNS Stealth":
			if value == "1" {
				displayValue = "TRUE"
			} else {
				displayValue = "FALSE"
			}
		}
		sb.WriteString(fmt.Sprintf("%-30s | %s\n", label, displayValue))
	}
	return sb.String()
}

func decryptAESECB(ciphertext, key []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	if len(ciphertext)%block.BlockSize() != 0 {
		return nil, errors.New("aes-ecb: ciphertext length not multiple of block size")
	}

	plaintext := make([]byte, len(ciphertext))
	bs := block.BlockSize()
	for start := 0; start < len(ciphertext); start += bs {
		block.Decrypt(plaintext[start:start+bs], ciphertext[start:start+bs])
	}
	return plaintext, nil
}

func pkcs7Unpad(data []byte, blockSize int) ([]byte, error) {
	if len(data) == 0 {
		return nil, errors.New("unpad: empty data")
	}
	if len(data)%blockSize != 0 {
		return nil, errors.New("unpad: data length not a multiple of block size")
	}

	paddingLen := int(data[len(data)-1])
	if paddingLen >= 1 && paddingLen <= blockSize {
		valid := true
		for i := len(data) - paddingLen; i < len(data); i++ {
			if int(data[i]) != paddingLen {
				valid = false
				break
			}
		}
		if valid {
			return data[:len(data)-paddingLen], nil
		}
	}

	result := data
	for len(result) > 0 {
		lastByte := result[len(result)-1]
		if lastByte < 32 || lastByte == ' ' {
			result = result[:len(result)-1]
		} else {
			break
		}
	}
	return result, nil
}
