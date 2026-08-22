// Package parse_test benchmarks multi-protocol proxy subscription and tunnel decoders.
// Source: https://pkg.go.dev/testing#B.Loop (Go standard library benchmarking)
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

func BenchmarkNativeXXTEAEncrypt(b *testing.B) {
	key := []byte("null=V5kU5+FFrY\x00")
	data := []byte("vless://benchmark-payload-data-stream-for-xxtea-encryption-1234567890")

	b.ReportAllocs()
	b.SetBytes(int64(len(data)))
	b.ResetTimer()

	for b.Loop() {
		_, _ = parse.NativeXXTEAEncrypt(data, key)
	}
}

func BenchmarkNativeXXTEADecrypt(b *testing.B) {
	key := []byte("null=V5kU5+FFrY\x00")
	data := []byte("vless://benchmark-payload-data-stream-for-xxtea-encryption-1234567890")
	enc, _ := parse.NativeXXTEAEncrypt(data, key)

	b.ReportAllocs()
	b.SetBytes(int64(len(enc)))
	b.ResetTimer()

	for b.Loop() {
		_, _ = parse.NativeXXTEADecrypt(enc, key)
	}
}

func BenchmarkDecryptHTTPInjector(b *testing.B) {
	configMap := map[string]interface{}{
		"v2rRawJson": `{"outbounds":[{"protocol":"vmess","settings":{"vnext":[{"address":"198.51.100.2","port":443}]}}]}`,
		"configSalt": "EVZJNI",
	}
	rawJSON, _ := json.Marshal(configMap)

	xxteaEncrypted, _ := parse.NativeXXTEAEncrypt(rawJSON, parse.EhiEooMasterKey)

	iv2 := parse.EhiStandardIvs[0]
	padLen := aes.BlockSize - (len(xxteaEncrypted) % aes.BlockSize)
	paddedL2 := append(xxteaEncrypted, bytes.Repeat([]byte{byte(padLen)}, padLen)...)

	blockL2, _ := aes.NewCipher(parse.EhiL2KeyStatic)
	encryptedL2 := make([]byte, len(paddedL2))
	modeL2 := cipher.NewCBCEncrypter(blockL2, iv2)
	modeL2.CryptBlocks(encryptedL2, paddedL2)

	token0B64 := base64.StdEncoding.EncodeToString(iv2)
	token1B64 := "SALT_DUMMY"
	token2B64 := base64.StdEncoding.EncodeToString(encryptedL2)
	colonFormatted := fmt.Sprintf("%s:%s:%s", token0B64, token1B64, token2B64)

	standardIV := []byte{0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}
	padLen1 := aes.BlockSize - (len(colonFormatted) % aes.BlockSize)
	paddedL1 := append([]byte(colonFormatted), bytes.Repeat([]byte{byte(padLen1)}, padLen1)...)

	blockL1, _ := aes.NewCipher(parse.EhiL1Key)
	encryptedL1 := make([]byte, len(paddedL1))
	modeL1 := cipher.NewCBCEncrypter(blockL1, standardIV)
	modeL1.CryptBlocks(encryptedL1, paddedL1)

	b.ReportAllocs()
	b.SetBytes(int64(len(encryptedL1)))
	b.ResetTimer()

	for b.Loop() {
		res, err := parse.DecryptHTTPInjector(encryptedL1)
		if err != nil || len(res) == 0 {
			b.Fatalf("decrypt failed: %v", err)
		}
	}
}
