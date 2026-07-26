# Specification: Hardening & Health Benchmarking

## Overview
Enhance HuntX with an automated proxy latency benchmarker, expanded format decoder testing, and Telegram bot notification alerts for proxy freshness.

## Functional Requirements
1. **Proxy Latency Benchmarking Gate**:
   - Perform real-time TCP connectivity and latency tests on decoded proxies.
   - Treat each endpoint probe as an independently bounded operation with an explicit timeout.
   - Use bounded concurrency so a large proxy set cannot create an unbounded number of sockets or tasks.
   - Cancel and close timed-out probe tasks cleanly; never allow abandoned probes to delay pipeline completion.
   - Retry a failed probe at most once, using a short bounded backoff before the retry.
   - Filter unreachable endpoints and proxies whose measured latency exceeds **3000 ms**.
   - Preserve non-proxy records without forcing them through the TCP benchmark gate.
   - Surface benchmark failures through structured error accounting rather than silently admitting unverified proxies.
2. **Decoder Suite Test Expansion**:
   - Comprehensive test cases covering malformed payloads and edge-case syntax for all 12 formats.
3. **Bot Freshness Alerting**:
   - Automated Telegram bot notification alerts when proxy counts fall below configured thresholds or on run completion.

## Acceptance Criteria
- Required GitHub Actions validation workflows pass.
- High-latency and unreachable proxies are removed prior to publishing.
- Probe concurrency, timeout, cancellation, retry, and backoff behaviour are covered by deterministic tests.
- Alert notifications are dispatched to configured bot channels under the documented triggering conditions.
