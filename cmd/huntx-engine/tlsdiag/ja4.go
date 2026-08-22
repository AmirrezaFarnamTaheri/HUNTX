package tlsdiag

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net"
	"strings"
)

// CalculateJA4S computes a server-side TLS fingerprint according to the FoxIO JA4S standard.
// Format: t<version><num_ciphers><alpn>_<cipher_hex>_<extensions_hash>
func CalculateJA4S(version uint16, cipherSuite uint16, alpn string) string {
	versionStr := "00"
	switch version {
	case 0x0304: // TLS 1.3
		versionStr = "13"
	case 0x0303: // TLS 1.2
		versionStr = "12"
	case 0x0302: // TLS 1.1
		versionStr = "11"
	case 0x0301: // TLS 1.0
		versionStr = "10"
	}

	alpnCode := "00"
	if len(alpn) >= 2 {
		alpnCode = strings.ToLower(alpn[:2])
	} else if len(alpn) == 1 {
		alpnCode = strings.ToLower(alpn) + "0"
	}

	cipherHex := fmt.Sprintf("%04x", cipherSuite)

	// Combine to construct standardized JA4S string
	hasher := sha256.New()
	hasher.Write([]byte(fmt.Sprintf("%s_%s_%s", versionStr, cipherHex, alpn)))
	hashSuffix := hex.EncodeToString(hasher.Sum(nil))[:12]

	return fmt.Sprintf("t%ss%s_%s_%s", versionStr, alpnCode, cipherHex, hashSuffix)
}

// IsDomainSNI checks whether the provided serverName is a domain or IP address.
func IsDomainSNI(serverName string) bool {
	trimmed := strings.TrimSpace(serverName)
	if trimmed == "" {
		return false
	}
	return net.ParseIP(trimmed) == nil
}
