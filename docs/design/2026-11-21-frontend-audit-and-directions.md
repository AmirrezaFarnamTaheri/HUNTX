# HUNTX frontend audit and three redesign directions

**Date:** 2026-11-21
**Evidence:** Repository source on `main` before the subscription-hub feature, including
`scripts/update_frontend.py`, `docs/index.html`,
`docs/assets/css/control-room.css`, `docs/assets/css/atlas-v2.css`,
`docs/assets/js/control-room.js`, `docs/assets/js/app.js`,
`UX-CONTRACT.md`, `DESIGN.md`, `docs/sw.js`, and frontend tests.

**Method limitation:** Source inspection and the project's executable CI are available.
This is a source-grounded UX audit, **not a screenshot-backed visual or assistive-technology
certification**. Actual color contrast, zoom layouts, screen-reader announcements and
device-specific visual polish must be confirmed with a live browser and screenshots.

## Existing product and jobs

HUNTX is a static operational proxy telemetry dashboard for researchers and
network operators. It already offers five workspaces, a responsive desktop rail
and mobile tab list, hash/keyboard navigation, a network globe, proxy search and
filters, subscription builder, decoder, artifact repository, theme and locale
switching, Network Doctor, offline-first assets and telemetry evidence.

The existing five tab IDs `radar`, `proxies`, `studio`, `decoder`, and
`artifacts` are a compatibility contract. The new per-protocol historical
subscriptions should live within **Artifacts**, not require a destructive
navigation migration.

## Audit findings — ordered by user impact

| Priority | Area | Evidence | Problem / opportunity | Design response |
|---|---|---|---|---|
| P0 | Information architecture | `docs/index.html` / `scripts/update_frontend.py` — feeds are nested under tab five; studio also uses “Subscription” in its label | Users seeking a ready-to-import subscription may confuse building a new subscription with downloading a published one | Dedicated subscription directory at the top of Artifacts; one-click masthead shortcut; distinguish Studio (build) vs Feeds (download) |
| P0 | Data trust | `UX-CONTRACT.md` and `docs/SUBSCRIPTION_FORMATS.md` distinguish authenticated releases from cumulative history | Historical newest-100 links can be mistaken for currently working nodes | Use unequivocal **Historical · not live-verified** language and a separate current release card |
| P0 | Discoverability | New `subscriptions/latest/index.json` exists in publisher but original dashboard has no dedicated presentation | The 20+ per-protocol URLs and combined `all.txt` / `all_base64.txt` are not directly browsable from the dashboard | Render a searchable catalog directly from index.json, with quick TXT/Base64/copy actions and master CTA |
| P1 | Navigation | Five workspace tabs, independent Network Doctor route and header utility buttons | Advanced operations are visible, but primary download intent competes with secondary tools; two meanings of “subscription” | Add “Subscriptions” shortcut without changing tab IDs, URLs, builder or shortcuts |
| P1 | Visual hierarchy | `control-room.css` and `atlas-v2.css` have many gradients, utility badges and data-density patterns | Users need a stronger distinction between primary master feed, secondary protocol list, and technical artifact inventory | Introduce one restrained hero, two feature panels and consistent protocol rows |
| P1 | Accessibility | Existing 44px minimum targets, focus ring, forced-colors/reduced-motion rules in `UX-CONTRACT.md` | New filter/copy actions must meet the same standard; raw generated content cannot be inserted as HTML | Native input/buttons/anchors, explicit labels, visible focus, textContent-only data, status announcements and empty/error/retry |
| P1 | Responsive | Desktop rail at 1120px; mobile horizontal tabs; workspace masthead stacks in `control-room.css` | 20+ cards could cause horizontal scrolling and congest smaller screens | Grid 3 → 2 → 1 columns; responsive search; flex-wrapped feed actions, long protocol names wrap |
| P2 | Typography | Shared `Plus Jakarta Sans` display/body with monospace telemetry; local/system fallbacks | Technical URIs and counts need crisp tabular alignment, without making every label monospace | Headings in established display family, protocol IDs/counts in monospace |
| P2 | Palette | `DESIGN.md` and `control-room.css` define slate/teal/cyan semantic tokens and both themes | Multiple saturated accents could look like competing status indicators | Reuse `--room-*` semantic colors and cyan as the single action accent; use amber only as a labelled caution cue |
| P2 | Download availability | `docs/sw.js` uses network-first for release/catalog but didn't include the new historical feeds | Return visitors could see stale cached historical metadata during publication | Treat `/subscriptions/latest/` and historical artifact mirrors as network-first, without pre-caching data files |
| P2 | States and recovery | Existing workspace loading shell, but no newest-100 discovery state | Loading, missing historical publication, zero-count categories and no-match results need actionable explanations | Loading status, retry, empty category count, no-results and copy feedback |

