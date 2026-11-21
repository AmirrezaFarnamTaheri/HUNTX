# HUNTX Frontend UX Contract

Status: maintained frontend behavior contract. Applies to the dashboard and Network Doctor as of the control-room redesign.

## User jobs and navigation

The product is an operational tool, not a marketing landing page. Its primary jobs are:

1. **Understand the evidence**: see what was published, what was tested, and what remains unknown.
2. **Find an endpoint**: search, filter, inspect, and copy published proxies without equating publication with reachability.
3. **Prepare a client**: build, inspect, and export configurations without silently changing credentials or transport.
4. **Find subscriptions**: identify feed artifacts and inspect publication metadata.
5. **Troubleshoot a local failure**: receive reversible, network-aware guidance and report self-tested outcomes.

The dashboard has five existing workspace IDs: `radar`, `proxies`, `studio`, `decoder`, `artifacts`. Hash deep links and the number shortcuts 1–5 remain supported. The desktop control rail is persistent at widths >=1120 CSS px; tablet and phone use a horizontally scrollable tab bar. Network Doctor remains a separate route with a direct link from the shell.

The canonical generated dashboard markup is `scripts/update_frontend.py`; `docs/index.html` must match its rendered output. The control-room shell uses `docs/assets/css/control-room.css` and `docs/assets/js/control-room.js`. Workspace context is text-only and may not inject user-provided proxy strings as HTML.

## Evidence and truthful labels

- **Published** means a configuration or feed artifact exists. It does **not** imply end-to-end reachability.
- **Artifact integrity** means a checksum or publication contract passed. It does **not** prove the proxy works.
- **Measured** means an explicitly attributed probe or client test ran. Operator cards report the median of available recorded latency samples (p50), sample count, and node count; they do not invent packet-loss figures. Report test source, time and scope where available.
- **Unverified** and **unknown geography** remain visible. Do not replace missing evidence with green badges, fabricated latency, inferred country flags or a claim of live connectivity.
- **Recovered original** and **working alternative** are distinct outcomes. The browser wizard never claims it ran a protocol-native test.

## Network Doctor

Network Doctor asks only for platform, network category and symptom. It provides a manual checklist, a metadata-only catalog check, and a self-reported outcome classification. The catalog check reports its publication timestamp and a 48-hour freshness warning, not live proxy health. Contradictory or invalid catalog metadata is treated as unavailable. It does not request a proxy URI, server secret, SSID, IP, device identifier or browsing history.

The recovery sequence has three stages: describe, try reversible changes, verify in a real client. The current stage is exposed using `aria-current="step"`. After submitting the first form, focus moves to the recovery heading; after reset, focus returns to the first device control. Editing the setup invalidates the previous plan and outcome; editing a reported result hides the stale summary. Catalog checks are bounded and cannot overwrite a later reset or diagnosis. On phones, the explanatory principles can be expanded on demand so the recovery form remains visible in the first viewport. The original configuration is preserved. No hidden network changes, credential guessing, TLS verification bypass, or silent direct-connection fallback.

The theme toggle stores only the existing `huntx_theme` preference. Recovery choices, generated plans and support summaries remain in memory unless the user explicitly copies the report. No analytics endpoint is added by this redesign.

## Accessibility and localization

- Use semantic landmarks, correctly labeled controls, keyboard-operable tabs and visible focus outlines.
- Important targets are at least 44 CSS px high. Mobile inputs use at least 16px font size.
- Respect `prefers-reduced-motion: reduce` and forced-colors. Never rely on color alone for health or evidence.
- No horizontal page overflow at 320, 375, 768, 1024 and 1440 CSS px. Horizontal tab scrolling on small screens is intentional and discoverable.
- The dashboard supports English, Persian, Simplified Chinese and Russian workspace context. Persian uses RTL for layout, while technical strings such as URIs, IPs and hashes remain LTR.
- Theme contrast must be verified in both dark and light modes. A stylesheet or automated audit alone is not a claim of WCAG certification.

## Offline, performance and dependency policy

The public dashboard is a static site that must work without third-party fonts, remote scripts, external image CDNs or a framework hydration step. Native ES modules remain the runtime. The service worker precaches the control-room and recovery assets and uses network-first delivery for first-party scripts/styles to prevent deploy-version skew.

Do not add GSAP, React, FLOWSTACK, or other dependencies solely for decoration when they would increase first-visit cost, break offline use, or require migrating the existing application without a measured benefit. Purposeful transitions should be compositor-friendly and disabled when reduced motion is requested.

