// Package localmihomo performs bounded, read-only HTTPS URL tests against a
// named leaf proxy through an authenticated Mihomo loopback controller.
// Controller results are not independent TLS evidence or proof of revival.
package localmihomo

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	testURL       = "https://www.gstatic.com/generate_204"
	responseLimit = 64 << 10
)

// Result contains no node names, controller addresses, authentication secrets,
// browsing history or proxy credentials.
type Result struct {
	Evidence                 string `json:"evidence"`
	Attempts                 int    `json:"attempts"`
	Successes                int    `json:"successes"`
	NativeTestPassed         bool   `json:"native_test_passed"`
	NodeAttributed           bool   `json:"node_attributed"`
	TLSIndependentlyVerified bool   `json:"tls_independently_verified"`
	OriginalRecovered        bool   `json:"original_recovered"`
	MedianDelayMS            int    `json:"median_delay_ms,omitempty"`
	ErrorClass               string `json:"error_class,omitempty"`
}

type Controller struct {
	base   *url.URL
	token  string
	client *http.Client
}

// New refuses any nonloopback, credentialed or non-HTTP controller URL.
// The controller's API token is mandatory and never printed.
func New(raw, token string) (*Controller, error) {
	u, err := url.Parse(raw)
	if err != nil || u == nil || u.Scheme != "http" || u.Host == "" || u.User != nil || u.Path != "" || u.RawQuery != "" || u.Fragment != "" || u.Opaque != "" || u.RawPath != "" {
		return nil, errors.New("invalid loopback Mihomo controller URL")
	}
	host := u.Hostname()
	ip := net.ParseIP(host)
	if strings.EqualFold(host, "localhost") {
		host = "127.0.0.1"
	} else if ip == nil || !ip.IsLoopback() {
		return nil, errors.New("controller must be loopback-only")
	}
	port, err := strconv.Atoi(u.Port())
	if err != nil || port < 1 || port > 65535 {
		return nil, errors.New("invalid controller port")
	}
	if err := validateToken(token); err != nil {
		return nil, err
	}
	pinned := net.JoinHostPort(host, u.Port())
	u.Host = pinned
	tr := &http.Transport{
		Proxy: nil,
		DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
			// Never allow a redirect or forged URL to dial any other address.
			return (&net.Dialer{Timeout: 2 * time.Second}).DialContext(ctx, "tcp", pinned)
		},
		DisableKeepAlives: true,
	}
	return &Controller{base: u, token: token, client: &http.Client{
		Transport:     tr,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}}, nil
}

func validateToken(token string) error {
	if len(token) < 12 || len(token) > 2048 || strings.TrimSpace(token) != token || strings.ContainsAny(token, "\r\n\x00") {
		return errors.New("Mihomo controller token must be nonempty, private and at least 12 characters")
	}
	return nil
}

// ReadTokenFile uses a separate protected file, never command-line arguments
// or environment variables that commonly leak into process reports.
func ReadTokenFile(path string) (string, error) {
	stat, err := os.Lstat(path)
	if err != nil {
		return "", errors.New("controller token file unavailable")
	}
	if !stat.Mode().IsRegular() || stat.Size() > 4096 || stat.Size() < 12 {
		return "", errors.New("invalid controller token file")
	}
	if runtime.GOOS != "windows" && stat.Mode().Perm()&0077 != 0 {
		return "", errors.New("controller token file must not be group/world accessible")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", errors.New("controller token file unavailable")
	}
	token := strings.TrimSpace(string(data))
	if err := validateToken(token); err != nil {
		return "", err
	}
	return token, nil
}

func validNode(name string) bool {
	if !utf8.ValidString(name) || len(name) > 256 || strings.TrimSpace(name) == "" || name == "." || name == ".." {
		return false
	}
	for _, r := range name {
		if r < 0x20 || r == 0x7f {
			return false
		}
	}
	return true
}

var concreteLeafTypes = map[string]bool{
	"shadowsocks": true, "ss": true, "shadowsocksr": true, "ssr": true,
	"vmess": true, "vless": true, "trojan": true, "hysteria": true, "hysteria2": true,
	"tuic": true, "socks5": true, "http": true, "https": true, "snell": true,
	"ssh": true, "wireguard": true, "anytls": true, "shadowtls": true,
}

