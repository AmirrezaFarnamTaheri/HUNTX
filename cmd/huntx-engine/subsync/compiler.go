// Package subsync provides universal compilers for proxy nodes into Sing-box 1.10+, Clash Meta / Mihomo, and Xray formats.
// Source: HUNTX Master Porting Compendium §4 & §8
package subsync

import (
	"errors"
	"fmt"
	"strings"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/stream"
)

// CompileOptions defines optional optimization flags including packet fragmentation and early data.
type CompileOptions struct {
	EnableFragment   bool   `json:"enable_fragment"`
	FragmentLength   string `json:"fragment_length"`   // default "10-20"
	FragmentInterval string `json:"fragment_interval"` // default "10-20"
	EnableEarlyData  bool   `json:"enable_early_data"`
	EarlyDataLength  int    `json:"early_data_length"` // default 2560
}

// CompileSingBox compiles a NormalizedNode into a Sing-box 1.10+ compatible outbound map.
func CompileSingBox(node stream.NormalizedNode, opts CompileOptions) (map[string]interface{}, error) {
	if node.Host == "" || node.Port == 0 {
		return nil, errors.New("subsync: invalid node host or port")
	}

	tag := node.Remark
	if tag == "" {
		tag = fmt.Sprintf("%s-%s-%d", node.Protocol, node.Host, node.Port)
	}

	out := map[string]interface{}{
		"type":        node.Protocol,
		"tag":         tag,
		"server":      node.Host,
		"server_port": node.Port,
	}

	// Protocol specific credentials
	switch node.Protocol {
	case "vless":
		out["uuid"] = node.UUID
		if node.Network == "tcp" && node.Security == "reality" {
			out["flow"] = "xtls-rprx-vision"
		}
	case "vmess":
		out["uuid"] = node.UUID
		out["security"] = "auto"
		out["alter_id"] = 0
	case "trojan":
		out["password"] = node.Password
	case "shadowsocks":
		out["method"] = node.Cipher
		out["password"] = node.Password
	case "hysteria2":
		out["password"] = node.Password
		if node.SNI != "" {
			out["tls"] = map[string]interface{}{
				"enabled":     true,
				"server_name": node.SNI,
				"insecure":    node.Insecure,
			}
		}
		return out, nil
	case "tuic":
		out["uuid"] = node.UUID
		out["password"] = node.Password
		out["congestion_control"] = "bbr"
		if node.SNI != "" {
			out["tls"] = map[string]interface{}{
				"enabled":     true,
				"server_name": node.SNI,
				"insecure":    node.Insecure,
			}
		}
		return out, nil
	default:
		return nil, fmt.Errorf("subsync: unsupported sing-box protocol %s", node.Protocol)
	}

	// TLS / Reality configurations
	if node.Security == "tls" || node.Security == "reality" {
		tlsMap := map[string]interface{}{
			"enabled":     true,
			"server_name": node.SNI,
			"insecure":    node.Insecure,
		}

		if node.ALPN != "" {
			tlsMap["alpn"] = strings.Split(node.ALPN, ",")
		}

		if node.Fingerprint != "" {
			tlsMap["utls"] = map[string]interface{}{
				"enabled":     true,
				"fingerprint": node.Fingerprint,
			}
		}

		if node.Security == "reality" {
			tlsMap["reality"] = map[string]interface{}{
				"enabled":    true,
				"public_key": node.PublicKey,
				"short_id":   node.ShortID,
			}
		}

		if opts.EnableFragment {
			fragLen := opts.FragmentLength
			if fragLen == "" {
				fragLen = "10-20"
			}
			fragInt := opts.FragmentInterval
			if fragInt == "" {
				fragInt = "10-20"
			}
			tlsMap["fragment"] = map[string]interface{}{
				"enabled": true,
				"size":    fragLen,
				"sleep":   fragInt,
			}
		}

		out["tls"] = tlsMap
	}

	// Transport configuration
	switch node.Network {
	case "grpc":
		out["transport"] = map[string]interface{}{
			"type":         "grpc",
			"service_name": node.ServiceName,
		}
	case "ws", "websocket":
		wsPath := node.Path
		if opts.EnableEarlyData {
			edLen := opts.EarlyDataLength
			if edLen <= 0 {
				edLen = 2560
			}
			wsPath = ApplyEarlyData(wsPath, edLen)
		}
		wsMap := map[string]interface{}{
			"type": "ws",
			"path": wsPath,
		}
		if node.HostHeader != "" {
			wsMap["headers"] = map[string]interface{}{
				"Host": node.HostHeader,
			}
		}
		out["transport"] = wsMap
	case "httpupgrade":
		out["transport"] = map[string]interface{}{
			"type": "httpupgrade",
			"path": node.Path,
			"host": node.HostHeader,
		}
	}

	return out, nil
}

// CompileClashMeta compiles a NormalizedNode into a Clash Meta / Mihomo compatible map.
func CompileClashMeta(node stream.NormalizedNode, opts CompileOptions) (map[string]interface{}, error) {
	if node.Host == "" || node.Port == 0 {
		return nil, errors.New("subsync: invalid node host or port")
	}

	name := node.Remark
	if name == "" {
		name = fmt.Sprintf("%s-%s-%d", node.Protocol, node.Host, node.Port)
	}

	out := map[string]interface{}{
		"name":   name,
		"type":   node.Protocol,
		"server": node.Host,
		"port":   node.Port,
	}

	switch node.Protocol {
	case "vless":
		out["uuid"] = node.UUID
		out["udp"] = true
	case "vmess":
		out["uuid"] = node.UUID
		out["alterId"] = 0
		out["cipher"] = "auto"
		out["udp"] = true
	case "trojan":
		out["password"] = node.Password
		out["udp"] = true
	case "shadowsocks":
		out["cipher"] = node.Cipher
		out["password"] = node.Password
		out["udp"] = true
		return out, nil
	case "hysteria2":
		out["password"] = node.Password
		out["sni"] = node.SNI
		out["skip-cert-verify"] = node.Insecure
		return out, nil
	case "tuic":
		out["uuid"] = node.UUID
		out["password"] = node.Password
		out["sni"] = node.SNI
		out["congestion-controller"] = "bbr"
		out["skip-cert-verify"] = node.Insecure
		return out, nil
	default:
		return nil, fmt.Errorf("subsync: unsupported clash protocol %s", node.Protocol)
	}

	// Security & TLS
	if node.Security == "tls" || node.Security == "reality" {
		out["tls"] = true
		out["servername"] = node.SNI
		out["skip-cert-verify"] = node.Insecure

		if node.Fingerprint != "" {
			out["client-fingerprint"] = node.Fingerprint
		}

		if node.Security == "reality" {
			out["reality-opts"] = map[string]interface{}{
				"public-key": node.PublicKey,
				"short-id":   node.ShortID,
			}
		}
	}

	// Network Transport
	if node.Network != "" && node.Network != "tcp" {
		out["network"] = node.Network
	}

	switch node.Network {
	case "grpc":
		out["grpc-opts"] = map[string]interface{}{
			"grpc-service-name": node.ServiceName,
		}
	case "ws", "websocket":
		wsPath := node.Path
		if opts.EnableEarlyData {
			edLen := opts.EarlyDataLength
			if edLen <= 0 {
				edLen = 2560
			}
			wsPath = ApplyEarlyData(wsPath, edLen)
		}
		wsOpts := map[string]interface{}{
			"path": wsPath,
		}
		if node.HostHeader != "" {
			wsOpts["headers"] = map[string]interface{}{
				"Host": node.HostHeader,
			}
		}
		out["ws-opts"] = wsOpts
	}

	return out, nil
}
