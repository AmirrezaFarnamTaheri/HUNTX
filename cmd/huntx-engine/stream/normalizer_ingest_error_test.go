package stream_test

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
)

type failingReader struct {
	read bool
}

func (r *failingReader) Read(p []byte) (int, error) {
	if r.read {
		return 0, errors.New("injected reader failure")
	}
	r.read = true
	return copy(p, "vless://example.com:443\n"), nil
}

func TestIngestReportsReaderFailure(t *testing.T) {
	nodes, errs := stream.Ingest(context.Background(), &failingReader{}, 1)
	for range nodes {
	}
	err, ok := <-errs
	if !ok || err == nil || !strings.Contains(err.Error(), "injected reader failure") {
		t.Fatalf("expected reader failure, got %v (open=%t)", err, ok)
	}
}

func TestIngestReportsOversizedLine(t *testing.T) {
	nodes, errs := stream.Ingest(context.Background(), strings.NewReader(strings.Repeat("x", 1024*1024+1)), 1)
	for range nodes {
	}
	err, ok := <-errs
	if !ok || err == nil {
		t.Fatalf("expected oversized-token error, got %v (open=%t)", err, ok)
	}
}