type proxyDetails struct {
	Name        string          `json:"name"`
	Type        string          `json:"type"`
	All         json.RawMessage `json:"all"`
	DialerProxy string          `json:"dialer-proxy"`
}

func checkLeaf(proxy proxyDetails, name string) bool {
	return proxy.Name == name && concreteLeafTypes[strings.ToLower(strings.TrimSpace(proxy.Type))] && len(proxy.All) == 0 && proxy.DialerProxy == ""
}

func (c *Controller) endpoint(name string, delay bool, timeout time.Duration) string {
	base := c.base.String() + "/proxies/" + url.PathEscape(name)
	if delay {
		q := url.Values{}
		q.Set("url", testURL)
		q.Set("expected", "204")
		q.Set("timeout", strconv.FormatInt(timeout.Milliseconds(), 10))
		base += "/delay?" + q.Encode()
	}
	return base
}

// request returns a generic error class, never a response body, URL or token.
func (c *Controller) request(ctx context.Context, endpoint string, limit time.Duration, out any) string {
	reqCtx, cancel := context.WithTimeout(ctx, limit)
	defer cancel()
	req, err := http.NewRequestWithContext(reqCtx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "invalid-request"
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")
	resp, err := c.client.Do(req)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(reqCtx.Err(), context.DeadlineExceeded) {
			return "timeout"
		}
		return "controller-unavailable"
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return "unauthorized"
	}
	if resp.StatusCode != http.StatusOK {
		return "controller-http"
	}
	if resp.ContentLength > responseLimit {
		return "invalid-response"
	}
	dec := json.NewDecoder(io.LimitReader(resp.Body, responseLimit+1))
	if err := dec.Decode(out); err != nil {
		return "invalid-response"
	}
	var extra any
	if err := dec.Decode(&extra); err != io.EOF {
		return "invalid-response"
	}
	return ""
}

// Probe performs at most three sequential HTTPS URL tests against an explicit
// Mihomo leaf proxy. A successful delay result is controller-reported native
// evidence, not independently verified TLS or server-side repair.
func (c *Controller) Probe(ctx context.Context, name string, timeout time.Duration, attempts int) Result {
	result := Result{Evidence: "mihomo-controller-native-urltest", Attempts: attempts}
	if !validNode(name) {
		result.ErrorClass = "invalid-node"
		return result
	}
	if timeout < time.Second || timeout > 15*time.Second || attempts < 1 || attempts > 3 {
		result.ErrorClass = "invalid-budget"
		return result
	}
	if ctx == nil {
		ctx = context.Background()
	}
	infoURL := c.endpoint(name, false, timeout)
	var before proxyDetails
	code := c.request(ctx, infoURL, 3*time.Second, &before)
	if code != "" {
		result.ErrorClass = code
		return result
	}
	if !checkLeaf(before, name) {
		result.ErrorClass = "not-leaf"
		return result
	}
	delays := make([]int, 0, attempts)
	for i := 0; i < attempts; i++ {
		var measurement struct {
			Delay int `json:"delay"`
		}
		code = c.request(ctx, c.endpoint(name, true, timeout), timeout+2*time.Second, &measurement)
		if code != "" {
			result.ErrorClass = code
			return result
		}
		if measurement.Delay <= 0 || measurement.Delay > 65535 {
			result.ErrorClass = "native-test-failed"
			return result
		}
		delays = append(delays, measurement.Delay)
		result.Successes++
	}
	var after proxyDetails
	code = c.request(ctx, infoURL, 3*time.Second, &after)
	if code != "" {
		result.ErrorClass = code
		return result
	}
	if !checkLeaf(after, name) || !strings.EqualFold(before.Type, after.Type) {
		result.ErrorClass = "changed-node"
		return result
	}
	sort.Ints(delays)
	result.MedianDelayMS = delays[len(delays)/2]
	if len(delays)%2 == 0 {
		result.MedianDelayMS = (delays[len(delays)/2-1] + delays[len(delays)/2]) / 2
	}
	result.NativeTestPassed = true
	result.NodeAttributed = true
	return result
}

// Sanity reference for fixed target, useful to prevent accidental overrides.
func FixedTarget() string { return testURL }
