// Package stream provides high-throughput stream ingestion, URI normalization, and deduplication for proxy nodes.
// Source: HUNTX Master Porting Compendium §4 & §8
package stream

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"sync"
)

// Pre-compiled regular expressions for fast string sanitization.
var (
	emojiRegex    = regexp.MustCompile(`[\x{1F600}-\x{1F64F}\x{1F300}-\x{1F5FF}\x{1F680}-\x{1F6FF}\x{1F700}-\x{1F77F}\x{1F780}-\x{1F7FF}\x{1F800}-\x{1F8FF}\x{1F900}-\x{1F9FF}\x{1FA00}-\x{1FA6F}\x{1FA70}-\x{1FAFF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}\x{1F1E6}-\x{1F1FF}]`)
	telegramRegex = regexp.MustCompile(`(?i)(?:https?://)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_+]+|@[a-zA-Z0-9_]+`)
	httpUrlRegex  = regexp.MustCompile(`(?i)https?://[^\s]+`)
	extraSpace    = regexp.MustCompile(`\s{2,}`)
)

// bufferPool recycles byte buffers to achieve zero-allocation streaming.
var bufferPool = sync.Pool{
	New: func() interface{} {
		return new(bytes.Buffer)
	},
}

// NormalizedNode represents a unified, canonical proxy endpoint.
type NormalizedNode struct {
	Protocol    string            `json:"protocol"`
	Host        string            `json:"host"`
	Port        int               `json:"port"`
	UUID        string            `json:"uuid,omitempty"`
	Password    string            `json:"password,omitempty"`
	Cipher      string            `json:"cipher,omitempty"`
	Security    string            `json:"security,omitempty"` // none, tls, reality
	SNI         string            `json:"sni,omitempty"`
	ALPN        string            `json:"alpn,omitempty"`
	Fingerprint string            `json:"fp,omitempty"`
	PublicKey   string            `json:"pbk,omitempty"`
	ShortID     string            `json:"sid,omitempty"`
	SpiderX     string            `json:"spx,omitempty"`
	Network     string            `json:"net,omitempty"` // tcp, ws, grpc, h2, httpupgrade
	Path        string            `json:"path,omitempty"`
	HostHeader  string            `json:"host_header,omitempty"`
	ServiceName string            `json:"service_name,omitempty"`
	Insecure    bool              `json:"insecure,omitempty"`
	Remark      string            `json:"remark,omitempty"`
	RawURI      string            `json:"raw_uri,omitempty"`
	Params      map[string]string `json:"params,omitempty"`
}

// IdentityKey produces a deterministic unique hash key based on transport identity.
func (n *NormalizedNode) IdentityKey() string {
	authKey := n.UUID
	if authKey == "" {
		authKey = n.Password
	}
	raw := fmt.Sprintf("%s://%s@%s:%d%s?sec=%s&net=%s&sni=%s&cipher=%s&alpn=%s&fp=%s&pbk=%s&sid=%s&spx=%s&host=%s&service=%s&insecure=%t",
		n.Protocol,
		authKey,
		strings.ToLower(n.Host),
		n.Port,
		n.Path,
		n.Security,
		n.Network,
		strings.ToLower(n.SNI),
		n.Cipher,
		n.ALPN,
		n.Fingerprint,
		n.PublicKey,
		n.ShortID,
		n.SpiderX,
		n.HostHeader,
		n.ServiceName,
		n.Insecure,
	)
	hash := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(hash[:])
}

// vmessJSON represents the vmess v2ray standard JSON schema.
type vmessJSON struct {
	V    interface{} `json:"v"`
	Ps   string      `json:"ps"`
	Add  string      `json:"add"`
	Port interface{} `json:"port"`
	ID   string      `json:"id"`
	Aid  interface{} `json:"aid"`
	Net  string      `json:"net"`
	Type string      `json:"type"`
	Host string      `json:"host"`
	Path string      `json:"path"`
	TLS  string      `json:"tls"`
	SNI  string      `json:"sni"`
	ALPN string      `json:"alpn"`
	Fp   string      `json:"fp"`
	Scy  string      `json:"scy"`
}

