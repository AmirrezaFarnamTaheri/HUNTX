package localmihomo

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

const testToken = "test-mihomo-secret-safe"

func TestValidateControllerRejectsRemoteAndCredentials(t *testing.T) {
	for _, input := range []string{
		"http://example.com:9090", "http://localhost.evil:9090", "https://127.0.0.1:9090", "http://192.168.1.3:9090", "http://127.0.0.1:9090/abc", "http://user:pass@127.0.0.1:9090", "http://127.0.0.1:9090?url=evil", "http://127.0.0.1:0", "http://127.0.0.1:9090#foo", "http://[::ffff:10.1.1.1]:9090",
	} {
		if _, err := New(input, testToken); err == nil {
			t.Errorf("accepted controller %q", input)
		}
	}
	for _, input := range []string{"http://127.0.0.1:9090", "http://[::1]:9090", "http://localhost:9090"} {
		if _, err := New(input, testToken); err != nil {
			t.Errorf("rejected loopback %q: %v", input, err)
		}
	}
}

func TestControllerNamedLeafNativeHTTPSChecks(t *testing.T) {
	var infoCalls, delayCalls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer "+testToken {
			http.Error(w, "unauthorized", 401)
			return
		}
		if r.Method != "GET" {
			http.Error(w, "not allowed", 405)
			return
		}
		switch r.URL.EscapedPath() {
		case "/proxies/DE%20Trojan":
			infoCalls.Add(1)
			_, _ = w.Write([]byte(`{"name":"DE Trojan","type":"Trojan","alive":false}`))
		case "/proxies/DE%20Trojan/delay":
			delayCalls.Add(1)
			q := r.URL.Query()
			if q.Get("expected") != "204" || q.Get("url") != "https://www.gstatic.com/generate_204" || q.Get("timeout") != "2000" {
				t.Errorf("unexpected URL test params: %v", q)
			}
			_, _ = w.Write([]byte(`{"delay":117}`))
		default:
			t.Errorf("unexpected request: %s", r.URL.String())
			http.NotFound(w, r)
		}
	}))
	defer server.Close()
	client, err := New(server.URL, testToken)
	if err != nil {
		t.Fatal(err)
	}
	out := client.Probe(context.Background(), "DE Trojan", 2*time.Second, 3)
	if !out.NativeTestPassed || !out.NodeAttributed || out.OriginalRecovered || out.TLSIndependentlyVerified || out.Successes != 3 || out.MedianDelayMS != 117 || out.Evidence != "mihomo-controller-native-urltest" {
		t.Fatalf("incorrect evidence: %+v", out)
	}
	if infoCalls.Load() != 2 || delayCalls.Load() != 3 {
		t.Fatalf("expected metadata before+after and 3 real delays, got %d %d", infoCalls.Load(), delayCalls.Load())
	}
}

func TestGroupDirectAndFalseLeavesAreNeverProbed(t *testing.T) {
	for _, info := range []string{`{"name":"ALL","type":"Selector","all":["a"]}`, `{"name":"ALL","type":"DIRECT"}`, `{"name":"ALL","type":"Trojan","all":[]}`, `{"name":"ALL","type":"Mystery"}`, `{"name":"ALL","type":"VLESS","dialer-proxy":"Other"}`} {
		var delayCalls atomic.Int32
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/proxies/ALL" {
				_, _ = w.Write([]byte(info))
				return
			}
			delayCalls.Add(1)
			_, _ = w.Write([]byte(`{"delay":1}`))
		}))
		c, err := New(server.URL, testToken)
		if err != nil {
			t.Fatal(err)
		}
		out := c.Probe(context.Background(), "ALL", time.Second, 1)
		if out.NodeAttributed || out.NativeTestPassed || out.OriginalRecovered || delayCalls.Load() != 0 || out.ErrorClass != "not-leaf" {
			t.Errorf("unsafe proxy %s: %+v, delay calls %d", info, out, delayCalls.Load())
		}
		server.Close()
	}
}

func TestControllerErrorsNeverLeakSecretsOrClaimSuccess(t *testing.T) {
	for _, tc := range []struct {
		name   string
		status int
		body   string
		code   string
	}{
		{"wrong-auth", 401, `{"message":"secret here"}`, "unauthorized"},
		{"redirect", 302, "", "controller-http"},
		{"malformed", 200, `{"delay":"123"}`, "invalid-response"},
		{"zero-delay", 200, `{"delay":0}`, "native-test-failed"},
		{"negative", 200, `{"delay":-2}`, "native-test-failed"},
		{"huge", 200, strings.Repeat("X", 70000), "invalid-response"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path == "/proxies/Node" {
					_, _ = w.Write([]byte(`{"name":"Node","type":"VLESS"}`))
					return
				}
				w.WriteHeader(tc.status)
				_, _ = w.Write([]byte(tc.body))
			}))
			defer server.Close()
			c, _ := New(server.URL, testToken)
			out := c.Probe(context.Background(), "Node", time.Second, 1)
			if out.NativeTestPassed || out.NodeAttributed || out.OriginalRecovered || out.ErrorClass != tc.code {
				t.Errorf("invalid success %+v expected %s", out, tc.code)
			}
			blob, _ := json.Marshal(out)
			if strings.Contains(string(blob), testToken) || strings.Contains(string(blob), "secret here") || strings.Contains(string(blob), "Node") {
				t.Fatalf("leaked sensitive data %s", blob)
			}
		})
	}
}

