package subfeed

import (
	"strings"
	"testing"
)

func TestDecodeRequestConstraints(t *testing.T) {
	base := `{"url":"https://raw.githubusercontent.com/x/y/main/a","etag":"etag"}`
	good, err := DecodeRequest(strings.NewReader(base))
	if err != nil || good.ETag != "etag" {
		t.Fatalf("valid feed request was rejected: %v %#v", err, good)
	}
	bad := []string{
		`{"url":"https://127.0.0.1/metadata"}`,
		`{"url":"https://raw.githubusercontent.com/x/y","unknown":"field"}`,
		base + ` {}`,
		`{"url":"https://raw.githubusercontent.com/x/y","etag":"` + strings.Repeat("x", 600) + `"}`,
		"",
	}
	for _, payload := range bad {
		if _, err := DecodeRequest(strings.NewReader(payload)); err == nil {
			t.Fatal("accepted invalid fetch stdin envelope")
		}
	}
}
