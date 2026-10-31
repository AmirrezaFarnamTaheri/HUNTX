package tlsdiag

import (
	"crypto/x509"
	"time"
)

// Option configures a Classifier instance using functional options.
type Option func(*Classifier)

// WithTimeout sets the handshake timeout for active TLS diagnostics.
func WithTimeout(d time.Duration) Option {
	return func(c *Classifier) {
		if d > 0 {
			c.Timeout = d
		}
	}
}

// WithInsecureSkipVerify controls whether certificate chains are verified.
func WithInsecureSkipVerify(skip bool) Option {
	return func(c *Classifier) {
		c.InsecureSkipVerify = skip
	}
}

// WithALPNProtocols sets the client ALPN negotiation preference list.
func WithALPNProtocols(protos []string) Option {
	return func(c *Classifier) {
		if len(protos) > 0 {
			c.ALPNProtos = protos
		}
	}
}

// WithRootCAs adds an explicit trust store for deterministic tests or private PKI.
// Nil uses the operating system's trusted roots.
func WithRootCAs(roots *x509.CertPool) Option {
	return func(c *Classifier) {
		c.RootCAs = roots
	}
}