### Accessibility verification still required

- Desktop/phone screenshots in dark and light, Persian RTL and 200% zoom.
- Keyboard traversal, focus after switching the Artifacts tab, live-region announcements.
- Real text/button color contrast measurements against composited surfaces.
- Touch-target measurement for compact actions, Firefox/Safari CSS support and screen readers.
- No claim of full WCAG compliance without those checks.

## Three distinct redesign directions

### A. Signal Atlas — recommended and implemented

**Character:** Analytical field instrument; energetic entry point with calm data rows.
**Colors:** Existing blue-black canvas, slate raised surfaces, soft cyan action,
amber labelled provenance caution. Existing light theme uses matching semantic roles.
**Typography:** Plus Jakarta Sans for interface hierarchy, monospace for protocol
identifiers and counts.
**Layout:** Persistent five-workspace shell; subscriptions become a strong editorial
introduction with master aggregate CTA, current-release card and protocol-card matrix.
**Signature:** A thin multi-protocol spectrum rule and a dominant “One link. Every protocol.”
master panel.
**Why:** Maximum improvement to find/copy/download jobs without disrupting
telemetry, tools, public URLs or theme support. **Implemented in this PR.**

### B. Luminous Registry — alternative concept, not implemented

**Character:** Bright operational library with a search-first content directory.
**Colors:** Porcelain `#F3F7FA`, slate `#142D3A`, cobalt `#125FAD`,
teal `#087F8C`, caution `#956500`.
**Typography:** System grotesk for headings and body; tabular sans/monospace for
metadata.
**Layout:** Wide light header, left filter column, compact list/table of protocols,
persistent pinned aggregate action.
**Signature:** An always-visible publication provenance strip separating historical
and verified feeds.
**Trade-off:** Excellent for document-heavy download use; less aligned with
HUNTX's current radar-oriented dark identity.

### C. Operator Matrix — alternative concept, not implemented

**Character:** Dense, keyboard-centric terminal-inspired tool for experts.
**Colors:** Graphite `#0F1720`, cold slate `#1D2C37`, turquoise `#55C7D7`,
ice `#E5F1F6`, warning amber `#E9C174`.
**Typography:** Medium-weight grotesk headings and compact IBM-Plex-like system
monospace (local fallbacks only).
**Layout:** Narrow sidebar + performance/evidence overview + dense protocol table
with sticky search and one-line copy/export actions.
**Signature:** One-click command strip showing a carefully attributed master feed
summary and last archive publication.
**Trade-off:** Fast for repeat operators, but cramped for first-time users,
mobile visitors and long protocol names.

## Implemented scope and non-goals

- Maintain all five workspace IDs, keyboard shortcuts, hash deep links and
  Network Doctor navigation.
- Make historical master feed + each independent protocol feed prominent,
  discoverable and searchable without fabricating numbers.
- Do **not** make the historical archive appear authenticated/current;
  preserve existing verified release artifacts and conversions.
- Keep native ES modules, no third-party CSS/fonts/images, current release
  gates, theme and locale handling.
- Avoid changing underlying proxy payloads, collector semantics and publisher
  trust checks.

### Validation path

Run `npm run lint`, `npm run test:unit`,
`python scripts/update_frontend.py --check`, `npx playwright test` and
existing GitHub PR validation. The CI/browser capture is the authority for
interaction claims; this report alone does not certify rendered visuals.