// NormalizeURI parses, validates, and normalizes a single proxy link string.
func NormalizeURI(rawURI string) (NormalizedNode, error) {
	rawURI = strings.TrimSpace(rawURI)
	if rawURI == "" {
		return NormalizedNode{}, errors.New("stream: empty URI")
	}

	lower := strings.ToLower(rawURI)

	switch {
	case strings.HasPrefix(lower, "vmess://"):
		return parseVMess(rawURI)
	case strings.HasPrefix(lower, "vless://"):
		return parseVLess(rawURI)
	case strings.HasPrefix(lower, "trojan://"):
		return parseTrojan(rawURI)
	case strings.HasPrefix(lower, "ss://"):
		return parseShadowsocks(rawURI)
	case strings.HasPrefix(lower, "hysteria2://") || strings.HasPrefix(lower, "hy2://"):
		return parseHysteria2(rawURI)
	case strings.HasPrefix(lower, "tuic://"):
		return parseTUIC(rawURI)
	default:
		return NormalizedNode{}, fmt.Errorf("stream: unsupported protocol in %q", rawURI)
	}
}

// parseVLess parses standard VLESS URI schemes.
func parseVLess(rawURI string) (NormalizedNode, error) {
	u, err := url.Parse(rawURI)
	if err != nil {
		return NormalizedNode{}, fmt.Errorf("stream: invalid vless URL: %w", err)
	}

	port, _ := strconv.Atoi(u.Port())
	if port == 0 {
		port = 443
	}

	q := u.Query()
	node := NormalizedNode{
		Protocol:    "vless",
		Host:        u.Hostname(),
		Port:        port,
		UUID:        u.User.Username(),
		Security:    q.Get("security"),
		SNI:         q.Get("sni"),
		ALPN:        q.Get("alpn"),
		Fingerprint: q.Get("fp"),
		PublicKey:   q.Get("pbk"),
		ShortID:     q.Get("sid"),
		SpiderX:     q.Get("spx"),
		Network:     q.Get("type"),
		Path:        q.Get("path"),
		HostHeader:  q.Get("host"),
		ServiceName: q.Get("serviceName"),
		Insecure:    q.Get("allowInsecure") == "1" || q.Get("insecure") == "1",
		Remark:      SanitizeRemark(u.Fragment),
		RawURI:      rawURI,
	}

	if node.Network == "" {
		node.Network = "tcp"
	}
	if node.Security == "" {
		node.Security = "none"
	}

	return node, nil
}

// parseVMess decodes base64-encoded vmess JSON definitions.
func parseVMess(rawURI string) (NormalizedNode, error) {
	b64Data := strings.TrimPrefix(rawURI, "vmess://")
	b64Data = strings.TrimPrefix(b64Data, "VMESS://")
	b64Data = strings.TrimSpace(b64Data)

	decoded, err := base64DecodeAuto(b64Data)
	if err != nil {
		return NormalizedNode{}, fmt.Errorf("stream: failed base64 decoding vmess: %w", err)
	}

	var v vmessJSON
	if err := json.Unmarshal(decoded, &v); err != nil {
		return NormalizedNode{}, fmt.Errorf("stream: failed json unmarshal vmess: %w", err)
	}

	port := 443
	switch p := v.Port.(type) {
	case float64:
		port = int(p)
	case string:
		if pi, err := strconv.Atoi(p); err == nil {
			port = pi
		}
	}

	security := strings.ToLower(v.TLS)
	if security == "" {
		security = "none"
	}

	sni := v.SNI
	if sni == "" && v.Host != "" {
		sni = v.Host
	}

	node := NormalizedNode{
		Protocol:    "vmess",
		Host:        v.Add,
		Port:        port,
		UUID:        v.ID,
		Security:    security,
		SNI:         sni,
		ALPN:        v.ALPN,
		Fingerprint: v.Fp,
		Network:     v.Net,
		Path:        v.Path,
		HostHeader:  v.Host,
		Remark:      SanitizeRemark(v.Ps),
		RawURI:      rawURI,
	}

	if node.Network == "" {
		node.Network = "tcp"
	}

	return node, nil
}

// parseTrojan parses standard trojan:// URIs.
func parseTrojan(rawURI string) (NormalizedNode, error) {
	u, err := url.Parse(rawURI)
	if err != nil {
		return NormalizedNode{}, fmt.Errorf("stream: invalid trojan URL: %w", err)
	}

	port, _ := strconv.Atoi(u.Port())
	if port == 0 {
		port = 443
	}

	q := u.Query()
	node := NormalizedNode{
		Protocol:    "trojan",
		Host:        u.Hostname(),
		Port:        port,
		Password:    u.User.Username(),
		Security:    q.Get("security"),
		SNI:         q.Get("sni"),
		ALPN:        q.Get("alpn"),
		Fingerprint: q.Get("fp"),
		Network:     q.Get("type"),
		Path:        q.Get("path"),
		HostHeader:  q.Get("host"),
		Insecure:    q.Get("allowInsecure") == "1" || q.Get("insecure") == "1",
		Remark:      SanitizeRemark(u.Fragment),
		RawURI:      rawURI,
	}

	if node.Security == "" {
		node.Security = "tls"
	}
	if node.Network == "" {
		node.Network = "tcp"
	}

	return node, nil
}

