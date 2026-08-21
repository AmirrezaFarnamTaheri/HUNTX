# HUNTX C4 Architecture Specification

This document provides a formal **C4 Model** architectural description of **HUNTX (GatherX)**, covering Context (Level 1), Container (Level 2), Component (Level 3), and Code/Data Flow (Level 4).

---

## 1. Level 1: System Context Diagram

The System Context diagram illustrates how HUNTX interacts with external proxy sources, automated CI/CD runners, and end-user client applications across the open web.

```mermaid
C4Context
    title System Context Diagram for HUNTX (GatherX)

    Person(user, "Proxy Consumer / Network Engineer", "Searches, filters, inspects, and downloads verified proxy configs via web UI or subscription URLs.")
    Person(admin, "DevOps / Core Maintainer", "Monitors pipeline health, tunes channel feeds, and inspects release integrity.")

    Enterprise_Boundary(b0, "HUNTX Ecosystem") {
        System(huntx, "HUNTX Node Intelligence Platform", "Aggregates, decodes, benchmarks, deduplicates, and publishes sovereign proxy endpoints.")
    }

    System_Ext(telegram, "Encrypted TG Channels & Bots", "Upstream raw proxy feeds, subscription channels, and bulletin broadcasts.")
    System_Ext(github_ci, "GitHub Actions CI/CD", "Automated scheduled ingestion runners (Cron/Workflow Dispatch).")
    System_Ext(clients, "Proxy Clients (v2rayNG, Sing-box, Clash, Shadowrocket)", "Fetches Base64 subscription URLs and connects via configured outbound nodes.")
    System_Ext(pages, "GitHub Pages CDN", "Serves static web assets, 3D telemetry radar, and published JSON/TXT artifacts.")

    Rel(admin, huntx, "Configures sources and inspects health via", "CLI / Config YAML")
    Rel(user, pages, "Views live nodes, inspects URI parameters, and generates QR codes via", "HTTPS")
    Rel(user, huntx, "Copies unified subscription URLs", "HTTPS")
    Rel(huntx, telegram, "Ingests raw protocol text and subscription blobs from", "MTProto / Bot API / Scraping")
    Rel(github_ci, huntx, "Triggers ingestion, geo-routing, and verification pipeline in", "Go 1.24 Runtime")
    Rel(huntx, pages, "Publishes verified proxies.json, proxies.txt, and catalog manifest to", "Git Push / HTTPS")
    Rel(clients, pages, "Pulls base64 subscription feed from", "HTTPS")
```

### Personas & Trust Boundaries
- **Proxy Consumer**: Untrusted external client querying the public web UI. Data rendered in the browser is strictly sanitized to prevent XSS.
- **Upstream Channels**: Untrusted external sources. Every ingested URI is treated as malicious until validated, sanitized, and parsed through strict regex/URL grammars.
- **GitHub Actions Runner**: Trusted execution environment executing Go binaries to generate immutable, SHA-256 verified artifact bundles.

---

## 2. Level 2: Container Diagram

The Container diagram zooms into the HUNTX boundary, detailing the runtime units, data stores, and static delivery containers.

```mermaid
C4Container
    title Container Diagram for HUNTX

    Person(user, "User / Proxy Client", "Accesses web dashboard or pulls subscription feeds.")
    
    System_Boundary(c1, "HUNTX Platform Containers") {
        Container(frontend, "Telemetry Web SPA", "HTML5, Vanilla ES Modules, Canvas 3D, Tailwind CSS", "Provides zero-dependency interactive 3D Geo-Radar, client-side protocol decoder, and QR code generator.")
        
        Container(engine, "HUNTX Engine Daemon", "Go (cmd/huntx-engine)", "High-throughput stream parser, benchmark tester, deduplicator, geo-routing engine, and healing daemon.")
        
        Container(tools, "HUNTX CLI Tools", "Go (cmd/huntx-tools)", "Operator utilities for catalog generation, output verification, and runtime manifest validation.")
        
        ContainerDb(artifacts, "Artifact Store & Manifests", "Git Tree / Flat Files (JSON/TXT)", "Stores proxies.json, proxies.txt, proxies_b64sub.txt, and SHA-256 catalog.json.")
    }

    System_Ext(upstream, "Upstream Sources (TG, Subscriptions, Pastebins)", "External proxy streams.")
    System_Ext(ghpages, "GitHub Pages Host", "Static site and asset CDN hosting.")

    Rel(user, frontend, "Interacts with", "HTTPS / Local file://")
    Rel(user, artifacts, "Downloads raw subscription from", "HTTPS")
    Rel(frontend, artifacts, "Fetches catalog.json & proxies.json from", "Fetch API (with local fallback)")
    Rel(engine, upstream, "Polls & streams proxy payloads from", "TCP / HTTPS / MTProto")
    Rel(engine, artifacts, "Writes verified, deduplicated proxy sets to", "Disk / File I/O")
    Rel(tools, artifacts, "Calculates SHA-256 checksums & updates catalog.json in", "Disk / File I/O")
    Rel(artifacts, ghpages, "Deployed to", "GitHub Pages Deploy Step")
```

### Container Specifications
1. **Frontend Telemetry SPA (`docs/`)**:
   - Zero external runtime dependencies (100% offline and `file:///` compliant).
   - High-performance 2D/3D Canvas engine rendering Fibonacci sphere radar.
   - Client-side decoder supporting VLESS Reality, VMess Base64 JSON, Trojan TLS, Shadowsocks, and Hysteria2.
2. **HUNTX Engine Daemon (`cmd/huntx-engine`)**:
   - Concurrency-safe Go pipeline processing thousands of proxy URIs per second.
   - GeoRoute Engine (`georoute`) mapping IP/domain endpoints to ISO-3166 alpha-2 country codes.
   - Stream Parser (`stream`) with automatic protocol detection and normalization.
   - Healing Daemon (`healing`) for proactive node recovery and dead-node pruning.
