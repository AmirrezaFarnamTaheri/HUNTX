// Package tlsdiag provides active TLS handshake probing, ALPN negotiation inspection,
// cipher suite audit, and JA4 fingerprint generation for proxy censorship analysis.
//
// Citations:
//   - TLS 1.3 Protocol: RFC 8446 (https://datatracker.ietf.org/doc/html/rfc8446)
//   - TLS ALPN Extension: RFC 7301 (https://datatracker.ietf.org/doc/html/rfc7301)
//   - FoxIO JA4 Specification: https://github.com/FoxIO-LLC/ja4
package tlsdiag

import (
	"context"
	"time"
)

// SecurityPosture evaluates the censorship and eavesdropping resilience of a target's TLS endpoint.
type SecurityPosture int

const (
	// PostureUnknown represents an unprobed or invalid security state.
	PostureUnknown SecurityPosture = iota
	// PostureHardened represents TLS 1.3 with modern ALPN (h2/h3) and authenticated AEAD ciphers.
	PostureHardened
	// PostureStandard represents standard TLS 1.2 with acceptable cipher suites.
	PostureStandard
	// PostureVulnerable represents deprecated TLS versions or weak/fingerprintable cipher configurations.
	PostureVulnerable
)

// String returns the canonical human-readable posture representation.
func (p SecurityPosture) String() string {
	switch p {
	case PostureHardened:
		return "hardened"
	case PostureStandard:
		return "standard"
	case PostureVulnerable:
		return "vulnerable"
	default:
		return "unknown"
	}
}

// TLSReport summarizes the negotiated TLS session parameters and security posture.
type TLSReport struct {
	Target         string          `json:"target"`
	ServerName     string          `json:"server_name"`
	TLSVersion     string          `json:"tls_version"`
	CipherSuite    string          `json:"cipher_suite"`
	ALPN           string          `json:"alpn"`
	JA4Fingerprint string          `json:"ja4_fingerprint"`
	Posture        SecurityPosture `json:"posture"`
	PostureName    string          `json:"posture_name"`
	HandshakeTime  time.Duration   `json:"handshake_time_ms"`
	Success        bool            `json:"success"`
	Error          string          `json:"error,omitempty"`
}

// Prober defines the contract for running active TLS diagnostic handshakes.
type Prober interface {
	Probe(ctx context.Context, target string, serverName string) TLSReport
}