// parseShadowsocks handles standard SIP002 shadowsocks URIs.
func parseShadowsocks(rawURI string) (NormalizedNode, error) {
	u, err := url.Parse(rawURI)
	if err != nil {
		return NormalizedNode{}, fmt.Errorf("stream: invalid ss URL: %w", err)
	}

	var cipher, password string

	if u.User != nil {
		userInfo := u.User.String()
		// Check if userinfo is base64 encoded
		decoded, err := base64DecodeAuto(userInfo)
		if err == nil && strings.Contains(string(decoded), ":") {
			parts := strings.SplitN(string(decoded), ":", 2)
			cipher = parts[0]
			password = parts[1]
		} else {
			cipher = u.User.Username()
			password, _ = u.User.Password()
		}
	}

	port, _ := strconv.Atoi(u.Port())
	if port == 0 {
		port = 8388
	}

	return NormalizedNode{
		Protocol: "shadowsocks",
		Host:     u.Hostname(),
		Port:     port,
		Cipher:   cipher,
		Password: password,
		Remark:   SanitizeRemark(u.Fragment),
		RawURI:   rawURI,
	}, nil
}

// parseHysteria2 handles hysteria2 / hy2 links.
func parseHysteria2(rawURI string) (NormalizedNode, error) {
	u, err := url.Parse(rawURI)
	if err != nil {
		return NormalizedNode{}, fmt.Errorf("stream: invalid hysteria2 URL: %w", err)
	}

	port, _ := strconv.Atoi(u.Port())
	if port == 0 {
		port = 443
	}

	q := u.Query()
	return NormalizedNode{
		Protocol: "hysteria2",
		Host:     u.Hostname(),
		Port:     port,
		Password: u.User.Username(),
		SNI:      q.Get("sni"),
		ALPN:     q.Get("alpn"),
		Insecure: q.Get("insecure") == "1",
		Remark:   SanitizeRemark(u.Fragment),
		RawURI:   rawURI,
	}, nil
}

// parseTUIC handles tuic:// links.
func parseTUIC(rawURI string) (NormalizedNode, error) {
	u, err := url.Parse(rawURI)
	if err != nil {
		return NormalizedNode{}, fmt.Errorf("stream: invalid tuic URL: %w", err)
	}

	port, _ := strconv.Atoi(u.Port())
	if port == 0 {
		port = 8443
	}

	uuid := u.User.Username()
	password, _ := u.User.Password()

	q := u.Query()
	return NormalizedNode{
		Protocol: "tuic",
		Host:     u.Hostname(),
		Port:     port,
		UUID:     uuid,
		Password: password,
		SNI:      q.Get("sni"),
		ALPN:     q.Get("alpn"),
		Insecure: q.Get("allow_insecure") == "1",
		Remark:   SanitizeRemark(u.Fragment),
		RawURI:   rawURI,
	}, nil
}

// SanitizeRemark removes emojis, Telegram channel promotions, HTTP links, and excessive spacing from remarks.
func SanitizeRemark(raw string) string {
	decoded, err := url.QueryUnescape(raw)
	if err == nil {
		raw = decoded
	}

	s := emojiRegex.ReplaceAllString(raw, "")
	s = telegramRegex.ReplaceAllString(s, "")
	s = httpUrlRegex.ReplaceAllString(s, "")
	s = extraSpace.ReplaceAllString(s, " ")
	s = strings.TrimSpace(s)

	// Clean trailing delimiters
	s = strings.Trim(s, "-_|/\\ ")

	if s == "" {
		return "HUNTX-Node"
	}
	return s
}

// EnrichedRemarkOptions configures rich telemetry and metadata attributes for node remarks.
type EnrichedRemarkOptions struct {
	Country        string  `json:"country,omitempty"`         // 2-letter ISO code (e.g. DE, IR, US)
	Operator       string  `json:"operator,omitempty"`        // Network/Operator code (e.g. MCI, MTN, CF)
	LatencyMs      int     `json:"latency_ms,omitempty"`      // Measured RTT ping latency in ms
	HealthScore    float64 `json:"health_score,omitempty"`    // Synthetic health score 0-100
	HealthGrade    string  `json:"health_grade,omitempty"`    // Grade letter (A+, A, B, C)
	Index          int     `json:"index,omitempty"`           // Sequential node identifier
	IncludeStats   bool    `json:"include_stats,omitempty"`   // Include ping/grade in tag
	IncludeEvasion bool    `json:"include_evasion,omitempty"` // Include TLS fragment/evasion status
	CustomTag      string  `json:"custom_tag,omitempty"`      // Optional user-specified tag
}

