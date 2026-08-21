# HUNTX / GatherX Frontend Design System (DESIGN.md)

## 1. Strategy & Essence

- **Artifact Type**: Cyber Telemetry & Node Intelligence Hub (Developer & Security Tool)
- **Positioning**: High-performance, zero-budget proxy configuration aggregation and node telemetry dashboard.
- **Brand Adjectives**: `Surgical`, `Kinetic`, `Hardened`, `Telemetry-Dense`, `Sovereign`.
- **Aesthetic Essence**: `Cybernetic Node Intelligence`.
- **Signature Move**: GPU-accelerated interactive 3D WebGL Telemetry Globe with animated node ping arcs, live protocol distribution telemetry, and zero-dependency standalone client-side decoder.

---

## 2. Typography System

- **Display & Monospace**: `'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace` (for metrics, protocol tags, node URIs, latency, hashes).
- **Body & Interface**: `'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` (for navigation, headings, labels, documentation).
- **Modular Scale**: `1.250` (Major Third):
  - `text-xs`: 0.75rem (12px)
  - `text-sm`: 0.875rem (14px)
  - `text-base`: 1.000rem (16px)
  - `text-lg`: 1.125rem (18px)
  - `text-xl`: 1.250rem (20px)
  - `text-2xl`: 1.500rem (24px)
  - `text-3xl`: 1.875rem (30px)
  - `text-4xl`: 2.250rem (36px)

---

## 3. Color Architecture (OKLCH & Hex Equivalence)

| Role | Token Name | OKLCH Value | Fallback Hex | Purpose |
|---|---|---|---|---|
| Deep Void | `--bg-void` | `oklch(12% 0.02 260)` | `#070a0f` | Background canvas |
| Surface Primary | `--bg-surface` | `oklch(16% 0.03 260)` | `#0e131d` | Card panels, header, dialogs |
| Surface Elevated | `--bg-elevated` | `oklch(20% 0.04 255)` | `#141b29` | Hover states, active tabs, inputs |
| Border Subtle | `--border-subtle` | `oklch(26% 0.04 250)` | `#1d2638` | Structural grid, card borders |
| Border Glow | `--border-glow` | `oklch(65% 0.15 210 / 0.4)` | `rgba(0, 210, 255, 0.4)` | Focus rings, active cards |
| Text Primary | `--text-main` | `oklch(95% 0.01 240)` | `#edf2f9` | Primary headings, titles, active data |
| Text Muted | `--text-muted` | `oklch(68% 0.04 240)` | `#8a99b5` | Secondary text, descriptions |
| Accent Cyan | `--accent-cyan` | `oklch(76% 0.16 210)` | `#00d2ff` | Primary action, active indicators, globe glow |
| VLESS Emerald | `--proto-vless` | `oklch(75% 0.18 150)` | `#10b981` | VLESS protocol badges and nodes |
| VMess Amber | `--proto-vmess` | `oklch(78% 0.17 75)` | `#f59e0b` | VMess protocol badges and nodes |
| Trojan Violet | `--proto-trojan` | `oklch(72% 0.18 290)` | `#a855f7` | Trojan protocol badges and nodes |
| Shadowsocks Sky | `--proto-ss` | `oklch(74% 0.16 230)` | `#38bdf8` | Shadowsocks protocol badges |
| Hysteria Rose | `--proto-hysteria`| `oklch(68% 0.22 15)` | `#f43f5e` | Hysteria / Hysteria2 protocol badges |

---

## 4. WebGL 3D Globe Specification

- **Renderer**: Pure WebGL 2.0 / 1.0 canvas engine with dynamic fallback to 2D isometric canvas.
- **DPR Clamping**: `Math.min(window.devicePixelRatio || 1, 2.0)` to eliminate GPU thermal load on mobile.
- **Interaction**: Pointer drag with inertia decay, scroll zoom, and touch gesture support.
- **Node Geometry**: Spherical coordinates converted to 3D Cartesian coordinates with pulse rings and connecting flight arcs.
- **Motion Safety**: Full compliance with `window.matchMedia('(prefers-reduced-motion: reduce)')`.

---

## 5. Component State Matrix

1. **Buttons & Actions**:
   - Default: Solid/Ghost border, clear hierarchy.
   - Hover: Subtle background elevation + cyan glow border.
   - Active: Scale `0.98` tactile depression.
   - Focus-Visible: `ring-2 ring-cyan-400 ring-offset-2 ring-offset-gray-900`.
   - Copied/Success: Instant green flash with checkmark icon.
2. **Search & Filter Inputs**:
   - Default: Border `--border-subtle`, dark background.
   - Focus: Border `--accent-cyan` with soft ambient glow.
   - Clear Action: Integrated reset badge with `/` shortcut trigger.
3. **Decoder & Inspector Modal**:
   - Backdrop: `backdrop-blur-md bg-black/70`.
   - Transitions: Smooth ease-out slide-up and fade-in.
   - Raw Syntax View: Tabular breakdown of UUID, Host, Port, SNI, Path, Security, ALPN, Fingerprint.
4. **Resilience & Offline Handling**:
   - Zero hard dependencies on external CDNs.
   - Built-in embedded fallback data if `fetch('./catalog.json')` fails on `file://` or offline mode.

---

## 6. Anti-Slop Self-Audit

- [x] No generic AI clichés (no purple-gradient-on-white, no centered generic 3-card grid).
- [x] High-density, real data representation (real proxy protocols, real parameters, real URIs).
- [x] Complete WCAG 2.1 AA accessibility (keyboard focus-visible rings, ARIA labels, contrast ratio > 4.5:1).
- [x] Zero-dependency execution that never crashes on `file://` protocol or behind Iranian ISP filters.
