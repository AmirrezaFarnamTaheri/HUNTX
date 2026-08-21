package stream

import (
	"bufio"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"strings"
	"sync"
)

type Record struct {
	UniqueHash string `json:"unique_hash"`
	RawURI     string `json:"raw_uri"`
	Protocol   string `json:"protocol"`
}

type StreamParser struct {
	BufSize         int
	MaxDecodedBytes int
	MaxBase64Depth  int
}

var supportedSchemes = map[string]struct{}{
	"vmess": {}, "vless": {}, "trojan": {}, "ss": {}, "ssr": {},
	"hysteria": {}, "hysteria2": {}, "hy2": {},
	"hysteria2+realm": {}, "hysteria2+realm+http": {},
	"tuic": {}, "wireguard": {}, "wg": {},
	"socks": {}, "socks4": {}, "socks4a": {}, "socks5": {},
	"anytls": {}, "juicity": {}, "mieru": {}, "mierus": {},
	"warp": {}, "dns": {}, "dnstt": {}, "ssh": {}, "shadowtls": {},
	"naive+https": {}, "naive+quic": {},
}

var base64Encodings = []*base64.Encoding{
	base64.StdEncoding,
	base64.RawStdEncoding,
	base64.URLEncoding,
	base64.RawURLEncoding,
}

var bufPool = sync.Pool{
	New: func() any {
		b := make([]byte, 65536)
		return &b
	},
}

func NewStreamParser(bufSize int) *StreamParser {
	if bufSize <= 0 {
		bufSize = 65536 // 64 KiB
	}
	if bufSize > 1024*1024 {
		bufSize = 1024 * 1024
	}
	return &StreamParser{
		BufSize:         bufSize,
		MaxDecodedBytes: 4 * 1024 * 1024,
		MaxBase64Depth:  3,
	}
}

func HashURI(uri string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(uri)))
	var dst [64]byte
	hex.Encode(dst[:], sum[:])
	return string(dst[:])
}

func ExtractProtocol(uri string) string {
	if idx := strings.Index(uri, "://"); idx > 0 {
		proto := strings.TrimSpace(uri[:idx])
		// Avoid allocation if already lowercase
		isLower := true
		for i := 0; i < len(proto); i++ {
			c := proto[i]
			if c >= 'A' && c <= 'Z' {
				isLower = false
				break
			}
		}
		if isLower {
			return proto
		}
		return strings.ToLower(proto)
	}
	return "unknown"
}

func isSupportedProxyURI(line string) bool {
	protocol := ExtractProtocol(line)
	_, ok := supportedSchemes[protocol]
	return ok
}

func plausibleBase64Line(line string) bool {
	if len(line) < 8 || strings.ContainsAny(line, " \t") {
		return false
	}
	for i := 0; i < len(line); i++ {
		r := line[i]
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') ||
			(r >= '0' && r <= '9') || r == '+' || r == '/' || r == '-' ||
			r == '_' || r == '=' {
			continue
		}
		return false
	}
	return true
}

func decodeBase64Text(value string) ([]byte, error) {
	trimmed := strings.TrimSpace(value)
	var lastErr error
	for _, encoding := range base64Encodings {
		decoded, err := encoding.DecodeString(trimmed)
		if err == nil {
			return decoded, nil
		}
		lastErr = err
	}
	return nil, lastErr
}

func appendUnique(records []Record, seen map[string]struct{}, record Record) []Record {
	if _, exists := seen[record.UniqueHash]; exists {
		return records
	}
	seen[record.UniqueHash] = struct{}{}
	return append(records, record)
}

func (sp *StreamParser) ParseStream(r io.Reader) ([]Record, error) {
	seen := make(map[string]struct{}, 128)
	return sp.parseStream(r, 0, seen)
}

func (sp *StreamParser) parseStream(
	r io.Reader,
	depth int,
	seen map[string]struct{},
) ([]Record, error) {
	if depth > sp.MaxBase64Depth {
		return nil, fmt.Errorf("base64 nesting exceeds limit %d", sp.MaxBase64Depth)
	}

	scanner := bufio.NewScanner(r)
	maxToken := sp.BufSize * 4
	if maxToken < sp.BufSize {
		maxToken = sp.BufSize
	}

	var bufPtr *[]byte
	if sp.BufSize == 65536 {
		bufPtr = bufPool.Get().(*[]byte)
		defer bufPool.Put(bufPtr)
		scanner.Buffer(*bufPtr, maxToken)
	} else {
		scanner.Buffer(make([]byte, sp.BufSize), maxToken)
	}

	records := make([]Record, 0, 64)
	var base64Accumulator strings.Builder
	maxEncodedBytes := sp.MaxDecodedBytes*2 + 16

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		if isSupportedProxyURI(line) {
			rec := Record{
				UniqueHash: HashURI(line),
				RawURI:     line,
				Protocol:   ExtractProtocol(line),
			}
			records = appendUnique(records, seen, rec)
			continue
		}

		// Ordinary prose and arbitrary URLs are ignored instead of poisoning an
		// otherwise valid subscription as an attempted base64 payload.
		if !plausibleBase64Line(line) {
			continue
		}
		if base64Accumulator.Len()+len(line) > maxEncodedBytes {
			return records, fmt.Errorf("base64 payload exceeds encoded input limit")
		}
		base64Accumulator.WriteString(line)
	}

	if err := scanner.Err(); err != nil {
		return records, fmt.Errorf("read stream buffer: %w", err)
	}

	if base64Accumulator.Len() == 0 {
		return records, nil
	}
	decoded, err := decodeBase64Text(base64Accumulator.String())
	if err != nil {
		// Incidental base64-looking prose must not fail parsing of valid records.
		return records, nil
	}
	if len(decoded) > sp.MaxDecodedBytes {
		return records, fmt.Errorf(
			"decoded base64 payload exceeds %d bytes",
			sp.MaxDecodedBytes,
		)
	}
	if depth >= sp.MaxBase64Depth {
		return records, fmt.Errorf("base64 nesting exceeds limit %d", sp.MaxBase64Depth)
	}

	decodedRecords, err := sp.parseStream(strings.NewReader(string(decoded)), depth+1, seen)
	if err != nil {
		return records, fmt.Errorf("parse base64 stream payload: %w", err)
	}
	records = append(records, decodedRecords...)
	return records, nil
}
