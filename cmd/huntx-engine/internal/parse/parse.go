// Package parse provides stream parsing helpers for HUNTX proxy subscription files.
// It wraps the stream.StreamParser in a testable, reusable library API.
package parse

import (
	"fmt"
	"io"
	"os"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
)

// ParseReader parses a proxy subscription stream from an io.Reader.
// It returns a non-nil (possibly empty) slice on success.
func ParseReader(r io.Reader) ([]stream.Record, error) {
	sp := stream.NewStreamParser(65536)
	records, err := sp.ParseStream(r)
	if err != nil {
		return nil, fmt.Errorf("parse: stream error: %w", err)
	}
	if records == nil {
		records = []stream.Record{}
	}
	return records, nil
}

// ParseFile opens the file at path and delegates to ParseReader.
func ParseFile(path string) ([]stream.Record, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("parse: open %q: %w", path, err)
	}
	defer f.Close()
	return ParseReader(f)
}
