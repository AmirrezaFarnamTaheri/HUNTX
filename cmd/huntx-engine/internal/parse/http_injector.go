// Package parse implements multi-protocol proxy subscription and tunnel decoders.
// Source: https://en.wikipedia.org/wiki/XXTEA (XXTEA block cipher specifications)
// Source: https://pkg.go.dev/golang.org/x/crypto/argon2 (Argon2id KDF specifications)
// Source: https://pkg.go.dev/golang.org/x/crypto/chacha20poly1305 (XChaCha20-Poly1305 specifications)
package parse

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"

	"golang.org/x/crypto/argon2"
	"golang.org/x/crypto/chacha20poly1305"
)

var (
	EhiL1Key        = []byte{0x7e, 0x12, 0x10, 0xf7, 0xaa, 0xb9, 0x56, 0xf7, 0xa6, 0x68, 0xbd, 0xa6, 0xe5, 0x7f, 0xed, 0xdb, 0x7f, 0x84, 0xad, 0x84, 0x0a, 0xef, 0x8d, 0x27, 0xb1, 0xb9, 0x69, 0x95, 0x9b, 0xe3, 0xab, 0x6c}
	EhiL2KeyStatic  = []byte{0xb2, 0xbc, 0x61, 0x7c, 0x32, 0xd8, 0xb9, 0xeb, 0x19, 0x43, 0xa5, 0xff, 0xa8, 0x05, 0x1e, 0xea}
	EhiEooMasterKey = []byte("null=V5kU5+FFrY\x00")

	EhiSideIvs = [][]byte{
		{0x22, 0x1d, 0x57, 0x23, 0x49, 0x55, 0x5f, 0x1d, 0x11, 0x21, 0x33, 0x23, 0x6b, 0x1f, 0x4a, 0x3f},
		{0x55, 0x43, 0x49, 0x4c, 0x53, 0x44, 0x3e, 0x3f, 0x4a, 0x6a, 0x45, 0x39, 0x38, 0x4e, 0x77, 0x6a},
		{0x37, 0x4c, 0x25, 0x41, 0x57, 0x5e, 0x4d, 0x53, 0x1a, 0x3c, 0x32, 0x7b, 0x75, 0x43, 0x1e, 0x5f},
	}

	EhiStandardIvs = [][]byte{
		{0x2c, 0x5d, 0x11, 0x47, 0xbb, 0xad, 0x42, 0x2b, 0x3b, 0x33, 0x4d, 0x4d, 0x23, 0x5f, 0x1a, 0x53},
		{0x52, 0x2b, 0x01, 0x43, 0x3a, 0x5e, 0x8b, 0x2f, 0xc7, 0x54, 0x9e, 0x1a, 0xd3, 0x68, 0xe5, 0x41},
		{0x33, 0x7a, 0x10, 0x35, 0xaa, 0xed, 0xf3, 0x45, 0x8c, 0xa1, 0x67, 0xe9, 0x2d, 0x74, 0xb8, 0x39},
	}

	EhiAllIVs = append(append([][]byte{}, EhiSideIvs...), EhiStandardIvs...)

	EhiCustomAlphabet = "RkLC2QaVMPYgGJW/A4f7qzDb9e+t6Hr0Zp8OlNyjuxKcTw1o5EIimhBn3UvdSFXs"
	ehiCustomEncoding = base64.NewEncoding(EhiCustomAlphabet)
)

const ehiXxteaDelta uint32 = 0x9e3779b9