// CountryCodeToFlag converts an ISO 3166-1 alpha-2 country code to its corresponding emoji flag.
func CountryCodeToFlag(countryCode string) string {
	countryCode = strings.ToUpper(strings.TrimSpace(countryCode))
	if len(countryCode) != 2 {
		return "🌐"
	}
	r1 := rune(countryCode[0]) + 127397
	r2 := rune(countryCode[1]) + 127397
	if r1 < 127462 || r1 > 127487 || r2 < 127462 || r2 > 127487 {
		return "🌐"
	}
	return string([]rune{r1, r2})
}

// DetectOperator inspects host, SNI, or remark keywords to deduce the ISP, CDN, or carrier.
func DetectOperator(host, sni, remark string) string {
	combined := strings.ToLower(fmt.Sprintf("%s %s %s", host, sni, remark))
	switch {
	case strings.Contains(combined, "mci") || strings.Contains(combined, "mcci") || strings.Contains(combined, "hamrah"):
		return "MCI"
	case strings.Contains(combined, "mtn") || strings.Contains(combined, "irancell"):
		return "MTN"
	case strings.Contains(combined, "rtl") || strings.Contains(combined, "rightel"):
		return "RTL"
	case strings.Contains(combined, "ztl") || strings.Contains(combined, "ziatel"):
		return "ZTL"
	case strings.Contains(combined, "mokhaberat") || strings.Contains(combined, "tci"):
		return "TCI"
	case strings.Contains(combined, "cloudflare") || strings.Contains(combined, "cf-") || strings.Contains(combined, ".workers.dev") || strings.Contains(combined, ".pages.dev"):
		return "CF"
	case strings.Contains(combined, "hetzner") || strings.Contains(combined, "your-server.de"):
		return "Hetzner"
	case strings.Contains(combined, "digitalocean") || strings.Contains(combined, "do-"):
		return "DO"
	case strings.Contains(combined, "ovh"):
		return "OVH"
	case strings.Contains(combined, "arvan") || strings.Contains(combined, "arvancloud"):
		return "Arvan"
	case strings.Contains(combined, "derak"):
		return "Derak"
	default:
		return ""
	}
}

// FormatEnrichedRemark generates an information-dense, structured display remark.
// Example: "🇩🇪 DE-CF | VLESS-REALITY-GRPC | ⚡38ms | ⭐A+ | #001"
func FormatEnrichedRemark(node NormalizedNode, opts EnrichedRemarkOptions) string {
	var parts []string

	// 1. Country & Flag
	country := strings.ToUpper(strings.TrimSpace(opts.Country))
	if country == "" {
		country = "GLOBAL"
	}
	flag := CountryCodeToFlag(country)

	op := opts.Operator
	if op == "" {
		op = DetectOperator(node.Host, node.SNI, node.Remark)
	}

	if op != "" {
		parts = append(parts, fmt.Sprintf("%s %s-%s", flag, country, op))
	} else {
		parts = append(parts, fmt.Sprintf("%s %s", flag, country))
	}

	// 2. Protocol & Security & Network
	protoTag := strings.ToUpper(node.Protocol)
	if node.Security != "" && node.Security != "none" {
		protoTag = fmt.Sprintf("%s-%s", protoTag, strings.ToUpper(node.Security))
	}
	if node.Network != "" && node.Network != "tcp" {
		protoTag = fmt.Sprintf("%s-%s", protoTag, strings.ToUpper(node.Network))
	}
	parts = append(parts, protoTag)

	// 3. Evasion Tag if applicable
	if opts.IncludeEvasion {
		if strings.Contains(strings.ToLower(node.Path), "frag") || strings.Contains(strings.ToLower(node.Remark), "frag") {
			parts = append(parts, "[Frag:1-3]")
		}
	}

	// 4. Latency & Performance stats
	if opts.IncludeStats || opts.LatencyMs > 0 || opts.HealthGrade != "" {
		if opts.LatencyMs > 0 {
			parts = append(parts, fmt.Sprintf("⚡%dms", opts.LatencyMs))
		}
		if opts.HealthGrade != "" {
			parts = append(parts, fmt.Sprintf("⭐%s", opts.HealthGrade))
		} else if opts.HealthScore > 0 {
			switch {
			case opts.HealthScore >= 90:
				parts = append(parts, "⭐A+")
			case opts.HealthScore >= 80:
				parts = append(parts, "⭐A")
			case opts.HealthScore >= 65:
				parts = append(parts, "⭐B")
			default:
				parts = append(parts, "⭐C")
			}
		}
	}

	// 5. Index Identifier
	if opts.Index > 0 {
		parts = append(parts, fmt.Sprintf("#%03d", opts.Index))
	} else if opts.CustomTag != "" {
		parts = append(parts, opts.CustomTag)
	}

	return strings.Join(parts, " | ")
}

