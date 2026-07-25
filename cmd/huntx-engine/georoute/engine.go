package georoute

import (
	"regexp"
	"strings"
	"sync"
)

var (
	countryTagRegex = regexp.MustCompile(`\b([A-Z]{2})\b`)
	tldCountryMap   = map[string]string{
		".de": "DE", ".fr": "FR", ".uk": "GB", ".us": "US", ".jp": "JP",
		".nl": "NL", ".sg": "SG", ".ca": "CA", ".au": "AU", ".ir": "IR",
		".kr": "KR", ".cn": "CN", ".ru": "RU", ".hk": "HK", ".tw": "TW",
	}
	validCountries = map[string]bool{
		"US": true, "DE": true, "FR": true, "GB": true, "NL": true,
		"SG": true, "JP": true, "CA": true, "AU": true, "IR": true,
		"KR": true, "CN": true, "RU": true, "HK": true, "TW": true,
	}
)

type ProxyRecord struct {
	UniqueHash  string `json:"unique_hash"`
	RawURI      string `json:"raw_uri"`
	Protocol    string `json:"protocol"`
	CountryCode string `json:"country_code"`
	RegionTier  int    `json:"region_tier"`
}

type Engine struct {
	mu    sync.RWMutex
	cache map[string]string
}

func NewEngine() *Engine {
	return &Engine{
		cache: make(map[string]string),
	}
}

func (e *Engine) InferCountryCode(uri string) string {
	e.mu.RLock()
	if code, found := e.cache[uri]; found {
		e.mu.RUnlock()
		return code
	}
	e.mu.RUnlock()

	code := "XX"

	// 1. Check hashtag remark
	if idx := strings.Index(uri, "#"); idx != -1 {
		remark := uri[idx+1:]
		matches := countryTagRegex.FindAllString(remark, -1)
		for _, m := range matches {
			if validCountries[m] {
				code = m
				break
			}
		}
	}

	// 2. Check TLD from hostname if not found
	if code == "XX" {
		lower := strings.ToLower(uri)
		for tld, c := range tldCountryMap {
			if strings.Contains(lower, tld) {
				code = c
				break
			}
		}
	}

	e.mu.Lock()
	e.cache[uri] = code
	e.mu.Unlock()

	return code
}

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

func FilterByRegion(records []ProxyRecord, country string) []ProxyRecord {
	target := strings.ToUpper(country)
	var filtered []ProxyRecord
	for _, r := range records {
		if r.CountryCode == target {
			filtered = append(filtered, r)
		}
	}
	return filtered
}