## Quality gates

The following must pass before merge:

- `npm run lint`
- `npm run test:unit`
- `npm run build:css` with no generated diff
- `python scripts/update_frontend.py --check`
- `npx playwright test` including control-room, existing browser, recovery, RTL and accessibility checks
- Browser captures for desktop, phone, Persian RTL, dark and light states; inspect actual captures and repair any visible defects.

Review source and generated markup together whenever changing the dashboard. The browser suite is the executable contract; changes to an existing interaction require updating its tests, not silently deleting coverage.

### Opt-in device-local recovery memory

Network Doctor offers an optional **Remember this manual result** action only after the user reports that the original node or a replacement worked, without disabling TLS verification. It is never automatic and is never described as protocol-native verification. Stored records are limited to device category, manually selected Wi-Fi/mobile category, symptom, reported-original/reported-alternative outcome and timestamp. No proxy identity, URI, credentials, SSID, IP address, browsing target, or actual network fingerprint is stored or transmitted.

The user can review and forget each category separately. Notes expire after 30 days and are purged when the browser next visits Network Doctor. Corrupt, forged or oversized storage entries are ignored, and blocked/private storage does not break the wizard. A note about a previous network category is historical context, not proof that a connection still works.


## Historical subscription directory and appearance directions (2026-11-21)

The existing five workspaces, hash links and 1–5 keyboard shortcuts stay.
The artifacts workspace begins with a subscription directory, while retaining
the original artifact browser, release downloads, QR tools and copy controls
below. The shortcut bar offers Statistics, Proxy Explorer and
Subscriptions/Downloads everywhere.

Data is loaded only from the same-origin subscriptions/latest/index.json.
Each supported protocol family has a separate plaintext and Base64 feed;
all.txt and all_base64.txt contain their uncapped union of up to 100 per
category. Old nodes are retained in the archive, not claimed as live.
Counts and timestamps are shown only after validating schema_version,
scope, health_status, latest_by, limit_per_protocol, checksums, filenames and
count bounds. Missing/malformed metadata produces unknown counts and Retry;
an empty published feed correctly shows zero because its file exists.

Local search supports immediate clear and availability filtering. URLs are
project-relative and never constructed from untrusted JSON-provided paths.
Copy failures produce recoverable, accessible status messages.

The three visual directions Signal, Ledger and Orbit use one native labeled
control. Only an allowlisted style string persists under
huntx_visual_direction, subject to storage availability; no proxy content
or network state is stored. The existing dark/light preference is separate.
Network Doctor remains on its standalone route with its privacy invariants.

Required responsive and accessibility behavior: no horizontal page overflow
at 320/375/768/1024/1440px, 44px touch actions, native semantic controls,
visible focus, live status/errors, keyboard operation, reduced-motion and
forced-color support, correct locale/RTL with technical content LTR.
Automated checks are not a WCAG certification.

## Latest-100 Subscriptions Library

The optional `subscriptions.html` route is a first-class **Subscriptions**
destination linked from the existing dashboard operation rail and narrow tab
bar. It does **not** change the five dashboard tab IDs, numbering shortcuts,
hash deep links, or Network Doctor route.

The page reads metadata from `subscriptions/latest/index.json` only.
It validates the cumulative-history schema and each safe protocol filename,
count (0–100), SHA-256 and aggregate equality before displaying a figure.
An unavailable, stale or malformed index must show unavailable counts,
plain-language retry guidance and links to the existing artifact browser,
without claiming proxies are working. Historical feeds are not health-verified.
Never fetch raw proxy URI contents into this UI or interpolate untrusted
metadata into HTML.

The page offers direct per-protocol TXT/Base64 downloads, an uncapped
`all.txt` / `all_base64.txt` master aggregate, an index.json link,
search, available-only filtering, clear and accessible copy URL feedback.
Each new protocol is listed by its own validated name; an "Others" category
is not created. The three visual directions (Signal, Canvas and Ledger)
share all semantics and functionality. Visual preference is deliberately
session-only and does not conflict with `huntx_theme`.

All controls retain native keyboard semantics, visible focus, good contrast,
reduced-motion and forced-colors compatibility. The product page is an offline
PWA shell, but latest metadata and feeds must be fetched network-first to
avoid presenting superseded publication bytes. Deployment verifies the new
page, CSS and ES module against the committed static snapshot. Playwright
covers search, filters, URLs, states, keyboard and 320–1440px reflow.