// NativeXXTEAEncrypt encrypts data using the standard XXTEA block cipher algorithm.
func NativeXXTEAEncrypt(data, key []byte) ([]byte, error) {
	n := len(data)
	if n == 0 {
		return data, nil
	}
	v := toUint32Array(data, false)
	k := toUint32Array(key, false)
	if len(k) < 4 {
		newK := make([]uint32, 4)
		copy(newK, k)
		k = newK
	}
	n = len(v)
	if n <= 1 {
		return data, nil
	}

	z := v[n-1]
	q := 6 + 52/n
	var sum uint32

	for q > 0 {
		sum += ehiXxteaDelta
		e := (sum >> 2) & 3
		for p := 0; p < n-1; p++ {
			y := v[p+1]
			v[p] += (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((sum ^ y) + (k[(p&3)^int(e)] ^ z))
			z = v[p]
		}
		y := v[0]
		v[n-1] += (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((sum ^ y) + (k[((n-1)&3)^int(e)] ^ z))
		z = v[n-1]
		q--
	}

	return toByteArray(v, false), nil
}

// NativeXXTEADecrypt decrypts data using the standard XXTEA block cipher algorithm.
func NativeXXTEADecrypt(data, key []byte) ([]byte, error) {
	n := len(data)
	if n == 0 {
		return data, nil
	}
	v := toUint32Array(data, false)
	k := toUint32Array(key, false)
	if len(k) < 4 {
		newK := make([]uint32, 4)
		copy(newK, k)
		k = newK
	}
	n = len(v)
	if n <= 1 {
		return data, nil
	}

	z := v[n-1]
	y := v[0]
	q := 6 + 52/n
	sum := uint32(q) * ehiXxteaDelta

	for sum != 0 {
		e := (sum >> 2) & 3
		for p := n - 1; p > 0; p-- {
			z = v[p-1]
			v[p] -= (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((sum ^ y) + (k[(p&3)^int(e)] ^ z))
			y = v[p]
		}
		z = v[n-1]
		v[0] -= (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((sum ^ y) + (k[int(e)] ^ z))
		y = v[0]
		sum -= ehiXxteaDelta
	}

	return toByteArray(v, false), nil
}

func toUint32Array(data []byte, includeLength bool) []uint32 {
	length := len(data)
	n := (((length & 3) == 0) && (length != 0))
	var result []uint32
	if n {
		result = make([]uint32, length>>2)
	} else {
		result = make([]uint32, (length>>2)+1)
	}
	for i := 0; i < length; i++ {
		result[i>>2] |= (uint32(data[i]) & 0xff) << ((i & 3) << 3)
	}
	if includeLength {
		result = append(result, uint32(length))
	}
	return result
}

func toByteArray(data []uint32, includeLength bool) []byte {
	n := len(data) << 2
	if includeLength {
		m := int(data[len(data)-1])
		n -= 4
		if (m < n-3) || (m > n) {
			return nil
		}
		n = m
	}
	result := make([]byte, n)
	for i := 0; i < n; i++ {
		result[i] = byte((data[i>>2] >> ((i & 3) << 3)) & 0xff)
	}
	return result
}

// DecryptHTTPInjector decodes and decrypts an HTTP Injector .ehi configuration file.
func DecryptHTTPInjector(fileBytes []byte) (string, error) {
	if len(fileBytes) < 16 {
		return "", errors.New("http_injector: payload too short")
	}

	if len(fileBytes)%aes.BlockSize != 0 {
		return "", errors.New("http_injector: payload not block aligned")
	}

	// 1. Layer 1 AES-256-CBC across candidate IVs
	candidateIVs := append([][]byte{
		{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0},
	}, EhiAllIVs...)

	var config map[string]interface{}
	var isBypass bool

	for idx, iv := range candidateIVs {
		l1Plaintext, err := decryptAESCBC(fileBytes, EhiL1Key, iv)
		if err != nil {
			continue
		}

		if json.Valid(l1Plaintext) {
			if err := json.Unmarshal(l1Plaintext, &config); err == nil {
				isBypass = true
				break
			}
		}

		tokens := strings.Split(string(l1Plaintext), ":")
		if len(tokens) < 3 {
			continue
		}

		iv2, err := base64.StdEncoding.DecodeString(tokens[0])
		if err != nil || len(iv2) != aes.BlockSize {
			continue
		}

		var garbageRaw []byte
		for i := 1; i < len(tokens); i++ {
			b, err := base64.StdEncoding.DecodeString(tokens[i])
			if err == nil && len(b) >= aes.BlockSize && len(b)%aes.BlockSize == 0 {
				garbageRaw = b
				break
			}
		}

		if len(garbageRaw) == 0 {
			continue
		}

		garbage, err := decryptAESCBC(garbageRaw, EhiL2KeyStatic, iv2)
		if err != nil {
			continue
		}

		finalRaw, err := NativeXXTEADecrypt(garbage, EhiEooMasterKey)
		if err != nil || len(finalRaw) == 0 {
			continue
		}

		startIdx := bytes.IndexByte(finalRaw, '{')
		if startIdx == -1 {
			continue
		}

		trimmed := bytes.TrimRight(finalRaw[startIdx:], "\x00 \t\r\n")
		if err := json.Unmarshal(trimmed, &config); err == nil {
			isBypass = idx < len(EhiSideIvs)
			break
		}
	}

	if config == nil {
		return "", errors.New("http_injector: decryption signature mismatch across standard matrix maps")
	}

	targetSalt := "EVZJNI"
	if s, ok := config["configSalt"].(string); ok && s != "" {
		targetSalt = s
	}

	var parsedFinal map[string]interface{}

	if isBypass {
		parsedFinal = config
	} else {
		targetData, _ := config["configData"].(string)
		if targetData != "" {
			aaaResult, err := decryptXorLayer(targetData, targetSalt)
			if err == nil && aaaResult != "" {
				rawPayload, err := base64.StdEncoding.DecodeString(aaaResult)
				if err == nil && len(rawPayload) > 50 {
					timeCost := binary.LittleEndian.Uint32(rawPayload[1:5])
					memoryCost := binary.LittleEndian.Uint32(rawPayload[5:9])
					parallelism := rawPayload[9]

					salt := rawPayload[0x0a:0x1a]
					nonce := rawPayload[0x1a:0x32]
					aad := rawPayload[:0x1a]

					masterKey := generateEhiMasterKey(config)
					argonKey := argon2.IDKey(masterKey, salt, timeCost, memoryCost, parallelism, 32)

					aead, err := chacha20poly1305.NewX(argonKey)
					if err == nil {
						decryptedJsonBytes, err := aead.Open(nil, nonce, rawPayload[0x32:], aad)
						if err == nil {
							_ = json.Unmarshal(decryptedJsonBytes, &parsedFinal)
						}
					}
				}
			}
		}
		if parsedFinal == nil {
			parsedFinal = config
		}
	}

	cleanedFinalJson := cleanInnerFields(parsedFinal, targetSalt)

	for _, jsonField := range []string{"v2rRawJson", "overwriteServerData"} {
		if rawStr, ok := cleanedFinalJson[jsonField].(string); ok {
			if parsedObj, success := tryNestedJsonParse(rawStr); success {
				cleanedFinalJson[jsonField] = parsedObj
			}
		}
	}

	prettyJSON, err := json.MarshalIndent(cleanedFinalJson, "", "  ")
	if err != nil {
		return "", err
	}

	return string(prettyJSON), nil
}

func decryptXorLayer(ciphertextStr string, key string) (string, error) {
	if strings.TrimSpace(ciphertextStr) == "" {
		return ciphertextStr, nil
	}

	reversed := reverseString(ciphertextStr)
	hexBytesRaw, err := customB64Decode(reversed)
	if err != nil {
		return "", err
	}

	hexStr := string(hexBytesRaw)
	if len(hexStr)%2 != 0 {
		hexStr = "0" + hexStr
	}

	rawBytes, err := hex.DecodeString(hexStr)
	if err != nil {
		return "", err
	}

	keyLen := len(key)
	decryptedBytes := make([]byte, 0, len(rawBytes))
	for i, b := range rawBytes {
		xorVal := b ^ key[i%keyLen]
		if xorVal != 0 {
			decryptedBytes = append(decryptedBytes, xorVal)
		}
	}

	return string(decryptedBytes), nil
}

func reverseString(s string) string {
	b := []byte(s)
	for i, j := 0, len(b)-1; i < j; i, j = i+1, j-1 {
		b[i], b[j] = b[j], b[i]
	}
	return string(b)
}

func customB64Decode(encodedStr string) ([]byte, error) {
	cleanStr := strings.ReplaceAll(encodedStr, "?", "")
	if rem := len(cleanStr) % 4; rem != 0 {
		cleanStr += strings.Repeat("=", 4-rem)
	}
	return ehiCustomEncoding.DecodeString(cleanStr)
}

func generateEhiMasterKey(config map[string]interface{}) []byte {
	configAesKey, _ := config["configAesKey"].(string)
	configIdentifier, _ := config["configIdentifier"].(string)
	configSalt, _ := config["configSalt"].(string)
	configTimestamp, _ := config["configTimestamp"].(string)
	configExpiryTimestamp, _ := config["configExpiryTimestamp"].(string)
	lockModes, _ := config["lockModes"].(string)
	lockModesHash, _ := config["lockModesHash"].(string)
	configHwid, _ := config["configHwid"].(string)
	configLockMobileOperatorId, _ := config["configLockMobileOperatorId"].(string)

	builder := configAesKey + configIdentifier + configSalt + configTimestamp + configExpiryTimestamp +
		lockModes + lockModesHash + configHwid + configLockMobileOperatorId

	sum := sha256.Sum256([]byte(builder))
	return sum[:]
}

func cleanInnerFields(config map[string]interface{}, salt string) map[string]interface{} {
	cleaned := make(map[string]interface{})
	for k, v := range config {
		if strVal, ok := v.(string); ok && strings.HasPrefix(strVal, "AAA") {
			if dec, err := decryptXorLayer(strVal, salt); err == nil && dec != "" {
				cleaned[k] = dec
				continue
			}
		}
		cleaned[k] = v
	}
	return cleaned
}

func tryNestedJsonParse(s string) (interface{}, bool) {
	var obj interface{}
	if err := json.Unmarshal([]byte(s), &obj); err == nil {
		return obj, true
	}
	return nil, false
}

func decryptAESCBC(ciphertext, key, iv []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}

	if len(ciphertext)%block.BlockSize() != 0 {
		return nil, errors.New("ciphertext is not a multiple of the block size")
	}

	mode := cipher.NewCBCDecrypter(block, iv)
	plaintext := make([]byte, len(ciphertext))
	mode.CryptBlocks(plaintext, ciphertext)

	// PKCS7 unpad
	if len(plaintext) > 0 {
		padLen := int(plaintext[len(plaintext)-1])
		if padLen >= 1 && padLen <= block.BlockSize() {
			allMatch := true
			for i := len(plaintext) - padLen; i < len(plaintext); i++ {
				if int(plaintext[i]) != padLen {
					allMatch = false
					break
				}
			}
			if allMatch {
				return plaintext[:len(plaintext)-padLen], nil
			}
		}
	}

	return plaintext, nil
}
