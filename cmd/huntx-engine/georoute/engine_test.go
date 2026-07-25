package georoute

import (
	"testing"
)

func TestInferCountryCode(t *testing.T) {
	e := NewEngine()
	if code := e.InferCountryCode("vless://u@host:443#US - Node"); code != "US" {
		t.Errorf("Expected US, got %s", code)
	}

	if code := e.InferCountryCode("vmess://u@server.de:443#DE_Server"); code != "DE" {
		t.Errorf("Expected DE, got %s", code)
	}

	if code := e.InferCountryCode("trojan://u@10.0.0.1:443#Node"); code != "XX" {
		t.Errorf("Expected XX, got %s", code)
	}
}

func TestClassifyAndFilter(t *testing.T) {
	e := NewEngine()
	r1 := e.Classify(ProxyRecord{RawURI: "vless://u@s.us:443#US", Protocol: "vless"})
	r2 := e.Classify(ProxyRecord{RawURI: "trojan://u@s.de:443#DE", Protocol: "trojan"})

	if r1.RegionTier != 1 {
		t.Errorf("Expected tier 1 for US, got %d", r1.RegionTier)
	}

	usOnly := FilterByRegion([]ProxyRecord{r1, r2}, "US")
	if len(usOnly) != 1 || usOnly[0].CountryCode != "US" {
		t.Errorf("Expected 1 US record, got %v", usOnly)
	}
}
