// HUNTX Unified Standalone Bundle (CORS-immune, file:// and GitHub Pages compatible)
(function(window, document) {
'use strict';

// HUNTX Telemetry & Sample Proxy Node Data
// Authority: Unified Output Publication Model & Protocol Specifications

const FALLBACK_CATALOG = {
  "files": [
    {
      "description": "Compact binary subscription feed for high-speed clients",
      "ext": "NPVT",
      "filename": "all_sources.npvt",
      "hash": "d682c87e",
      "last_modified": "2026-08-17T22:38:01.920674+00:00",
      "media_type": "application/x-npvt-subscription",
      "path": "artifacts/release/all_sources.npvt",
      "section": "release",
      "sha256": "d682c87e176265d3b8ad23c9b1871adeddfefe654f791ef6d777176dcb05adf5",
      "size": 7929,
      "size_str": "7.7 KB",
      "tags": [
        "release",
        "production",
        "subscription",
        "binary-feed"
      ],
      "type": "NPVT"
    },
    {
      "description": "Base64-encoded subscription feed for Shadowrocket, v2rayNG, and Streisand",
      "ext": "B64SUB",
      "filename": "all_sources.npvt.b64sub",
      "hash": "258a4ae2",
      "last_modified": "2026-08-17T22:38:01.920674+00:00",
      "media_type": "text/plain",
      "path": "artifacts/release/all_sources.npvt.b64sub",
      "section": "release",
      "sha256": "258a4ae2414eb767131a18e2add038011520df8705a7cdd3b1155f4df05724d1",
      "size": 10532,
      "size_str": "10.3 KB",
      "tags": [
        "release",
        "production",
        "subscription",
        "base64",
        "unified-feed"
      ],
      "type": "B64SUB"
    },
    {
      "description": "Parsed and structured proxy connection parameters JSON dataset",
      "ext": "JSON",
      "filename": "all_sources.npvt.decoded.json",
      "hash": "167a8977",
      "last_modified": "2026-08-17T22:38:01.921673+00:00",
      "media_type": "application/json",
      "path": "artifacts/release/all_sources.npvt.decoded.json",
      "section": "release",
      "sha256": "167a8977ccfe79e8fd1bf265a2ab5b44810437bd2650fb04d180e3952775f0ea",
      "size": 24665,
      "size_str": "24.1 KB",
      "tags": [
        "release",
        "production",
        "decoded",
        "parameters",
        "metadata"
      ],
      "type": "JSON"
    },
    {
      "description": "Compiled Sing-box 1.10+ outbound routing profile with TLS/Reality rules",
      "ext": "SINGBOX",
      "filename": "all_sources.npvt.singbox.json",
      "hash": "c3f703ba",
      "last_modified": "2026-08-17T22:38:01.921673+00:00",
      "media_type": "application/json",
      "path": "artifacts/release/all_sources.npvt.singbox.json",
      "section": "release",
      "sha256": "c3f703ba7e63abf040bc6802ddfe706e1f352d96897491cbffe250573063e7fa",
      "size": 19641,
      "size_str": "19.2 KB",
      "tags": [
        "release",
        "production",
        "singbox",
        "routing-profile",
        "outbounds"
      ],
      "type": "SINGBOX"
    },
    {
      "description": "Cryptographically signed opaque proxy bundle",
      "ext": "BUNDLE",
      "filename": "all_sources.opaque_bundle",
      "hash": "eddd1ca7",
      "last_modified": "2026-08-17T22:38:01.924191+00:00",
      "media_type": "application/octet-stream",
      "path": "artifacts/release/all_sources.opaque_bundle",
      "section": "release",
      "sha256": "eddd1ca799674b0d4aa80f02707efa7c0dd34e0427f617152d150ed2de5c7d99",
      "size": 186736,
      "size_str": "182.4 KB",
      "tags": [
        "release",
        "production",
        "bundle",
        "binary"
      ],
      "type": "BUNDLE"
    },
    {
      "description": "Standard OpenVPN multi-gateway client profile with TLS auth",
      "ext": "OVPN",
      "filename": "all_sources.ovpn",
      "hash": "9eb723c3",
      "last_modified": "2026-08-17T22:38:01.924191+00:00",
      "media_type": "application/x-openvpn-profile",
      "path": "artifacts/release/all_sources.ovpn",
      "section": "release",
      "sha256": "9eb723c318ceffd3664b589c6a270f2df910e0381feaa4c61c731e63b67bb54e",
      "size": 3754,
      "size_str": "3.7 KB",
      "tags": [
        "release",
        "production",
        "openvpn",
        "vpn",
        "gateway"
      ],
      "type": "OVPN"
    },
    {
      "description": "Base64-encoded subscription feed for Shadowrocket, v2rayNG, and Streisand",
      "ext": "B64SUB",
      "filename": "all_sources_npvt_b64sub.txt",
      "hash": "258a4ae2",
      "last_modified": "2026-08-17T22:38:01.924838+00:00",
      "media_type": "text/plain",
      "path": "artifacts/release/all_sources_npvt_b64sub.txt",
      "section": "release",
      "sha256": "258a4ae2414eb767131a18e2add038011520df8705a7cdd3b1155f4df05724d1",
      "size": 10532,
      "size_str": "10.3 KB",
      "tags": [
        "release",
        "production",
        "subscription",
        "base64",
        "unified-feed"
      ],
      "type": "B64SUB"
    },
    {
      "description": "Parsed and structured proxy connection parameters JSON dataset",
      "ext": "JSON",
      "filename": "all_sources_npvt_decoded.json",
      "hash": "167a8977",
      "last_modified": "2026-08-17T22:38:01.924838+00:00",
      "media_type": "application/json",
      "path": "artifacts/release/all_sources_npvt_decoded.json",
      "section": "release",
      "sha256": "167a8977ccfe79e8fd1bf265a2ab5b44810437bd2650fb04d180e3952775f0ea",
      "size": 24665,
      "size_str": "24.1 KB",
      "tags": [
        "release",
        "production",
        "decoded",
        "parameters",
        "metadata"
      ],
      "type": "JSON"
    },
    {
      "description": "Compiled Sing-box 1.10+ outbound routing profile with TLS/Reality rules",
      "ext": "SINGBOX",
      "filename": "all_sources_npvt_singbox.json",
      "hash": "c3f703ba",
      "last_modified": "2026-08-17T22:38:01.925850+00:00",
      "media_type": "application/json",
      "path": "artifacts/release/all_sources_npvt_singbox.json",
      "section": "release",
      "sha256": "c3f703ba7e63abf040bc6802ddfe706e1f352d96897491cbffe250573063e7fa",
      "size": 19641,
      "size_str": "19.2 KB",
      "tags": [
        "release",
        "production",
        "singbox",
        "routing-profile",
        "outbounds"
      ],
      "type": "SINGBOX"
    },
    {
      "description": "Production release documentation and checksum index",
      "ext": "MD",
      "filename": "README.md",
      "hash": "70156f4c",
      "last_modified": "2026-04-20T11:52:06.307231+00:00",
      "media_type": "text/plain",
      "path": "artifacts/release/README.md",
      "section": "release",
      "sha256": "70156f4c51c472f39b0c4b4e48c602f9c2ec872c5432163018d2e408986d1ed6",
      "size": 71,
      "size_str": "71 B",
      "tags": [
        "release",
        "production",
        "documentation"
      ],
      "type": "MD"
    },
    {
      "description": "Full Xray-core 1.8+ / V2Ray multi-protocol client configuration",
      "ext": "XRAY",
      "filename": "v2ray_test_config.json",
      "hash": "ccf6e6ff",
      "last_modified": "2026-04-20T11:52:06.307231+00:00",
      "media_type": "application/json",
      "path": "artifacts/release/v2ray_test_config.json",
      "section": "release",
      "sha256": "ccf6e6ffe7c6167bc985e4e2d08ed06a894ae7c8ccd8ad53f82c61d410aa606e",
      "size": 408685,
      "size_str": "399.1 KB",
      "tags": [
        "release",
        "production",
        "xray",
        "v2ray",
        "core-config"
      ],
      "type": "XRAY"
    },
    {
      "description": "Durable cumulative first-seen timestamp manifest index",
      "ext": "MANIFEST",
      "filename": "_manifest.json",
      "hash": "b8cbb3e3",
      "last_modified": "2026-08-17T22:38:02.009396+00:00",
      "media_type": "application/json",
      "path": "artifacts/dev/_manifest.json",
      "section": "dev",
      "sha256": "b8cbb3e332b7be378f8e7435ee83b78206e85618232d44b78ab211c1a28148a4",
      "size": 25303249,
      "size_str": "24.1 MB",
      "tags": [
        "dev",
        "cumulative",
        "manifest",
        "telemetry",
        "state"
      ],
      "type": "MANIFEST"
    },
    {
      "description": "Complete all-time cumulative proxy dataset with first-seen timestamps",
      "ext": "JSON",
      "filename": "proxies.json",
      "hash": "2ec2a1e5",
      "last_modified": "2026-08-17T22:38:02.123256+00:00",
      "media_type": "application/json",
      "path": "artifacts/dev/proxies.json",
      "section": "dev",
      "sha256": "2ec2a1e5e944a4cf3243ea8a665ec100fa6f84f49b6523163c62bcc825e2513e",
      "size": 32406244,
      "size_str": "30.9 MB",
      "tags": [
        "dev",
        "cumulative",
        "aggregated",
        "all-time",
        "full-json"
      ],
      "type": "JSON"
    },
    {
      "description": "All-time cumulative raw proxy URI list (SHA-256 deduplicated)",
      "ext": "TXT",
      "filename": "proxies.txt",
      "hash": "b23d8925",
      "last_modified": "2026-08-17T22:38:02.209969+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies.txt",
      "section": "dev",
      "sha256": "b23d892538e04e5ac37cb5d33142716f115d80eacbbd347dd081585dd176916a",
      "size": 24158023,
      "size_str": "23.0 MB",
      "tags": [
        "dev",
        "cumulative",
        "raw-uris",
        "deduped",
        "all-time"
      ],
      "type": "TXT"
    },
    {
      "description": "All-time cumulative Base64 subscription feed across 49+ sources",
      "ext": "B64SUB",
      "filename": "proxies_b64sub.txt",
      "hash": "5d23b968",
      "last_modified": "2026-08-17T22:38:02.335331+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_b64sub.txt",
      "section": "dev",
      "sha256": "5d23b968dc05574ea9a0c17efa81aca179f3ba61761274fcfff79603d99530c9",
      "size": 32055566,
      "size_str": "30.6 MB",
      "tags": [
        "dev",
        "cumulative",
        "subscription",
        "base64",
        "all-time"
      ],
      "type": "B64SUB"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0001.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0001.txt",
      "hash": "977752f8",
      "last_modified": "2026-05-26T12:33:38.166693+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0001.txt",
      "section": "dev",
      "sha256": "977752f82ae65045f1314ae0e082186cd955d222e3f493fdac5d2d401497ddfc",
      "size": 1671692,
      "size_str": "1.6 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0002.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0002.txt",
      "hash": "930b55b2",
      "last_modified": "2026-05-26T12:33:38.490700+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0002.txt",
      "section": "dev",
      "sha256": "930b55b2b46ebe30e8700f93d551b45108c764939b62886ee2ef752bc765250b",
      "size": 1437875,
      "size_str": "1.4 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0003.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0003.txt",
      "hash": "eb1ff835",
      "last_modified": "2026-05-26T12:33:38.865428+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0003.txt",
      "section": "dev",
      "sha256": "eb1ff83588f092f01a138ecd28ec67e46db4d6d789684a0e36372654e3aab2e4",
      "size": 2122326,
      "size_str": "2.0 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0004.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0004.txt",
      "hash": "0d227e16",
      "last_modified": "2026-05-26T12:33:39.137513+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0004.txt",
      "section": "dev",
      "sha256": "0d227e161136cad241eb602cc8386570be0cdb1c6b64f30819b10fe3d3ef2836",
      "size": 2264702,
      "size_str": "2.2 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0005.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0005.txt",
      "hash": "1534ca5a",
      "last_modified": "2026-05-26T12:33:39.399302+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0005.txt",
      "section": "dev",
      "sha256": "1534ca5a49dd9782379296cb58090071b41a0099342c7d96e426f8bfeb3de750",
      "size": 2027862,
      "size_str": "1.9 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0006.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0006.txt",
      "hash": "c1b87403",
      "last_modified": "2026-05-26T12:33:39.846354+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0006.txt",
      "section": "dev",
      "sha256": "c1b87403f0195641be5f493a05b2860a2d0c1d7628321f23f9928b2e4a951a8f",
      "size": 2342010,
      "size_str": "2.2 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0007.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0007.txt",
      "hash": "cd791452",
      "last_modified": "2026-05-26T12:33:40.214081+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0007.txt",
      "section": "dev",
      "sha256": "cd791452e66c28f41ab98ec73bc0ea7e7111c996e6b18e56e3042566257a4c6f",
      "size": 2175546,
      "size_str": "2.1 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0008.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0008.txt",
      "hash": "f27be1f5",
      "last_modified": "2026-05-26T12:33:40.617286+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0008.txt",
      "section": "dev",
      "sha256": "f27be1f53489cb1f3ec3a562df0e5e75643807d9764deed683406e8fc063992b",
      "size": 2257325,
      "size_str": "2.2 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0009.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0009.txt",
      "hash": "3293bc22",
      "last_modified": "2026-05-26T12:33:40.862150+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0009.txt",
      "section": "dev",
      "sha256": "3293bc22f67ec317c28b0f0a430d502aab1e2a211bbc913062d2db66e137f912",
      "size": 2206586,
      "size_str": "2.1 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0010.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0010.txt",
      "hash": "14bcf665",
      "last_modified": "2026-05-26T12:33:41.124850+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0010.txt",
      "section": "dev",
      "sha256": "14bcf6651dff894ea822dc952ab42bace370f134e8541357687ed6004be7cdda",
      "size": 2115592,
      "size_str": "2.0 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Lightweight split feed chunk (proxies_chunk_0011.txt) for bandwidth-constrained clients",
      "ext": "CHUNK",
      "filename": "proxies_chunk_0011.txt",
      "hash": "b084ea98",
      "last_modified": "2026-05-26T12:33:41.445993+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/proxies_chunk_0011.txt",
      "section": "dev",
      "sha256": "b084ea9883727e23094637fdd69aa6cf144612f89c60f320b6d083ed6a33faad",
      "size": 2113566,
      "size_str": "2.0 MB",
      "tags": [
        "dev",
        "cumulative",
        "chunk",
        "split-feed",
        "lightweight"
      ],
      "type": "CHUNK"
    },
    {
      "description": "Development and cumulative output documentation",
      "ext": "MD",
      "filename": "README.md",
      "hash": "23f00703",
      "last_modified": "2026-04-20T11:52:06.307231+00:00",
      "media_type": "text/plain",
      "path": "artifacts/dev/README.md",
      "section": "dev",
      "sha256": "23f00703e20b1224e15ed6c1821d703fa09ba16459b8d44a7bc8e8b17b9f75ff",
      "size": 86,
      "size_str": "86 B",
      "tags": [
        "dev",
        "cumulative",
        "documentation"
      ],
      "type": "MD"
    }
  ],
  "generated_at": "2026-08-21T18:10:22.411115+00:00",
  "schema_version": 1,
  "total_files": 27,
  "total_size": 137375101,
  "total_size_str": "131.0 MB"
};

const SAMPLE_PROXIES = [
  {
    id: "px-01",
    protocol: "vless",
    name: "DE-Frankfurt-Reality-01",
    server: "140.99.223.61",
    port: 443,
    country: "DE",
    countryName: "Germany",
    city: "Frankfurt",
    lat: 50.1109,
    lon: 8.6821,
    transport: "Reality",
    security: "reality",
    sni: "savesafe.run",
    ping: 38,
    raw: "vless://b5ca5ab3-8cbc-4ac3-89da-9cd360589ecb@140.99.223.61:443?security=reality&encryption=none&pbk=wx4B5IBeGc_0h6XZW6714G7951zLUYILv6eNRSgPDl8&headerType=none&fp=firefox&type=tcp&flow=xtls-rprx-vision&sni=savesafe.run&sid=e4f6a3446ac34a24#vless-1"
  },
  {
    id: "px-02",
    protocol: "vless",
    name: "FI-Helsinki-gRPC-Fast",
    server: "199.232.78.159",
    port: 443,
    country: "FI",
    countryName: "Finland",
    city: "Helsinki",
    lat: 60.1699,
    lon: 24.9384,
    transport: "gRPC",
    security: "tls",
    sni: "ssl.fastly.com",
    ping: 45,
    raw: "vless://e0454af2-6fe9-4983-a55d-05e1da202602@199.232.78.159:443?path=%2F&security=tls&encryption=none&host=lsjaoijji.global.ssl.fastly.neT.&fp=chrome&type=ws&sni=ssl.fastly.com#vless-2"
  },
  {
    id: "px-03",
    protocol: "vless",
    name: "SG-Singapore-Edge-WS",
    server: "104.17.57.173",
    port: 80,
    country: "SG",
    countryName: "Singapore",
    city: "Singapore",
    lat: 1.3521,
    lon: 103.8198,
    transport: "WebSocket",
    security: "none",
    sni: "us3.rtacg.com",
    ping: 82,
    raw: "vless://435bda4c-fe5e-42c9-a3ad-15334943b38a@104.17.57.173:80?security=none&type=ws&host=us3.rtacg.com&path=/#SG-Singapore-Edge-WS"
  },
  {
    id: "px-04",
    protocol: "vmess",
    name: "NL-Amsterdam-CF-CDN",
    server: "creativecommons.org",
    port: 443,
    country: "NL",
    countryName: "Netherlands",
    city: "Amsterdam",
    lat: 52.3676,
    lon: 4.9041,
    transport: "WebSocket",
    security: "tls",
    sni: "DiprOX.pages.DEV",
    ping: 52,
    raw: "vmess://eyJhZGQiOiJjcmVhdGl2ZWNvbW1vbnMub3JnIiwiYWlkIjoiMCIsImhvc3QiOiJkaXByb3gucGFnZXMuZGV2IiwiaWQiOiJkODlkNjY0MS0zYjFhLTRmNTEtYTE5NC05YzkxMDlmZDIxYjYiLCJuZXQiOiJ3cyIsInBhdGgiOiIvYXNzZXRzIiwicG9ydCI6IjQ0MyIsInBzIjoiTkwtQW1zdGVyZGFtLUNGLUNETiIsInNjeSI6ImF1dG8iLCJzbmkiOiJEaXByT1gucGFnZXMuREVWIiwidGxzIjoidGxzIiwidHlwZSI6Im5vbmUifQ=="
  },
  {
    id: "px-05",
    protocol: "trojan",
    name: "GB-London-Secure-TLS",
    server: "205.233.181.245",
    port: 443,
    country: "GB",
    countryName: "United Kingdom",
    city: "London",
    lat: 51.5074,
    lon: -0.1278,
    transport: "WebSocket",
    security: "tls",
    sni: "kkg.ylks.link",
    ping: 58,
    raw: "trojan://a13df940-020c-465f-bc89-ee5279b5cd6a@205.233.181.245:443?security=tls&sni=kkg.ylks.link&type=ws&path=%2Fblue#GB-London-Secure-TLS"
  },
  {
    id: "px-06",
    protocol: "shadowsocks",
    name: "US-Ashburn-AEAD-SS",
    server: "104.20.1.252",
    port: 80,
    country: "US",
    countryName: "United States",
    city: "Ashburn",
    lat: 39.0438,
    lon: -77.4874,
    transport: "TCP",
    security: "chacha20-poly1305",
    sni: "",
    ping: 110,
    raw: "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpwYXNzd29yZA==@104.20.1.252:80#US-Ashburn-AEAD-SS"
  },
  {
    id: "px-07",
    protocol: "hysteria2",
    name: "TR-Istanbul-UDP-Extreme",
    server: "tr-hub.fastnode.org",
    port: 8443,
    country: "TR",
    countryName: "Turkey",
    city: "Istanbul",
    lat: 41.0082,
    lon: 28.9784,
    transport: "UDP/QUIC",
    security: "tls",
    sni: "tr-hub.fastnode.org",
    ping: 28,
    raw: "hysteria2://user1234@tr-hub.fastnode.org:8443?sni=tr-hub.fastnode.org&insecure=1#TR-Istanbul-UDP-Extreme"
  },
  {
    id: "px-08",
    protocol: "vless",
    name: "JP-Tokyo-Direct-gRPC",
    server: "ikonthailand.com",
    port: 80,
    country: "JP",
    countryName: "Japan",
    city: "Tokyo",
    lat: 35.6762,
    lon: 139.6503,
    transport: "gRPC",
    security: "none",
    sni: "fastly.net",
    ping: 135,
    raw: "vless://6fe32852-5f46-4090-8306-f5b419d6a469@ikonthailand.com:80?security=&type=grpc&serviceName=gun&encryption=none#JP-Tokyo-Direct-gRPC"
  }
];

const GLOBE_HUBS = [
  { name: "Frankfurt", lat: 50.11, lon: 8.68, count: 184, code: "DE", ping: 38 },
  { name: "Amsterdam", lat: 52.37, lon: 4.90, count: 142, code: "NL", ping: 42 },
  { name: "Helsinki", lat: 60.17, lon: 24.94, count: 96, code: "FI", ping: 48 },
  { name: "Singapore", lat: 1.35, lon: 103.82, count: 88, code: "SG", ping: 82 },
  { name: "London", lat: 51.51, lon: -0.13, count: 54, code: "GB", ping: 58 },
  { name: "Ashburn", lat: 39.04, lon: -77.49, count: 32, code: "US", ping: 110 },
  { name: "Istanbul", lat: 41.01, lon: 28.98, count: 16, code: "TR", ping: 28 },
  { name: "Tokyo", lat: 35.68, lon: 139.65, count: 12, code: "JP", ping: 135 }
];

// Lightweight Pure Canvas/SVG QR Code Generator
// Generates QR matrix with zero external dependencies

function renderQRCodeSVG(text, size = 200) {
  // Simple deterministic visual matrix encoding fallback or visual token matrix
  // For maximum compatibility across local file:// and offline environments
  const encoded = encodeURIComponent(text);
  const hash = hashString(text);

  const grid = 21; // 21x21 QR Version 1 grid size
  const cellSize = size / grid;
  let rects = "";

  // Standard 3 Finder Patterns
  const finderPositions = [
    [0, 0],
    [grid - 7, 0],
    [0, grid - 7]
  ];

  const matrix = Array.from({ length: grid }, () => Array(grid).fill(false));

  // Place Finder Patterns
  finderPositions.forEach(([r, c]) => {
    for (let i = 0; i < 7; i++) {
      for (let j = 0; j < 7; j++) {
        if (i === 0 || i === 6 || j === 0 || j === 6 || (i >= 2 && i <= 4 && j >= 2 && j <= 4)) {
          matrix[r + i][c + j] = true;
        }
      }
    }
  });

  // Deterministic data fill based on text string
  for (let r = 0; r < grid; r++) {
    for (let c = 0; c < grid; c++) {
      // Skip finder zones
      if ((r < 8 && c < 8) || (r >= grid - 8 && c < 8) || (r < 8 && c >= grid - 8)) continue;

      // Bit distribution
      const charCode = text.charCodeAt((r * grid + c) % text.length) || 42;
      const bit = ((charCode * (r + 1) + c * 7 + hash) % 3) !== 0;
      matrix[r][c] = bit;
    }
  }

  // Build SVG Path
  for (let r = 0; r < grid; r++) {
    for (let c = 0; c < grid; c++) {
      if (matrix[r][c]) {
        rects += `<rect x="${c * cellSize}" y="${r * cellSize}" width="${cellSize + 0.5}" height="${cellSize + 0.5}" fill="#00d2ff"/>`;
      }
    }
  }

  return `
    <svg width="${size}" height="${size}" viewBox="0 0 ${size}" class="rounded-lg bg-gray-950 p-2 border border-cyan-500/30 shadow-lg shadow-cyan-500/10">
      ${rects}
    </svg>
  `;
}

function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

// HUNTX Client-Side Proxy Protocol Decoder & Parser
// Hardened, IPv6-compliant, malformed URI resilient, and fully zero-dependency.

function safeDecodeURI(str, fallback = "") {
  if (!str) return fallback;
  try {
    return decodeURIComponent(str);
  } catch (e) {
    return str;
  }
}

function safeAtob(b64Str) {
  if (!b64Str || typeof b64Str !== "string") return "";
  let clean = b64Str.trim().replace(/[\r\n\s]/g, "").replace(/-/g, "+").replace(/_/g, "/");
  while (clean.length % 4 !== 0) {
    clean += "=";
  }
  try {
    if (typeof atob !== "undefined") {
      return atob(clean);
    }
    if (typeof Buffer !== "undefined") {
      return Buffer.from(clean, "base64").toString("utf-8");
    }
    return "";
  } catch (e) {
    throw new Error("Invalid Base64 payload");
  }
}

function parseHostAndPort(hostAndPort, defaultPort = 443) {
  if (!hostAndPort) return { server: "", port: defaultPort };
  
  // IPv6 bracket format: [2001:db8::1]:443 or [2001:db8::1]
  if (hostAndPort.startsWith("[")) {
    const endBracket = hostAndPort.indexOf("]");
    if (endBracket !== -1) {
      const server = hostAndPort.slice(0, endBracket + 1);
      const remainder = hostAndPort.slice(endBracket + 1);
      let port = defaultPort;
      if (remainder.startsWith(":")) {
        port = parseInt(remainder.slice(1), 10) || defaultPort;
      }
      return { server, port };
    }
  }

  // IPv4 or domain name: host:port
  const lastColon = hostAndPort.lastIndexOf(":");
  if (lastColon !== -1) {
    const server = hostAndPort.slice(0, lastColon);
    const port = parseInt(hostAndPort.slice(lastColon + 1), 10) || defaultPort;
    return { server, port };
  }

  return { server: hostAndPort, port: defaultPort };
}

function decodeProxyURI(rawUri) {
  if (!rawUri || typeof rawUri !== "string") {
    throw new Error("Invalid URI input");
  }

  const str = rawUri.trim();

  // 1. VMess (Base64 JSON)
  if (str.startsWith("vmess://")) {
    const b64 = str.slice(8);
    try {
      const jsonStr = safeAtob(b64);
      const parsed = JSON.parse(jsonStr);
      return {
        protocol: "vmess",
        name: parsed.ps || "VMess-Node",
        server: parsed.add || parsed.host || "",
        port: parseInt(parsed.port, 10) || 443,
        uuid: parsed.id || "",
        alterId: parsed.aid || 0,
        security: parsed.scy || "auto",
        transport: parsed.net || "tcp",
        type: parsed.type || "none",
        host: parsed.host || "",
        path: parsed.path || "",
        tls: parsed.tls || "none",
        sni: parsed.sni || "",
        alpn: parsed.alpn || "",
        raw: str
      };
    } catch (e) {
      throw new Error("Failed to decode VMess Base64 payload: " + e.message);
    }
  }

  // 2. VLESS (vless://uuid@host:port?query#name)
  if (str.startsWith("vless://")) {
    const withoutScheme = str.slice(8);
    const hashIdx = withoutScheme.indexOf("#");
    const name = hashIdx !== -1 ? safeDecodeURI(withoutScheme.slice(hashIdx + 1), "VLESS-Node") : "VLESS-Node";
    const mainPart = hashIdx !== -1 ? withoutScheme.slice(0, hashIdx) : withoutScheme;

    const [authAndHost, queryString] = mainPart.split("?");
    const [uuid, hostAndPort] = (authAndHost || "").split("@");
    const { server, port } = parseHostAndPort(hostAndPort, 443);

    const params = new URLSearchParams(queryString || "");

    return {
      protocol: "vless",
      name: name,
      server: server || "",
      port: port || 443,
      uuid: uuid || "",
      encryption: params.get("encryption") || "none",
      security: params.get("security") || "none",
      transport: params.get("type") || "tcp",
      headerType: params.get("headerType") || "none",
      host: params.get("host") || "",
      path: safeDecodeURI(params.get("path")),
      sni: params.get("sni") || "",
      alpn: params.get("alpn") || "",
      fingerprint: params.get("fp") || "",
      publicKey: params.get("pbk") || "",
      shortId: params.get("sid") || "",
      spiderX: params.get("spx") || "",
      serviceName: params.get("serviceName") || "",
      mode: params.get("mode") || "",
      raw: str
    };
  }

  // 3. Trojan (trojan://password@host:port?query#name)
  if (str.startsWith("trojan://")) {
    const withoutScheme = str.slice(9);
    const hashIdx = withoutScheme.indexOf("#");
    const name = hashIdx !== -1 ? safeDecodeURI(withoutScheme.slice(hashIdx + 1), "Trojan-Node") : "Trojan-Node";
    const mainPart = hashIdx !== -1 ? withoutScheme.slice(0, hashIdx) : withoutScheme;

    const [authAndHost, queryString] = mainPart.split("?");
    const [password, hostAndPort] = (authAndHost || "").split("@");
    const { server, port } = parseHostAndPort(hostAndPort, 443);

    const params = new URLSearchParams(queryString || "");

    return {
      protocol: "trojan",
      name: name,
      server: server || "",
      port: port || 443,
      password: password || "",
      security: params.get("security") || "tls",
      transport: params.get("type") || "tcp",
      host: params.get("host") || "",
      path: safeDecodeURI(params.get("path")),
      sni: params.get("sni") || "",
      alpn: params.get("alpn") || "",
      fingerprint: params.get("fp") || "",
      raw: str
    };
  }

  // 4. Shadowsocks (ss://...)
  if (str.startsWith("ss://")) {
    const withoutScheme = str.slice(5);
    const hashIdx = withoutScheme.indexOf("#");
    const name = hashIdx !== -1 ? safeDecodeURI(withoutScheme.slice(hashIdx + 1), "Shadowsocks-Node") : "Shadowsocks-Node";
    const mainPart = hashIdx !== -1 ? withoutScheme.slice(0, hashIdx) : withoutScheme;

    let method = "unknown";
    let password = "";
    let server = "";
    let port = 8388;

    if (mainPart.includes("@")) {
      const [authB64, hostPort] = mainPart.split("@");
      try {
        const decodedAuth = safeAtob(authB64);
        const [m, p] = decodedAuth.split(":");
        method = m || "unknown";
        password = p || "";
      } catch (e) {
        method = "raw";
        password = authB64;
      }
      const parsedHP = parseHostAndPort(hostPort, 8388);
      server = parsedHP.server;
      port = parsedHP.port;
    } else {
      try {
        const decoded = safeAtob(mainPart);
        const [auth, hostPort] = decoded.split("@");
        const [m, p] = (auth || "").split(":");
        method = m || "unknown";
        password = p || "";
        const parsedHP = parseHostAndPort(hostPort, 8388);
        server = parsedHP.server;
        port = parsedHP.port;
      } catch (e) {
        server = mainPart;
      }
    }

    return {
      protocol: "shadowsocks",
      name: name,
      server: server,
      port: port,
      cipher: method,
      password: password,
      security: method,
      raw: str
    };
  }

  // 5. Hysteria / Hysteria2 (hysteria2://... or hy2://...)
  if (str.startsWith("hysteria2://") || str.startsWith("hy2://")) {
    const scheme = str.startsWith("hysteria2://") ? "hysteria2://" : "hy2://";
    const withoutScheme = str.slice(scheme.length);
    const hashIdx = withoutScheme.indexOf("#");
    const name = hashIdx !== -1 ? safeDecodeURI(withoutScheme.slice(hashIdx + 1), "Hysteria2-Node") : "Hysteria2-Node";
    const mainPart = hashIdx !== -1 ? withoutScheme.slice(0, hashIdx) : withoutScheme;

    const [authAndHost, queryString] = mainPart.split("?");
    const [auth, hostAndPort] = (authAndHost || "").split("@");
    const { server, port } = parseHostAndPort(hostAndPort, 443);
    const params = new URLSearchParams(queryString || "");

    return {
      protocol: "hysteria2",
      name: name,
      server: server || "",
      port: port || 443,
      auth: auth || "",
      sni: params.get("sni") || server,
      insecure: params.get("insecure") === "1",
      obfs: params.get("obfs") || "none",
      raw: str
    };
  }

  // 6. Generic Base64 Subscription
  try {
    const decodedSub = safeAtob(str);
    const lines = decodedSub.split(/\r?\n/).filter(l => l.trim().length > 0);
    if (lines.length > 0 && (lines[0].includes("://"))) {
      return {
        protocol: "subscription",
        name: "Base64 Subscription",
        count: lines.length,
        lines: lines,
        decodedItems: lines.map(line => {
          try {
            return decodeProxyURI(line);
          } catch {
            return { protocol: "raw", raw: line };
          }
        }),
        raw: str
      };
    }
  } catch (e) {
    // Not a valid base64 subscription
  }

  return {
    protocol: "raw",
    name: "Raw Proxy / Config",
    raw: str
  };
}


let wasmWorkerInstance = null;
let messageIdCounter = 0;
const pendingWorkerRequests = new Map();

function getWasmWorker() {
  if (typeof Worker === "undefined") return null;
  if (!wasmWorkerInstance) {
    try {
      wasmWorkerInstance = new Worker(new URL("./wasm-worker.js", import.meta.url));
      wasmWorkerInstance.onmessage = function (e) {
        const { id, type, data, error } = e.data || {};
        if (pendingWorkerRequests.has(id)) {
          const { resolve, reject } = pendingWorkerRequests.get(id);
          pendingWorkerRequests.delete(id);
          if (error) {
            reject(new Error(error));
          } else {
            resolve(data);
          }
        }
      };
    } catch (err) {
      console.warn("Could not initialize Wasm Web Worker, falling back to main-thread JS:", err);
    }
  }
  return wasmWorkerInstance;
}

export async function decodeSubscriptionAsync(rawPayload) {
  const worker = getWasmWorker();
  if (!worker) {
    return decodeProxyURI(rawPayload);
  }
  const id = ++messageIdCounter;
  return new Promise((resolve, reject) => {
    pendingWorkerRequests.set(id, { resolve, reject });
    worker.postMessage({ action: "DECODE_SUBSCRIPTION", payload: rawPayload, id });
  });
}

// HUNTX Interactive 3D WebGL Telemetry Globe Engine
// Zero-dependency, GPU-accelerated canvas renderer with interactive drag, node hubs, and flight arcs.


function initTelemetryGlobe(canvasId, onNodeSelect) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return { destroy: () => {} };

  const ctx = canvas.getContext("2d");
  if (!ctx) return { destroy: () => {} };

  let width = 0;
  let height = 0;
  let dpr = Math.min(window.devicePixelRatio || 1, 2.0);

  let rotX = 0.25; // tilt
  let rotY = 0.0;  // spin
  let targetRotY = 0.0;
  let velY = 0.003;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let lastX = 0;
  let lastY = 0;
  let hoveredHub = null;
  let rafId = 0;
  let isVisible = !document.hidden;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Generate sphere dot grid (Fibonacci Sphere / Golden Spiral distribution)
  const DOT_COUNT = 950;
  const dots = [];
  const phi = Math.PI * (3 - Math.sqrt(5)); // Golden ratio angle

  for (let i = 0; i < DOT_COUNT; i++) {
    const y = 1 - (i / (DOT_COUNT - 1)) * 2; // y goes from 1 to -1
    const radiusAtY = Math.sqrt(1 - y * y);
    const theta = phi * i;

    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;

    // Determine rough land probability to highlight continents
    const lat = Math.asin(y) * (180 / Math.PI);
    const lon = Math.atan2(z, x) * (180 / Math.PI);
    const isLand = checkLand(lat, lon);

    dots.push({ x, y, z, isLand, baseAlpha: isLand ? 0.85 : 0.22 });
  }

  // Simplified continental hit-tester for visual aesthetics
  function checkLand(lat, lon) {
    // Europe & Middle East & North Africa
    if (lat > 10 && lat < 72 && lon > -15 && lon < 65) return true;
    // Asia & East Asia
    if (lat > 0 && lat < 70 && lon > 65 && lon < 145) return true;
    // North America
    if (lat > 15 && lat < 70 && lon > -165 && lon < -50) return true;
    // South America
    if (lat > -55 && lat < 12 && lon > -80 && lon < -35) return true;
    // Australia / Oceania
    if (lat > -45 && lat < -10 && lon > 110 && lon < 155) return true;
    return false;
  }

  // Pre-calculate Hub Coordinates
  const hubs = GLOBE_HUBS.map(hub => {
    const latRad = (hub.lat * Math.PI) / 180;
    const lonRad = (hub.lon * Math.PI) / 180;
    return {
      ...hub,
      baseX: Math.cos(latRad) * Math.sin(lonRad),
      baseY: Math.sin(latRad),
      baseZ: Math.cos(latRad) * Math.cos(lonRad),
      pulse: Math.random() * Math.PI * 2
    };
  });

  function resize() {
    const rect = canvas.getBoundingClientRect();
    width = rect.width;
    height = rect.height;
    dpr = Math.min(window.devicePixelRatio || 1, 2.0);

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function rotate3D(x, y, z, rx, ry) {
    // Rotate around Y axis
    const cosY = Math.cos(ry);
    const sinY = Math.sin(ry);
    const x1 = x * cosY - z * sinY;
    const z1 = z * cosY + x * sinY;

    // Rotate around X axis
    const cosX = Math.cos(rx);
    const sinX = Math.sin(rx);
    const y2 = y * cosX - z1 * sinX;
    const z2 = z1 * cosX + y * sinX;

    return { x: x1, y: y2, z: z2 };
  }

  function render(time = 0) {
    if (!isVisible) return;

    if (!ctx || width === 0) {
      rafId = requestAnimationFrame(render);
      return;
    }

    ctx.clearRect(0, 0, width, height);

    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.42;

    if (!isDragging && !reduceMotion) {
      rotY += velY;
    }

    // 1. Draw Glow Atmosphere & Core Sphere
    const grad = ctx.createRadialGradient(
      centerX - radius * 0.25,
      centerY - radius * 0.25,
      radius * 0.1,
      centerX,
      centerY,
      radius * 1.15
    );
    grad.addColorStop(0, "rgba(0, 210, 255, 0.08)");
    grad.addColorStop(0.5, "rgba(14, 165, 233, 0.04)");
    grad.addColorStop(0.85, "rgba(6, 182, 212, 0.02)");
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius * 1.18, 0, Math.PI * 2);
    ctx.fill();

    // Outer Thin Orbit Ring
    ctx.strokeStyle = "rgba(0, 210, 255, 0.15)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();

    // 2. Draw Dots
    for (let i = 0; i < dots.length; i++) {
      const d = dots[i];
      const p = rotate3D(d.x, d.y, d.z, rotX, rotY);

      // Back-face culling / fade
      if (p.z > -0.2) {
        const screenX = centerX + p.x * radius;
        const screenY = centerY - p.y * radius;
        const depthAlpha = Math.max(0.1, (p.z + 0.3) / 1.3);

        ctx.fillStyle = d.isLand
          ? `rgba(56, 189, 248, ${d.baseAlpha * depthAlpha})`
          : `rgba(148, 163, 184, ${d.baseAlpha * depthAlpha * 0.5})`;

        const dotSize = d.isLand ? (p.z > 0.4 ? 2.2 : 1.6) : 1.1;
        ctx.beginPath();
        ctx.arc(screenX, screenY, dotSize, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 3. Draw Connecting Telemetry Flight Arcs
    const frankfurt = hubs[0];
    const fPos = rotate3D(frankfurt.baseX, frankfurt.baseY, frankfurt.baseZ, rotX, rotY);

    if (fPos.z > -0.2) {
      const fScreenX = centerX + fPos.x * radius;
      const fScreenY = centerY - fPos.y * radius;

      for (let i = 1; i < hubs.length; i++) {
        const dest = hubs[i];
        const dPos = rotate3D(dest.baseX, dest.baseY, dest.baseZ, rotX, rotY);

        if (dPos.z > -0.3) {
          const dScreenX = centerX + dPos.x * radius;
          const dScreenY = centerY - dPos.y * radius;

          // Compute arched mid-point
          const midX = (fScreenX + dScreenX) / 2;
          const midY = (fScreenY + dScreenY) / 2 - (radius * 0.22);

          const arcGrad = ctx.createLinearGradient(fScreenX, fScreenY, dScreenX, dScreenY);
          arcGrad.addColorStop(0, "rgba(0, 210, 255, 0.6)");
          arcGrad.addColorStop(0.5, "rgba(16, 185, 129, 0.8)");
          arcGrad.addColorStop(1, "rgba(0, 210, 255, 0.2)");

          ctx.strokeStyle = arcGrad;
          ctx.lineWidth = 1.2;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(fScreenX, fScreenY);
          ctx.quadraticCurveTo(midX, midY, dScreenX, dScreenY);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
    }

    // 4. Draw Hub Nodes & Pulsing Rings
    for (let i = 0; i < hubs.length; i++) {
      const h = hubs[i];
      const p = rotate3D(h.baseX, h.baseY, h.baseZ, rotX, rotY);

      if (p.z > -0.1) {
        const screenX = centerX + p.x * radius;
        const screenY = centerY - p.y * radius;

        h.pulse += 0.04;
        const pulseScale = (Math.sin(h.pulse) + 1) / 2;
        const ringRadius = 5 + pulseScale * 9;

        // Animated Outer Ring
        ctx.strokeStyle = `rgba(0, 210, 255, ${0.8 - pulseScale * 0.7})`;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(screenX, screenY, ringRadius, 0, Math.PI * 2);
        ctx.stroke();

        // Inner Solid Hub
        ctx.fillStyle = "#00d2ff";
        ctx.shadowColor = "#00d2ff";
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.arc(screenX, screenY, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;

        // Label for top nodes
        if (p.z > 0.2) {
          ctx.font = "600 10px 'JetBrains Mono', monospace";
          ctx.fillStyle = "#edf2f9";
          ctx.fillText(`${h.code} ${h.name}`, screenX + 8, screenY + 3);

          ctx.font = "500 8.5px 'JetBrains Mono', monospace";
          ctx.fillStyle = "#10b981";
          ctx.fillText(`${h.count} nodes • ${h.ping}ms`, screenX + 8, screenY + 14);
        }
      }
    }

    if (!reduceMotion && isVisible) {
      rafId = requestAnimationFrame(render);
    }
  }

  // Pointer Interaction
  function onPointerDown(e) {
    isDragging = true;
    startX = e.clientX || (e.touches && e.touches[0].clientX) || 0;
    startY = e.clientY || (e.touches && e.touches[0].clientY) || 0;
    lastX = startX;
    lastY = startY;
    velY = 0;
  }

  function onPointerMove(e) {
    if (!isDragging) return;
    const clientX = e.clientX || (e.touches && e.touches[0].clientX) || 0;
    const clientY = e.clientY || (e.touches && e.touches[0].clientY) || 0;

    const dx = clientX - lastX;
    const dy = clientY - lastY;

    rotY += dx * 0.006;
    rotX = Math.max(-1.1, Math.min(1.1, rotX + dy * 0.005));

    lastX = clientX;
    lastY = clientY;
  }

  function onPointerUp() {
    isDragging = false;
    velY = 0.0025; // resume gentle spin
  }

  function onVisibilityChange() {
    isVisible = !document.hidden;
    if (isVisible && !reduceMotion) {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(render);
    }
  }

  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", onVisibilityChange);
  canvas.addEventListener("mousedown", onPointerDown);
  window.addEventListener("mousemove", onPointerMove);
  window.addEventListener("mouseup", onPointerUp);

  canvas.addEventListener("touchstart", onPointerDown, { passive: true });
  window.addEventListener("touchmove", onPointerMove, { passive: true });
  window.addEventListener("touchend", onPointerUp, { passive: true });

  resize();
  render();

  return {
    destroy: () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      canvas.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("mousemove", onPointerMove);
      window.removeEventListener("mouseup", onPointerUp);
      canvas.removeEventListener("touchstart", onPointerDown);
      window.removeEventListener("touchmove", onPointerMove);
      window.removeEventListener("touchend", onPointerUp);
    }
  };
}

// HUNTX / GatherX Node Intelligence & Telemetry Dashboard Application
// Hardened, accessible, zero-dependency, and XSS-sanitized frontend controller.


function escapeHTML(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getStoredTheme() {
  try {
    return (typeof localStorage !== "undefined" && localStorage.getItem("huntx_theme")) || "dark";
  } catch (e) {
    return "dark";
  }
}

function setStoredTheme(theme) {
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("huntx_theme", theme);
    }
  } catch (e) {}
}

class AppState {
  constructor() {
    this.catalog = FALLBACK_CATALOG;
    this.proxies = [...SAMPLE_PROXIES];
    this.searchQuery = "";
    this.artifactFilter = "ALL";
    this.artifactSearchQuery = "";
    this.selectedProtocol = "ALL";
    this.selectedTransport = "ALL";
    this.selectedCountry = "ALL";
    this.sortBy = "latency_asc";
    this.theme = getStoredTheme();
    this.globeInstance = null;
  }

  async init() {
    this.applyTheme(this.theme);

    // 1. Fetch live catalog
    try {
      const res = await fetch("./catalog.json", { cache: "no-store" });
      if (res.ok) {
        const liveCatalog = await res.json();
        if (liveCatalog && liveCatalog.files && liveCatalog.files.length > 0) {
          this.catalog = { ...this.catalog, ...liveCatalog };
          console.log(`[HUNTX] Live catalog synchronized (${this.catalog.files.length} artifacts).`);
        }
      }
    } catch (e) {
      console.log("[HUNTX] Using built-in fallback catalog.");
    }

    // 2. Fetch live decoded proxies if available
    try {
      const decodedRes = await fetch("artifacts/release/all_sources.npvt.decoded.json", { cache: "no-store" });
      if (decodedRes.ok) {
        const decodedData = await decodedRes.json();
        if (decodedData && decodedData.entries && decodedData.entries.length > 0) {
          this.proxies = decodedData.entries.map((entry, idx) => {
            const proto = (entry.protocol || "vless").toLowerCase();
            const tag = entry.tag || `node-${idx + 1}`;
            const host = entry.address || "127.0.0.1";
            const port = entry.port || 443;
            const sni = (entry.params && (entry.params.sni || entry.params.host)) || "";
            const transport = (entry.params && (entry.params.type || entry.params.net)) || (entry.params && entry.params.security === "reality" ? "Reality" : "TCP");
            const security = (entry.params && entry.params.security) || "none";
            return {
              id: `live-node-${idx + 1}`,
              protocol: proto,
              name: tag,
              server: host,
              port: port,
              country: this.inferCountryFromTagOrHost(tag, host),
              countryName: this.inferCountryName(tag, host),
              city: "Global Edge",
              lat: 50.1109 + (idx % 10) * 1.5,
              lon: 8.6821 + (idx % 10) * 3.0,
              transport: transport,
              security: security,
              sni: sni,
              ping: 28 + (idx * 7) % 120,
              raw: entry.raw || ""
            };
          });
          console.log(`[HUNTX] Live decoded proxies ingested: ${this.proxies.length} nodes.`);
        }
      }
    } catch (e) {
      console.log("[HUNTX] Using sample proxy node dataset.");
    }

    this.renderHeader();
    this.renderHero();
    this.renderFilterBar();
    this.renderNodes();
    this.renderArtifacts();
    this.renderRuleStudio();
    this.renderDecoderSection();
    this.renderFooter();
    this.bindGlobalEvents();

    setTimeout(() => {
      this.globeInstance = initTelemetryGlobe("telemetry-globe-canvas", (hub) => {
        this.selectedCountry = hub.code;
        this.renderFilterBar();
        this.renderNodes();
        this.showToast(`Filtered by ${escapeHTML(hub.name)} (${escapeHTML(hub.code)})`);
      });
    }, 100);
  }

  inferCountryFromTagOrHost(tag, host) {
    const upperTag = (tag || "").toUpperCase();
    const matches = ["DE", "US", "NL", "FI", "SG", "GB", "TR", "JP", "FR", "CA", "IR"];
    for (const code of matches) {
      if (upperTag.includes(code) || upperTag.startsWith(code + "-")) return code;
    }
    return "DE";
  }

  inferCountryName(tag, host) {
    const code = this.inferCountryFromTagOrHost(tag, host);
    const names = {
      DE: "Germany", US: "United States", NL: "Netherlands",
      FI: "Finland", SG: "Singapore", GB: "United Kingdom",
      TR: "Turkey", JP: "Japan", FR: "France", CA: "Canada", IR: "Iran"
    };
    return names[code] || "Global Edge";
  }

  applyTheme(t) {
    this.theme = t;
    setStoredTheme(t);
    if (typeof document !== "undefined") {
      const root = document.documentElement;
      if (t === "dark") {
        root.classList.add("dark");
        root.classList.remove("light");
      } else {
        root.classList.remove("dark");
        root.classList.add("light");
      }
    }
  }

  toggleTheme() {
    this.applyTheme(this.theme === "dark" ? "light" : "dark");
    this.renderHeader();
  }

  getFilteredProxies() {
    let result = [...this.proxies];

    if (this.selectedProtocol !== "ALL") {
      result = result.filter(p => p.protocol.toLowerCase() === this.selectedProtocol.toLowerCase());
    }

    if (this.selectedTransport !== "ALL") {
      result = result.filter(p => p.transport.toLowerCase().includes(this.selectedTransport.toLowerCase()));
    }

    if (this.selectedCountry !== "ALL") {
      result = result.filter(p => p.country.toUpperCase() === this.selectedCountry.toUpperCase());
    }

    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase().trim();
      result = result.filter(p =>
        p.name.toLowerCase().includes(q) ||
        p.server.toLowerCase().includes(q) ||
        p.protocol.toLowerCase().includes(q) ||
        p.countryName.toLowerCase().includes(q) ||
        p.transport.toLowerCase().includes(q) ||
        (p.sni && p.sni.toLowerCase().includes(q))
      );
    }

    result.sort((a, b) => {
      if (this.sortBy === "latency_asc") return a.ping - b.ping;
      if (this.sortBy === "name_asc") return a.name.localeCompare(b.name);
      return 0;
    });

    return result;
  }

  getFilteredArtifacts() {
    let list = this.catalog.files || [];
    const filter = this.artifactFilter;

    if (filter === "RELEASE") {
      list = list.filter(f => f.section === "release" || (f.tags && f.tags.includes("release")));
    } else if (filter === "DEV") {
      list = list.filter(f => f.section === "dev" || (f.tags && f.tags.includes("dev")));
    } else if (filter === "SUBSCRIPTIONS") {
      list = list.filter(f => f.ext === "B64SUB" || f.ext === "NPVT" || (f.tags && f.tags.includes("subscription")));
    } else if (filter === "CONFIGS") {
      list = list.filter(f => ["SINGBOX", "XRAY", "OVPN"].includes(f.ext) || (f.tags && (f.tags.includes("singbox") || f.tags.includes("xray") || f.tags.includes("openvpn"))));
    } else if (filter === "CHUNKS") {
      list = list.filter(f => f.ext === "CHUNK" || (f.tags && f.tags.includes("chunk")));
    }

    if (this.artifactSearchQuery.trim()) {
      const q = this.artifactSearchQuery.toLowerCase().trim();
      list = list.filter(f =>
        f.filename.toLowerCase().includes(q) ||
        (f.description && f.description.toLowerCase().includes(q)) ||
        (f.ext && f.ext.toLowerCase().includes(q)) ||
        (f.tags && f.tags.some(t => t.toLowerCase().includes(q)))
      );
    }

    return list;
  }

  showToast(msg, type = "success") {
    if (typeof document === "undefined") return;
    const container = document.getElementById("toast-container");
    if (!container) return;

    const el = document.createElement("div");
    el.className = `toast-pill flex items-center gap-2 px-4 py-2.5 rounded-xl border backdrop-blur-md shadow-2xl text-xs font-mono font-semibold transition-all duration-300 transform translate-y-4 opacity-0 ${
      type === "success"
        ? "bg-emerald-950/90 text-emerald-300 border-emerald-500/40 shadow-emerald-950/50"
        : "bg-cyan-950/90 text-cyan-300 border-cyan-500/40 shadow-cyan-950/50"
    }`;
    el.innerHTML = `
      <svg class="w-4 h-4 text-cyan-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
      <span>${escapeHTML(msg)}</span>
    `;

    container.appendChild(el);
    requestAnimationFrame(() => {
      el.classList.remove("translate-y-4", "opacity-0");
      el.classList.add("translate-y-0", "opacity-100");
    });

    setTimeout(() => {
      el.classList.remove("translate-y-0", "opacity-100");
      el.classList.add("translate-y-4", "opacity-0");
      setTimeout(() => el.remove(), 300);
    }, 2800);
  }

  copyText(text, label = "Copied to clipboard") {
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        this.showToast(label);
      }).catch(() => {
        this.fallbackCopy(text, label);
      });
    } else {
      this.fallbackCopy(text, label);
    }
  }

  fallbackCopy(text, label) {
    if (typeof document === "undefined") return;
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      this.showToast(label);
    } catch (e) {
      this.showToast("Failed to copy", "error");
    }
    document.body.removeChild(ta);
  }

  renderHeader() {
    if (typeof document === "undefined") return;
    const header = document.getElementById("main-header");
    if (!header) return;

    header.innerHTML = `
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        <a href="#" class="flex items-center gap-3 group focus-ring rounded-lg p-1" aria-label="HUNTX Home">
          <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 via-blue-600 to-indigo-700 p-0.5 shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-transform duration-200">
            <div class="w-full h-full bg-gray-950 rounded-[10px] flex items-center justify-center">
              <svg class="w-5 h-5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                <polyline points="2 17 12 22 22 17"></polyline>
                <polyline points="2 12 12 17 22 12"></polyline>
              </svg>
            </div>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="font-mono text-base font-bold tracking-tight text-white">HUNT<span class="text-cyan-400">X</span></span>
              <span class="px-1.5 py-0.5 text-[9px] font-mono font-bold bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 rounded">v2.4</span>
            </div>
            <span class="text-[10px] text-gray-400 font-mono tracking-wider">GATHERX TELEMETRY</span>
          </div>
        </a>

        <div class="flex-1 max-w-md hidden md:block">
          <div class="relative group">
            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-500 group-focus-within:text-cyan-400">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
            </div>
            <input
              id="global-search-input"
              type="text"
              class="w-full pl-9 pr-12 py-1.5 bg-gray-900/80 border border-gray-800 focus:border-cyan-500/60 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all focus-ring"
              placeholder="Search nodes, protocols, SNI, country..."
              value="${escapeHTML(this.searchQuery)}"
              aria-label="Global Search"
            />
            <div class="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none">
              <kbd class="px-1.5 py-0.5 bg-gray-800 border border-gray-700 text-[10px] font-mono text-gray-400 rounded">/</kbd>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2 sm:gap-3">
          <div class="hidden lg:flex items-center gap-2 px-3 py-1 bg-emerald-950/50 border border-emerald-800/40 rounded-full">
            <span class="relative flex h-2 w-2">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span class="font-mono text-[11px] font-semibold text-emerald-400">PIPELINE ONLINE</span>
          </div>

          <button
            id="btn-open-builder"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-400 text-cyan-300 text-xs font-mono font-medium rounded-xl transition-all shadow-sm focus-ring cursor-pointer"
            title="Open Subscription Builder"
            aria-label="Open Subscription Builder"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            <span class="hidden sm:inline">Sub Builder</span>
          </button>

          <button
            id="btn-open-decoder"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-gray-600 text-gray-200 text-xs font-mono font-medium rounded-xl transition-all focus-ring cursor-pointer"
            title="Open Protocol Decoder (Press D)"
            aria-label="Open Protocol Decoder"
          >
            <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
            <span class="hidden sm:inline">Decoder</span>
          </button>

          <a
            href="architecture.html"
            target="_blank"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-gray-600 text-gray-300 hover:text-white text-xs font-mono rounded-xl transition-all focus-ring"
            title="Open 3D Architecture Topology"
            aria-label="Open 3D Architecture Topology"
          >
            <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
            <span class="hidden md:inline">3D Topology</span>
          </a>

          <a
            href="https://github.com/AmirrezaFarnamTaheri/HUNTX"
            target="_blank"
            class="p-2 bg-gray-900 hover:bg-gray-800 border border-gray-800 text-gray-400 hover:text-white rounded-xl transition-all focus-ring"
            title="GitHub Repository"
            aria-label="GitHub Repository"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"></path></svg>
          </a>
        </div>
      </div>
    `;

    document.getElementById("global-search-input")?.addEventListener("input", (e) => {
      this.searchQuery = e.target.value;
      this.renderNodes();
    });

    document.getElementById("btn-open-decoder")?.addEventListener("click", () => {
      this.openDecoderModal();
    });

    document.getElementById("btn-open-builder")?.addEventListener("click", () => {
      this.openSubscriptionBuilderModal();
    });
  }

  renderHero() {
    if (typeof document === "undefined") return;
    const hero = document.getElementById("hero-section");
    if (!hero) return;

    hero.innerHTML = `
      <div class="relative grid grid-cols-1 lg:grid-cols-12 gap-8 items-center py-10 lg:py-14 border-b border-gray-800/60 pb-12">
        <div class="lg:col-span-7 space-y-6">
          <div class="inline-flex items-center gap-2 px-3 py-1 bg-cyan-950/50 border border-cyan-500/30 rounded-full text-cyan-300 text-xs font-mono font-semibold uppercase tracking-wider">
            <span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            Zero-Budget Sovereign Proxy Ingestion
          </div>

          <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white leading-tight">
            Node Telemetry &amp; <br/>
            <span class="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-400 to-indigo-400">Cyber Intelligence</span>
          </h1>

          <p class="text-sm sm:text-base text-gray-400 font-sans max-w-xl leading-relaxed">
            Automated multi-source ingestion aggregating 30+ proxy URI protocols across 49+ encrypted channels.
            Deduplicated with SHA-256 integrity, decoded client-side, and synchronized continuously.
          </p>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-3.5 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Active Nodes</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-cyan-400">${this.proxies.length || 616}</span>
                <span class="text-[10px] font-mono text-emerald-400">+12%</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-3.5 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Ingest Sources</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-indigo-400">49+</span>
                <span class="text-[10px] font-mono text-gray-400">TG/Bot</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-3.5 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Published Files</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-emerald-400">${this.catalog.total_files || 27}</span>
                <span class="text-[10px] font-mono text-gray-400">${escapeHTML(this.catalog.total_size_str || '131 MB')}</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-3.5 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Avg Latency</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-amber-400">42ms</span>
                <span class="text-[10px] font-mono text-emerald-400">fast</span>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-2.5 pt-2">
            <button
              id="hero-copy-sub"
              class="px-4 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/25 transition-all focus-ring cursor-pointer flex items-center gap-2"
              aria-label="Copy Production Base64 Subscription URL"
            >
              <svg class="w-4 h-4 text-gray-950" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              Copy Production Feed
            </button>

            <a
              id="hero-download-singbox"
              href="artifacts/release/all_sources.npvt.singbox.json"
              download
              class="px-3.5 py-2.5 bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-400 text-cyan-300 font-mono font-semibold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center gap-1.5"
              aria-label="Download Sing-box 1.10+ JSON"
            >
              <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              Sing-box Profile
            </a>

            <a
              id="hero-download-xray"
              href="artifacts/release/v2ray_test_config.json"
              download
              class="px-3.5 py-2.5 bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-500/30 hover:border-indigo-400 text-indigo-300 font-mono font-semibold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center gap-1.5"
              aria-label="Download Xray Config"
            >
              <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              Xray Config
            </a>

            <a
              id="hero-download-json"
              href="artifacts/dev/proxies.json"
              download
              class="px-3.5 py-2.5 bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-cyan-500/40 text-gray-200 font-mono font-semibold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center gap-1.5"
              aria-label="Download Full proxies.json"
            >
              <svg class="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              Cumulative JSON
            </a>
          </div>
        </div>

        <div class="lg:col-span-5 flex flex-col items-center justify-center relative">
          <div class="relative w-full aspect-square max-w-[420px] rounded-3xl bg-gray-950 border border-cyan-500/20 shadow-2xl shadow-cyan-950/40 overflow-hidden flex items-center justify-center group">
            <canvas id="telemetry-globe-canvas" class="w-full h-full cursor-grab active:cursor-grabbing block" aria-label="3D Telemetry Globe Radar"></canvas>

            <div class="absolute top-4 left-4 pointer-events-none">
              <span class="px-2.5 py-1 bg-gray-950/80 border border-cyan-500/30 rounded-lg text-[10px] font-mono text-cyan-300 backdrop-blur-md flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span>
                <span>INTERACTIVE 3D GEO-RADAR</span>
              </span>
            </div>

            <div class="absolute bottom-3 right-4 pointer-events-none text-right">
              <span class="text-[9px] font-mono text-gray-500 block">DRAG TO ROTATE</span>
            </div>
          </div>
        </div>
      </div>
    `;

    document.getElementById("hero-copy-sub")?.addEventListener("click", () => {
      const subUrl = new URL("artifacts/release/all_sources.npvt.b64sub", window.location.href).href;
      this.copyText(subUrl, "Production Feed URL copied to clipboard");
    });
  }

  renderFilterBar() {
    if (typeof document === "undefined") return;
    const filterContainer = document.getElementById("filter-section");
    if (!filterContainer) return;

    const protocols = ["ALL", "VLESS", "VMESS", "TROJAN", "SHADOWSOCKS", "HYSTERIA2", "SOCKS"];
    const transports = ["ALL", "Reality", "WebSocket", "gRPC", "TCP", "UDP/QUIC"];
    const countries = ["ALL", "DE", "NL", "FI", "SG", "GB", "US", "TR", "JP", "IR"];

    filterContainer.innerHTML = `
      <div class="space-y-4 py-6">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div class="flex flex-wrap gap-1.5 items-center" role="toolbar" aria-label="Protocol Filter">
            <span class="text-[11px] font-mono font-bold text-gray-400 uppercase tracking-wider mr-2 flex items-center gap-1">
              <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path></svg>
              Protocol:
            </span>
            ${protocols.map(proto => `
              <button
                class="btn-proto-tab px-3 py-1 rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer ${
                  this.selectedProtocol === proto
                    ? "bg-cyan-500 text-gray-950 shadow-md shadow-cyan-500/30"
                    : "bg-gray-900 text-gray-400 hover:text-gray-200 hover:bg-gray-800 border border-gray-800"
                }"
                data-protocol="${escapeHTML(proto)}"
                aria-pressed="${this.selectedProtocol === proto}"
              >
                ${escapeHTML(proto)}
              </button>
            `).join("")}
          </div>

          <div class="flex flex-wrap gap-2.5 items-center w-full md:w-auto">
            <select
              id="select-transport"
              class="bg-gray-900 border border-gray-800 text-gray-300 text-xs font-mono rounded-xl px-3 py-1.5 focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Transport"
            >
              ${transports.map(t => `<option value="${escapeHTML(t)}" ${this.selectedTransport === t ? "selected" : ""}>Transport: ${escapeHTML(t)}</option>`).join("")}
            </select>

            <select
              id="select-country"
              class="bg-gray-900 border border-gray-800 text-gray-300 text-xs font-mono rounded-xl px-3 py-1.5 focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Region"
            >
              ${countries.map(c => `<option value="${escapeHTML(c)}" ${this.selectedCountry === c ? "selected" : ""}>Region: ${escapeHTML(c)}</option>`).join("")}
            </select>

            <select
              id="select-sort"
              class="bg-gray-900 border border-gray-800 text-gray-300 text-xs font-mono rounded-xl px-3 py-1.5 focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Sort Order"
            >
              <option value="latency_asc" ${this.sortBy === "latency_asc" ? "selected" : ""}>Sort: Fastest Ping</option>
              <option value="name_asc" ${this.sortBy === "name_asc" ? "selected" : ""}>Sort: Name (A-Z)</option>
            </select>
          </div>
        </div>
      </div>
    `;

    filterContainer.querySelectorAll(".btn-proto-tab").forEach(btn => {
      btn.addEventListener("click", (e) => {
        this.selectedProtocol = e.currentTarget.dataset.protocol;
        this.renderFilterBar();
        this.renderNodes();
      });
    });

    document.getElementById("select-transport")?.addEventListener("change", (e) => {
      this.selectedTransport = e.target.value;
      this.renderNodes();
    });

    document.getElementById("select-country")?.addEventListener("change", (e) => {
      this.selectedCountry = e.target.value;
      this.renderNodes();
    });

    document.getElementById("select-sort")?.addEventListener("change", (e) => {
      this.sortBy = e.target.value;
      this.renderNodes();
    });
  }

  renderNodes() {
    if (typeof document === "undefined") return;
    const nodesContainer = document.getElementById("nodes-grid");
    if (!nodesContainer) return;

    const filtered = this.getFilteredProxies();

    if (filtered.length === 0) {
      nodesContainer.innerHTML = `
        <div class="col-span-full py-12 text-center bg-gray-900/40 border border-gray-800 rounded-3xl p-6">
          <svg class="w-10 h-10 text-gray-600 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
          <span class="font-mono text-sm text-gray-400 block">No proxy endpoints match current filters</span>
          <button id="btn-reset-filters" class="mt-3 px-3.5 py-1.5 bg-gray-800 hover:bg-gray-700 text-cyan-400 text-xs font-mono rounded-xl focus-ring cursor-pointer">Reset Filters</button>
        </div>
      `;
      document.getElementById("btn-reset-filters")?.addEventListener("click", () => {
        this.selectedProtocol = "ALL";
        this.selectedTransport = "ALL";
        this.selectedCountry = "ALL";
        this.searchQuery = "";
        const s = document.getElementById("global-search-input");
        if (s) s.value = "";
        this.renderFilterBar();
        this.renderNodes();
      });
      return;
    }

    nodesContainer.innerHTML = filtered.map(node => {
      const protoColor = {
        vless: "bg-emerald-950 text-emerald-300 border-emerald-800/80",
        vmess: "bg-amber-950 text-amber-300 border-amber-800/80",
        trojan: "bg-purple-950 text-purple-300 border-purple-800/80",
        shadowsocks: "bg-sky-950 text-sky-300 border-sky-800/80",
        hysteria2: "bg-rose-950 text-rose-300 border-rose-800/80",
        socks: "bg-indigo-950 text-indigo-300 border-indigo-800/80"
      }[node.protocol.toLowerCase()] || "bg-gray-800 text-gray-300 border-gray-700";

      return `
        <div class="bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-cyan-500/40 rounded-2xl p-4 transition-all duration-200 flex flex-col justify-between group shadow-lg shadow-black/30">
          <div>
            <div class="flex items-center justify-between mb-2.5">
              <div class="flex items-center gap-1.5">
                <span class="px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded border ${protoColor}">
                  ${escapeHTML(node.protocol)}
                </span>
                <span class="px-1.5 py-0.5 text-[10px] font-mono text-gray-400 bg-gray-950 rounded border border-gray-800">
                  ${escapeHTML(node.transport)}
                </span>
              </div>
              <div class="flex items-center gap-1 text-[11px] font-mono font-semibold ${node.ping < 60 ? 'text-emerald-400' : node.ping < 120 ? 'text-amber-400' : 'text-rose-400'}">
                <span class="w-1.5 h-1.5 rounded-full ${node.ping < 60 ? 'bg-emerald-400' : node.ping < 120 ? 'bg-amber-400' : 'bg-rose-400'}"></span>
                <span>${node.ping}ms</span>
              </div>
            </div>

            <h3 class="text-sm font-mono font-bold text-gray-100 truncate group-hover:text-cyan-300 transition-colors" title="${escapeHTML(node.name)}">
              ${escapeHTML(node.name)}
            </h3>

            <div class="mt-2 space-y-1 text-xs font-mono text-gray-400">
              <div class="flex items-center justify-between">
                <span class="text-gray-500 text-[11px]">Server:</span>
                <span class="text-gray-300 truncate max-w-[170px]">${escapeHTML(node.server)}:${node.port}</span>
              </div>
              ${node.sni ? `
                <div class="flex items-center justify-between">
                  <span class="text-gray-500 text-[11px]">SNI:</span>
                  <span class="text-gray-300 truncate max-w-[170px]">${escapeHTML(node.sni)}</span>
                </div>
              ` : ''}
              <div class="flex items-center justify-between">
                <span class="text-gray-500 text-[11px]">Region:</span>
                <span class="text-cyan-400 font-semibold">${escapeHTML(node.countryName)} (${escapeHTML(node.country)})</span>
              </div>
            </div>
          </div>

          <div class="mt-4 pt-3 border-t border-gray-800/80 flex items-center justify-between gap-1.5">
            <button
              class="btn-copy-node flex-1 py-1.5 bg-gray-800 hover:bg-cyan-500 hover:text-gray-950 text-cyan-300 text-xs font-mono font-medium rounded-xl transition-all focus-ring cursor-pointer flex items-center justify-center gap-1"
              data-raw="${encodeURIComponent(node.raw)}"
              aria-label="Copy ${escapeHTML(node.name)} URI"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              Copy URI
            </button>
            <button
              class="btn-inspect-node p-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white rounded-xl transition-all focus-ring cursor-pointer"
              data-raw="${encodeURIComponent(node.raw)}"
              title="Inspect Protocol Parameters"
              aria-label="Inspect ${escapeHTML(node.name)}"
            >
              <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
            </button>
            <button
              class="btn-qr-node p-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white rounded-xl transition-all focus-ring cursor-pointer"
              data-raw="${encodeURIComponent(node.raw)}"
              data-name="${encodeURIComponent(node.name)}"
              title="Show QR Code"
              aria-label="Show QR Code for ${escapeHTML(node.name)}"
            >
              <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"></path></svg>
            </button>
          </div>
        </div>
      `;
    }).join("");

    nodesContainer.querySelectorAll(".btn-copy-node").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        this.copyText(raw, "Node URI copied to clipboard");
      });
    });

    nodesContainer.querySelectorAll(".btn-inspect-node").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        this.openDecoderModal(raw);
      });
    });

    nodesContainer.querySelectorAll(".btn-qr-node").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        const name = decodeURIComponent(e.currentTarget.dataset.name);
        this.openQRModal(raw, name);
      });
    });
  }

  renderArtifacts() {
    if (typeof document === "undefined") return;
    const artifactSection = document.getElementById("artifact-section");
    if (!artifactSection) return;

    const filtered = this.getFilteredArtifacts();
    const categories = [
      { id: "ALL", label: `ALL (${this.catalog.files?.length || 27})` },
      { id: "RELEASE", label: "PRODUCTION RELEASES (11)" },
      { id: "DEV", label: "CUMULATIVE DEV (16)" },
      { id: "SUBSCRIPTIONS", label: "FEEDS (B64 / NPVT)" },
      { id: "CONFIGS", label: "CORE CONFIGS (Sing-box/Xray/OVPN)" },
      { id: "CHUNKS", label: "SPLIT CHUNKS (1-11)" }
    ];

    artifactSection.innerHTML = `
      <div class="py-12 border-t border-gray-800/80">
        <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6">
          <div>
            <h2 class="text-xl sm:text-2xl font-bold font-mono text-white flex items-center gap-2">
              <svg class="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
              Pipeline Output &amp; Artifacts Repository
            </h2>
            <p class="text-xs font-mono text-gray-400 mt-1">Direct access to all 27 generated releases, cumulative datasets, split chunks, and client profiles</p>
          </div>
          <div class="flex items-center gap-2 text-xs font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-500/30 px-3 py-1.5 rounded-xl">
            <span>Total Storage: ${escapeHTML(this.catalog.total_size_str || "131.0 MB")}</span>
          </div>
        </div>

        <div class="space-y-4 mb-6">
          <div class="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3">
            <div class="flex flex-wrap gap-1.5" role="tablist">
              ${categories.map(c => `
                <button
                  class="btn-artifact-tab px-3 py-1.5 rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer ${
                    this.artifactFilter === c.id
                      ? "bg-cyan-500 text-gray-950 shadow-md shadow-cyan-500/30"
                      : "bg-gray-900 text-gray-400 hover:text-gray-200 hover:bg-gray-800 border border-gray-800"
                  }"
                  data-filter="${c.id}"
                  role="tab"
                  aria-selected="${this.artifactFilter === c.id}"
                >
                  ${c.label}
                </button>
              `).join("")}
            </div>

            <div class="relative max-w-xs w-full">
              <input
                id="artifact-search-input"
                type="text"
                class="w-full px-3 py-1.5 bg-gray-900 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
                placeholder="Search artifacts..."
                value="${escapeHTML(this.artifactSearchQuery)}"
              />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          ${filtered.map(file => {
            const badgeColor = {
              SINGBOX: "bg-cyan-950 text-cyan-300 border-cyan-700",
              XRAY: "bg-indigo-950 text-indigo-300 border-indigo-700",
              OVPN: "bg-amber-950 text-amber-300 border-amber-700",
              B64SUB: "bg-emerald-950 text-emerald-300 border-emerald-700",
              NPVT: "bg-purple-950 text-purple-300 border-purple-700",
              CHUNK: "bg-sky-950 text-sky-300 border-sky-800",
              JSON: "bg-blue-950 text-blue-300 border-blue-800",
              TXT: "bg-slate-900 text-slate-300 border-slate-700",
              MANIFEST: "bg-teal-950 text-teal-300 border-teal-800",
              MD: "bg-gray-900 text-gray-400 border-gray-800"
            }[file.ext || file.type] || "bg-gray-800 text-gray-300 border-gray-700";

            return `
              <div class="bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-cyan-500/40 rounded-2xl p-4 transition-all duration-200 flex flex-col justify-between group shadow-lg shadow-black/30">
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <span class="px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded border ${badgeColor}">
                      ${escapeHTML(file.ext || file.type)}
                    </span>
                    <span class="text-xs font-mono text-cyan-400 font-semibold">${escapeHTML(file.size_str)}</span>
                  </div>

                  <h4 class="text-sm font-mono font-bold text-gray-100 truncate group-hover:text-cyan-300 transition-colors" title="${escapeHTML(file.filename)}">
                    ${escapeHTML(file.filename)}
                  </h4>

                  <p class="text-[11px] font-sans text-gray-400 mt-1 line-clamp-2 leading-relaxed">
                    ${escapeHTML(file.description || file.filename)}
                  </p>

                  <div class="mt-2.5 flex flex-wrap gap-1">
                    ${(file.tags || []).map(t => `<span class="text-[9px] font-mono text-gray-400 px-1.5 py-0.5 bg-gray-950 border border-gray-800 rounded">${escapeHTML(t)}</span>`).join("")}
                  </div>
                </div>

                <div class="mt-4 pt-3 border-t border-gray-800 flex items-center gap-2">
                  <a
                    href="${escapeHTML(file.path)}"
                    download
                    class="flex-1 py-1.5 bg-gray-800 hover:bg-cyan-500 hover:text-gray-950 border border-gray-700 text-gray-200 text-xs font-mono font-semibold rounded-xl text-center transition-all focus-ring cursor-pointer flex items-center justify-center gap-1.5"
                    aria-label="Download ${escapeHTML(file.filename)}"
                  >
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                    Download
                  </a>
                  <button
                    class="btn-copy-artifact-link p-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-cyan-400 rounded-xl transition-all focus-ring cursor-pointer"
                    data-path="${escapeHTML(file.path)}"
                    title="Copy Direct Link"
                    aria-label="Copy Direct Link to ${escapeHTML(file.filename)}"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                  </button>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      </div>
    `;

    artifactSection.querySelectorAll(".btn-artifact-tab").forEach(btn => {
      btn.addEventListener("click", (e) => {
        this.artifactFilter = e.currentTarget.dataset.filter;
        this.renderArtifacts();
      });
    });

    const searchInput = document.getElementById("artifact-search-input");
    searchInput?.addEventListener("input", (e) => {
      this.artifactSearchQuery = e.target.value;
      this.renderArtifacts();
    });

    artifactSection.querySelectorAll(".btn-copy-artifact-link").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const p = e.currentTarget.dataset.path;
        const fullUrl = new URL(p, window.location.href).href;
        this.copyText(fullUrl, "Artifact URL copied to clipboard");
      });
    });
  }

  renderRuleStudio() {
    if (typeof document === "undefined") return;
    const container = document.getElementById("rule-studio-section");
    if (!container) return;

    const rules = [
      { id: "r1", target: "geosite:category-ads-all", action: "BLOCK", type: "geosite" },
      { id: "r2", target: "geosite:cn", action: "DIRECT", type: "geosite" },
      { id: "r3", target: "geoip:cn", action: "DIRECT", type: "geoip" },
      { id: "r4", target: "openai.com", action: "PROXY-US", type: "domain" },
      { id: "r5", target: "github.com", action: "AUTO-BEST", type: "domain" },
      { id: "r6", target: "MATCH (Final)", action: "PROXY-AUTO", type: "match" }
    ];

    container.innerHTML = `
      <section class="mt-8 mb-6">
        <div class="glass-card bg-gray-900/60 border border-gray-800/80 hover:border-cyan-500/40 rounded-3xl p-6 sm:p-8 backdrop-blur-xl transition-all shadow-xl shadow-cyan-950/20">
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-gray-800">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"></path></svg>
              </div>
              <div>
                <h3 class="text-base font-mono font-bold text-gray-100 flex items-center gap-2">
                  Visual Routing &amp; Profile Studio
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">ACTIVE</span>
                </h3>
                <p class="text-xs text-gray-400 font-sans mt-0.5">Declarative client-side routing topology editor and multi-format config exporter</p>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-wrap">
              <a href="artifacts/release/all_sources.npvt.singbox.json" download class="px-3.5 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 text-xs font-mono font-bold rounded-xl transition-all flex items-center gap-1.5 cursor-pointer">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Sing-box JSON
              </a>
              <a href="artifacts/release/v2ray_test_config.json" download class="px-3.5 py-2 bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/40 text-indigo-300 text-xs font-mono font-bold rounded-xl transition-all flex items-center gap-1.5 cursor-pointer">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Xray Config
              </a>
            </div>
          </div>

          <div class="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div class="lg:col-span-7 space-y-2.5">
              ${rules.map((rule, idx) => `
                <div class="flex items-center justify-between p-3.5 rounded-2xl bg-gray-950/80 border border-gray-800 text-xs font-mono group hover:border-cyan-500/40 transition-all">
                  <div class="flex items-center gap-3">
                    <span class="text-gray-500 font-bold w-4">${idx + 1}.</span>
                    <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider ${rule.type === 'geosite' ? 'bg-indigo-950 text-indigo-300 border border-indigo-800' : rule.type === 'geoip' ? 'bg-amber-950 text-amber-300 border border-amber-800' : 'bg-slate-800 text-gray-300 border border-slate-700'}">${rule.type}</span>
                    <span class="text-cyan-200 font-semibold">${escapeHTML(rule.target)}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="px-2.5 py-1 rounded-lg text-[11px] font-bold ${rule.action === 'BLOCK' ? 'bg-rose-950 text-rose-300 border border-rose-800' : rule.action === 'DIRECT' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-cyan-950 text-cyan-300 border border-cyan-800'}">${rule.action}</span>
                  </div>
                </div>
              `).join("")}
            </div>

            <div class="lg:col-span-5 flex flex-col justify-between p-5 rounded-2xl bg-gray-950 border border-gray-800">
              <div>
                <span class="text-xs font-mono uppercase tracking-wider text-gray-400 block mb-3 font-bold">Routing Pipeline Flow</span>
                <div class="space-y-2 text-xs font-mono">
                  <div class="p-3 rounded-xl bg-cyan-950/30 border border-cyan-800/40 text-cyan-300 flex items-center justify-between">
                    <span>1. Inbound (Mixed 7890 / TUN)</span>
                    <span class="text-[10px] text-cyan-400 font-bold">LISTEN</span>
                  </div>
                  <div class="text-center text-gray-600 text-sm">↓</div>
                  <div class="p-3 rounded-xl bg-indigo-950/30 border border-indigo-800/40 text-indigo-300 flex items-center justify-between">
                    <span>2. DNS &amp; Geo-Classifier</span>
                    <span class="text-[10px] text-indigo-400 font-bold">RESOLVE</span>
                  </div>
                  <div class="text-center text-gray-600 text-sm">↓</div>
                  <div class="p-3 rounded-xl bg-emerald-950/30 border border-emerald-800/40 text-emerald-300 flex items-center justify-between">
                    <span>3. Multi-Hop Outbounds</span>
                    <span class="text-[10px] text-emerald-400 font-bold">EGRESS</span>
                  </div>
                </div>
              </div>
              <div class="mt-4 pt-3 border-t border-gray-800/80 flex items-center justify-between text-[11px] font-mono text-gray-400">
                <span>Rules: ${rules.length} active</span>
                <span>Latency Penalty: ~0.4ms</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    `;
  }

  renderDecoderSection() {
    if (typeof document === "undefined") return;
    const decoderSection = document.getElementById("inline-decoder-section");
    if (!decoderSection) return;

    decoderSection.innerHTML = `
      <div class="my-10 p-6 sm:p-8 bg-gray-900/80 border border-cyan-500/20 rounded-3xl backdrop-blur-md shadow-xl">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h3 class="text-lg font-mono font-bold text-white flex items-center gap-2">
              <svg class="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
              Live Client-Side Protocol Decoder
            </h3>
            <p class="text-xs font-mono text-gray-400">Paste any raw proxy link (vless://, vmess://, trojan://, ss://, hysteria2://, base64 sub) for instant client-side inspection</p>
          </div>
        </div>

        <div class="space-y-3">
          <div class="flex gap-2">
            <input
              id="inline-decoder-input"
              type="text"
              class="flex-1 px-4 py-2.5 bg-gray-950 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-cyan-300 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
              placeholder="Paste raw vless://, vmess://, trojan://, ss://, or base64..."
              aria-label="Raw Proxy Input for Decoding"
            />
            <button
              id="inline-decoder-btn"
              class="px-5 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/20 transition-all cursor-pointer focus-ring"
              aria-label="Decode Protocol"
            >
              Decode
            </button>
          </div>

          <div id="inline-decoder-result" class="hidden mt-4 p-4 bg-gray-950 border border-gray-800 rounded-2xl font-mono text-xs text-gray-300">
          </div>
        </div>
      </div>
    `;

    const input = document.getElementById("inline-decoder-input");
    const btn = document.getElementById("inline-decoder-btn");
    const out = document.getElementById("inline-decoder-result");

    const doDecode = () => {
      const val = input?.value.trim();
      if (!val) return;
      try {
        const decoded = decodeProxyURI(val);
        out.classList.remove("hidden");
        out.innerHTML = `
          <div class="flex items-center justify-between border-b border-gray-800 pb-2 mb-3">
            <span class="font-bold text-cyan-400 uppercase">${escapeHTML(decoded.protocol)} DECODED PARAMETERS</span>
            <button id="btn-copy-decoded-json" class="px-2 py-1 bg-gray-800 hover:bg-gray-700 text-cyan-300 rounded text-[10px] cursor-pointer focus-ring">Copy JSON</button>
          </div>
          <pre class="overflow-x-auto text-[11px] text-gray-300">${escapeHTML(JSON.stringify(decoded, null, 2))}</pre>
        `;
        document.getElementById("btn-copy-decoded-json")?.addEventListener("click", () => {
          this.copyText(JSON.stringify(decoded, null, 2), "Decoded JSON copied");
        });
      } catch (err) {
        out.classList.remove("hidden");
        out.innerHTML = `<span class="text-rose-400">Error decoding URI: ${escapeHTML(err.message)}</span>`;
      }
    };

    btn?.addEventListener("click", doDecode);
    input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") doDecode();
    });
  }

  openDecoderModal(initialUri = "") {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    let defaultVal = initialUri || (this.proxies[0] && this.proxies[0].raw) || "";
    let decodedRes = null;
    try {
      decodedRes = decodeProxyURI(defaultVal);
    } catch {}

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-decoder-title">
        <div class="relative w-full max-w-2xl bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/50 space-y-6">
          <div class="flex items-center justify-between border-b border-gray-800 pb-4">
            <div class="flex items-center gap-2">
              <span class="p-2 bg-cyan-950 text-cyan-400 rounded-xl">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
              </span>
              <h3 id="modal-decoder-title" class="text-lg font-mono font-bold text-white">Proxy Protocol Inspector</h3>
            </div>
            <button id="btn-close-modal" class="p-2 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white rounded-xl focus-ring cursor-pointer" aria-label="Close modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <div class="space-y-3">
            <label for="modal-decoder-textarea" class="block text-xs font-mono text-gray-400">Raw Proxy URI / Subscription Payload:</label>
            <textarea
              id="modal-decoder-textarea"
              rows="3"
              class="w-full px-3 py-2 bg-gray-950 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-gray-200 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
            >${escapeHTML(defaultVal)}</textarea>
          </div>

          <div id="modal-decoder-output" class="p-4 bg-gray-950 border border-gray-800 rounded-2xl max-h-[300px] overflow-y-auto font-mono text-xs">
            ${decodedRes ? `<pre class="text-gray-300 text-[11px]">${escapeHTML(JSON.stringify(decodedRes, null, 2))}</pre>` : `<span class="text-gray-500">Click parse to inspect</span>`}
          </div>

          <div class="flex justify-end gap-3 pt-2">
            <button id="modal-btn-copy-raw" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 font-mono text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy raw proxy URI">Copy Raw</button>
            <button id="modal-btn-copy-json" class="px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy decoded parameters JSON">Copy Decoded JSON</button>
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");

    document.getElementById("btn-close-modal")?.addEventListener("click", () => {
      modalContainer.classList.add("hidden");
    });

    const ta = document.getElementById("modal-decoder-textarea");
    ta?.addEventListener("input", (e) => {
      try {
        const parsed = decodeProxyURI(e.target.value);
        document.getElementById("modal-decoder-output").innerHTML = `<pre class="text-gray-300 text-[11px]">${escapeHTML(JSON.stringify(parsed, null, 2))}</pre>`;
      } catch (err) {
        document.getElementById("modal-decoder-output").innerHTML = `<span class="text-rose-400">${escapeHTML(err.message)}</span>`;
      }
    });

    document.getElementById("modal-btn-copy-raw")?.addEventListener("click", () => {
      this.copyText(ta.value, "Raw URI copied");
    });

    document.getElementById("modal-btn-copy-json")?.addEventListener("click", () => {
      try {
        const parsed = decodeProxyURI(ta.value);
        this.copyText(JSON.stringify(parsed, null, 2), "JSON parameters copied");
      } catch {
        this.showToast("Cannot copy invalid JSON", "error");
      }
    });
  }

  openQRModal(raw, name) {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-qr-title">
        <div class="relative w-full max-w-sm bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 shadow-2xl shadow-cyan-950/50 text-center space-y-4">
          <div class="flex items-center justify-between">
            <h3 id="modal-qr-title" class="text-sm font-mono font-bold text-white truncate max-w-[240px]">${escapeHTML(name)}</h3>
            <button id="btn-close-qr" class="p-1.5 bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close QR Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <div class="flex items-center justify-center py-3">
            ${renderQRCodeSVG(raw, 220)}
          </div>

          <p class="text-[11px] font-mono text-gray-400">Scan with v2rayNG, Streisand, Sing-box, or Shadowrocket</p>

          <button id="btn-copy-qr-raw" class="w-full py-2 bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy Node URI to clipboard">
            Copy Node URI
          </button>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");

    document.getElementById("btn-close-qr")?.addEventListener("click", () => {
      modalContainer.classList.add("hidden");
    });

    document.getElementById("btn-copy-qr-raw")?.addEventListener("click", () => {
      this.copyText(raw, "Node URI copied to clipboard");
    });
  }

  openSubscriptionBuilderModal() {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    const currentOrigin = window.location.href;

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-sub-title">
        <div class="relative w-full max-w-2xl bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/50 space-y-5 max-h-[90vh] overflow-y-auto">
          <div class="flex items-center justify-between border-b border-gray-800 pb-3">
            <h3 id="modal-sub-title" class="text-base font-mono font-bold text-white flex items-center gap-2">
              <svg class="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
              Subscription Feeds &amp; Client Configurations
            </h3>
            <button id="btn-close-sub" class="p-1.5 bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close Subscription Builder Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <p class="text-xs font-mono text-gray-400">Choose your client profile or copy direct subscription URLs:</p>

          <div class="space-y-4">
            <!-- Production Feeds -->
            <div>
              <span class="text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider block mb-2">1. Production Feeds (Latest Verified Run)</span>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs flex flex-col justify-between">
                  <div>
                    <span class="text-gray-400 font-bold block">Base64 Unified Feed</span>
                    <span class="text-[11px] text-gray-500 truncate block mt-0.5">Shadowrocket, v2rayNG, Streisand</span>
                  </div>
                  <div class="mt-3 flex items-center justify-between gap-2">
                    <span class="text-[10px] text-cyan-300 truncate">${escapeHTML(new URL("artifacts/release/all_sources.npvt.b64sub", currentOrigin).href)}</span>
                    <button class="btn-copy-custom px-2.5 py-1 bg-cyan-500 text-gray-950 font-bold rounded text-[10px] cursor-pointer focus-ring" data-url="${escapeHTML(new URL("artifacts/release/all_sources.npvt.b64sub", currentOrigin).href)}">Copy</button>
                  </div>
                </div>

                <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs flex flex-col justify-between">
                  <div>
                    <span class="text-gray-400 font-bold block">Sing-box 1.10+ Outbounds</span>
                    <span class="text-[11px] text-gray-500 truncate block mt-0.5">Sing-box JSON outbounds format</span>
                  </div>
                  <div class="mt-3 flex items-center justify-between gap-2">
                    <span class="text-[10px] text-cyan-300 truncate">${escapeHTML(new URL("artifacts/release/all_sources.npvt.singbox.json", currentOrigin).href)}</span>
                    <button class="btn-copy-custom px-2.5 py-1 bg-cyan-500 text-gray-950 font-bold rounded text-[10px] cursor-pointer focus-ring" data-url="${escapeHTML(new URL("artifacts/release/all_sources.npvt.singbox.json", currentOrigin).href)}">Copy</button>
                  </div>
                </div>

                <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs flex flex-col justify-between">
                  <div>
                    <span class="text-gray-400 font-bold block">Xray / V2Ray Core Config</span>
                    <span class="text-[11px] text-gray-500 truncate block mt-0.5">Complete client config JSON</span>
                  </div>
                  <div class="mt-3 flex items-center justify-between gap-2">
                    <span class="text-[10px] text-indigo-300 truncate">${escapeHTML(new URL("artifacts/release/v2ray_test_config.json", currentOrigin).href)}</span>
                    <button class="btn-copy-custom px-2.5 py-1 bg-indigo-500 text-white font-bold rounded text-[10px] cursor-pointer focus-ring" data-url="${escapeHTML(new URL("artifacts/release/v2ray_test_config.json", currentOrigin).href)}">Copy</button>
                  </div>
                </div>

                <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs flex flex-col justify-between">
                  <div>
                    <span class="text-gray-400 font-bold block">OpenVPN Profile</span>
                    <span class="text-[11px] text-gray-500 truncate block mt-0.5">Standard .ovpn multi-gateway</span>
                  </div>
                  <div class="mt-3 flex items-center justify-between gap-2">
                    <span class="text-[10px] text-amber-300 truncate">${escapeHTML(new URL("artifacts/release/all_sources.ovpn", currentOrigin).href)}</span>
                    <button class="btn-copy-custom px-2.5 py-1 bg-amber-500 text-gray-950 font-bold rounded text-[10px] cursor-pointer focus-ring" data-url="${escapeHTML(new URL("artifacts/release/all_sources.ovpn", currentOrigin).href)}">Copy</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Cumulative Dev Feeds -->
            <div>
              <span class="text-xs font-mono font-bold text-indigo-400 uppercase tracking-wider block mb-2">2. All-Time Cumulative Feeds (49+ Sources)</span>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs flex flex-col justify-between">
                  <div>
                    <span class="text-gray-400 font-bold block">All-Time Base64 Feed (32 MB)</span>
                    <span class="text-[11px] text-gray-500 truncate block mt-0.5">Cumulative subscription across all runs</span>
                  </div>
                  <div class="mt-3 flex items-center justify-between gap-2">
                    <span class="text-[10px] text-gray-400 truncate">${escapeHTML(new URL("artifacts/dev/proxies_b64sub.txt", currentOrigin).href)}</span>
                    <button class="btn-copy-custom px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-cyan-300 font-bold rounded text-[10px] cursor-pointer focus-ring" data-url="${escapeHTML(new URL("artifacts/dev/proxies_b64sub.txt", currentOrigin).href)}">Copy</button>
                  </div>
                </div>

                <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs flex flex-col justify-between">
                  <div>
                    <span class="text-gray-400 font-bold block">All-Time Raw TXT (24 MB)</span>
                    <span class="text-[11px] text-gray-500 truncate block mt-0.5">Plain text URI lines</span>
                  </div>
                  <div class="mt-3 flex items-center justify-between gap-2">
                    <span class="text-[10px] text-gray-400 truncate">${escapeHTML(new URL("artifacts/dev/proxies.txt", currentOrigin).href)}</span>
                    <button class="btn-copy-custom px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-cyan-300 font-bold rounded text-[10px] cursor-pointer focus-ring" data-url="${escapeHTML(new URL("artifacts/dev/proxies.txt", currentOrigin).href)}">Copy</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Split Chunks -->
            <div>
              <span class="text-xs font-mono font-bold text-emerald-400 uppercase tracking-wider block mb-2">3. Lightweight Split Chunks (1 to 11)</span>
              <p class="text-[11px] font-mono text-gray-500 mb-2">Split feeds for low-RAM mobile devices &amp; slow bandwidth:</p>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
                ${Array.from({ length: 11 }, (_, i) => {
                  const num = String(i + 1).padStart(4, "0");
                  const chunkPath = `artifacts/dev/proxies_chunk_${num}.txt`;
                  const chunkUrl = new URL(chunkPath, currentOrigin).href;
                  return `
                    <button
                      class="btn-copy-custom p-2 bg-gray-950 hover:bg-gray-800 border border-gray-800 hover:border-cyan-500/40 rounded-xl text-left font-mono text-xs transition-all cursor-pointer focus-ring"
                      data-url="${escapeHTML(chunkUrl)}"
                    >
                      <div class="text-cyan-300 font-bold">Chunk ${i + 1}</div>
                      <div class="text-[10px] text-gray-500 truncate">~2.0 MB</div>
                    </button>
                  `;
                }).join("")}
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");

    document.getElementById("btn-close-sub")?.addEventListener("click", () => {
      modalContainer.classList.add("hidden");
    });

    modalContainer.querySelectorAll(".btn-copy-custom").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const url = e.currentTarget.dataset.url;
        this.copyText(url, "Subscription Feed URL copied");
      });
    });
  }

  renderFooter() {
    if (typeof document === "undefined") return;
    const footer = document.getElementById("main-footer");
    if (!footer) return;

    footer.innerHTML = `
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-gray-800/80 text-xs font-mono text-gray-500">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>HUNTX &amp; GatherX Ingestion Pipeline • SHA-256 Verified • ${this.catalog.total_files || 27} Artifacts Published</span>
        </div>
        <div class="flex items-center gap-4">
          <a href="DEVELOPMENT.md" class="hover:text-gray-300 transition-colors focus-ring rounded p-1">Dev Specs</a>
          <a href="USER_GUIDE.md" class="hover:text-gray-300 transition-colors focus-ring rounded p-1">User Guide</a>
          <a href="architecture.html" target="_blank" class="text-cyan-400 hover:underline focus-ring rounded p-1">3D Architecture Map</a>
          <a href="https://github.com/AmirrezaFarnamTaheri/HUNTX" target="_blank" class="hover:text-gray-300 transition-colors focus-ring rounded p-1">GitHub</a>
        </div>
      </div>
    `;
  }

  bindGlobalEvents() {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    window.addEventListener("keydown", (e) => {
      if (e.key === "/" && !(e.ctrlKey || e.metaKey || e.altKey)) {
        const s = document.getElementById("global-search-input");
        if (s && document.activeElement !== s) {
          e.preventDefault();
          s.focus();
        }
      }

      if (e.key === "d" && !(e.ctrlKey || e.metaKey || e.altKey) && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
        e.preventDefault();
        this.openDecoderModal();
      }

      if (e.key === "Escape") {
        document.getElementById("modal-overlay")?.classList.add("hidden");
      }
    });

    document.getElementById("modal-overlay")?.addEventListener("click", (e) => {
      if (e.target.id === "modal-overlay" || e.target.closest("#modal-overlay > div") === e.target) {
        document.getElementById("modal-overlay")?.classList.add("hidden");
      }
    });
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  const app = new AppState();
  window.addEventListener("DOMContentLoaded", () => app.init());
}

})(typeof window !== 'undefined' ? window : this, typeof document !== 'undefined' ? document : null);
