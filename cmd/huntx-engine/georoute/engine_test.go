package georoute

import "testing"

func TestInferCountryCode(t *testing.T) {
	e := NewEngine()
	if code := e.InferCountryCode("vless://u@host:443#US - Node"); code != "US" {
		t.Errorf("Expected US, got %s", code)
	}

	if code := e.InferCountryCode("trojan://u@server.de:443#Node"); code != "DE" {
		t.Errorf("Expected DE from hostname TLD, got %s", code)
	}

	if code := e.InferCountryCode("trojan://u@10.0.0.1:443#Node"); code != "XX" {
		t.Errorf("Expected XX, got %s", code)
	}
}

func TestCountryInferenceCannotBeSpoofedByPasswordPathOrQuery(t *testing.T) {
	e := NewEngine()
	fixtures := []string{
		"trojan://secret.de@server.example:443#Node",
		"vless://user@server.example:443/path.de#Node",
		"vless://user@server.example:443?peer=cdn.de#Node",
	}
	for _, uri := range fixtures {
		if code := e.InferCountryCode(uri); code != "XX" {
			t.Fatalf("URI %q should not infer a country from non-host fields; got %s", uri, code)
		}
	}
}

func TestPercentEncodedRemarkCountry(t *testing.T) {
	e := NewEngine()
	if code := e.InferCountryCode("vless://u@server.example:443#Fast%20DE%20Node"); code != "DE" {
		t.Fatalf("expected DE from decoded remark, got %s", code)
	}
}

func TestHostnameUsesFinalLabelOnly(t *testing.T) {
	e := NewEngine()
	if code := e.InferCountryCode("vless://u@de.example.com:443#Node"); code != "XX" {
		t.Fatalf("subdomain text must not masquerade as a country TLD; got %s", code)
	}
	if code := e.InferCountryCode("vless://u@edge.example.jp:443#Node"); code != "JP" {
		t.Fatalf("expected JP from final hostname label, got %s", code)
	}
}

func TestClassifyAndFilter(t *testing.T) {
	e := NewEngine()
	r1 := e.Classify(ProxyRecord{RawURI: "vless://u@s.us:443#US", Protocol: "vless"})
	r2 := e.Classify(ProxyRecord{RawURI: "trojan://u@s.de:443#DE", Protocol: "trojan"})

	if r1.RegionTier != 1 {
		t.Errorf("Expected tier 1 for US, got %d", r1.RegionTier)
	}

	usOnly := FilterByRegion([]ProxyRecord{r1, r2}, " us ")
	if len(usOnly) != 1 || usOnly[0].CountryCode != "US" {
		t.Errorf("Expected 1 US record, got %v", usOnly)
	}
}

func ExampleEngine_Classify() {
	engine := NewEngine()
	record := engine.Classify(ProxyRecord{
		RawURI:   "vless://uuid@node.example.de:443#DE-Fast",
		Protocol: "VLESS",
	})
	_ = record.CountryCode // "DE"
}
