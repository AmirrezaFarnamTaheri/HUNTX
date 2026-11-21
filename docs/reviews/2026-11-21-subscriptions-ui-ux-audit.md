# HUNTX frontend and UI/UX audit — subscription discovery redesign

**Date:** 2026-11-21
**Evidence type:** Repository source, maintained UX contract, HTML/CSS/JS and checked-in test coverage. **Not** a screenshot-backed or user-tested visual accessibility certification.
**Scope:** Static dashboard at `docs/index.html`, `docs/assets/css/{control-room,atlas-v2}.css`, `docs/assets/js/{app,control-room}.js`, Network Doctor as an existing route, and the latest-100 publication model.

## Executive assessment

HUNTX is already an operationally capable interface with a persistent desktop rail, a responsive tab strip, comprehensive node exploration, a subscription studio, a decoder, artifact library, and a separate connection-recovery route. Replacing its existing app or simplifying away the tools would be a regression. The highest-impact improvement is **separating the job of finding an immediately importable subscription from the more advanced jobs of building configurations or browsing the entire artifact registry**.

The review is a source-level UX audit of the current implementation. A live screenshot capture and automated/assistive-technology accessibility test are still needed to establish visual defects in each supported browser; none are invented here.

## Current navigation and user journeys

1. **Understand network evidence:** `#radar` — telemetry snapshot and measurement labels
2. **Find a proxy:** `#proxies` — filters, grid/table/feed variants, connection evidence
3. **Prepare a client:** `#studio` — conversion and subscription builder
4. **Inspect a config:** `#decoder` — raw parameters, decoder
5. **Browse all files:** `#artifacts` — full generated artifact registry
6. **Fix a connection:** `network-doctor.html` — guided recovery, separate route

Existing hash links, hotkeys 1–5 and desktop/mobile rail behavior are preserved. The sixth *destination* `subscriptions.html` is a **separate static page**, not a breaking sixth tab.

## Audit findings and actions

| Area | Finding | Severity | Recommendation / implementation |
| --- | --- | --- | --- |
| Information architecture | Protocol subscriptions, conversion and complete artifact downloads compete for discovery under Studio and Artifacts, with no dedicated top-level latest-100 destination. | **High** | First-class **Subscriptions** entry in the persistent rail and responsive tab bar; a dedicated library organized by protocol and master aggregate |
| Navigation | Five existing workspaces use hash routes, but downloads and the newest historical subscription links are separate mental models. | **High** | Preserve all hash routes; provide explicit destinations: Dashboard, Proxy explorer, Subscriptions, Downloads, Studio, Inspector, Network Doctor |
| Honest state | A published URI, a catalog checksum and a successful authenticated proxy test are distinct kinds of evidence; the maintained UX contract already recognizes this. | **High** | Mark every new historical feed **not verified live**, explain no age cutoff and separate the release artifacts |
| Downloads | Metadata-heavy artifact listings are powerful but demand filtering before a user can copy a specific protocol subscription. | **High** | Put `all.txt`, `all_base64.txt` and `index.json` in a prominent master panel; separate per-protocol TXT, Base64 and copy actions |
| Metadata integrity | Static Pages can serve old data after new releases if the service worker reuses cached manifests. | **High** | Use network-first delivery for `/subscriptions/latest/`; validate the index schema and refuse fabricated counts |
| Responsiveness | Existing desktop rail becomes horizontally scrollable mobile tabs at 1120px; off-screen destinations can be less discoverable. | **Medium** | Dedicated hub uses an explicit labeled horizontal mobile navigation strip, large touch targets and 320px-reflow rules |
| Typography | The dashboard uses many compact 11–13px labels and falls back when referenced font families are not installed; this is dense but suits expert telemetry. | **Medium** | New hub uses 14–15px body and larger headline/stat hierarchy with a clear mono metadata style; preserve existing expert surfaces |
| Visual consistency | The generated dashboard combines a large inline CSS section with `control-room.css` and `atlas-v2.css`; multiple layers require careful specificity when evolving the palette. | **Medium** | Scope all new route tokens to `subscription-hub.css`; record token ownership; avoid global styling changes to established panels |
| Color and contrast | Dark/light operational tokens and protocol semantic accents exist; source declarations alone do not prove rendered contrast and focus under every state. | **Medium** | Deliberately chosen, high-contrast three-mode palettes, visible focus, forced-colors fallback and automated browser review |
| Accessibility | Existing skip link, tab semantics, visible focus, reduced-motion and RTL tests are strengths. Screen-reader flow and each theme still need browser/AT verification. | **Medium** | Native form controls and links, explicit labels, status announcements, no hover-only actions, 44px targets and stable focus |
| Performance | The existing dashboard loads substantial telemetry code and visualization tools, which need not be fetched by someone seeking a TXT feed. | **Medium** | New page loads one small ES module and one stylesheet, with no external fonts, images, frameworks or proxy-credential downloads |
| Internationalization | The main control room supports English, Persian, Chinese and Russian, while the new specialist page launches with English copy. | **Follow-up** | Keep main locale behavior intact; scope a future translation pass with verified text length, RTL and terminology checks rather than invent partial translations |

