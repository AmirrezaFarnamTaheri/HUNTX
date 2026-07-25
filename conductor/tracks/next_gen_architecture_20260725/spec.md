# Specification: Next-Gen Architecture (Zero-Copy Streaming, Geo-Clustering & Autonomous Self-Healing)

## Overview
This track delivers four core architectural capabilities for HUNTX:
1. **Zero-Copy Streaming Ingestion Engine**: 64KB chunked buffer decoding for base64 and JSON subscription streams to keep RAM usage strictly below 50MB under heavy load.
2. **Intelligent Geo-Clustering & Dynamic Target Routing**: Autonomous protocol taxonomy classification (`vless`, `vmess`, `trojan`, `shadowsocks`, `hysteria2`, `tuic`, `wireguard`) and ISO country/ASN geo-tagging and dynamic routing.
3. **Autonomous Self-Healing Daemon**: Async background health poller with exponential backoff re-testing (5m -> 15m -> 1h -> 6h) and auto-purging proxies unreachable for >48 hours to maintain a lightweight state database.
4. **Multi-Region Resiliency & Integration**: Full integration inside `UnifiedOrchestrator` with `AsyncCircuitBreaker` fast-fail protection.

## Requirements & Acceptance Criteria
- **Streaming Parsing**: `StreamingChunkParser` processes 10MB+ payload streams without accumulating entire buffers in RAM.
- **Geo-Clustering**: `GeoRoutingEngine` accurately classifies proxy nodes by country code, ASN, and protocol scheme.
- **Self-Healing**: `SelfHealingDaemon` successfully schedules retry cycles and purges dead nodes older than 48 hours.
- **Quality Gates**: All pytest tests pass green.
