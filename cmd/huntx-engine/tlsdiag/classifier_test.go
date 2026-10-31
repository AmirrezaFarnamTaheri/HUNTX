package tlsdiag

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"math/big"
	"net"
	"testing"
	"time"
)

func generateSelfSignedCert(t *testing.T) tls.Certificate {
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("failed to generate private key: %v", err)
	}

	template := x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject: pkix.Name{
			Organization: []string{"HUNTX Test Org"},
			CommonName:   "127.0.0.1",
		},
		IPAddresses: []net.IP{net.ParseIP("127.0.0.1")},
		DNSNames:    []string{"localhost", "node.test"},
		NotBefore:   time.Now().Add(-time.Hour),
		NotAfter:    time.Now().Add(24 * time.Hour),
		KeyUsage:    x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}

	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &priv.PublicKey, priv)
	if err != nil {
		t.Fatalf("failed to create certificate: %v", err)
	}

	return tls.Certificate{
		Certificate: [][]byte{certDER},
		PrivateKey:  priv,
	}
}

func startMockTLSServer(t *testing.T, cert tls.Certificate, alpn []string) (string, func()) {
	config := &tls.Config{
		Certificates: []tls.Certificate{cert},
		NextProtos:   alpn,
		MinVersion:   tls.VersionTLS12,
		MaxVersion:   tls.VersionTLS13,
	}

	ln, err := tls.Listen("tcp", "127.0.0.1:0", config)
	if err != nil {
		t.Fatalf("failed to start TLS listener: %v", err)
	}

	stopChan := make(chan struct{})
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				select {
				case <-stopChan:
					return
				default:
					return
				}
			}
			go func(c net.Conn) {
				defer c.Close()
				tlsConn, ok := c.(*tls.Conn)
				if ok {
					_ = tlsConn.Handshake()
				}
			}(conn)
		}
	}()

	cleanup := func() {
		close(stopChan)
		_ = ln.Close()
	}

	return ln.Addr().String(), cleanup
}

func TestJA4SCalculation(t *testing.T) {
	fp := CalculateJA4S(0x0304, 0x1301, "h2")
	if fp == "" {
		t.Fatalf("expected non-empty JA4S fingerprint")
	}
	if fp[:4] != "t13s" {
		t.Errorf("expected TLS 1.3 JA4S prefix 't13s', got %s", fp[:4])
	}
}

func TestTLSClassifierProbesLocalTLSServer(t *testing.T) {
	cert := generateSelfSignedCert(t)
	addr, cleanup := startMockTLSServer(t, cert, []string{"h2", "http/1.1"})
	defer cleanup()

	classifier := NewClassifier(WithTimeout(2*time.Second), WithInsecureSkipVerify(true))
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	report := classifier.Probe(ctx, addr, "localhost")
	if !report.Success {
		t.Fatalf("expected TLS probe success, got error: %s", report.Error)
	}

	if report.TLSVersion != "TLS 1.3" && report.TLSVersion != "TLS 1.2" {
		t.Errorf("unexpected TLS version: %s", report.TLSVersion)
	}

	if report.ALPN != "h2" {
		t.Errorf("expected negotiated ALPN 'h2', got %q", report.ALPN)
	}

	if report.Posture != PostureUnknown || report.CertificateVerified {
		t.Errorf("untrusted diagnostic handshake must not count as verified secure TLS: %+v", report)
	}
}

func TestTLSClassifierHandlesConnectionRefused(t *testing.T) {
	classifier := NewClassifier(WithTimeout(200 * time.Millisecond))
	ctx := context.Background()

	// Port 59999 is typically unbound
	report := classifier.Probe(ctx, "127.0.0.1:59999", "localhost")
	if report.Success {
		t.Fatalf("expected failure on unbound port, got success")
	}
	if report.Posture != PostureUnknown {
		t.Errorf("failed connection has unknown posture, not a TLS vulnerability: %v", report.Posture)
	}
}

func TestTLSClassifierRejectsUntrustedCertificateByDefault(t *testing.T) {
	cert := generateSelfSignedCert(t)
	addr, cleanup := startMockTLSServer(t, cert, []string{"h2"})
	defer cleanup()

	report := NewClassifier(WithTimeout(2*time.Second)).Probe(context.Background(), addr, "localhost")
	if report.Success || report.CertificateVerified {
		t.Errorf("untrusted self-signed endpoint must not be reported as valid: %+v", report)
	}
	if report.Posture != PostureUnknown {
		t.Errorf("failed verification does not establish vulnerable TLS: %+v", report)
	}
}

func TestTLSClassifierAcceptsExplicitlyTrustedCertificate(t *testing.T) {
	cert := generateSelfSignedCert(t)
	addr, cleanup := startMockTLSServer(t, cert, []string{"h2"})
	defer cleanup()
	leaf, err := x509.ParseCertificate(cert.Certificate[0])
	if err != nil {
		t.Fatal(err)
	}
	roots := x509.NewCertPool()
	roots.AddCert(leaf)
	classifier := NewClassifier(WithTimeout(2*time.Second), WithRootCAs(roots))
	report := classifier.Probe(context.Background(), addr, "localhost")
	if !report.Success || !report.CertificateVerified {
		t.Errorf("trusted certificate must be explicitly verified: %+v", report)
	}
	if report.Posture != PostureHardened && report.Posture != PostureStandard {
		t.Errorf("verified modern TLS must have a supported posture: %+v", report)
	}
}

func Example_probeTLS() {
	classifier := NewClassifier(
		WithTimeout(time.Second),
		WithInsecureSkipVerify(true),
	)
	_ = classifier
}
