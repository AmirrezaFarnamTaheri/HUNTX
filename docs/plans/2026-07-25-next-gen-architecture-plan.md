---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
date: 2026-07-25
status: approved
title: HUNTX Next-Gen Architecture — Zero-Copy Streaming, Geo-Clustering & Autonomous Self-Healing
---

# HUNTX Next-Gen Architecture Implementation Plan

## Executive Overview

This plan details the technical implementation of the next-generation architecture for **HUNTX**. Building upon the consolidated `UnifiedOrchestrator`, `AsyncCircuitBreaker`, and `ProxyScoringEngine`, this milestone introduces four core architectural advances:
1. **Zero-Copy Streaming Ingestion Engine**: Chunked 64KB buffer decoders for processing multi-gigabyte proxy feed payloads without loading full buffers into RAM.
2. **Intelligent Geo-Clustering & Dynamic Target Routing**: Autonomous taxonomy classification (ISO country, continent, ASN) and target routing.
3. **Autonomous Self-Healing Daemon**: Async background health monitoring with exponential backoff re-testing (5m, 15m, 1h, 6h) and automatic 48-hour dead node purging.
4. **Multi-Region Resiliency & Integration**: Full orchestration wiring inside `UnifiedOrchestrator` with fast-fail circuit breaker protection.

---

## Technical Architecture & Component Design

```
                             [ Subscriptions / Feeds ]
                                        │
                                        ▼ (64KB Chunked Stream)
                           ┌──────────────────────────┐
                           │   StreamingChunkParser   │
                           │(src/huntx/formats/stream)│
                           └────────────┬─────────────┘
                                        │ (Zero-copy proxy records)
                                        ▼
                           ┌──────────────────────────┐
                           │    ProxyScoringEngine    │
                           │ (src/huntx/core/scoring) │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                           ┌──────────────────────────┐
                           │     GeoRoutingEngine     │
                           │(src/huntx/core/geo_rout) │
                           └────────────┬─────────────┘
                                        │ (Geo & Protocol tagged)
                                        ▼
                           ┌──────────────────────────┐
                           │    SelfHealingDaemon     │
                           │(src/huntx/core/healing)  │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                         [ Active State DB / Outputs ]
```

### File & Symbol Map
- `src/huntx/formats/streaming.py`: Implements `StreamingChunkParser` (64KB chunk iterator for base64/JSON streams).
- `src/huntx/core/geo_routing.py`: Implements `GeoRoutingEngine` (ISO country/ASN parser and protocol taxonomy matcher).
- `src/huntx/core/self_healing.py`: Implements `SelfHealingDaemon` (async background task with exponential backoff schedule).
- `src/huntx/core/unified_orchestrator.py`: Updated to integrate `StreamingChunkParser`, `GeoRoutingEngine`, and `SelfHealingDaemon`.
- `tests/test_streaming_parser.py`: Unit tests for zero-copy streaming chunk parser.
- `tests/test_geo_routing.py`: Unit tests for geo-clustering and dynamic target routing engine.
- `tests/test_self_healing.py`: Unit tests for self-healing background poller and dead node purger.

---

## Phase-by-Phase Task Breakdown

### Phase 1: Zero-Copy Streaming Ingestion Engine

