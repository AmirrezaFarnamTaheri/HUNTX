package kernel

import (
	"testing"
)

func TestWireGuardParseHandshakeInitiation(t *testing.T) {
	// Build mock 148-byte WireGuard Initiation packet
	raw := make([]byte, 148)
	raw[0] = 1 // TypeHandshakeInitiation
	raw[1] = 0 // Reserved 1
	raw[2] = 0 // Reserved 2
	raw[3] = 0 // Reserved 3

	// Sender index = 0x12345678 (little endian in WireGuard protocol)
	raw[4] = 0x78
	raw[5] = 0x56
	raw[6] = 0x34
	raw[7] = 0x12

	// Ephemeral public key (32 bytes)
	for i := 0; i < 32; i++ {
		raw[8+i] = byte(i + 1)
	}

	hdr, err := ParseWireGuardHeader(raw)
	if err != nil {
		t.Fatalf("unexpected error parsing WireGuard header: %v", err)
	}

	if hdr.Type != TypeHandshakeInitiation {
		t.Errorf("expected TypeHandshakeInitiation (1), got %d", hdr.Type)
	}
	if hdr.SenderIndex != 0x12345678 {
		t.Errorf("expected sender index 0x12345678, got 0x%X", hdr.SenderIndex)
	}
	if hdr.EphemeralKey[0] != 1 || hdr.EphemeralKey[31] != 32 {
		t.Errorf("ephemeral key mismatch")
	}
}

func TestWireGuardParseTransportData(t *testing.T) {
	raw := make([]byte, 48)
	raw[0] = 4 // TypeTransportData
	// Receiver index = 0xAABBCCDD
	raw[4] = 0xDD
	raw[5] = 0xCC
	raw[6] = 0xBB
	raw[7] = 0xAA
	// Counter = 100
	raw[8] = 100

	hdr, err := ParseWireGuardHeader(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if hdr.Type != TypeTransportData {
		t.Errorf("expected TypeTransportData, got %d", hdr.Type)
	}
	if hdr.ReceiverIndex != 0xAABBCCDD {
		t.Errorf("expected receiver index 0xAABBCCDD, got 0x%X", hdr.ReceiverIndex)
	}
	if hdr.Counter != 100 {
		t.Errorf("expected counter 100, got %d", hdr.Counter)
	}
}

func TestWireGuardParseInvalidLength(t *testing.T) {
	raw := []byte{1, 0, 0} // Too short
	_, err := ParseWireGuardHeader(raw)
	if err == nil {
		t.Errorf("expected error on truncated packet, got nil")
	}
}

func BenchmarkWireGuardParseHeader(b *testing.B) {
	raw := make([]byte, 148)
	raw[0] = 1
	raw[4] = 0x78
	raw[5] = 0x56
	raw[6] = 0x34
	raw[7] = 0x12

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = ParseWireGuardHeader(raw)
	}
}