// EnrichURI injects the enriched remark into any supported proxy link.
func EnrichURI(rawURI string, opts EnrichedRemarkOptions) (string, error) {
	node, err := NormalizeURI(rawURI)
	if err != nil {
		return rawURI, err
	}

	remark := FormatEnrichedRemark(node, opts)

	if strings.HasPrefix(strings.ToLower(rawURI), "vmess://") {
		b64Data := strings.TrimPrefix(rawURI, "vmess://")
		b64Data = strings.TrimPrefix(b64Data, "VMESS://")
		decoded, err := base64DecodeAuto(b64Data)
		if err != nil {
			return rawURI, err
		}
		var v map[string]interface{}
		if err := json.Unmarshal(decoded, &v); err != nil {
			return rawURI, err
		}
		v["ps"] = remark
		newJSON, err := json.Marshal(v)
		if err != nil {
			return rawURI, err
		}
		return "vmess://" + base64.StdEncoding.EncodeToString(newJSON), nil
	}

	// For URI protocols with #fragment
	idx := strings.LastIndex(rawURI, "#")
	base := rawURI
	if idx != -1 {
		base = rawURI[:idx]
	}
	return fmt.Sprintf("%s#%s", base, url.QueryEscape(remark)), nil
}

// StreamDeduplicator provides thread-safe, high-capacity identity deduplication.
type StreamDeduplicator struct {
	mu       sync.RWMutex
	capacity int
	seen     map[string]struct{}
}

// NewStreamDeduplicator instantiates a thread-safe deduplication engine.
func NewStreamDeduplicator(capacity int) *StreamDeduplicator {
	if capacity <= 0 {
		capacity = 50000
	}
	return &StreamDeduplicator{
		capacity: capacity,
		seen:     make(map[string]struct{}, capacity),
	}
}

// IsDuplicate checks if the given node has already been observed.
func (d *StreamDeduplicator) IsDuplicate(node NormalizedNode) bool {
	key := node.IdentityKey()
	d.mu.RLock()
	defer d.mu.RUnlock()
	_, exists := d.seen[key]
	return exists
}

// Add attempts to record a node. Returns true if newly added, false if already seen.
func (d *StreamDeduplicator) Add(node NormalizedNode) bool {
	key := node.IdentityKey()
	d.mu.Lock()
	defer d.mu.Unlock()

	if _, exists := d.seen[key]; exists {
		return false
	}

	if len(d.seen) >= d.capacity {
		// Evict randomly to prevent unbounded memory growth in high-load streaming
		for k := range d.seen {
			delete(d.seen, k)
			break
		}
	}

	d.seen[key] = struct{}{}
	return true
}

// Count returns the number of unique identity keys tracked in memory.
func (d *StreamDeduplicator) Count() int {
	d.mu.RLock()
	defer d.mu.RUnlock()
	return len(d.seen)
}

// Ingest reads lines from an io.Reader and streams unique, normalized nodes over a channel.
func Ingest(ctx context.Context, r io.Reader, bufferSize int) <-chan NormalizedNode {
	if bufferSize <= 0 {
		bufferSize = 256
	}
	out := make(chan NormalizedNode, bufferSize)
	dedup := NewStreamDeduplicator(100000)

	go func() {
		defer close(out)
		scanner := bufio.NewScanner(r)
		// Allocate 64KB scan buffer
		buf := make([]byte, 64*1024)
		scanner.Buffer(buf, 1024*1024)

		for scanner.Scan() {
			select {
			case <-ctx.Done():
				return
			default:
			}

			line := strings.TrimSpace(scanner.Text())
			if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(line, "//") {
				continue
			}

			node, err := NormalizeURI(line)
			if err != nil {
				continue
			}

			if dedup.Add(node) {
				select {
				case out <- node:
				case <-ctx.Done():
					return
				}
			}
		}
	}()

	return out
}

// base64DecodeAuto handles both standard and URL base64 encodings with optional padding.
func base64DecodeAuto(s string) ([]byte, error) {
	s = strings.TrimSpace(s)
	// Add padding if missing
	if pad := len(s) % 4; pad != 0 {
		s += strings.Repeat("=", 4-pad)
	}

	if data, err := base64.StdEncoding.DecodeString(s); err == nil {
		return data, nil
	}

	return base64.URLEncoding.DecodeString(s)
}
