# HUNTX frontend experience audit and redesign decisions

Date: 2026-11-21  
Scope: dashboard, all five workspaces, publication/download journeys, Network Doctor, static GitHub Pages delivery.

## Evidence and limits

This is a **source-backed interface and interaction audit**, not a claim of
observational user research or certified accessibility. Evidence inspected:
docs/index.html, the canonical scripts/update_frontend.py generator,
docs/assets/js/app.js, control-room.js, docs/assets/css/control-room.css,
atlas-v2.css and interface.css, docs/sw.js, maintained DESIGN.md and
UX-CONTRACT.md, and the existing browser/unit tests. No authenticated browser
screenshots were available directly in the chat runtime. The PR includes new
Playwright coverage; a human visual inspection of CI captures remains
advisable before merging.

## Journey and information architecture

| Step | Surface / user job | Existing strengths | Audit finding | Health |
|---|---|---|---|---|
| 1 | Network Overview: understand published evidence | Radar, measurement status, geography and evidence-strip metrics; explicit unverified states | First-visit header and telemetry competes with a direct "where do I get a subscription?" route | Functional, discoverability risk |
| 2 | Proxy Explorer: find and compare nodes | Search, protocol and advanced filters, cards/table/feed, copy/QR, keyboard tests | Very dense filter and action language; task hierarchy depends on knowledge of proxy terminology | Functional, cognitive load risk |
| 3 | Subscription Studio: build/convert | Existing local converter and reference routing tools; no server roundtrip | "Subscription Studio" versus "Artifacts & Feeds" duplicates subscription vocabulary for different actions | Functional, naming clarity risk |
| 4 | Protocol Inspector: decode safely | Local-only inspection, client conversions, keyboard-enabled inspector tabs | Technical terms and raw output benefit from a clearer handoff to downloads | Functional, specialist-oriented |
| 5 | Published Feeds: locate an importable URL | Catalog search, categories, QR, direct copy and downloads | Latest-100 per-protocol feeds previously had no dedicated, obvious directory with historical trust labels and aggregate prominence | **High priority** |
| 6 | Network Doctor: diagnose a local failure | Separate focused route with reversible three-stage wizard and explicit self-report | Keep this interaction separate; don't imply diagnostic recommendations prove protocol-native success | Strong safety semantics |

## Cross-cutting UX findings and remedies

