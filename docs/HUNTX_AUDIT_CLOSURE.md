# HUNTX Audit-Derived Closure Ledger

This ledger maps the six-repository audit findings and synthesis recommendations to HUNTX. It intentionally does not claim that defects in the comparison repositories existed in HUNTX unchanged.

## Status definitions

- **Implemented** — code and repository-owned regression evidence exist.
- **Integrated** — implementation is on the production execution/publication path.
- **Partial** — a reusable primitive or contract exists, but one or more production call sites remain.
- **Not applicable** — the comparison-repository defect is not present in HUNTX; the corresponding invariant is still tested where valuable.
- **Open** — no adequate HUNTX implementation or executable proof yet exists.

## Finding mapping

| Audit item | HUNTX disposition | Evidence |
|---|---|---|
| D-01 invalid JSON caused by metadata preambles | Partial | `release_manifest.py` strict-parses JSON artifacts; production manifest generation is invoked by `generate_site_data.py`. Native client validation remains open. |
| D-02 SIP002 plaintext credential corruption | Open | HUNTX NPVT currently extracts URI strings; protocol-aware SIP002 admission/round-trip fixtures remain required. |
| D-03 ineffective cross-run dedup | Existing HUNTX mechanism; further proof open | SQLite state and canonical record hashes exist. Replay/idempotency tests should be expanded to artifact equivalence. |
| D-04 stale-source timestamp conflation | Partial | Source trust states now exist. Separate attempt/success/nonempty lifecycle fields and transition tests remain open. |
| D-05 Hysteria2 obfuscation field aliasing | Open | Protocol-specific field preservation fixtures remain required. |
| D-06 fabricated empty-category endpoints | Not applicable | HUNTX health gate fails on zero artifacts; no fake endpoint generator was identified. |
| D-07 TLS verification bypass in default feeds | Open | Independent policy verdict contract exists; renderer/build integration and secure-tier scan remain required. |
| D-08 documentation/output path drift | Integrated | Site catalog is generated from a verified SHA-256 release manifest and preserves artifact-relative paths. |
| D-09 output coordinate collision | Implemented | Release manifest rejects duplicate coordinates; site generation rejects duplicate destinations. Build-stage pre-write collision detection remains desirable. |
| D-10 fail-open workflow | Integrated | PR validation is required before build; production CLI returns explicit run outcomes; build/deploy jobs are separated. |
| D-11 recursive source-branch publication | Integrated | Production workflow no longer commits generated outputs to `main`; Pages consumes an artifact. |
| D-12 permissive lexical validator | Open | Current NPVT URI extraction remains lexical. Protocol-aware full-record validation is required. |
| D-13 uncontrolled source discovery/trust | Partial | Candidate/approved/degraded/quarantined/retired states and approval evidence are validated; only approved sources enter hardened runs. Registry persistence and promotion command remain open. |
| D-14 geolocation request amplification | Not directly applicable | No equivalent inline provider-pattern fan-out was identified in HUNTX. External-call budgets should still be enforced connector-wide. |
| D-15 no automated tests | Implemented | HUNTX already had a substantial suite; PR #49 adds runtime, governance, manifest, verdict, and lease tests. |
| D-16 unauthenticated wildcard listener | Not applicable | HUNTX publishes configuration artifacts and does not generate the cited sing-box listener by default. |
| D-17 subscriber-count inflation | Not applicable | No equivalent ranking parser was identified. |
| D-18 non-atomic JSON state | Existing HUNTX mechanism | HUNTX uses SQLite/WAL and atomic file utilities. S3 state promotion still needs generation/checksum semantics. |
| D-19 fragment-based duplicate inflation | Partial | HUNTX strips nonsemantic remarks for dedup and has regression tests. Corpus-level duplicate-ratio SLI remains open. |
| D-20 browser secret persistence | Not applicable | HUNTX does not include the cited Abzar browser workflow. |
| D-21 placeholder Clash conversion | Not applicable | No equivalent placeholder UI renderer was identified. Renderer-native conformance remains a general requirement. |
| D-22 unbounded legacy HTTP calls | Partial | HUNTX connectors have retry/freshness controls; connector-wide byte/redirect/global-deadline contracts require a dedicated audit. |
| D-23 unescaped MTProto HTML | Not applicable | HUNTX does not use the cited static MTProto HTML generator. |
| D-24 mutable CI/dependency inputs | Partial | Actions and runtime dependencies are immutable/hash-locked. Development dependency hash lock, SBOM, and provenance remain open. |
| D-25 duplicated legacy scraper forks | Not applicable | HUNTX centralizes connector and pipeline logic. |

## Synthesis architecture status

| Synthesis item | Status | HUNTX implementation |
|---|---|---|
| SYN-01 typed proxy IR | Open | Existing record model remains format/dictionary oriented. |
| SYN-02 governed source registry | Partial | Source lifecycle enum, approval evidence, and execution exclusion implemented. |
| SYN-03 transactional lineage state | Partial | SQLite/WAL and repositories exist; explicit artifact/source lineage schema needs expansion. |
| SYN-04 syntax/probe/policy separation | Implemented contract, integration open | `core/verdicts.py` and tests. |
| SYN-05 pure renderers/manifest publication | Partial | Strict release manifest and manifest-driven catalog implemented; renderer purity audit remains. |
| SYN-06 native client gates | Open | Pin/checksum and invoke required client validators before release. |
| SYN-07 durable orchestration | Integrated baseline | Explicit run states, deadlines, cancellation, partial-export policy, and health gates. |
| SYN-08 observability contract | Open | Structured IDs, metrics, and trace propagation remain. |
| SYN-09 supply-chain boundary | Partial | Full-SHA actions and hashed runtime lock; dev lock/SBOM/provenance remain. |
| SYN-10 immutable distribution | Integrated | Build artifact and Pages deployment replace source-branch output commits. |
| SYN-11 thin safe client UI | Not applicable | No equivalent local browser tool in HUNTX. |
| SYN-12 contract-generated catalog | Integrated | Site catalog derives from verified release records. |

## Merge-blocking items

PR #49 must remain draft until:

1. PR validation is green.
2. Production site generation proves manifest verification and artifact copying in an integration fixture.
3. Source-state defaults in `config.prod.yaml` are reviewed so legacy sources are not accidentally treated as newly approved discoveries.
4. Protocol admission fixtures cover SIP002, Hysteria2 obfuscation, VLESS/Reality, VMess, Trojan, and MTProto.
5. Secure-tier policy is enforced at build selection and scanned in release artifacts.
6. Native client validation policy is implemented or explicitly scoped out with a release-blocking follow-up.
7. Development dependency locking, SBOM, and provenance have executable checks.
8. Remaining broad exception and external-call boundaries are reviewed.

## Explicit non-claims

This PR does not claim that live remote endpoints are trustworthy, reachable, or secure. It does not treat source popularity as approval. It does not claim native client compatibility until client checks run against promoted artifacts.