package geoip_test

import (
	"testing"

	"github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/internal/geoip"
)

func TestAnycastIPNeverInventsAPhysicalCountry(t *testing.T) {
	provider := geoip.NewGeoIPProvider(nil)
	for _, ip := range []string{"1.1.1.1", "8.8.8.8", "9.9.9.9", "208.67.222.222"} {
		record, err := provider.LookupIP(ip)
		if err != nil {
			t.Fatal(err)
		}
		if record.CountryCode != "XX" {
			t.Fatalf("%s: expected unknown anycast country, got %s", ip, record.CountryCode)
		}
		if !record.IsAnycast {
			t.Fatalf("%s: expected anycast provenance", ip)
		}
		if record.AttributionSource != "static_prefix_hint" {
			t.Fatalf("%s: expected explicit static evidence, got %q", ip, record.AttributionSource)
		}
	}
}

func TestNonPublicReservedIPIsNotMisrepresentedAsPublic(t *testing.T) {
	provider := geoip.NewGeoIPProvider(nil)
	for _, ip := range []string{
		"100.64.0.1", "192.0.2.1", "198.51.100.5",
		"203.0.113.5", "198.18.0.1", "2001:db8::1",
	} {
		record, err := provider.LookupIP(ip)
		if err != nil {
			t.Fatal(err)
		}
		if !record.IsPrivate || record.ASN != 0 {
			t.Errorf("%s: non-public address classified as externally attributed: %+v", ip, record)
		}
	}
}

func TestGeoIPHostnameHeuristicUsesOnlyActualCountryTLD(t *testing.T) {
	provider := geoip.NewGeoIPProvider(nil)
	for _, host := range []string{
		"de.example.com", "ams.nl.proxy", "london.uk.co", "example.com.de.evil",
	} {
		if country := provider.InferCountryFromDomain(host); country != "XX" {
			t.Errorf("%q: unexpected location hint %q", host, country)
		}
	}
}
