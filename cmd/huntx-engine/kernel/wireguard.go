// Package kernel provides WireGuard Noise IK protocol frame parsing and kernel models.
//
// Authority:
//
//	WireGuard Protocol Specification: https://www.wireguard.com/papers/wireguard.pdf
//	RFC 7539 (ChaCha20-Poly1305): https://datatracker.ietf.org/doc/html/rfc7539
package kernel

import (
	"encoding/binary"
	"errors"
	"fmt"
)

// WireGuard Message Types
const (
	TypeHandshakeInitiation uint8 = 1
	TypeHandshakeResponse   uint8 = 2
	TypeCookieReply         uint8 = 3
	TypeTransportData       uint8 = 4
)

var (
	// ErrTruncatedPacket indicates the buffer is too small for a valid WireGuard frame.
	ErrTruncatedPacket = errors.New("wireguard packet truncated")
	// ErrUnknownMessageType indicates an invalid message header.
	ErrUnknownMessageType = errors.New("unknown wireguard message type")
)

// WireGuardHeader represents parsed fields from a WireGuard protocol packet.
type WireGuardHeader struct {
	Type          uint8
	SenderIndex   uint32
	ReceiverIndex uint32
	Counter       uint64
	EphemeralKey  [32]byte
}

// ParseWireGuardHeader performs zero-allocation parsing of a raw WireGuard packet header.
func ParseWireGuardHeader(buf []byte) (WireGuardHeader, error) {
	if len(buf) < 4 {
		return WireGuardHeader{}, ErrTruncatedPacket
	}

	msgType := buf[0]
	hdr := WireGuardHeader{Type: msgType}

	switch msgType {
	case TypeHandshakeInitiation:
		if len(buf) < 148 {
			return WireGuardHeader{}, fmt.Errorf("%w: initiation requires 148 bytes, got %d", ErrTruncatedPacket, len(buf))
		}
		hdr.SenderIndex = binary.LittleEndian.Uint32(buf[4:8])
		copy(hdr.EphemeralKey[:], buf[8:40])
		return hdr, nil

	case TypeHandshakeResponse:
		if len(buf) < 92 {
			return WireGuardHeader{}, fmt.Errorf("%w: response requires 92 bytes, got %d", ErrTruncatedPacket, len(buf))
		}
		hdr.SenderIndex = binary.LittleEndian.Uint32(buf[4:8])
		hdr.ReceiverIndex = binary.LittleEndian.Uint32(buf[8:12])
		copy(hdr.EphemeralKey[:], buf[12:44])
		return hdr, nil

	case TypeCookieReply:
		if len(buf) < 64 {
			return WireGuardHeader{}, fmt.Errorf("%w: cookie reply requires 64 bytes, got %d", ErrTruncatedPacket, len(buf))
		}
		hdr.ReceiverIndex = binary.LittleEndian.Uint32(buf[4:8])
		return hdr, nil

	case TypeTransportData:
		if len(buf) < 32 {
			return WireGuardHeader{}, fmt.Errorf("%w: transport packet requires >=32 bytes, got %d", ErrTruncatedPacket, len(buf))
		}
		hdr.ReceiverIndex = binary.LittleEndian.Uint32(buf[4:8])
		hdr.Counter = binary.LittleEndian.Uint64(buf[8:16])
		return hdr, nil

	default:
		return WireGuardHeader{}, fmt.Errorf("%w: type %d", ErrUnknownMessageType, msgType)
	}
}
