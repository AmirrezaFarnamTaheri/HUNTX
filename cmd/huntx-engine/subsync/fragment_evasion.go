// Package subsync implements TLS Hello packet fragmentation and DPI evasion strategies.
// Source: HUNTX Master Porting Compendium §4 & §8
package subsync

import (
	"fmt"
	"strings"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
)

// FragmentConfig configures Xray/Sing-box TLS ClientHello packet splitting.
type FragmentConfig struct {
	Packets  string `json:"packets"`  // "tlshello" or "1-3"
	Length   string `json:"length"`   // "10-20" or "50-100"
	Interval string `json:"interval"` // "10-20" or "30-50" (ms)
}

// DefaultFragmentConfig returns standard evasion parameters tuned for deep packet inspection bypass.
func DefaultFragmentConfig() FragmentConfig {
	return FragmentConfig{
		Packets:  "tlshello",
		Length:   "10-20",
		Interval: "10-20",
	}
}

// BuildXrayFragmentOutbound generates a multi-outbound Xray configuration chained through a fragment freedom dialer.
func BuildXrayFragmentOutbound(node stream.NormalizedNode, frag FragmentConfig) (map[string]interface{}, error) {
	if frag.Packets == "" {
		frag.Packets = "tlshello"
	}
	if frag.Length == "" {
		frag.Length = "10-20"
	}
	if frag.Interval == "" {
		frag.Interval = "10-20"
	}

	fragmentOutbound := map[string]interface{}{
		"protocol":       "freedom",
		"tag":            "fragment",
		"domainStrategy": "UseIP",
		"sniffing": map[string]interface{}{
			"enabled":      true,
			"destOverride": []string{"http", "tls"},
		},
		"settings": map[string]interface{}{
			"fragment": map[string]interface{}{
				"packets":  frag.Packets,
				"length":   frag.Length,
				"interval": frag.Interval,
			},
		},
		"streamSettings": map[string]interface{}{
			"sockopt": map[string]interface{}{
				"mark": 255,
			},
		},
	}

	proxyOutbound := map[string]interface{}{
		"protocol": node.Protocol,
		"tag":      "proxy",
		"streamSettings": map[string]interface{}{
			"sockopt": map[string]interface{}{
				"dialerProxy": "fragment",
			},
		},
	}

	return map[string]interface{}{
		"outbounds": []interface{}{
			proxyOutbound,
			fragmentOutbound,
		},
	}, nil
}

// ApplyEarlyData appends the ?ed=XXXX or &ed=XXXX query parameter for WebSocket 0-RTT handshakes.
func ApplyEarlyData(path string, earlyDataLength int) string {
	if earlyDataLength <= 0 {
		earlyDataLength = 2560
	}

	path = strings.TrimSpace(path)
	if path == "" {
		path = "/"
	}

	if strings.Contains(path, "?") {
		return fmt.Sprintf("%s&ed=%d", path, earlyDataLength)
	}

	return fmt.Sprintf("%s?ed=%d", path, earlyDataLength)
}