3. **Artifact Store (`docs/artifacts/dev/` & `data/artifacts`)**:
   - Flat-file storage model optimized for Git LFS/Pages caching and instant CDN delivery.

---

## 3. Level 3: Component Diagram

### 3.1 Backend: HUNTX Go Engine Components

```mermaid
C4Component
    title Component Diagram — HUNTX Engine (Go)

    Container_Boundary(engine_boundary, "HUNTX Engine (cmd/huntx-engine)") {
        Component(main, "Engine Entrypoint", "main.go", "CLI argument parser, worker pool coordinator, and lifecycle manager.")
        Component(stream_parser, "Stream Parser", "stream/parser.go", "Tokenizes raw input streams, strips ANSI/metadata, and isolates URI payloads.")
        Component(internal_parse, "Protocol Parser", "internal/parse/parse.go", "Grammar-based parser for VLESS, VMess, Trojan, SS, and Hysteria2 URIs.")
        Component(georoute, "GeoRoute Engine", "georoute/engine.go", "Performs IP/CIDR/GeoIP lookups and attaches country tags.")
        Component(benchmarker, "Benchmark Runner", "benchmark/benchmarker.go", "Measures TCP handshake, TLS negotiation latency, and ping jitter.")
        Component(healing, "Healing Daemon", "healing/daemon.go", "Monitors node degradation and attempts fallback reconnects.")
    }

    Rel(main, stream_parser, "Feeds raw stream to")
    Rel(stream_parser, internal_parse, "Passes isolated URIs to")
    Rel(internal_parse, georoute, "Decorates nodes with geo-metadata via")
    Rel(internal_parse, benchmarker, "Submits parsed nodes for latency benchmarking to")
    Rel(benchmarker, healing, "Reports node health metrics to")
```

### 3.2 Frontend: Telemetry SPA Components

```mermaid
C4Component
    title Component Diagram — Telemetry SPA (docs/assets/js/)

    Container_Boundary(spa_boundary, "Frontend SPA (assets/js/)") {
        Component(app_state, "AppState Controller", "app.js", "Central reactive state store, theme manager, and DOM event coordinator.")
        Component(globe_radar, "3D Telemetry Radar", "globe.js", "Fibonacci sphere projection, RAF loop with visibilitychange battery saver.")
        Component(protocol_decoder, "Protocol Decoder", "decoder.js", "Pure JS parser for VLESS Reality, VMess, Trojan, SS, Hy2, and Base64 subs.")
        Component(qr_generator, "QR Code Matrix Engine", "qrcode.js", "Pure SVG vector QR matrix generator with finder patterns.")
        Component(data_catalog, "Data Catalog & Hubs", "data.js", "Telemetry hubs, fallback proxy matrices, and fallback catalog data.")
    }

    Rel(app_state, data_catalog, "Initializes default state & coordinates from")
    Rel(app_state, globe_radar, "Instantiates and receives node selection events from")
    Rel(app_state, protocol_decoder, "Invokes for modal inspections & live decoding via")
    Rel(app_state, qr_generator, "Requests inline SVG QR markup from")
```

---

## 4. Level 4: Code & Data Flow Diagram

The diagram below traces the end-to-end lifecycle of a proxy URI from raw ingest to client rendering:

```mermaid
sequenceDiagram
    autonumber
    participant Source as Upstream TG/Bot Channel
    participant Ingest as Go Stream Parser
    participant Parser as Protocol Parser (internal/parse)
    participant Bench as Benchmarker & GeoRoute
    participant Disk as Artifact Store (proxies.json)
    participant UI as Frontend AppState (app.js)
    participant Canvas as 3D Globe Radar (globe.js)
    participant Client as End-User / Proxy App

    Source->>Ingest: Stream raw text / Base64 chunks
    Ingest->>Parser: Extract protocol URIs (vless://, vmess://, etc.)
    Parser->>Bench: Validate parameters, extract SNI & port
    Bench->>Bench: Measure TCP/TLS latency & resolve GeoIP
    Bench->>Disk: Deduplicate via SHA-256 hash and write artifacts
    Disk->>UI: Synchronize catalog.json & proxies.json
    UI->>Canvas: Project node coordinates (lat/lon to 3D Cartesian)
    Canvas-->>UI: User clicks hub (e.g. Frankfurt / DE)
    UI->>UI: Filter nodes grid & display matching proxies
    UI->>Client: User copies Base64 subscription URL
    Client->>Disk: Fetches unified subscription feed (proxies_b64sub.txt)
```

---

## 5. Architectural Invariants & Quality Attributes

| Attribute | Architectural Decision | Verification Method |
| :--- | :--- | :--- |
| **Zero-Dependency Resilience** | Frontend operates 100% offline with zero CDN dependencies via embedded CSS tokens and vanilla ES modules. | Tested via `file:///` local protocol and browser sandboxing. |
| **XSS Elimination** | All user and proxy-supplied strings are escaped via `escapeHTML()` before DOM injection. | Unit test audit with malformed HTML/JS payloads. |
| **Deduplication Integrity** | Proxies are indexed and deduplicated by SHA-256 fingerprint of normalized configuration parameters. | `internal/outputverify` test suite. |
| **Low-Resource Graphics** | Canvas DPR capped at 2.0; RAF loops pause automatically when `document.hidden == true`. | Profiled under Chromium DevTools Performance tab. |
| **Multi-Platform Support** | Support for VLESS Reality, VMess, Trojan, Shadowsocks, and Hysteria2. | Verified across decoder test suites in Go and Node.js. |
