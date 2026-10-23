package subfeed

import (
	"net/http"
	"net/netip"
	"strings"
	"testing"
	"time"
)

func TestPublicSourceURLRestrictions(t *testing.T) {
	good := []string{
		"https://raw.githubusercontent.com/owner/repo/main/configs.txt",
		"https://sub.whitedns.one/sub/mihomo.yaml",
	}
	bad := []string{
		"http://raw.githubusercontent.com/a/b",
		"https://127.0.0.1/config",
		"https://169.254.169.254/meta",
		"https://example.com/redirect",
		"https://user:pass@raw.githubusercontent.com/a/b",
		"https://raw.githubusercontent.com:22/path",
		"https://raw.githubusercontent.com/path#frag",
	}
	for _, u := range good {
		if _, err := ValidateURL(u); err != nil {
			t.Errorf("rejected public feed URL: %v", err)
		}
	}
	for _, u := range bad {
		if _, err := ValidateURL(u); err == nil {
			t.Errorf("accepted unsafe feed URL %q", u)
		}
	}
}

func TestPublicAddressDoesNotConfuseUnicastAndPublic(t *testing.T) {
	bad := []string{
		"127.0.0.1", "::1", "10.0.0.1", "192.168.1.1",
		"169.254.169.254", "100.64.2.3", "192.0.2.10",
		"198.51.100.2", "203.0.113.1", "198.19.0.1",
		"fc00::1", "fe80::1", "2001:db8::1", "ff02::1",
		"2002:c0a8:101::1", "2001:20::1", "3fff::1",
	}
	for _, address := range bad {
		if PublicAddress(netip.MustParseAddr(address)) {
			t.Errorf("special-purpose address deemed public: %s", address)
		}
	}
	for _, address := range []string{"1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"} {
		if !PublicAddress(netip.MustParseAddr(address)) {
			t.Errorf("public address rejected: %s", address)
		}
	}
}

func TestCacheValidatorsStripResponseSplitting(t *testing.T) {
	if got := sanitizedValidator(" \"etag\" "); got != "\"etag\"" {
		t.Fatalf("unexpected cache validator %q", got)
	}
	for _, unsafe := range []string{"x\r\nHeader: injected", strings.Repeat("x", 513)} {
		if sanitizedValidator(unsafe) != "" {
			t.Fatalf("accepted unsafe validator")
		}
	}
}

func TestSingleFetchClientBoundsHeadersAndDisablesIdleConnections(t *testing.T) {
	client := newClient(2 * time.Second)
	tr, ok := client.Transport.(*http.Transport)
	if !ok {
		t.Fatal("expected native HTTPS transport")
	}
	if tr.Proxy != nil || !tr.DisableKeepAlives ||
		tr.MaxResponseHeaderBytes > 32*1024 ||
		tr.ResponseHeaderTimeout != 2*time.Second {
		t.Fatalf("unbounded or proxy-redirectable HTTP fetch transport: %+v", tr)
	}
}