| Axis | Source-backed assessment | Priority | Implemented direction |
|---|---|---|---|
| Navigation | Five persistent workspace IDs with 1–5 keyboard shortcuts, rail at desktop, mobile scrollable tabs; existing labels compete for attention | High | Preserve routes and labels; add cross-workspace task shortcuts to Statistics, Proxy Explorer and Subscriptions/Downloads |
| Information architecture | Current dashboard distinguishes telemetry, exploration, building, inspection, publication but subscription access is mixed into a broader artifacts catalog | High | Add a first-class subscriptions directory *before* the original downloadable artifact library |
| Usability and feedback | Data-loader and catalog states exist; historical feed counts need explicit unknown/loading/empty distinction | High | Schema-check index.json, show real counts only, retain 0 for published empty feeds, provide Retry and clear search |
| Layout and hierarchy | Existing full-width header, 226px control rail and dense cards can compete at narrower widths | High | Scope one concise aggregate hero, responsive cards, mobile single-column layout; do not replace core workspace shells |
| Typography | Brand system specifies Plus Jakarta Sans / JetBrains Mono but offline runtime uses system fallbacks; numeric data needs consistent tabular alignment | Medium | Use system-local stack, deliberate display/utility pairing per direction, tabular counts; avoid remote font dependency |
| Colors and contrast | Multiple historical theme layers (interface, control-room, Atlas) and Tailwind utility colors create potential palette drift; exact WCAG status cannot be inferred from declarations | High | Reinterpret semantic --room-* tokens consistently across dark/light directions, preserve visible focus/forced colors; manual contrast scan still required |
| Accessibility | Native tab navigation, labeled controls and role/status landmarks already have regression tests; copy/filter states need equivalent keyboard routes | High | Native select/buttons/links, live status, clear/retry actions, 44px minimum targets, explicit unavailable links; test mobile and keyboard |
| Responsiveness | Breakpoints exist at 1120px desktop rail and smaller mobile views; existing tests cover 320/375/768/1440 but new controls also need tests | High | New subscription grid changes from 3 to 2 to 1 column, quick actions wrap; test 320/375/768/1440 in Playwright |
| Consistency | Different card styles in the legacy telemetry, Atlas and artifact renderers are constrained by existing behavior | Medium | New styles depend on shared tokens rather than overriding parser, routing or modal behavior; three looks share one DOM |
| Motion | Existing workspaces use short entrance transitions and reduced-motion CSS | Medium | Only tactile hover elevation in Orbit, disabled when reduced motion is requested |
| Performance | Static module dashboard includes substantial first-party app/data payload; a new framework or font CDN would increase cost and failure risk | Medium | One small module and stylesheet, no dependency changes, keep indexed data fetch limited to a small metadata JSON |
| Offline and freshness | Service worker caches shell resources but subscription metadata must not lag a new publication | High | Precache new UI shell only; serve latest feeds and artifact mirror network-first with offline fallback |
| Trust language | Artifact integrity is not proxy reachability; cumulative history contains old/unverified connections | Critical | "Historical, not a live connectivity guarantee" is visible beside master links and below each directory |

## Three implemented visual directions

The user can switch among all three using the **Interface style** control.
These are three visual systems over the same functional workspaces—no feature
or data difference and no second router.

### A. Signal — Operator instrument (default)
- Maritime charcoal/navy background, teal indicators, balanced 14px panels and sans/monospace hierarchy
- Signature: one dominant aggregate download plus quieter protocol statistics
- For users prioritizing monitoring, latency evidence and fast routine operations
- Retains the incumbent HUNTX look and creates the smallest transition cost

### B. Ledger — Technical editorial
- Slate-white / warm-graphite surfaces, crisp cobalt/amber highlights, thin rules and near-square controls
- Georgia display headings and a utility monospace for exact node counts and file types
- Signature: broad editorial heading with a short colored reading line; protocol cards read as a compact data ledger
- For researchers scanning source dates, proofs, release history and a high-density file inventory

### C. Orbit — Spectral console
- Deep indigo / pale violet with purple directional accents, 20px panels and controlled luminous surfaces
- Modern sans headlines paired with exact-number monospace; no animated background or looping decorative glow
- Signature: a single concentric motif behind the master feed, not repeated on every card
- For dashboard demos, discovery and users who prefer expressive visual grouping

## Requirements trace

- One named feed per supported proxy protocol: all 20 requested groups are part of CORE_PROTOCOLS, and new published categories appear individually.
- No Others bucket; alias grouping remains the publisher's canonical behavior.
- Per-protocol entries are capped at 100 by the publisher, not the frontend.
- Master aggregate has **no overall 100 limit**; derived from the exact per-category subsets.
- Master plain, Base64 and index JSON all have visible actions once metadata is available.
- Historical unverified status is always visible; no healthy/live claims are inferred from checksums or dates.
- Statistics come from publication metadata only; unknown stays unknown.
- Original radar, explorer, builder, inspector, artifact downloads, architecture and Network Doctor are preserved.

## Verification and remaining checks

New tests: tests/frontend_subscription_hub.test.mjs and
tests/frontend_subscription_hub.spec.mjs. Existing unit, lint, canonical
HTML generation, dark/light, RTL, narrow viewport, browser and publisher
checks remain required in PR CI. Manual screen-reader testing, 200% zoom
and human review of captured dark/light screens are still needed before
claiming full WCAG 2.2 AA conformance.
