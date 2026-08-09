from huntx.core.geo_routing import GeoRoutingEngine


def test_geo_routing_infer_country():
    engine = GeoRoutingEngine()
    assert engine.infer_country_code("vless://user@1.1.1.1:443#US - Server 1") == "US"
    assert engine.infer_country_code("vmess://user@server.de:443#DE_Node") == "DE"
    assert engine.infer_country_code("trojan://user@server.jp:443#Node") == "JP"
    assert engine.infer_country_code("vless://user@10.0.0.1:443#Unknown") == "XX"


def test_geo_routing_classify():
    engine = GeoRoutingEngine()
    record = {
        "raw_uri": "hysteria2://user@server.us:443#US High Speed",
        "protocol": "hy2"
    }
    classified = engine.classify_proxy(record)
    assert classified["country_code"] == "US"
    assert classified["protocol"] == "hysteria2"
    assert classified["taxonomy"]["is_fast"] is True
    assert classified["taxonomy"]["region_tier"] == 1


def test_geo_routing_filters():
    engine = GeoRoutingEngine()
    p1 = engine.classify_proxy({"raw_uri": "vless://u@s.us:443#US", "protocol": "vless"})
    p2 = engine.classify_proxy({"raw_uri": "trojan://u@s.de:443#DE", "protocol": "trojan"})
    p3 = engine.classify_proxy({"raw_uri": "ss://u@s.nl:443#NL", "protocol": "ss"})

    us_proxies = engine.route_by_region([p1, p2, p3], "US")
    assert len(us_proxies) == 1
    assert us_proxies[0]["protocol"] == "vless"

    ss_proxies = engine.route_by_protocol([p1, p2, p3], "shadowsocks")
    assert len(ss_proxies) == 1
    assert ss_proxies[0]["country_code"] == "NL"