## Three implemented design directions

### Signal / sovereign control room
Deep navy surfaces, cyan connection signals, narrow operational lines and numeric metadata. Optimized for experts moving between protocol rows and live tooling. The orbital illustration around the aggregate represents **union of separate feeds**, not an invented connectivity graphic.

### Canvas / legible explorer
Soft white-lilac canvas, indigo actions, larger rounded cards and more open spacing. Optimized for first-time visitors importing subscriptions into a client.

### Ledger / structured technical archive
Warm chalk surfaces, editorial serif headlines, compact ruled statistic blocks and restrained green-blue actions. Optimized for researchers comparing historical feed categories.

The three designs are **real, selectable CSS modes** on `subscriptions.html`, not static mockup descriptions. They share an identical, semantic HTML and metadata contract. The design switch changes visual treatment only, stores no user data and never modifies feed URLs or backend behavior.

## New destination and functionality

- **`subscriptions.html`**: responsive, labeled index and clear entry from the dashboard
- **`subscriptions/latest/index.json`**: validated counts, publication timestamp, distinct named protocols, no Others category
- **`subscriptions/latest/<protocol>.txt`** and **`<protocol>_base64.txt`**: individual historical feeds, max 100 of each
- **`subscriptions/latest/all.txt`** and **`all_base64.txt`**: full union across every protocol; no aggregate 100 cap
- Search, available-only toggle, no-results state, retryable unavailable-index state and clipboard feedback
- Dashboard link, deep links to proxy explorer, Studio, Inspector, Artifacts and Network Doctor

**Trust statement:** a historical feed connection can be expired or broken. Latest is based on first discovery, not on a recent authenticated protocol test. The interface does not claim those links work now.

## Tests and verification boundary

The PR adds Node unit tests for schema rejection, protocol handling, URL safety, filtering and 20 named types, plus Playwright flows for downloads, theme switching, search, offline/index errors, navigation and reflow at 320/375/768/1024/1440px. The existing CI includes frontend lint/build, Python, Go and Pages publication gates. `docs/subscriptions.html` and its CSS/JS are included in the service-worker shell and exact live publication integrity check.

**Not yet verified from this chat:** actual pixel screenshots, individual assistive-technology/screen-reader sessions, physical-device touch/zoom, and production deployment. Automated assertions do not constitute WCAG 2.2 AA certification.

## Recommended follow-up after rollout

Measure feed discovery and import success with privacy-preserving opt-in research rather than adding tracking. Consolidate the historical dashboard's layered CSS only as a separate reviewable refactor, and conduct an RTL/i18n pass across the new specialist page without changing the proven core flows.
