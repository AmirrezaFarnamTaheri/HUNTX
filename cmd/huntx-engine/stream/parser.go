package stream

import (
	"bufio"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"strings"
)

const maxAccumulatorBytes = 8 * 1024 * 1024

type Record struct {
	UniqueHash string `json:"unique_hash"`
	RawURI string `json:"raw_uri"`
	Protocol string `json:"protocol"`
}

type StreamParser struct { BufSize int }

func NewStreamParser(bufSize int) *StreamParser {
	if bufSize <= 0 { bufSize = 65536 }
	return &StreamParser{BufSize: bufSize}
}

func HashURI(uri string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(uri)))
	return hex.EncodeToString(sum[:8])
}

func ExtractProtocol(uri string) string {
	if idx := strings.Index(uri, "://"); idx != -1 { return strings.ToLower(uri[:idx]) }
	return "unknown"
}

func (sp *StreamParser) ParseStream(r io.Reader) ([]Record, error) {
	if r == nil { return nil, fmt.Errorf("nil input reader") }
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, sp.BufSize), sp.BufSize*4)
	var records []Record
	var base64Accumulator strings.Builder

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") { continue }
		if strings.Contains(line, "://") {
			records = append(records, Record{UniqueHash: HashURI(line), RawURI: line, Protocol: ExtractProtocol(line)})
		} else {
			if base64Accumulator.Len()+len(line) > maxAccumulatorBytes {
				return records, fmt.Errorf("base64 payload exceeds max size %d bytes", maxAccumulatorBytes)
			}
			base64Accumulator.WriteString(line)
		}
	}
	if err := scanner.Err(); err != nil { return records, fmt.Errorf("read stream buffer: %w", err) }
	if base64Accumulator.Len() > 0 {
		decoded, err := base64.StdEncoding.DecodeString(base64Accumulator.String())
		if err != nil { return records, fmt.Errorf("decode base64 payload: %w", err) }
		b64Records, err := sp.ParseStream(strings.NewReader(string(decoded)))
		if err != nil { return records, fmt.Errorf("parse base64 stream payload: %w", err) }
		records = append(records, b64Records...)
	}
	return records, nil
}
