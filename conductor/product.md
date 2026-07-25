# Product Definition: HuntX

## Vision
HuntX is a zero-budget, incremental proxy configuration harvesting, decoding, and aggregation pipeline with an integrated GatherX Telegram bot. It continuously collects VPN and proxy configurations across 49+ Telegram channels and external collectors, normalizes 20+ proxy protocols across 12 custom payload formats, deduplicates content using SHA-256 state tracking, and delivers clean subscription links to users.

## Target Audience
- Privacy-focused users and network administrators requiring reliable, up-to-date proxy/VPN configurations.
- GatherX Telegram bot subscribers receiving automated subscription updates.
- Open-source proxy catalog consumers accessing GitHub Pages endpoints.

## Core Features
1. **Multi-Source Ingestion**: Dual Telegram connectors (Bot API and MTProto User Sessions) for historical lookbacks and realtime monitoring across 49+ channels.
2. **Multi-Format & Protocol Decoding**: Full parsing and decoding for 12 binary/opaque configuration formats (`npvt`, `npvtsub`, `ovpn`, `npv4`, `conf_lines`, `ehi`, `hc`, `hat`, `sip`, `nm`, `dark`, `opaque_bundle`) into standard structured proxy URIs (VMess, VLess, Trojan, Shadowsocks, Hysteria2, TUIC, WireGuard, Anytls, etc.).
3. **Incremental State Engine**: SQLite-backed deduplication, magic-byte media/APK filtering, and windowed lookback queues.
4. **GatherX Telegram Bot**: DM-based interactive bot with user preference management and automated subscription delivery.
5. **Quality Gates & Auto-Deploy**: Automated linting, typing, unit testing, and GitHub Pages catalog publishing.

## Success Metrics
- **Zero Silent Failures**: 100% error handling across malformed payloads and external network drops.
- **Freshness**: Sub-hour ingestion and delivery cycle for active proxies.
- **Quality**: 0% APK or invalid payload contamination in delivered subscriptions.
