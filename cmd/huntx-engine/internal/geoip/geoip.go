// Package geoip implements high-performance IP geolocation, ASN lookup, and reverse geographic inference.
// Source: https://www.iana.org/assignments/ipv4-address-space/ipv4-address-space.xhtml (IANA IPv4 address assignments)
// Source: https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2 (ISO 3166-1 alpha-2 country codes)
package geoip

import (
	"errors"
	"net"
	"strings"
	"sync"
)

// GeoIPRecord holds geographic and autonomous system intelligence for an IP address.
type GeoIPRecord struct {
	IP          string  `json:"ip"`
	CountryCode string  `json:"country_code"`
	CountryName string  `json:"country_name"`
	City        string  `json:"city"`
	ASN         uint32  `json:"asn"`
	ASOrg       string  `json:"as_org"`
	IsPrivate   bool    `json:"is_private"`
	Latitude    float64 `json:"latitude,omitempty"`
	Longitude   float64 `json:"longitude,omitempty"`
}

// Config allows customizing the GeoIPProvider behavior.
type Config struct {
	MMDBPath string
}

// GeoIPProvider queries IP geolocation and ASN data.
type GeoIPProvider struct {
	config  Config
	cache   sync.Map // map[string]GeoIPRecord
	subnets []subnetEntry
}

type subnetEntry struct {
	cidr   *net.IPNet
	record GeoIPRecord
}

var defaultTLDMap = map[string]string{
	".de": "DE", ".fr": "FR", ".uk": "GB", ".co.uk": "GB", ".uk.co": "GB",
	".us": "US", ".jp": "JP", ".nl": "NL", ".sg": "SG", ".ca": "CA",
	".au": "AU", ".ir": "IR", ".kr": "KR", ".cn": "CN", ".ru": "RU",
	".hk": "HK", ".tw": "TW", ".se": "SE", ".fi": "FI", ".ch": "CH",
	".it": "IT", ".es": "ES", ".tr": "TR", ".in": "IN", ".br": "BR",
}

// NewGeoIPProvider creates a new GeoIPProvider initialized with static intelligence tables.
func NewGeoIPProvider(cfg *Config) *GeoIPProvider {
	p := &GeoIPProvider{}
	if cfg != nil {
		p.config = *cfg
	}

	p.initStaticSubnets()
	return p
}

func (p *GeoIPProvider) initStaticSubnets() {
	staticRules := []struct {
		cidrStr string
		record  GeoIPRecord
	}{
		// Cloudflare
		{"1.1.1.0/24", GeoIPRecord{CountryCode: "US", CountryName: "United States", ASN: 13335, ASOrg: "Cloudflare, Inc."}},
		{"1.0.0.0/24", GeoIPRecord{CountryCode: "US", CountryName: "United States", ASN: 13335, ASOrg: "Cloudflare, Inc."}},
		{"104.16.0.0/12", GeoIPRecord{CountryCode: "US", CountryName: "United States", ASN: 13335, ASOrg: "Cloudflare, Inc."}},
		// Google
		{"8.8.8.0/24", GeoIPRecord{CountryCode: "US", CountryName: "United States", ASN: 15169, ASOrg: "Google LLC"}},
		{"8.8.4.0/24", GeoIPRecord{CountryCode: "US", CountryName: "United States", ASN: 15169, ASOrg: "Google LLC"}},
		// Quad9
		{"9.9.9.0/24", GeoIPRecord{CountryCode: "CH", CountryName: "Switzerland", ASN: 19281, ASOrg: "Quad9"}},
		// OpenDNS
		{"208.67.222.0/24", GeoIPRecord{CountryCode: "US", CountryName: "United States", ASN: 36692, ASOrg: "Cisco OpenDNS"}},
		{"208.67.220.0/24", GeoIPRecord{CountryCode: "US", CountryName: "United States", ASN: 36692, ASOrg: "Cisco OpenDNS"}},
	}

	for _, rule := range staticRules {
		_, ipnet, err := net.ParseCIDR(rule.cidrStr)
		if err == nil {
			p.subnets = append(p.subnets, subnetEntry{
				cidr:   ipnet,
				record: rule.record,
			})
		}
	}
}

// LookupIP resolves an IP address into geographic and ASN intelligence.
func (p *GeoIPProvider) LookupIP(ipStr string) (GeoIPRecord, error) {
	ipStr = strings.TrimSpace(ipStr)
	parsedIP := net.ParseIP(ipStr)
	if parsedIP == nil {
		return GeoIPRecord{}, errors.New("geoip: invalid ip address")
	}

	// 1. Check in-memory cache
	if v, ok := p.cache.Load(ipStr); ok {
		return v.(GeoIPRecord), nil
	}

	// 2. Check RFC1918 / Private / Loopback
	if parsedIP.IsLoopback() || parsedIP.IsPrivate() || parsedIP.IsUnspecified() || parsedIP.IsLinkLocalUnicast() {
		rec := GeoIPRecord{
			IP:          ipStr,
			CountryCode: "LAN",
			CountryName: "Local Network",
			City:        "Private Subnet",
			ASN:         0,
			ASOrg:       "Private Network",
			IsPrivate:   true,
		}
		p.cache.Store(ipStr, rec)
		return rec, nil
	}

	// 3. Static Subnet Match
	for _, entry := range p.subnets {
		if entry.cidr.Contains(parsedIP) {
			rec := entry.record
			rec.IP = ipStr
			p.cache.Store(ipStr, rec)
			return rec, nil
		}
	}

	// 4. Default Unknown
	rec := GeoIPRecord{
		IP:          ipStr,
		CountryCode: "XX",
		CountryName: "Unknown",
		ASN:         0,
		ASOrg:       "Unknown Provider",
		IsPrivate:   false,
	}
	p.cache.Store(ipStr, rec)
	return rec, nil
}

// InferCountryFromDomain deduces a 2-letter ISO country code from domain TLDs or regional host prefixes.
func (p *GeoIPProvider) InferCountryFromDomain(domain string) string {
	domain = strings.ToLower(strings.TrimSpace(domain))
	if domain == "" {
		return "XX"
	}

	// Check TLD suffixes
	for tld, code := range defaultTLDMap {
		if strings.HasSuffix(domain, tld) {
			return code
		}
	}

	// Check domain segments (e.g. "ams.nl.proxy")
	parts := strings.Split(domain, ".")
	for _, part := range parts {
		if code, exists := defaultTLDMap["."+part]; exists {
			return code
		}
	}

	return "XX"
}
