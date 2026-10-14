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
- **Measured** means an explicitly attributed probe or client test ran. Report test source, time and scope where available.
- **Unverified** and **unknown geography** remain visible. Do not replace missing evidence with green badges, fabricated latency, inferred country flags or a claim of live connectivity.
- **Recovered original** and **working alternative** are distinct outcomes. The browser wizard never claims it ran a protocol-native test.

## Network Doctor

Network Doctor asks only for platform, network category and symptom. It provides a manual checklist, a metadata-only catalog check, and a self-reported outcome classification. It does not request a proxy URI, server secret, SSID, IP, device identifier or browsing history.

The recovery sequence has three stages: describe, try reversible changes, verify in a real client. The current stage is exposed using `aria-current="step"`. After submitting the first form, focus moves to the recovery heading; after reset, focus returns to the first device control. The original configuration is preserved. No hidden network changes, credential guessing, TLS verification bypass, or silent direct-connection fallback.

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
