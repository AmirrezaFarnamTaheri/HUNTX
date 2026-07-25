package georoute

import (
	"regexp"
	"strings"
	"sync"
)

const maxCacheEntries = 4096

var (
	countryTagRegex = regexp.MustCompile(`(?:^|[^A-Za-z0-9])([A-Z]{2})(?:$|[^A-Za-z0-9])`)
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
	return &Engine{cache: make(map[string]string)}
}

func (e *Engine) InferCountryCode(uri string) string {
	e.mu.RLock()
	if code, found := e.cache[uri]; found {
		e.mu.RUnlock()
		return code
	}
	e.mu.RUnlock()

	code := "XX"
	if idx := strings.Index(uri, "#"); idx != -1 {
		remark := uri[idx+1:]
		matches := countryTagRegex.FindAllStringSubmatch(remark, -1)
		for _, match := range matches {
			if len(match) > 1 && validCountries[match[1]] {
				code = match[1]
				break
			}
		}
	}

	if code == "XX" {
		lower := strings.ToLower(uri)
		for tld, country := range tldCountryMap {
			if strings.Contains(lower, tld) {
				code = country
				break
			}
		}
	}

	e.mu.Lock()
	if len(e.cache) >= maxCacheEntries {
		clear(e.cache)
	}
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
	for _, record := range records {
		if record.CountryCode == target {
			filtered = append(filtered, record)
		}
	}
	return filtered
}
