package stream

import (
	"bufio"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"io"
	"strings"
)

type Record struct {
	UniqueHash string `json:"unique_hash"`
	RawURI     string `json:"raw_uri"`
	Protocol   string `json:"protocol"`
}

type StreamParser struct {
	BufSize int
}

func NewStreamParser(bufSize int) *StreamParser {
	if bufSize <= 0 {
		bufSize = 65536 // 64KB
	}
	return &StreamParser{BufSize: bufSize}
}

func HashURI(uri string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(uri)))
	return hex.EncodeToString(sum[:8])
}

func ExtractProtocol(uri string) string {
	if idx := strings.Index(uri, "://"); idx != -1 {
		return strings.ToLower(uri[:idx])
	}
	return "unknown"
}

func (sp *StreamParser) ParseStream(r io.Reader) ([]Record, error) {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, sp.BufSize), sp.BufSize*4)

	var records []Record
	var base64Accumulator strings.Builder

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		if strings.Contains(line, "://") {
			rec := Record{
				UniqueHash: HashURI(line),
				RawURI:     line,
				Protocol:   ExtractProtocol(line),
			}
			records = append(records, rec)
		} else {
			base64Accumulator.WriteString(line)
		}
	}

	if err := scanner.Err(); err != nil {
		return records, err
	}

	// Process base64 payload if accumulated
	if base64Accumulator.Len() > 0 {
		decoded, err := base64.StdEncoding.DecodeString(base64Accumulator.String())
		if err == nil {
			decodedReader := strings.NewReader(string(decoded))
			b64Records, _ := sp.ParseStream(decodedReader)
			records = append(records, b64Records...)
		}
	}

	return records, nil
}