#### Task 1.1: Implement `StreamingChunkParser`
- **File**: [`src/huntx/formats/streaming.py`](file:///D:/GitHub/HUNTX/src/huntx/formats/streaming.py)
- **Description**: Create a memory-efficient chunked iterator (`parse_stream`) reading streams in 64KB blocks. Automatically detects base64 encoding vs line-separated subscription links without accumulating the entire payload in memory.
- **Contract**:
  ```python
  class StreamingChunkParser:
      def __init__(self, chunk_size: int = 65536):
          self.chunk_size = chunk_size

      async def parse_stream(self, stream: AsyncIterator[bytes], source_info: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
          ...
  ```
- **Verification**: Ensure RAM footprint stays flat (<50MB) during processing of a 10MB test stream payload.

#### Task 1.2: Add Streaming Parser Unit Test Suite
- **File**: [`tests/test_streaming_parser.py`](file:///D:/GitHub/HUNTX/tests/test_streaming_parser.py)
- **Description**: Verify chunked decoding of base64-encoded proxy lists, raw line feeds, and malformed streams.
- **Verification Command**: `python -m pytest tests/test_streaming_parser.py`

---

### Phase 2: Intelligent Geo-Clustering & Dynamic Target Routing

#### Task 2.1: Implement `GeoRoutingEngine`
- **File**: [`src/huntx/core/geo_routing.py`](file:///D:/GitHub/HUNTX/src/huntx/core/geo_routing.py)
- **Description**: Analyze proxy endpoint hostnames and IP addresses against country code lookup mechanisms and regex patterns. Classify protocol types (`vless`, `vmess`, `trojan`, `shadowsocks`, `hysteria2`, `tuic`, `wireguard`). Provide routing methods to filter top-performing proxies by region.
- **Contract**:
  ```python
  class GeoRoutingEngine:
      def classify_proxy(self, proxy_data: Dict[str, Any]) -> Dict[str, Any]:
          ...
      
      def route_by_region(self, proxies: List[Dict[str, Any]], country_code: str) -> List[Dict[str, Any]]:
          ...
  ```
- **Verification**: Unit test regex and classification routines on representative URI samples.

#### Task 2.2: Add Geo-Routing Unit Test Suite
- **File**: [`tests/test_geo_routing.py`](file:///D:/GitHub/HUNTX/tests/test_geo_routing.py)
- **Description**: Test classification of IP addresses, domain TLDs, protocol schemes, and regional routing filters.
- **Verification Command**: `python -m pytest tests/test_geo_routing.py`

---

### Phase 3: Autonomous Self-Healing Daemon

#### Task 3.1: Implement `SelfHealingDaemon`
- **File**: [`src/huntx/core/self_healing.py`](file:///D:/GitHub/HUNTX/src/huntx/core/self_healing.py)
- **Description**: Async daemon task that queries degraded proxy records from the state store, applies exponential backoff re-testing intervals (5m -> 15m -> 1h -> 6h), auto-reinstates recovered nodes to active status, and purges nodes unreachable for >48 hours.
- **Contract**:
  ```python
  class SelfHealingDaemon:
      def __init__(self, db_path: str, backoff_schedule: Optional[List[int]] = None):
          ...
      
      async def run_poller_cycle(self) -> Dict[str, int]:
          ...
      
      def purge_stale_proxies(self, max_age_hours: int = 48) -> int:
          ...
  ```
- **Verification**: Mock clock transitions and verify retry schedules, node reinstatements, and 48-hour purge logic.

#### Task 3.2: Add Self-Healing Unit Test Suite
- **File**: [`tests/test_self_healing.py`](file:///D:/GitHub/HUNTX/tests/test_self_healing.py)
- **Description**: Test retry interval escalation, state recovery, and purge execution against an isolated SQLite test database.
- **Verification Command**: `python -m pytest tests/test_self_healing.py`

---

### Phase 4: Unified Orchestration & System Verification

#### Task 4.1: Wire Next-Gen Components into `UnifiedOrchestrator`
- **File**: [`src/huntx/core/unified_orchestrator.py`](file:///D:/GitHub/HUNTX/src/huntx/core/unified_orchestrator.py)
- **Description**: Update `UnifiedOrchestrator` to instantiate and expose `StreamingChunkParser`, `GeoRoutingEngine`, and `SelfHealingDaemon`.
- **Verification**: Run `tests/test_unified_orchestrator.py` to confirm backwards compatibility and integrated pipeline execution.

#### Task 4.2: Full Test Suite Verification
- **Command**: `python -m pytest`
- **Criteria**: 100% green test pass across all unit and integration test suites.

---

## Verification Strategy & Success Metrics

### Automated Verification Protocol
```bash
# 1. Run full unit and integration test suite
python -m pytest -v

# 2. Verify top-level API exports
python -c "import huntx; print(dir(huntx))"
```

### Key Acceptance Criteria
- **Zero-Copy Ingestion**: Stream processing functions without creating unbounded list allocations in RAM.
- **Geo-Clustering**: Accurate classification of protocol types and country/ASN tags.
- **Self-Healing**: Automated background retry cycle with 48h stale node purging.
- **Test Integrity**: All existing and new tests pass with 0 failures or warnings.

---

## Failure Modes & Rollback Strategy

| Risk / Failure Mode | Mitigation / Recovery |
| :--- | :--- |
| **Stream Parsing Error** | Fallback to standard line-by-line buffered decoder if stream chunking fails. |
| **Geo-IP Lookup Latency** | Cache country code lookups in-memory (`lru_cache`) to avoid repetitive parsing overhead. |
| **Database Lock Contention** | Use SQLite Write-Ahead Logging (WAL mode) for concurrent daemon reads/writes. |
| **Daemon Resource Overhead** | Restrict background poller batch size to max 100 proxies per interval cycle. |

---