func TestRejectInjectedNodeAndInvalidBudgets(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("network should never be accessed")
		http.Error(w, "bad", 500)
	}))
	defer server.Close()
	c, _ := New(server.URL, testToken)
	for _, name := range []string{"", ".", "..", "   ", strings.Repeat("x", 257), "abc\nset-header:evil"} {
		out := c.Probe(context.Background(), name, time.Second, 1)
		if out.ErrorClass != "invalid-node" {
			t.Errorf("accepted %q: %+v", name, out)
		}
	}
	for _, budget := range []time.Duration{0, 100 * time.Millisecond, 16 * time.Second} {
		out := c.Probe(context.Background(), "safe", budget, 1)
		if out.ErrorClass != "invalid-budget" {
			t.Errorf("accepted invalid timeout: %+v", out)
		}
	}
	for _, attempts := range []int{0, 4, 1000} {
		out := c.Probe(context.Background(), "safe", time.Second, attempts)
		if out.ErrorClass != "invalid-budget" {
			t.Errorf("accepted invalid attempts: %+v", out)
		}
	}
}

func TestReadTokenFileIsPrivateAndBounded(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "mihomo.secret")
	if err := os.WriteFile(file, []byte(testToken+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	secret, err := ReadTokenFile(file)
	if err != nil || secret != testToken {
		t.Fatalf("read error %v token match %t", err, secret == testToken)
	}
	if err := os.Chmod(file, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadTokenFile(file); err == nil {
		t.Fatal("accepted world-readable token")
	}
	_ = os.Chmod(file, 0600)
	if err := os.WriteFile(file, []byte(strings.Repeat("a", 5000)), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadTokenFile(file); err == nil {
		t.Fatal("accepted oversized secret")
	}
	_ = os.WriteFile(file, []byte(testToken), 0600)
	link := filepath.Join(dir, "link")
	if err := os.Symlink(file, link); err == nil {
		if _, err := ReadTokenFile(link); err == nil {
			t.Fatal("accepted symlink")
		}
	}
}

func TestProxyNameIsEscapedAsOnePathSegment(t *testing.T) {
	var observed atomic.Bool
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.EscapedPath() == "/proxies/a%2Fb%3Fx=y" {
			observed.Store(true)
			_, _ = w.Write([]byte(`{"name":"a/b?x=y","type":"Trojan"}`))
			return
		}
		if r.URL.EscapedPath() == "/proxies/a%2Fb%3Fx=y/delay" {
			_, _ = w.Write([]byte(`{"delay":23}`))
			return
		}
		http.NotFound(w, r)
	}))
	defer server.Close()
	c, _ := New(server.URL, testToken)
	out := c.Probe(context.Background(), "a/b?x=y", time.Second, 1)
	if !observed.Load() || !out.NativeTestPassed {
		t.Fatalf("escaped name not preserved: %+v", out)
	}
}

func TestChangingNodeMetadataRejectsCompletedProbe(t *testing.T) {
	var meta atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/delay") {
			_, _ = w.Write([]byte(`{"delay":77}`))
			return
		}
		if meta.Add(1) == 1 {
			_, _ = w.Write([]byte(`{"name":"A","type":"Trojan"}`))
			return
		}
		_, _ = w.Write([]byte(`{"name":"A","type":"Selector","all":["B"]}`))
	}))
	defer server.Close()
	c, _ := New(server.URL, testToken)
	out := c.Probe(context.Background(), "A", time.Second, 1)
	if out.NativeTestPassed || out.NodeAttributed || out.ErrorClass != "changed-node" {
		t.Fatalf("changed node passed %+v", out)
	}
}

func TestRejectOversizedChunkedJSONEvenWhenPayloadIsInitiallyValid(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/proxies/Test" {
			_, _ = w.Write([]byte(`{"name":"Test","type":"VLESS"}`))
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.(http.Flusher).Flush() // Force chunked framing (unknown ContentLength).
		_, _ = w.Write([]byte(`{"delay":40}` + strings.Repeat(" ", 70000)))
	}))
	defer server.Close()
	c, err := New(server.URL, testToken)
	if err != nil {
		t.Fatal(err)
	}
	outcome := c.Probe(context.Background(), "Test", time.Second, 1)
	if outcome.NativeTestPassed || outcome.ErrorClass != "invalid-response" {
		t.Fatalf("oversized chunked JSON must be rejected: %+v", outcome)
	}
}
