// Package kernel provides eBPF/XDP acceleration and kernel-level network models.
//
// Authority:
//   Linux eBPF / XDP Architecture Specification: https://docs.ebpf.io/
package kernel

import (
	"encoding/binary"
	"net"
	"sync"
)

// XDPAction represents the verdict returned by an XDP program.
type XDPAction uint32

const (
	// XDPAborted indicates the program errored and dropped the packet.
	XDPAborted XDPAction = 0
	// XDPDrop indicates the packet is dropped immediately in the driver NIC.
	XDPDrop XDPAction = 1
	// XDPPass passes the packet up to the normal kernel network stack.
	XDPPass XDPAction = 2
	// XDPTx transmits the packet out of the same interface.
	XDPTx XDPAction = 3
)

// XDPPacketFilter simulates zero-copy XDP fast packet filtering and BPF maps.
type XDPPacketFilter struct {
	mu           sync.RWMutex
	blacklisted  map[[4]byte]struct{}
	allowedPorts map[uint16]struct{}
}

// NewXDPPacketFilter initializes a fast kernel filter.
func NewXDPPacketFilter() *XDPPacketFilter {
	return &XDPPacketFilter{
		blacklisted:  make(map[[4]byte]struct{}),
		allowedPorts: make(map[uint16]struct{}),
	}
}

// BlacklistIP adds an IPv4 address to the hardware drop table.
func (f *XDPPacketFilter) BlacklistIP(ip net.IP) {
	ipv4 := ip.To4()
	if ipv4 == nil {
		return
	}
	var k [4]byte
	copy(k[:], ipv4)

	f.mu.Lock()
	f.blacklisted[k] = struct{}{}
	f.mu.Unlock()
}

// ProcessPacket inspects raw packet bytes and returns the XDP fast-path action.
func (f *XDPPacketFilter) ProcessPacket(data []byte) XDPAction {
	if len(data) < 20 {
		return XDPDrop
	}

	// Verify IPv4 (version == 4)
	version := data[0] >> 4
	if version != 4 {
		return XDPPass
	}

	// Extract source IP (bytes 12-15)
	var srcIP [4]byte
	copy(srcIP[:], data[12:16])

	f.mu.RLock()
	_, blocked := f.blacklisted[srcIP]
	f.mu.RUnlock()

	if blocked {
		return XDPDrop
	}

	// Inspect Layer 4 ports if TCP (6) or UDP (17)
	proto := data[9]
	ihl := int(data[0]&0x0F) * 4
	if len(data) >= ihl+4 && (proto == 6 || proto == 17) {
		dstPort := binary.BigEndian.Uint16(data[ihl+2 : ihl+4])
		f.mu.RLock()
		if len(f.allowedPorts) > 0 {
			if _, ok := f.allowedPorts[dstPort]; !ok {
				f.mu.RUnlock()
				return XDPDrop
			}
		}
		f.mu.RUnlock()
	}

	return XDPPass
}
