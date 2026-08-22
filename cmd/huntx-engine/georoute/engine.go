// Package georoute provides ISO-3166-1 alpha-2 geolocation classification and filtering
// for proxy URI configurations based on URL remarks and hostname top-level domains.
package georoute

import (
	"net/url"
	"regexp"
	"strings"
)

var (
	countryTagRegex = regexp.MustCompile(`(?:^|[^A-Z])([A-Z]{2})(?:$|[^A-Z])`)
	tldCountryMap   = map[string]string{
		"de": "DE", "fr": "FR", "uk": "GB", "us": "US", "jp": "JP",
		"nl": "NL", "sg": "SG", "ca": "CA", "au": "AU", "ir": "IR",
		"kr": "KR", "cn": "CN", "ru": "RU", "hk": "HK", "tw": "TW",
	}
	validCountries = map[string]bool{
		"US": true, "DE": true, "FR": true, "GB": true, "NL": true,
		"SG": true, "JP": true, "CA": true, "AU": true, "IR": true,
		"KR": true, "CN": true, "RU": true, "HK": true, "TW": true,
	}
)

// ProxyRecord represents a single proxy endpoint with classification metadata.
type ProxyRecord struct {
	UniqueHash  string `json:"unique_hash"`
	RawURI      string `json:"raw_uri"`
	Protocol    string `json:"protocol"`
	CountryCode string `json:"country_code"`
	RegionTier  int    `json:"region_tier"`
}

// Engine performs geolocation tag extraction and routing tier classification.
type Engine struct{}

// NewEngine creates a new geolocation routing engine.
func NewEngine() *Engine {
	return &Engine{}
}

func countryFromRemark(fragment string) string {
	remark, err := url.QueryUnescape(fragment)
	if err != nil {
		remark = fragment
	}
	upper := strings.ToUpper(remark)
	matches := countryTagRegex.FindAllStringSubmatch(upper, -1)
	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		code := match[1]
		if validCountries[code] {
			return code
		}
	}
	return "XX"
}

func countryFromHostname(hostname string) string {
	host := strings.TrimSuffix(strings.ToLower(strings.TrimSpace(hostname)), ".")
	if host == "" {
		return "XX"
	}
	labels := strings.Split(host, ".")
	if len(labels) < 2 {
		return "XX"
	}
	if code, ok := tldCountryMap[labels[len(labels)-1]]; ok {
		return code
	}
	return "XX"
}

// InferCountryCode extracts an ISO country code from the URI remark fragment or hostname TLD.
// Returns "XX" if no valid country code could be identified.
func (e *Engine) InferCountryCode(uri string) string {
	// Parse only the structured URI fragment and hostname. Searching the full
	// URI for strings such as ".de" lets passwords, query parameters and paths
	// spoof a country classification.
	parsed, err := url.Parse(strings.TrimSpace(uri))
	if err != nil {
		return "XX"
	}

	if code := countryFromRemark(parsed.Fragment); code != "XX" {
		return code
	}
	return countryFromHostname(parsed.Hostname())
}

// NormalizeProtocol standardizes protocol aliases to canonical names (e.g. ss -> shadowsocks).
func NormalizeProtocol(proto string) string {
	p := strings.ToLower(strings.TrimSpace(proto))
	switch p {
	case "ss", "shadowsocks":
		return "shadowsocks"
	case "hy2", "hysteria2":
		return "hysteria2"
	case "wg", "wireguard":
		return "wireguard"
	default:
		return p
	}
}

// Classify enriches a ProxyRecord with its inferred CountryCode, normalized Protocol, and RegionTier.
func (e *Engine) Classify(rec ProxyRecord) ProxyRecord {
	country := e.InferCountryCode(rec.RawURI)
	proto := NormalizeProtocol(rec.Protocol)

	tier := 2
	if country == "US" || country == "DE" || country == "NL" || country == "SG" || country == "JP" {
		tier = 1
	}

	rec.CountryCode = country
	rec.Protocol = proto
	rec.RegionTier = tier
	return rec
}

// FilterByRegion returns a new slice containing only records matching the target ISO country code.
func FilterByRegion(records []ProxyRecord, country string) []ProxyRecord {
	target := strings.ToUpper(strings.TrimSpace(country))
	var filtered []ProxyRecord
	for _, r := range records {
		if r.CountryCode == target {
			filtered = append(filtered, r)
		}
	}
	return filtered
}
