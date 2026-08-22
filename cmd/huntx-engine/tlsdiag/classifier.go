package tlsdiag

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"time"
)

// Classifier manages active TLS probe handshakes and security posture audits.
type Classifier struct {
	Timeout            time.Duration
	InsecureSkipVerify bool
	ALPNProtos         []string
}

var _ Prober = (*Classifier)(nil)

// NewClassifier creates a new TLS classifier configured with functional options.
func NewClassifier(opts ...Option) *Classifier {
	c := &Classifier{
		Timeout:            3 * time.Second,
		InsecureSkipVerify: true, // Default true for diagnostic inspection of untrusted proxy nodes
		ALPNProtos:         []string{"h2", "http/1.1"},
	}
	for _, opt := range opts {
		opt(c)
	}
	return c
}

// Probe executes an active TLS handshake against target and returns the diagnostic report.
func (c *Classifier) Probe(ctx context.Context, target string, serverName string) TLSReport {
	start := time.Now()
	report := TLSReport{
		Target:      target,
		ServerName:  serverName,
		Posture:     PostureVulnerable,
		PostureName: PostureVulnerable.String(),
		Success:     false,
	}

	dialer := &net.Dialer{
		Timeout: c.Timeout,
	}

	ctxTimeout, cancel := context.WithTimeout(ctx, c.Timeout)
	defer cancel()

	rawConn, err := dialer.DialContext(ctxTimeout, "tcp", target)
	if err != nil {
		report.Error = fmt.Sprintf("tcp dial failed: %v", err)
		report.HandshakeTime = time.Since(start)
		return report
	}
	defer rawConn.Close()

	tlsConfig := &tls.Config{
		ServerName:         serverName,
		InsecureSkipVerify: c.InsecureSkipVerify,
		NextProtos:         c.ALPNProtos,
		MinVersion:         tls.VersionTLS10,
		MaxVersion:         tls.VersionTLS13,
	}

	tlsConn := tls.Client(rawConn, tlsConfig)
	defer tlsConn.Close()

	if err := tlsConn.HandshakeContext(ctxTimeout); err != nil {
		report.Error = fmt.Sprintf("tls handshake failed: %v", err)
		report.HandshakeTime = time.Since(start)
		return report
	}

	state := tlsConn.ConnectionState()
	report.HandshakeTime = time.Since(start)
	report.Success = true
	report.ALPN = state.NegotiatedProtocol
	report.CipherSuite = tls.CipherSuiteName(state.CipherSuite)

	switch state.Version {
	case tls.VersionTLS13:
		report.TLSVersion = "TLS 1.3"
		if state.NegotiatedProtocol == "h2" || state.NegotiatedProtocol == "h3" {
			report.Posture = PostureHardened
		} else {
			report.Posture = PostureStandard
		}
	case tls.VersionTLS12:
		report.TLSVersion = "TLS 1.2"
		report.Posture = PostureStandard
	default:
		report.TLSVersion = fmt.Sprintf("0x%04x", state.Version)
		report.Posture = PostureVulnerable
	}

	report.PostureName = report.Posture.String()
	report.JA4Fingerprint = CalculateJA4S(state.Version, state.CipherSuite, state.NegotiatedProtocol)

	return report
}
