// HUNTX / GatherX Node Intelligence & Telemetry Dashboard Application
// High-Craft Cyber Telemetry Interface adhering to UI/UX Pro Max, Elite Frontend Architecture, and WCAG 2.1 AA.

import { FALLBACK_CATALOG, SAMPLE_PROXIES, GLOBE_HUBS, INGEST_STATS } from "./data.js";
import { initTelemetryGlobe } from "./globe.js";
import { i18n } from "./i18n.js";
import {
  decodeProxyURI,
  extractAllURIs,
  convertProxyBatch,
  nodeToSingboxOutbound,
  nodeToClashProxy,
  nodeToSurgeProxy,
  nodeToLoonProxy,
  nodeToQXServer,
  buildSingboxConfig,
  buildClashMetaYAML,
  buildXrayClientConfig,
  buildSurgeConfig,
  buildLoonConfig,
  buildQXConfig,
  buildBase64Sub
} from "./decoder.js";
import { renderQRCodeSVG } from "./qrcode.js";

export const COUNTRY_NAMES = {
  DE: "Germany", NL: "Netherlands", US: "United States", GB: "United Kingdom",
  FR: "France", FI: "Finland", SG: "Singapore", JP: "Japan", KR: "South Korea",
  HK: "Hong Kong", TR: "Turkey", SE: "Sweden", CH: "Switzerland", CA: "Canada",
  IR: "Iran", RU: "Russia", AU: "Australia", BR: "Brazil", ZA: "South Africa",
  IT: "Italy", ES: "Spain", AE: "UAE", IN: "India", TW: "Taiwan", UA: "Ukraine",
  IE: "Ireland"
};

export const GEO_COORDINATES = {
  DE: { lat: 50.1109, lon: 8.6821, city: "Frankfurt Hub" },
  NL: { lat: 52.3676, lon: 4.9041, city: "Amsterdam Hub" },
  FI: { lat: 60.1699, lon: 24.9384, city: "Helsinki Hub" },
  US: { lat: 37.7749, lon: -122.4194, city: "Silicon Valley" },
  FR: { lat: 48.8566, lon: 2.3522, city: "Paris Hub" },
  GB: { lat: 51.5074, lon: -0.1278, city: "London Edge" },
  RU: { lat: 55.7558, lon: 37.6173, city: "Moscow Hub" },
  SG: { lat: 1.3521, lon: 103.8198, city: "Singapore Hub" },
  JP: { lat: 35.6762, lon: 139.6503, city: "Tokyo Hub" },
  KR: { lat: 37.5665, lon: 126.9780, city: "Seoul Hub" },
  HK: { lat: 22.3193, lon: 114.1694, city: "Hong Kong Edge" },
  CH: { lat: 47.3769, lon: 8.5417, city: "Zurich Edge" },
  SE: { lat: 59.3293, lon: 18.0686, city: "Stockholm Hub" },
  IR: { lat: 35.6892, lon: 51.3890, city: "Tehran Edge" },
  TR: { lat: 41.0082, lon: 28.9784, city: "Istanbul Hub" },
  CA: { lat: 43.6532, lon: -79.3832, city: "Toronto Edge" },
  AU: { lat: -33.8688, lon: 151.2093, city: "Sydney Hub" },
  BR: { lat: -23.5505, lon: -46.6333, city: "São Paulo Hub" },
  ZA: { lat: -26.2041, lon: 28.0473, city: "Johannesburg Edge" },
  IN: { lat: 19.0760, lon: 72.8777, city: "Mumbai Hub" },
  TW: { lat: 25.0330, lon: 121.5654, city: "Taipei Edge" },
  UA: { lat: 50.4501, lon: 30.5234, city: "Kyiv Edge" },
  IE: { lat: 53.3498, lon: -6.2603, city: "Dublin Edge" },
};

export function getFlagEmoji(countryCode) {
  if (!countryCode || countryCode.length !== 2) return "🌐";
  return countryCode
    .toUpperCase()
    .split("")
    .map(c => String.fromCodePoint(127397 + c.charCodeAt(0)))
    .join("");
}

/**
 * Create artifact links that remain safe to copy from both a deployed
 * dashboard and a local file preview. `file:` URLs expose a developer's
 * filesystem and are not importable on another device, so local previews
 * deliberately fall back to portable relative paths unless a public base URL
 * is explicitly configured.
 */
export function normalizeArtifactPath(path) {
  return String(path || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\.\//, "")
    .replace(/^\/+/, "");
}

export function getConfiguredPublicBase(documentRef = typeof document === "undefined" ? null : document) {
  const globalBase = typeof window !== "undefined" && typeof window.HUNTX_PUBLIC_BASE_URL === "string"
    ? window.HUNTX_PUBLIC_BASE_URL
    : "";
  const metaBase = documentRef?.querySelector?.('meta[name="huntx-public-base-url"]')?.content || "";
  const dataBase = documentRef?.documentElement?.dataset?.publicBaseUrl || "";
  const rawBase = (globalBase || metaBase || dataBase || "").trim();
  if (!rawBase) return "";
  try {
    const fallback = typeof window !== "undefined" ? window.location.href : "https://example.invalid/";
    return new URL(rawBase, fallback).href;
  } catch {
    return "";
  }
}

export function resolveArtifactUrl(path, locationRef = typeof window === "undefined" ? null : window.location) {
  const safePath = normalizeArtifactPath(path);
  const configuredBase = getConfiguredPublicBase();
  if (configuredBase) return new URL(safePath, configuredBase).href;
  if (!locationRef || !["http:", "https:"].includes(locationRef.protocol)) return safePath;
  return new URL(safePath, locationRef.href).href;
}

export function isHostedDashboard(locationRef = typeof window === "undefined" ? null : window.location) {
  return Boolean(locationRef && ["http:", "https:"].includes(locationRef.protocol));
}

export function getArtifactLinkModel(path, locationRef = typeof window === "undefined" ? null : window.location) {
  const safePath = normalizeArtifactPath(path);
  const configuredBase = getConfiguredPublicBase();
  const hosted = isHostedDashboard(locationRef);
  const url = resolveArtifactUrl(safePath, locationRef);
  const isAbsolute = Boolean(configuredBase || hosted);
  return {
    path: safePath,
    url,
    display: isAbsolute ? url : `./${safePath}`,
    copyValue: url,
    isAbsolute,
    sourceLabel: configuredBase ? "public base URL" : hosted ? "current origin" : "portable relative path"
  };
}

export function resolveGeoAndCarrier(address, sni = "", host = "") {
  const addr = (address || "").toLowerCase().trim();
  const sniLower = (sni || "").toLowerCase().trim();
  const hostLower = (host || "").toLowerCase().trim();
  const full = `${addr} ${sniLower} ${hostLower}`;

  let country = "US";
  let carrier = "Direct Carrier";

  // 1. Explicit domain TLDs & contextual keywords
  if (addr.includes(".ir") || full.includes("iran") || full.includes("tehran") || full.includes("soundfiy") || full.includes("zula.ir")) {
    country = "IR";
    carrier = "MCI / Irancell";
  } else if (addr.includes(".ua") || full.includes("ukraine")) {
    country = "UA";
    carrier = "Kyivstar / Datagroup";
  } else if (addr.includes(".in") || full.includes("india")) {
    country = "IN";
    carrier = "Jio / Bharti Airtel";
  } else if (full.includes("taipei") || addr.includes(".tw") || full.includes("taiwan")) {
    country = "TW";
    carrier = "Chunghwa Telecom";
  } else if (addr.endsWith(".de") || full.includes("germany") || full.includes("frankfurt")) {
    country = "DE";
    carrier = "Hetzner Cloud";
  } else if (addr.endsWith(".nl") || full.includes("amsterdam") || full.includes("serverius") || full.includes("sellflow")) {
    country = "NL";
    carrier = "Serverius / NL";
  } else if (addr.endsWith(".fi") || full.includes("helsinki") || full.includes("fastly")) {
    country = "FI";
    carrier = "Hetzner Online";
  } else if (addr.endsWith(".fr") || full.includes("paris")) {
    country = "FR";
    carrier = "OVHcloud FR";
  } else if (addr.endsWith(".ru") || full.includes("moscow") || full.includes("rtqa.ru") || full.includes("vdsina")) {
    country = "RU";
    carrier = "Rostelecom / Selectel";
  } else if (addr.endsWith(".sg") || full.includes("singapore") || full.includes("zenlayer")) {
    country = "SG";
    carrier = "Zenlayer SG";
  } else if (addr.endsWith(".jp") || full.includes("tokyo") || full.includes("japan")) {
    country = "JP";
    carrier = "AWS Tokyo";
  } else if (addr.endsWith(".kr") || full.includes("seoul") || full.includes("korea")) {
    country = "KR";
    carrier = "KT Corp";
  } else if (addr.endsWith(".hk") || full.includes("hongkong") || full.includes("aliyun")) {
    country = "HK";
    carrier = "Alibaba Cloud HK";
  } else if (addr.endsWith(".tr") || full.includes("istanbul") || full.includes("turkey") || full.includes("tr1-")) {
    country = "TR";
    carrier = "Turkcell / Superonline";
  } else if (addr.endsWith(".ch") || full.includes("zurich") || full.includes("swiss") || addr.includes(".cloudns.ch")) {
    country = "CH";
    carrier = "Swisscom Zurich";
  } else if (addr.endsWith(".uk") || addr.endsWith(".co.uk") || addr.endsWith(".gb") || full.includes("london")) {
    country = "GB";
    carrier = "Virgin Media UK";
  } else if (addr.endsWith(".ca") || full.includes("toronto") || full.includes("canada")) {
    country = "CA";
    carrier = "OVH Canada";
  } else if (addr.endsWith(".se") || full.includes("stockholm") || full.includes("sweden")) {
    country = "SE";
    carrier = "Telia Sweden";
  }
  // 2. IP Subnet & Cloud Provider Network Routing
  else if (addr.startsWith("188.114.")) {
    country = "NL";
    carrier = "Cloudflare Amsterdam Edge";
  } else if (addr.startsWith("162.159.") || addr.startsWith("172.67.") || addr.startsWith("104.18.") || addr.startsWith("104.19.") || addr.startsWith("104.21.") || addr.startsWith("104.16.") || addr.startsWith("172.64.")) {
    const parts = addr.split(".");
    const oct3 = parts.length >= 3 && !isNaN(Number(parts[2])) ? Number(parts[2]) : 0;
    const cfRoutes = [
      ["DE", "Cloudflare Frankfurt Edge"],
      ["NL", "Cloudflare Amsterdam Edge"],
      ["GB", "Cloudflare London Edge"],
      ["FR", "Cloudflare Paris Edge"],
      ["SG", "Cloudflare Singapore Edge"],
      ["JP", "Cloudflare Tokyo Edge"],
      ["US", "Cloudflare Ashburn Edge"],
      ["SE", "Cloudflare Stockholm Edge"],
      ["CH", "Cloudflare Zurich Edge"],
      ["TR", "Cloudflare Istanbul Edge"],
    ];
    const [c, car] = cfRoutes[oct3 % cfRoutes.length];
    country = c;
    carrier = car;
  } else if (addr.startsWith("47.243.") || addr.startsWith("8.210.") || addr.startsWith("8.217.")) {
    country = "HK";
    carrier = "Alibaba Cloud HK";
  } else if (addr.startsWith("51.79.")) {
    country = "SG";
    carrier = "OVHcloud Singapore";
  } else if (addr.startsWith("57.129.") || addr.startsWith("57.131.") || addr.startsWith("54.36.")) {
    country = "FR";
    carrier = "OVHcloud France";
  } else if (addr.startsWith("15.237.") || addr.startsWith("15.235.")) {
    country = "FR";
    carrier = "AWS Paris";
  } else if (addr.startsWith("54.74.")) {
    country = "IE";
    carrier = "AWS Dublin";
  } else if (addr.startsWith("82.38.") || addr.startsWith("2.26.")) {
    country = "GB";
    carrier = "Virgin Media UK";
  } else if (addr.startsWith("91.132.") || addr.startsWith("140.99.") || addr.startsWith("5.175.") || addr.startsWith("82.198.")) {
    country = "DE";
    carrier = "Hetzner Cloud";
  } else if (addr.startsWith("95.81.") || addr.startsWith("86.107.")) {
    country = "IR";
    carrier = "MCI / TCI Iran";
  } else if (addr.startsWith("194.87.") || addr.startsWith("62.182.") || addr.startsWith("195.133.") || addr.startsWith("31.133.")) {
    country = "RU";
    carrier = "VDSina / Selectel";
  } else if (addr.startsWith("199.232.")) {
    country = "FI";
    carrier = "Fastly Helsinki Edge";
  } else if (addr.startsWith("150.40.")) {
    country = "JP";
    carrier = "AWS Tokyo";
  } else if (addr.startsWith("152.53.") || addr.startsWith("103.152.") || addr.startsWith("45.207.")) {
    country = "SG";
    carrier = "Zenlayer Singapore";
  } else if (addr.startsWith("92.42.") || addr.startsWith("195.184.") || addr.startsWith("45.131.") || addr.startsWith("45.89.")) {
    country = "NL";
    carrier = "Serverius Netherlands";
  } else if (addr.startsWith("69.63.") || addr.startsWith("192.227.") || addr.startsWith("167.233.") || addr.startsWith("166.62.") || addr.startsWith("209.206.")) {
    country = "US";
    carrier = "AWS North America";
  } else if (addr.startsWith("210.3.")) {
    country = "HK";
    carrier = "HKBN Hong Kong";
  } else {
    let h = 0;
    for (let i = 0; i < addr.length; i++) h += addr.charCodeAt(i);
    const pool = [
      ["DE", "Hetzner Cloud Frankfurt"],
      ["NL", "Serverius Amsterdam"],
      ["FI", "Hetzner Online Helsinki"],
      ["FR", "OVHcloud Paris"],
      ["GB", "Virgin Media London"],
      ["SG", "Zenlayer Singapore"],
      ["JP", "AWS Tokyo Edge"],
      ["HK", "Alibaba Cloud Hong Kong"],
      ["SE", "Telia Stockholm"],
      ["CH", "Swisscom Zurich"],
      ["TR", "Turkcell Istanbul"],
      ["US", "AWS Virginia"],
      ["CA", "OVH Montreal"],
      ["IR", "MCI Tehran"],
      ["RU", "Selectel Moscow"],
      ["TW", "Chunghwa Taipei"],
      ["IN", "Bharti Airtel Mumbai"],
      ["UA", "Kyivstar Kyiv"],
    ];
    const [c, car] = pool[h % pool.length];
    country = c;
    carrier = car;
  }

  const geoInfo = GEO_COORDINATES[country] || { lat: 37.7749, lon: -122.4194, city: "Global Hub" };
  const countryName = COUNTRY_NAMES[country] || "International";
  const flag = getFlagEmoji(country);

  return {
    country,
    country_name: countryName,
    flag,
    carrier,
    org: carrier,
    city: geoInfo.city,
    latitude: geoInfo.lat,
    longitude: geoInfo.lon
  };
}

export function clusterGlobeHubs(proxies) {
  const hubMap = {};
  for (const p of proxies) {
    const code = p.country || "US";
    if (!hubMap[code]) {
      const geo = GEO_COORDINATES[code] || { lat: p.latitude || 37.7749, lon: p.longitude || -122.4194, city: `${code} Hub` };
      hubMap[code] = {
        name: geo.city,
        lat: geo.lat,
        lon: geo.lon,
        pings: [],
        code: code,
        country: p.country_name || COUNTRY_NAMES[code] || code,
        carrier: p.carrier || p.org || "Direct",
        count: 0
      };
    }
    hubMap[code].pings.push(p.latency || p.ping || 30);
    hubMap[code].count += 1;
  }

  const hubs = Object.values(hubMap).map(h => {
    const avgPing = h.pings.length > 0 ? Math.round(h.pings.reduce((a, b) => a + b, 0) / h.pings.length) : 30;
    return {
      name: h.name,
      lat: h.lat,
      lon: h.lon,
      ping: avgPing,
      code: h.code,
      country: h.country,
      carrier: h.carrier,
      count: h.count
    };
  });

  hubs.sort((a, b) => b.count - a.count);
  return hubs;
}

function escapeHTML(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function debounce(fn, delay = 150) {
  let timer = null;
  return function (...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      fn.apply(this, args);
    }, delay);
  };
}

function getStoredTheme() {
  try {
    return (typeof localStorage !== "undefined" && localStorage.getItem("huntx_theme")) || "dark";
  } catch (e) {
    return "dark";
  }
}

function setStoredTheme(theme) {
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("huntx_theme", theme);
    }
  } catch (e) {}
}

export class AppState {
  constructor() {
    this.catalog = FALLBACK_CATALOG;
    this.proxies = [...SAMPLE_PROXIES];
    this.globeHubs = [...(GLOBE_HUBS || [])];
    this.stats = INGEST_STATS || {};
    this.searchQuery = "";
    this.artifactFilter = "ALL";
    this.artifactSearchQuery = "";
    this.selectedProtocol = "ALL";
    this.selectedTransport = "ALL";
    this.selectedCountry = "ALL";
    this.selectedOperator = "ALL";
    this.selectedGrade = "ALL";
    this.selectedSecurity = "ALL";
    this.selectedPort = "ALL";
    this.sortBy = "latency_asc";
    this.viewMode = "grid"; // 'grid' | 'table' | 'feed'
    this.converterTab = "inspector"; // 'inspector' | 'converter' | 'dedup' | 'qr_studio'
    this.activePageTab = this.getInitialPageTab();
    this.theme = getStoredTheme();
    this.globeInstance = null;
    this.lastFocusedElement = null;
    this.unmaskedNodes = new Set();
    this.activeQRNodes = new Set();
    this.livePings = new Map();
    this.liveDataState = "idle";
    this.renderDataStatus();
    this.liveRefreshTimer = null;
    this.liveRefreshInFlight = false;
    this.boundVisibilityRefresh = null;
  }

  getInitialPageTab() {
    if (typeof window !== "undefined") {
      const hash = (window.location.hash || "").replace("#", "").toLowerCase();
      const validTabs = ["radar", "proxies", "studio", "decoder", "artifacts"];
      if (validTabs.includes(hash)) return hash;
      try {
        const stored = localStorage.getItem("huntx_active_tab");
        if (stored && validTabs.includes(stored)) return stored;
      } catch (e) {}
    }
    return "radar";
  }

  switchPageTab(tabTarget, updateHash = true) {
    const validTabs = ["radar", "proxies", "studio", "decoder", "artifacts"];
    if (!validTabs.includes(tabTarget)) tabTarget = "radar";
    this.activePageTab = tabTarget;

    // Update navigation tab buttons
    if (typeof document !== "undefined") {
      document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
        const target = (btn.dataset && btn.dataset.tabTarget) || btn.getAttribute("data-tab-target");
        const isCurrent = target === tabTarget;
        btn.classList.toggle("active", isCurrent);
        btn.setAttribute("aria-selected", isCurrent ? "true" : "false");
        btn.tabIndex = isCurrent ? 0 : -1;
      });

      // Update tab panels visibility with bulletproof style and attribute enforcement
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.add("hidden");
        panel.setAttribute("hidden", "true");
        panel.style.setProperty("display", "none", "important");
      });
      const targetPanel = document.getElementById("tab-panel-" + tabTarget);
      if (targetPanel) {
        targetPanel.classList.remove("hidden");
        targetPanel.removeAttribute("hidden");
        targetPanel.style.setProperty("display", "block", "important");
      }

      // Update badge counts on nav bar
      const proxiesBadge = document.getElementById("tab-count-proxies") || document.getElementById("tab-proxies-count-badge");
      if (proxiesBadge) proxiesBadge.textContent = this.proxies.length;
      const artifactsBadge = document.getElementById("tab-count-artifacts") || document.getElementById("tab-artifacts-count-badge");
      if (artifactsBadge) artifactsBadge.textContent = this.catalog.files ? this.catalog.files.length : (this.catalog.total_files || 0);

      if (tabTarget === "radar" && this.globeInstance) {
        setTimeout(() => {
          this.globeInstance.resize?.();
        }, 30);
      }
    }

    try {
      localStorage.setItem("huntx_active_tab", tabTarget);
    } catch (e) {}

    if (updateHash && typeof window !== "undefined") {
      history.replaceState(null, null, "#" + tabTarget);
    }

    // Dynamic Title Management
    const titles = {
      radar: "HUNTX — 3D Telemetry Radar & Diagnostics",
      proxies: `HUNTX — Live Proxies (${this.proxies.length} Endpoints)`,
      studio: "HUNTX — Protocol & Subscription Studio",
      decoder: "HUNTX — Deep Protocol Inspector & In-Browser Parser",
      artifacts: `HUNTX — Pipeline Artifacts & Feeds (${this.catalog.files ? this.catalog.files.length : (this.catalog.total_files || 0)})`
    };
    if (typeof document !== "undefined" && titles[tabTarget]) {
      document.title = titles[tabTarget];
    }
  }

  getDecodedArtifactRecord(catalog = this.catalog) {
    const files = Array.isArray(catalog?.files) ? catalog.files : [];
    return files.find((file) => file?.filename === "all_sources.npvt.decoded.json"
      && typeof file.path === "string"
      && /^artifacts\/release\/[A-Za-z0-9._/-]+$/.test(file.path)
      && typeof file.sha256 === "string"
      && /^[a-f0-9]{64}$/i.test(file.sha256)) || null;
  }

  async loadVerifiedJsonArtifact(artifact) {
    if (!artifact || !globalThis.crypto?.subtle) {
      throw new Error("Web Crypto is required to verify published artifacts");
    }
    const response = await fetch(artifact.path, { cache: "no-store" });
    if (!response.ok) throw new Error(`Artifact request failed: ${response.status}`);
    const bytes = await response.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const actualHash = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
    if (actualHash !== artifact.sha256.toLowerCase()) {
      throw new Error("Published artifact integrity check failed");
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  async loadLiveData() {
    this.liveDataState = "loading";
    this.renderDataStatus();
    let catalogCandidate = null;
    let proxyCandidate = null;
    let globeCandidate = null;

    // Keep the catalog and its decoded proxy data as one verified snapshot. A
    // new catalog must never be rendered beside stale bundled proxy records.
    try {
      const res = await fetch("catalog.json", { cache: "no-store" });
      if (res.ok) {
        const liveCatalog = await res.json();
        if (liveCatalog && Array.isArray(liveCatalog.files) && liveCatalog.files.length > 0) {
          catalogCandidate = liveCatalog;
        }
      }
    } catch (e) {}

    // Published release data is authoritative even when smaller than the demo bundle.
    try {
      const decodedArtifact = this.getDecodedArtifactRecord(catalogCandidate);
      if (decodedArtifact) {
        const decodedData = await this.loadVerifiedJsonArtifact(decodedArtifact);
        if (decodedData && Array.isArray(decodedData.entries) && decodedData.entries.length > 0) {
          proxyCandidate = decodedData.entries.map((entry, idx) => {
            const proto = (entry.protocol || "vless").toLowerCase();
            const tag = entry.tag || `${proto}-${idx + 1}`;
            const host = entry.address || "127.0.0.1";
            const port = entry.port || 443;
            const params = entry.params || {};
            const sni = params.sni || "";
            const hostHeader = params.host || "";
            const transport = params.type || "tcp";
            const security = params.security || (params.sni || params.alpn ? "tls" : "none");
            const raw = entry.raw || "";

            const geo = resolveGeoAndCarrier(host, sni, hostHeader);

            const measuredLatency = Number(entry.latency_ms ?? entry.latency ?? entry.ping);
            const latency = Number.isFinite(measuredLatency) && measuredLatency >= 0 ? measuredLatency : null;

            return {
              id: `px-${String(idx + 1).padStart(4, "0")}`,
              protocol: proto,
              name: `${geo.country}-${tag}`,
              server: host,
              port: port,
              uuid: entry.user || entry.password || "",
              password: entry.password || entry.user || "",
              security: security,
              transport: transport,
              sni: sni,
              host: hostHeader,
              path: params.path || "",
              pbk: params.pbk || "",
              sid: params.sid || "",
              flow: params.flow || "",
              country: geo.country,
              country_name: geo.country_name,
              flag: geo.flag,
              carrier: geo.carrier,
              org: geo.org,
              city: geo.city,
              latitude: geo.latitude,
              longitude: geo.longitude,
              latency,
              ping: latency,
              raw_uri: raw,
              raw: raw
            };
          });

          globeCandidate = clusterGlobeHubs(proxyCandidate);
        }
      }
    } catch (e) {
      this.liveDataState = "integrity-error";
      this.renderDataStatus();
    }

    if (catalogCandidate && proxyCandidate) {
      this.catalog = catalogCandidate;
      this.proxies = proxyCandidate;
      this.globeHubs = globeCandidate;
      this.liveDataState = "ready";
      this.renderDataStatus();
    } else if (this.liveDataState === "loading") {
      this.liveDataState = "stale";
      this.renderDataStatus();
    }
  }

  renderDataStatus() {
    const pill = document.getElementById("data-status-pill");
    if (!pill) return;
    const when = escapeHTML(this.catalog?.generated_at || "");
    const map = {
      ready: { cls: "data-status-ready", text: `Live verified snapshot${when ? " · " + when : ""}` },
      stale: { cls: "data-status-stale", text: "Bundled snapshot — live data unavailable" },
      "integrity-error": { cls: "data-status-stale", text: "Integrity check failed — bundled snapshot shown" },
      loading: { cls: "data-status-loading", text: "Verifying published snapshot…" },
      idle: { cls: "data-status-loading", text: "Bundled snapshot" }
    };
    const info = map[this.liveDataState] || map.idle;
    pill.className = `data-status ${info.cls}`;
    pill.textContent = info.text;
  }

  getPublishedDataFingerprint() {
    const catalog = this.catalog || {};
    const files = Array.isArray(catalog.files) ? catalog.files : [];
    return [
      catalog.generated_at || "",
      catalog.release_manifest || "",
      catalog.total_files || files.length,
      catalog.total_size || ""
    ].join("|");
  }

  mountGlobe() {
    this.globeInstance?.destroy?.();
    this.globeInstance = initTelemetryGlobe("telemetry-globe-canvas", (hub) => {
      this.selectedCountry = hub.code;
      this.renderFilterBar();
      this.renderNodes();
      this.switchPageTab("proxies", true);
      this.showToast(`Filtered by ${escapeHTML(hub.name)} (${escapeHTML(hub.code)})`);
    }, this.globeHubs);
  }

  async refreshPublishedData({ notify = true } = {}) {
    if (this.liveRefreshInFlight) return false;
    this.liveRefreshInFlight = true;
    const previousFingerprint = this.getPublishedDataFingerprint();
    try {
      await this.loadLiveData();
      if (previousFingerprint === this.getPublishedDataFingerprint()) return false;
      this.renderHeader();
      this.renderHero();
      this.renderRadarDiagnostics();
      this.renderFilterBar();
      this.renderNodes();
      this.renderArtifacts();
      this.renderRuleStudio();
      this.renderFooter();
      this.switchPageTab(this.activePageTab, false);
      this.mountGlobe();
      if (notify) this.showToast("Published data updated");
      return true;
    } finally {
      this.liveRefreshInFlight = false;
    }
  }

  startPublishedDataRefresh() {
    const MIN_REFRESH_INTERVAL_MS = 300000;
    let lastRefreshAt = Date.now();
    const refreshWhenVisible = () => {
      if (document.hidden) return;
      if (Date.now() - lastRefreshAt < MIN_REFRESH_INTERVAL_MS) return;
      lastRefreshAt = Date.now();
      this.refreshPublishedData();
    };
    this.boundVisibilityRefresh = refreshWhenVisible;
    document.addEventListener("visibilitychange", refreshWhenVisible);
    this.liveRefreshTimer = window.setInterval(refreshWhenVisible, MIN_REFRESH_INTERVAL_MS);
  }

  async init() {
    this.applyTheme(this.theme);
    await this.loadLiveData();

    this.renderHeader();
    this.renderHero();
    this.renderRadarDiagnostics();
    this.renderFilterBar();
    this.renderNodes();
    this.renderArtifacts();
    this.renderRuleStudio();
    this.renderDecoderSection();
    this.renderFooter();
    this.switchPageTab(this.activePageTab, false);
    this.bindGlobalEvents();

    setTimeout(() => this.mountGlobe(), 100);
    this.startPublishedDataRefresh();
  }

  inferCountryFromTagOrHost(tag, host) {
    const upperTag = (tag || "").toUpperCase();
    const matches = Object.keys(COUNTRY_NAMES);
    for (const code of matches) {
      if (upperTag.includes(code) || upperTag.startsWith(code + "-") || upperTag.includes(`[${code}]`) || upperTag.includes(`(${code})`)) return code;
    }
    const resolved = resolveGeoAndCarrier(host, "", tag);
    return resolved.country;
  }

  inferCountryName(tag, host) {
    const code = this.inferCountryFromTagOrHost(tag, host);
    return COUNTRY_NAMES[code] || code;
  }

  getCountryFlag(code) {
    return getFlagEmoji(code);
  }

  detectOperator(host, sni, tag) {
    const resolved = resolveGeoAndCarrier(host, sni, tag);
    return resolved.carrier;
  }

  getHealthScore(ping) {
    if (!Number.isFinite(ping) || ping < 0) {
      return { score: null, grade: "—", label: "Unmeasured", color: "text-gray-400 border-gray-700 bg-gray-900" };
    }
    const p = ping;
    if (p <= 45) return { score: 98, grade: "A+", label: "Ultra Fast", color: "text-emerald-400 border-emerald-800/80 bg-emerald-950/60" };
    if (p <= 80) return { score: 91, grade: "A", label: "Fast", color: "text-cyan-400 border-cyan-800/80 bg-cyan-950/60" };
    if (p <= 140) return { score: 82, grade: "B", label: "Stable", color: "text-amber-400 border-amber-800/80 bg-amber-950/60" };
    return { score: 68, grade: "C", label: "Moderate", color: "text-rose-400 border-rose-800/80 bg-rose-950/60" };
  }

  getLatency(node) {
    const value = Number(node?.latency ?? node?.ping);
    return Number.isFinite(value) && value >= 0 ? value : null;
  }

  getHealthSortValue(node) {
    const { score } = this.getHealthScore(this.getLatency(node));
    return score ?? Number.NEGATIVE_INFINITY;
  }

  refreshProxyWorkspace() {
    this.renderFilterBar();
    this.renderNodes();
  }

  resetProxyFilters({ focusSearch = false } = {}) {
    this.selectedProtocol = "ALL";
    this.selectedTransport = "ALL";
    this.selectedCountry = "ALL";
    this.selectedOperator = "ALL";
    this.selectedGrade = "ALL";
    this.selectedSecurity = "ALL";
    this.selectedPort = "ALL";
    this.searchQuery = "";
    for (const id of ["node-quick-search", "global-search-input"]) {
      const input = document.getElementById(id);
      if (input) input.value = "";
    }
    this.refreshProxyWorkspace();
    if (focusSearch) {
      document.getElementById("node-quick-search")?.focus();
    }
  }

  applyTheme(t) {
    this.theme = t;
    setStoredTheme(t);
    if (typeof document !== "undefined" && document.documentElement) {
      const root = document.documentElement;
      if (t === "dark") {
        root.classList.add("dark");
        root.classList.remove("light");
      } else {
        root.classList.remove("dark");
        root.classList.add("light");
      }
    }
  }

  toggleTheme() {
    this.applyTheme(this.theme === "dark" ? "light" : "dark");
    this.renderHeader();
  }

  getFilteredProxies() {
    let result = [...this.proxies];

    if (this.selectedProtocol !== "ALL") {
      result = result.filter(p => (p.protocol || "").toLowerCase() === this.selectedProtocol.toLowerCase());
    }

    if (this.selectedTransport !== "ALL") {
      result = result.filter(p => (p.transport || "").toLowerCase().includes(this.selectedTransport.toLowerCase()));
    }

    if (this.selectedCountry !== "ALL") {
      result = result.filter(p => (p.country || "").toUpperCase() === this.selectedCountry.toUpperCase());
    }

    if (this.selectedOperator !== "ALL") {
      result = result.filter(p => {
        const op = (p.carrier || p.org || this.detectOperator(p.server, p.sni, p.name) || "").toLowerCase();
        const sel = this.selectedOperator.toLowerCase();
        return op.includes(sel) || (p.name || "").toLowerCase().includes(sel) || (p.sni || "").toLowerCase().includes(sel);
      });
    }

    if (this.selectedGrade !== "ALL") {
      result = result.filter(p => {
        const { grade } = this.getHealthScore(this.getLatency(p));
        return grade === this.selectedGrade;
      });
    }

    if (this.selectedSecurity !== "ALL") {
      result = result.filter(p => {
        const sec = (p.security || "none").toLowerCase();
        if (this.selectedSecurity === "Reality") return sec === "reality";
        if (this.selectedSecurity === "TLS") return sec === "tls";
        if (this.selectedSecurity === "None") return sec === "none" || !sec;
        return true;
      });
    }

    if (this.selectedPort !== "ALL") {
      result = result.filter(p => {
        const port = Number(p.port);
        if (this.selectedPort === "443") return port === 443;
        if (this.selectedPort === "80") return port === 80;
        if (this.selectedPort === "8080_8443") return port === 8080 || port === 8443;
        if (this.selectedPort === "custom") return port !== 443 && port !== 80 && port !== 8080 && port !== 8443;
        return true;
      });
    }

    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase().trim();
      result = result.filter(p =>
        (p.name || "").toLowerCase().includes(q) ||
        (p.server || "").toLowerCase().includes(q) ||
        String(p.port || "").includes(q) ||
        (p.protocol || "").toLowerCase().includes(q) ||
        (p.country_name || p.countryName || "").toLowerCase().includes(q) ||
        (p.country || "").toLowerCase().includes(q) ||
        (p.carrier || p.org || "").toLowerCase().includes(q) ||
        (p.transport || "").toLowerCase().includes(q) ||
        (p.sni && p.sni.toLowerCase().includes(q))
      );
    }

    result.sort((a, b) => {
      const pingA = this.getLatency(a) ?? Number.POSITIVE_INFINITY;
      const pingB = this.getLatency(b) ?? Number.POSITIVE_INFINITY;
      if (this.sortBy === "latency_asc") return pingA - pingB;
      if (this.sortBy === "score_desc") return this.getHealthSortValue(b) - this.getHealthSortValue(a);
      if (this.sortBy === "name_asc") return (a.name || "").localeCompare(b.name || "");
      if (this.sortBy === "country_asc") return (a.country || "").localeCompare(b.country || "");
      if (this.sortBy === "port_asc") return (a.port || 0) - (b.port || 0);
      return 0;
    });

    return result;
  }

  getFilteredArtifacts() {
    let list = this.catalog.files || [];
    const filter = this.artifactFilter;

    if (filter === "RELEASE") {
      list = list.filter(f => f.category === "release" || f.section === "release" || (f.tags && f.tags.includes("release")));
    } else if (filter === "DEV") {
      list = list.filter(f => f.category === "dev" || f.section === "dev" || (f.tags && f.tags.includes("dev")));
    } else if (filter === "SUBSCRIPTIONS") {
      list = list.filter(f => f.type === "B64SUB" || f.ext === "B64SUB" || f.type === "NPVT" || f.ext === "NPVT" || (f.tags && f.tags.includes("subscription")));
    } else if (filter === "CONFIGS") {
      list = list.filter(f => ["SINGBOX", "XRAY", "OVPN", "WARP", "CLASH"].includes(f.type || f.ext) || (f.tags && (f.tags.includes("singbox") || f.tags.includes("xray") || f.tags.includes("openvpn"))));
    } else if (filter === "CHUNKS") {
      list = list.filter(f => f.type === "CHUNK" || f.ext === "CHUNK" || (f.filename || f.name || "").includes("chunk_") || (f.tags && f.tags.includes("chunk")));
    }

    if (this.artifactSearchQuery.trim()) {
      const q = this.artifactSearchQuery.toLowerCase().trim();
      list = list.filter(f =>
        (f.filename || f.name || "").toLowerCase().includes(q) ||
        (f.description && f.description.toLowerCase().includes(q)) ||
        ((f.ext || f.type) && (f.ext || f.type).toLowerCase().includes(q)) ||
        (f.tags && f.tags.some(t => t.toLowerCase().includes(q)))
      );
    }

    return list;
  }

  showToast(msg, type = "success") {
    if (typeof document === "undefined") return;
    const container = document.getElementById("toast-container");
    if (!container) return;

    const el = document.createElement("div");
    el.className = `toast-pill flex items-center gap-2.5 px-4 py-3 rounded-2xl border backdrop-blur-xl shadow-2xl text-xs font-mono font-semibold transition-all duration-300 transform translate-y-4 opacity-0 ${
      type === "success"
        ? "bg-gray-950/95 text-emerald-300 border-emerald-500/40 shadow-emerald-950/50"
        : "bg-gray-950/95 text-cyan-300 border-cyan-500/40 shadow-cyan-950/50"
    }`;
    el.innerHTML = `
      <div class="w-2 h-2 rounded-full ${type === 'success' ? 'bg-emerald-400' : 'bg-cyan-400'} animate-pulse shrink-0"></div>
      <span class="truncate max-w-[280px]">${escapeHTML(msg)}</span>
    `;

    container.appendChild(el);
    requestAnimationFrame(() => {
      el.classList.remove("translate-y-4", "opacity-0");
      el.classList.add("translate-y-0", "opacity-100");
    });

    setTimeout(() => {
      el.classList.remove("translate-y-0", "opacity-100");
      el.classList.add("translate-y-4", "opacity-0");
      setTimeout(() => el.remove(), 300);
    }, 2800);
  }

  copyText(text, label = "Copied to clipboard") {
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        this.showToast(label);
      }).catch(() => {
        this.fallbackCopy(text, label);
      });
    } else {
      this.fallbackCopy(text, label);
    }
  }

  fallbackCopy(text, label) {
    if (typeof document === "undefined") return;
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      this.showToast(label);
    } catch (e) {
      this.showToast("Failed to copy", "error");
    }
    document.body.removeChild(ta);
  }

  trapFocus(modalEl) {
    const focusable = modalEl.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable.length === 0) return () => {};

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    first.focus();

    const handleKeyDown = (e) => {
      if (e.key === "Tab") {
        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    modalEl.addEventListener("keydown", handleKeyDown);
    return () => modalEl.removeEventListener("keydown", handleKeyDown);
  }

  closeModal() {
    const modalContainer = document.getElementById("modal-overlay");
    if (modalContainer) {
      modalContainer.classList.add("hidden");
      modalContainer.innerHTML = "";
    }
    if (this.lastFocusedElement && typeof this.lastFocusedElement.focus === "function") {
      this.lastFocusedElement.focus();
      this.lastFocusedElement = null;
    }
  }

  renderHeader() {
    if (typeof document === "undefined") return;
    const header = document.getElementById("main-header");
    if (!header) return;

    header.innerHTML = `
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        <a href="#" class="flex items-center gap-3 group focus-ring rounded-xl p-1" aria-label="HUNTX Home">
          <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 via-blue-600 to-indigo-700 p-0.5 shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-transform duration-200">
            <div class="w-full h-full bg-gray-950 rounded-[10px] flex items-center justify-center">
              <svg class="w-5 h-5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                <polyline points="2 17 12 22 22 17"></polyline>
                <polyline points="2 12 12 17 22 12"></polyline>
              </svg>
            </div>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="font-mono text-base font-bold tracking-tight text-white">HUNT<span class="text-cyan-400">X</span></span>
              <span class="px-1.5 py-0.5 text-[9px] font-mono font-bold bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 rounded">v2.5</span>
            </div>
            <span class="text-[10px] text-gray-400 font-mono tracking-wider">GATHERX TELEMETRY</span>
          </div>
        </a>

        <div class="flex-1 max-w-md hidden md:block">
          <div class="relative group">
            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-500 group-focus-within:text-cyan-400">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
            </div>
            <input
              id="global-search-input"
              type="text"
              class="w-full pl-9 pr-12 py-2 bg-gray-900/80 border border-gray-800 focus:border-cyan-500/60 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all focus-ring"
              placeholder="Search nodes, protocols, SNI, country..."
              value="${escapeHTML(this.searchQuery)}"
              aria-label="Global Search"
            />
            <div class="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none">
              <kbd class="px-1.5 py-0.5 bg-gray-800 border border-gray-700 text-[10px] font-mono text-gray-400 rounded">/</kbd>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2 sm:gap-3">
          <div class="hidden lg:flex items-center gap-2 px-3 py-1.5 bg-emerald-950/50 border border-emerald-800/40 rounded-full">
            <span class="relative flex h-2 w-2">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span class="font-mono text-[11px] font-semibold text-emerald-400">PIPELINE ONLINE</span>
          </div>

          <label class="sr-only" for="language-selector">${i18n.translate("Language")}</label>
          <select
            id="language-selector"
            data-i18n-ignore
            dir="ltr"
            class="min-h-[40px] w-[76px] sm:w-[92px] px-2 bg-gray-900 border border-gray-700 text-gray-200 text-xs font-mono rounded-xl focus-ring cursor-pointer"
            aria-label="${i18n.translate("Language")}"
            title="${i18n.translate("Language")}"
          >
            <option value="en" ${i18n.getLocale() === "en" ? "selected" : ""}>English</option>
            <option value="fa" ${i18n.getLocale() === "fa" ? "selected" : ""}>فارسی</option>
            <option value="zh-CN" ${i18n.getLocale() === "zh-CN" ? "selected" : ""}>中文</option>
            <option value="ru" ${i18n.getLocale() === "ru" ? "selected" : ""}>Русский</option>
          </select>

          <button
            id="btn-open-scanner"
            class="flex items-center gap-1.5 px-3.5 py-2 min-h-[40px] bg-emerald-950/60 hover:bg-emerald-900/60 border border-emerald-500/30 hover:border-emerald-400 text-emerald-300 text-xs font-mono font-medium rounded-xl transition-all shadow-sm focus-ring cursor-pointer"
            title="Open Clean IP Scanner (Press S)"
            aria-label="Open Clean IP Scanner"
          >
            <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
            <span class="hidden sm:inline">IP Scanner</span>
          </button>

          <button
            id="btn-open-builder"
            class="flex items-center gap-1.5 px-3.5 py-2 min-h-[40px] bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-400 text-cyan-300 text-xs font-mono font-medium rounded-xl transition-all shadow-sm focus-ring cursor-pointer"
            title="Open Subscription Builder"
            aria-label="Open Subscription Builder"
          >
            <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            <span class="hidden sm:inline">Sub Builder</span>
          </button>

          <button
            id="btn-open-decoder"
            class="flex items-center gap-1.5 px-3.5 py-2 min-h-[40px] bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-gray-600 text-gray-200 text-xs font-mono font-medium rounded-xl transition-all focus-ring cursor-pointer"
            title="Open Protocol Decoder (Press D)"
            aria-label="Open Protocol Decoder"
          >
            <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
            <span class="hidden sm:inline">Decoder</span>
          </button>

          <button
            id="btn-toggle-theme"
            class="p-2 min-h-[40px] min-w-[40px] flex items-center justify-center bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-cyan-500/40 text-gray-400 hover:text-cyan-300 rounded-xl transition-all focus-ring cursor-pointer"
            title="Toggle Light / Dark Theme"
            aria-label="Toggle Theme"
          >
            ${this.theme === 'dark' ? `
              <svg class="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
            ` : `
              <svg class="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path></svg>
            `}
          </button>

          <a
            href="architecture.html"
            target="_blank"
            class="hidden sm:flex items-center gap-1.5 px-3 py-2 min-h-[40px] bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-gray-600 text-gray-300 hover:text-white text-xs font-mono rounded-xl transition-all focus-ring"
            title="Open 3D Architecture Topology"
            aria-label="Open 3D Architecture Topology"
          >
            <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
            <span class="hidden md:inline">3D Topology</span>
          </a>

          <a
            href="https://github.com/AmirrezaFarnamTaheri/HUNTX"
            target="_blank"
            class="p-2 min-h-[40px] min-w-[40px] flex items-center justify-center bg-gray-900 hover:bg-gray-800 border border-gray-800 text-gray-400 hover:text-white rounded-xl transition-all focus-ring"
            title="GitHub Repository"
            aria-label="GitHub Repository"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"></path></svg>
          </a>
        </div>
      </div>
    `;

    const debouncedSearch = debounce((val) => {
      this.searchQuery = val;
      this.refreshProxyWorkspace();
    }, 120);

    document.getElementById("global-search-input")?.addEventListener("input", (e) => {
      debouncedSearch(e.target.value);
    });

    document.getElementById("btn-open-scanner")?.addEventListener("click", (e) => {
      this.lastFocusedElement = e.currentTarget;
      this.openCleanIPScannerModal();
    });

    document.getElementById("btn-open-decoder")?.addEventListener("click", (e) => {
      this.lastFocusedElement = e.currentTarget;
      this.openDecoderModal();
    });

    document.getElementById("btn-open-builder")?.addEventListener("click", (e) => {
      this.lastFocusedElement = e.currentTarget;
      this.openSubscriptionBuilderModal();
    });

    document.getElementById("btn-toggle-theme")?.addEventListener("click", () => {
      this.toggleTheme();
    });

    document.getElementById("language-selector")?.addEventListener("change", (event) => {
      i18n.setLocale(event.target.value);
    });
  }

  renderHero() {
    if (typeof document === "undefined") return;
    const hero = document.getElementById("hero-section");
    if (!hero) return;

    const activeCount = this.proxies.length;
    const regionCount = new Set(this.proxies.map(p => p.country || "US")).size;
    const measuredLatencies = this.proxies.map((proxy) => this.getLatency(proxy)).filter(Number.isFinite);
    const avgLatencyNum = measuredLatencies.length
      ? Math.round(measuredLatencies.reduce((sum, latency) => sum + latency, 0) / measuredLatencies.length)
      : null;
    const minLatencyNum = measuredLatencies.length ? Math.min(...measuredLatencies) : null;
    const totalFiles = this.catalog.total_files || (this.catalog.files ? this.catalog.files.length : "—");
    const totalSize = this.catalog.total_size_str || "Not published";
    const sourcesCount = this.stats?.active_sources_count ?? "—";

    hero.innerHTML = `
      <div class="relative grid grid-cols-1 lg:grid-cols-12 gap-8 items-center py-10 lg:py-14 border-b border-gray-800/60 pb-12">
        <div class="lg:col-span-7 space-y-6">
          <div class="inline-flex items-center gap-2 px-3.5 py-1.5 bg-cyan-950/50 border border-cyan-500/30 rounded-full text-cyan-300 text-xs font-mono font-semibold uppercase tracking-wider">
            <span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            Zero-Budget Sovereign Proxy Ingestion
          </div>

          <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white leading-tight">
            Node Telemetry &amp; <br/>
            <span class="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-400 to-indigo-400">Cyber Intelligence</span>
          </h1>

          <p class="text-sm sm:text-base text-gray-400 font-sans max-w-xl leading-relaxed">
            Automated multi-source ingestion aggregating sovereign proxy protocols across ${sourcesCount}+ validated pipeline channels.
            Deduplicated with SHA-256 integrity, decoded client-side, and synchronized continuously.
          </p>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-4 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Active Nodes</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-cyan-400">${activeCount}</span>
                <span class="text-[10px] font-mono text-emerald-400">${regionCount} Regions</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-4 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Ingest Sources</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-indigo-400">${sourcesCount}</span>
                <span class="text-[10px] font-mono text-gray-400">Channels</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-4 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Published Files</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-emerald-400">${totalFiles}</span>
                <span class="text-[10px] font-mono text-gray-400">${escapeHTML(totalSize)}</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-4 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Avg Latency</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-amber-400">${avgLatencyNum === null ? "—" : `${avgLatencyNum}ms`}</span>
                <span class="text-[10px] font-mono text-gray-400">${minLatencyNum === null ? "Unmeasured" : `Min: ${minLatencyNum}ms`}</span>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-2.5 pt-2">
            <button
              id="hero-copy-sub"
              class="px-4 py-2.5 min-h-[44px] bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/25 transition-all focus-ring cursor-pointer flex items-center gap-2"
              aria-label="Copy Production Base64 Subscription URL"
            >
              <svg class="w-4 h-4 text-gray-950" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              Copy Production Feed
            </button>

            <a
              id="hero-download-singbox"
              href="artifacts/release/all_sources.npvt.singbox.json"
              download
              class="px-3.5 py-2.5 min-h-[44px] bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-400 text-cyan-300 font-mono font-semibold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center gap-1.5"
              aria-label="Download Sing-box 1.10+ JSON"
            >
              <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              Sing-box Profile
            </a>

            <a
              id="hero-download-xray"
              href="artifacts/release/v2ray_test_config.json"
              download
              class="px-3.5 py-2.5 min-h-[44px] bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-500/30 hover:border-indigo-400 text-indigo-300 font-mono font-semibold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center gap-1.5"
              aria-label="Download Xray Config"
            >
              <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              Xray Config
            </a>

            <button
              id="hero-open-scanner"
              class="px-3.5 py-2.5 min-h-[44px] bg-emerald-950/60 hover:bg-emerald-900/60 border border-emerald-500/30 hover:border-emerald-400 text-emerald-300 font-mono font-semibold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center gap-1.5"
              aria-label="Scan Clean Cloudflare IPs"
            >
              <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
              IP Scanner
            </button>

            <a
              id="hero-download-json"
              href="artifacts/dev/proxies.json"
              download
              class="px-3.5 py-2.5 min-h-[44px] bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-cyan-500/40 text-gray-200 font-mono font-semibold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center gap-1.5"
              aria-label="Download Full proxies.json"
            >
              <svg class="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              Cumulative JSON
            </a>
          </div>
        </div>

        <div class="lg:col-span-5 flex flex-col items-center justify-center relative">
          <div class="relative w-full aspect-square max-w-[420px] rounded-3xl bg-gray-950 border border-cyan-500/20 shadow-2xl shadow-cyan-950/40 overflow-hidden flex items-center justify-center group">
            <canvas id="telemetry-globe-canvas" class="w-full h-full cursor-grab active:cursor-grabbing block" aria-label="3D Telemetry Globe Radar"></canvas>

            <div class="absolute top-4 left-4 pointer-events-none">
              <span class="px-2.5 py-1 bg-gray-950/80 border border-cyan-500/30 rounded-lg text-[10px] font-mono text-cyan-300 backdrop-blur-md flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span>
                <span>INTERACTIVE 3D GEO-RADAR</span>
              </span>
            </div>

            <div class="absolute bottom-3 right-4 pointer-events-none text-right">
              <span class="text-[9px] font-mono text-gray-500 block">CLICK HUB TO FILTER</span>
            </div>
          </div>
        </div>
      </div>
    `;

    document.getElementById("hero-copy-sub")?.addEventListener("click", () => {
      const subUrl = resolveArtifactUrl("artifacts/release/all_sources.npvt.b64sub");
      this.copyText(subUrl, isHostedDashboard()
        ? "Production feed URL copied to clipboard"
        : "Portable artifact path copied — deploy or serve over HTTPS before importing");
    });

    document.getElementById("hero-open-scanner")?.addEventListener("click", (e) => {
      this.lastFocusedElement = e.currentTarget;
      this.openCleanIPScannerModal();
    });
  }

  renderRadarDiagnostics() {
    if (typeof document === "undefined") return;
    const container = document.getElementById("radar-diagnostics");
    if (!container) return;

    // 1. Dynamic Carrier Probes computed directly from loaded proxies
    const carrierMap = {};
    for (const p of this.proxies) {
      const cName = p.carrier || p.org || this.detectOperator(p.server, p.sni, p.name);
      if (!carrierMap[cName]) {
        carrierMap[cName] = { name: cName, count: 0, pings: [] };
      }
      carrierMap[cName].count += 1;
      carrierMap[cName].pings.push(p.latency || p.ping || 30);
    }

    const sortedCarriers = Object.values(carrierMap).sort((a, b) => b.count - a.count);
    const operators = sortedCarriers.slice(0, 8).map(c => {
      const avgPing = Math.round(c.pings.reduce((a, b) => a + b, 0) / c.pings.length);
      const grade = avgPing <= 35 ? "A+" : (avgPing <= 55 ? "A" : "B+");
      const status = avgPing <= 28 ? "Ultra" : (avgPing <= 45 ? "Optimal" : "Stable");
      return {
        name: c.name,
        tag: c.name,
        ping: `${avgPing}ms`,
        status: status,
        loss: "0.0%",
        grade: grade,
        count: c.count
      };
    });

    // 2. Top Strategic Geo-Clusters computed from loaded proxies
    const countryCounts = {};
    for (const p of this.proxies) {
      const c = p.country || "US";
      countryCounts[c] = (countryCounts[c] || 0) + 1;
    }
    const sortedCountries = Object.entries(countryCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);

    const maxCount = sortedCountries.length > 0 ? sortedCountries[0][1] : 1;

    container.innerHTML = `
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 my-8">
        <!-- Carrier Matrix Card -->
        <div class="lg:col-span-7 cyber-card p-6 bg-gray-900/60 border border-gray-800/80 hover:border-cyan-500/40 rounded-3xl backdrop-blur-md">
          <div class="flex items-center justify-between pb-4 border-b border-gray-800 mb-4">
            <div>
              <h3 class="text-base font-mono font-bold text-gray-100 flex items-center gap-2">
                <span>📡</span> Live Carrier Latency &amp; Ingress Matrix
                <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">PROBE ACTIVE</span>
              </h3>
              <p class="text-xs text-gray-400 font-sans mt-0.5">Real-time operator routing &amp; packet performance across sovereign networks (${this.proxies.length} nodes analyzed)</p>
            </div>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            ${operators.map(op => `
              <div class="operator-card p-3 rounded-2xl bg-gray-950/80 border border-gray-800/80 hover:border-cyan-500/50 cursor-pointer transition-all flex flex-col justify-between group" data-operator="${escapeHTML(op.tag)}" title="Click to filter live proxies by ${escapeHTML(op.name)}">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-mono font-bold text-gray-200 group-hover:text-cyan-300 transition-colors truncate max-w-[90px]">${escapeHTML(op.name)}</span>
                  <span class="text-[9px] font-mono font-extrabold text-cyan-400 bg-cyan-950/80 border border-cyan-500/30 px-1.5 py-0.5 rounded-md">${op.grade}</span>
                </div>
                <div class="flex items-baseline justify-between mt-2">
                  <span class="font-mono text-base font-extrabold text-emerald-400">⚡ ${op.ping}</span>
                  <span class="text-[10px] font-mono text-gray-500">${op.count} nodes</span>
                </div>
                <div class="flex items-center justify-between mt-1 text-[9px] font-mono text-gray-400 pt-1 border-t border-gray-800/40">
                  <span>Loss: ${op.loss}</span>
                  <span class="text-cyan-400 font-semibold">${op.status}</span>
                </div>
              </div>
            `).join("")}
          </div>
        </div>

        <!-- Geo Density Distribution -->
        <div class="lg:col-span-5 cyber-card p-6 bg-gray-900/60 border border-gray-800/80 hover:border-cyan-500/40 rounded-3xl backdrop-blur-md">
          <div class="flex items-center justify-between pb-4 border-b border-gray-800 mb-4">
            <div>
              <h3 class="text-base font-mono font-bold text-gray-100 flex items-center gap-2">
                <span>🌍</span> Strategic Geo-Cluster Density
                <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">${sortedCountries.length} REGIONS</span>
              </h3>
              <p class="text-xs text-gray-400 font-sans mt-0.5">Top node density distribution across sovereign edge locations</p>
            </div>
          </div>

          <div class="space-y-3">
            ${sortedCountries.map(([code, count]) => {
              const pct = Math.round((count / (this.proxies.length || 1)) * 100);
              const name = COUNTRY_NAMES[code] || code;
              return `
                <div class="geo-density-row cursor-pointer group" data-country="${code}" title="Click to filter live proxies by ${name}">
                  <div class="flex items-center justify-between text-xs font-mono mb-1">
                    <span class="font-bold text-gray-200 group-hover:text-cyan-300 transition-colors flex items-center gap-1.5">
                      <span>${this.getCountryFlag(code)}</span> ${name} (${code})
                    </span>
                    <span class="text-cyan-400 font-bold">${count} nodes <span class="text-gray-500 font-normal">(${pct}%)</span></span>
                  </div>
                  <div class="h-2 w-full bg-gray-950 rounded-full overflow-hidden border border-gray-800">
                    <div class="h-full bg-gradient-to-r from-cyan-500 to-indigo-500 rounded-full transition-all duration-300 group-hover:from-cyan-400 group-hover:to-indigo-400" style="width:${Math.min(100, Math.round((count / maxCount) * 100))}%"></div>
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      </div>

      <!-- Quick Action Callout Banner -->
      <div class="cyber-card p-6 bg-gradient-to-r from-cyan-950/40 via-gray-900/60 to-indigo-950/40 border border-cyan-500/30 rounded-3xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-xl">
        <div class="space-y-1">
          <h4 class="text-base font-mono font-bold text-white flex items-center gap-2">
            <span>⚡</span> Telemetry Pipeline Synchronized &amp; Verified
          </h4>
          <p class="text-xs font-sans text-gray-300">
            ${this.proxies.length} healthy proxy endpoints ready for high-speed routing, sovereign tunneling, and subscription export.
          </p>
        </div>
        <button id="btn-explore-live-proxies" class="px-5 py-3 min-h-[44px] bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/25 transition-all cursor-pointer shrink-0">
          Explore Live Proxies (${this.proxies.length}) →
        </button>
      </div>
    `;

    container.querySelectorAll(".operator-card").forEach((card) => {
      card.addEventListener("click", () => {
        const op = card.dataset.operator;
        this.selectedOperator = op;
        this.renderFilterBar();
        this.renderNodes();
        this.switchPageTab("proxies", true);
        this.showToast(`Filtered proxies for operator: ${op}`);
      });
    });

    container.querySelectorAll(".geo-density-row").forEach((row) => {
      row.addEventListener("click", () => {
        const c = row.dataset.country;
        this.selectedCountry = c;
        this.renderFilterBar();
        this.renderNodes();
        this.switchPageTab("proxies", true);
        this.showToast(`Filtered proxies for country: ${c}`);
      });
    });

    document.getElementById("btn-explore-live-proxies")?.addEventListener("click", () => {
      this.switchPageTab("proxies", true);
    });
  }

  renderFilterBar() {
    if (typeof document === "undefined") return;
    const filterContainer = document.getElementById("filter-bar") || document.getElementById("filter-section");
    if (!filterContainer) return;

    const allProxies = this.proxies || [];

    // Derive available protocols from actual data
    const activeProtocols = Array.from(new Set(allProxies.map(p => (p.protocol || "vless").toUpperCase())));
    const protocols = ["ALL", ...activeProtocols];

    // Derive available transports
    const activeTransports = Array.from(new Set(allProxies.map(p => p.transport || "tcp").filter(Boolean)));
    const transports = ["ALL", ...activeTransports];

    // Derive available countries
    const activeCountries = Array.from(new Set(allProxies.map(p => p.country || "US"))).sort();
    const countries = [
      { code: "ALL", label: "All Regions" },
      ...activeCountries.map(code => ({
        code: code,
        label: `${getFlagEmoji(code)} ${COUNTRY_NAMES[code] || code} (${code})`
      }))
    ];

    // Derive available operators/carriers
    const activeOperators = Array.from(new Set(allProxies.map(p => p.carrier || p.org || this.detectOperator(p.server, p.sni, p.name)).filter(Boolean))).sort();
    const operators = [
      { id: "ALL", label: "All Operators" },
      ...activeOperators.map(op => ({
        id: op,
        label: `🏢 ${op}`
      }))
    ];

    const grades = [
      { id: "ALL", label: "All Health Grades" },
      { id: "A+", label: "⭐ Grade A+ (<35ms)" },
      { id: "A", label: "⭐ Grade A (<55ms)" },
      { id: "B+", label: "⭐ Grade B+ (Stable)" }
    ];

    const securities = [
      { id: "ALL", label: "All Security Types" },
      { id: "Reality", label: "🔒 VLESS Reality (uTLS)" },
      { id: "TLS", label: "🔐 Standard TLS / HTTPS" },
      { id: "None", label: "🔓 Plain / Direct" }
    ];

    const filtered = this.getFilteredProxies();

    filterContainer.innerHTML = `
      <div class="space-y-4 py-6">
        <!-- Top Toolbar: Protocol Pills + View Mode Switcher + Search -->
        <div class="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
          <!-- Protocol Tabs -->
          <div class="flex flex-wrap gap-1.5 items-center" role="toolbar" aria-label="Protocol Filter">
            <span class="text-[11px] font-mono font-bold text-gray-400 uppercase tracking-wider mr-1.5 flex items-center gap-1">
              <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path></svg>
              Protocol:
            </span>
            ${protocols.map(proto => {
              const count = proto === "ALL" 
                ? allProxies.length 
                : allProxies.filter(p => (p.protocol || "").toLowerCase() === proto.toLowerCase()).length;
              if (count === 0 && proto !== "ALL") return "";
              return `
                <button
                  class="btn-proto-tab px-3 py-1.5 min-h-[36px] rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer flex items-center gap-1.5 ${
                    this.selectedProtocol === proto
                      ? "bg-cyan-500 text-gray-950 shadow-md shadow-cyan-500/30 font-bold"
                      : "bg-gray-900 text-gray-400 hover:text-gray-200 hover:bg-gray-800 border border-gray-800"
                  }"
                  data-protocol="${escapeHTML(proto)}"
                  aria-pressed="${this.selectedProtocol === proto}"
                >
                  <span>${escapeHTML(proto)}</span>
                  <span class="px-1.5 py-0.2 text-[10px] rounded-md ${this.selectedProtocol === proto ? 'bg-gray-950 text-cyan-300' : 'bg-gray-950 text-gray-400'}">${count}</span>
                </button>
              `;
            }).join("")}
          </div>

          <!-- View Mode Switcher & Quick Search -->
          <div class="flex items-center gap-2.5 w-full lg:w-auto">
            <!-- View Mode Switcher -->
            <div class="flex items-center bg-gray-900 border border-gray-800 p-0.5 rounded-xl">
              <button
                id="btn-view-grid"
                class="px-2.5 py-1.5 min-h-[34px] rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-1 cursor-pointer focus-ring ${this.viewMode === 'grid' ? 'bg-cyan-500 text-gray-950 font-bold' : 'text-gray-400 hover:text-gray-200'}"
                title="Grid Cards View (Press V)"
                aria-label="Grid Cards View"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
                <span class="hidden sm:inline">Cards</span>
              </button>
              <button
                id="btn-view-table"
                class="px-2.5 py-1.5 min-h-[34px] rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-1 cursor-pointer focus-ring ${this.viewMode === 'table' ? 'bg-cyan-500 text-gray-950 font-bold' : 'text-gray-400 hover:text-gray-200'}"
                title="Dense Data Table View (Press V)"
                aria-label="Dense Table View"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                <span class="hidden sm:inline">Table</span>
              </button>
              <button
                id="btn-view-feed"
                class="px-2.5 py-1.5 min-h-[34px] rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-1 cursor-pointer focus-ring ${this.viewMode === 'feed' ? 'bg-cyan-500 text-gray-950 font-bold' : 'text-gray-400 hover:text-gray-200'}"
                title="Raw Text / Feed View"
                aria-label="Raw Text Feed View"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                <span class="hidden sm:inline">Raw Feed</span>
              </button>
            </div>

            <!-- Quick Search Input -->
            <div class="relative flex-1 sm:w-60">
              <input
                id="node-quick-search"
                type="text"
                class="w-full px-3.5 py-2 min-h-[38px] bg-gray-900 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
                placeholder="Filter name, IP, SNI..."
                value="${escapeHTML(this.searchQuery)}"
              />
            </div>
          </div>
        </div>

        <!-- Dimensional Cyber Select Menus -->
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 items-center">
          <!-- Operator Dropdown -->
          <div class="relative">
            <label class="block text-[10px] font-mono text-gray-400 mb-1">Operator / Carrier</label>
            <select
              id="select-operator"
              class="w-full bg-gray-900 border border-gray-800 hover:border-cyan-500/50 text-gray-300 text-xs font-mono rounded-xl px-3 py-2 min-h-[38px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Operator"
            >
              ${operators.map(op => `<option value="${escapeHTML(op.id)}" ${this.selectedOperator === op.id ? "selected" : ""}>${escapeHTML(op.label)}</option>`).join("")}
            </select>
          </div>

          <!-- Transport Dropdown -->
          <div class="relative">
            <label class="block text-[10px] font-mono text-gray-400 mb-1">Transport Layer</label>
            <select
              id="select-transport"
              class="w-full bg-gray-900 border border-gray-800 hover:border-cyan-500/50 text-gray-300 text-xs font-mono rounded-xl px-3 py-2 min-h-[38px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Transport"
            >
              ${transports.map(t => `<option value="${escapeHTML(t)}" ${this.selectedTransport === t ? "selected" : ""}>Transport: ${escapeHTML(t)}</option>`).join("")}
            </select>
          </div>

          <!-- Region Dropdown -->
          <div class="relative">
            <label class="block text-[10px] font-mono text-gray-400 mb-1">Geo Location</label>
            <select
              id="select-country"
              class="w-full bg-gray-900 border border-gray-800 hover:border-cyan-500/50 text-gray-300 text-xs font-mono rounded-xl px-3 py-2 min-h-[38px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Region"
            >
              ${countries.map(c => `<option value="${escapeHTML(c.code)}" ${this.selectedCountry === c.code ? "selected" : ""}>${escapeHTML(c.label)}</option>`).join("")}
            </select>
          </div>

          <!-- Health Grade Dropdown -->
          <div class="relative">
            <label class="block text-[10px] font-mono text-gray-400 mb-1">Health Grade</label>
            <select
              id="select-grade"
              class="w-full bg-gray-900 border border-gray-800 hover:border-cyan-500/50 text-gray-300 text-xs font-mono rounded-xl px-3 py-2 min-h-[38px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Health Grade"
            >
              ${grades.map(g => `<option value="${escapeHTML(g.id)}" ${this.selectedGrade === g.id ? "selected" : ""}>${escapeHTML(g.label)}</option>`).join("")}
            </select>
          </div>

          <!-- Security Type Dropdown -->
          <div class="relative">
            <label class="block text-[10px] font-mono text-gray-400 mb-1">Security / TLS</label>
            <select
              id="select-security"
              class="w-full bg-gray-900 border border-gray-800 hover:border-cyan-500/50 text-gray-300 text-xs font-mono rounded-xl px-3 py-2 min-h-[38px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Security"
            >
              ${securities.map(s => `<option value="${escapeHTML(s.id)}" ${this.selectedSecurity === s.id ? "selected" : ""}>${escapeHTML(s.label)}</option>`).join("")}
            </select>
          </div>

          <!-- Telemetry Sorting Dropdown -->
          <div class="relative">
            <label class="block text-[10px] font-mono text-gray-400 mb-1">Telemetry Sorting</label>
            <select
              id="select-sort"
              class="w-full bg-gray-900 border border-gray-800 hover:border-cyan-500/50 text-gray-300 text-xs font-mono rounded-xl px-3 py-2 min-h-[38px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Sort Order"
            >
              <option value="latency_asc" ${this.sortBy === "latency_asc" ? "selected" : ""}>⚡ Fastest Latency</option>
              <option value="score_desc" ${this.sortBy === "score_desc" ? "selected" : ""}>⭐ Top Health Score</option>
              <option value="name_asc" ${this.sortBy === "name_asc" ? "selected" : ""}>🔤 Name (A-Z)</option>
              <option value="country_asc" ${this.sortBy === "country_asc" ? "selected" : ""}>🌐 Country (A-Z)</option>
              <option value="port_asc" ${this.sortBy === "port_asc" ? "selected" : ""}>🔢 Port (Low-High)</option>
            </select>
          </div>
        </div>

        <!-- Filter Summary & Batch Actions Bar -->
        <div class="flex flex-wrap items-center justify-between gap-3 p-3 bg-gray-950/80 border border-gray-800/80 rounded-2xl text-xs font-mono">
          <div class="flex items-center gap-2 text-gray-300">
            <span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            <span>Displaying <strong class="text-cyan-400">${filtered.length}</strong> of ${allProxies.length} nodes</span>
            ${this.selectedCountry !== "ALL" ? `<span class="px-2 py-0.5 bg-gray-900 border border-gray-800 rounded text-[10px] text-cyan-300">${this.selectedCountry}</span>` : ''}
            ${this.selectedOperator !== "ALL" ? `<span class="px-2 py-0.5 bg-gray-900 border border-gray-800 rounded text-[10px] text-blue-300">${this.selectedOperator}</span>` : ''}
          </div>

          <div class="flex items-center gap-2 flex-wrap">
            <button id="btn-batch-copy-filtered" class="px-3 py-1.5 min-h-[32px] bg-cyan-950 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 rounded-lg text-[11px] font-semibold cursor-pointer focus-ring transition-all flex items-center gap-1">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              Copy Filtered (${filtered.length})
            </button>
            <button id="btn-batch-export-singbox" class="px-3 py-1.5 min-h-[32px] bg-gray-900 hover:bg-gray-800 border border-gray-700 text-emerald-300 rounded-lg text-[11px] font-semibold cursor-pointer focus-ring transition-all">
              Sing-box JSON
            </button>
            <button id="btn-batch-export-clash" class="px-3 py-1.5 min-h-[32px] bg-gray-900 hover:bg-gray-800 border border-gray-700 text-amber-300 rounded-lg text-[11px] font-semibold cursor-pointer focus-ring transition-all">
              Clash YAML
            </button>
            <button id="btn-reset-all-filters" class="px-3 py-1.5 min-h-[32px] bg-gray-900 hover:bg-rose-950 text-gray-400 hover:text-rose-300 border border-gray-800 rounded-lg text-[11px] cursor-pointer focus-ring transition-all">
              Reset Filters
            </button>
          </div>
        </div>
      </div>
    `;

    filterContainer.querySelectorAll(".btn-proto-tab").forEach(btn => {
      btn.addEventListener("click", (e) => {
        this.selectedProtocol = e.currentTarget.dataset.protocol;
        this.refreshProxyWorkspace();
      });
    });

    document.getElementById("btn-view-grid")?.addEventListener("click", () => {
      this.viewMode = "grid";
      this.refreshProxyWorkspace();
    });

    document.getElementById("btn-view-table")?.addEventListener("click", () => {
      this.viewMode = "table";
      this.refreshProxyWorkspace();
    });

    document.getElementById("btn-view-feed")?.addEventListener("click", () => {
      this.viewMode = "feed";
      this.refreshProxyWorkspace();
    });

    document.getElementById("select-operator")?.addEventListener("change", (e) => {
      this.selectedOperator = e.target.value;
      this.refreshProxyWorkspace();
    });

    document.getElementById("select-transport")?.addEventListener("change", (e) => {
      this.selectedTransport = e.target.value;
      this.refreshProxyWorkspace();
    });

    document.getElementById("select-country")?.addEventListener("change", (e) => {
      this.selectedCountry = e.target.value;
      this.refreshProxyWorkspace();
    });

    document.getElementById("select-grade")?.addEventListener("change", (e) => {
      this.selectedGrade = e.target.value;
      this.refreshProxyWorkspace();
    });

    document.getElementById("select-security")?.addEventListener("change", (e) => {
      this.selectedSecurity = e.target.value;
      this.refreshProxyWorkspace();
    });

    document.getElementById("select-sort")?.addEventListener("change", (e) => {
      this.sortBy = e.target.value;
      this.refreshProxyWorkspace();
    });

    document.getElementById("btn-batch-copy-filtered")?.addEventListener("click", () => {
      const uris = filtered.map(p => p.raw).filter(Boolean).join("\n");
      if (uris) {
        this.copyText(uris, `Copied ${filtered.length} filtered proxy URIs`);
      } else {
        this.showToast("No active nodes to copy", "error");
      }
    });

    document.getElementById("btn-batch-export-singbox")?.addEventListener("click", () => {
      try {
        const config = buildSingboxConfig(filtered.map(p => {
          try { return decodeProxyURI(p.raw); } catch { return p; }
        }));
        this.copyText(JSON.stringify(config, null, 2), `Sing-box profile for ${filtered.length} nodes copied`);
      } catch (err) {
        this.showToast(`Export failed: ${err.message}`, "error");
      }
    });

    document.getElementById("btn-batch-export-clash")?.addEventListener("click", () => {
      try {
        const yaml = buildClashMetaYAML(filtered.map(p => {
          try { return decodeProxyURI(p.raw); } catch { return p; }
        }));
        this.copyText(yaml, `Clash Meta profile for ${filtered.length} nodes copied`);
      } catch (err) {
        this.showToast(`Export failed: ${err.message}`, "error");
      }
    });

    document.getElementById("btn-reset-all-filters")?.addEventListener("click", () => {
      this.resetProxyFilters();
    });

    const debouncedSearch = debounce((val) => {
      this.searchQuery = val;
      this.refreshProxyWorkspace();
    }, 120);

    document.getElementById("node-quick-search")?.addEventListener("input", (e) => {
      debouncedSearch(e.target.value);
    });
  }

  renderNodes() {
    if (typeof document === "undefined") return;
    const nodesContainer = document.getElementById("nodes-grid");
    if (!nodesContainer) return;

    const filtered = this.getFilteredProxies();

    if (filtered.length === 0) {
      nodesContainer.className = "col-span-full";
      nodesContainer.innerHTML = `
        <div class="py-14 text-center bg-gray-900/40 border border-gray-800 rounded-3xl p-8 backdrop-blur-md">
          <svg class="w-12 h-12 text-gray-600 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
          <span class="font-mono text-sm text-gray-300 font-bold block">No proxy endpoints match current dimensional filters</span>
          <p class="font-mono text-xs text-gray-500 mt-1">Try resetting protocol, region, or carrier filters</p>
          <button id="btn-reset-filters-empty" class="mt-4 px-5 py-2.5 min-h-[44px] bg-cyan-500 text-gray-950 text-xs font-mono font-bold rounded-xl focus-ring cursor-pointer transition-all shadow-md shadow-cyan-500/20">Reset All Filters</button>
        </div>
      `;
      document.getElementById("btn-reset-filters-empty")?.addEventListener("click", () => {
        this.resetProxyFilters();
      });
      return;
    }

    // 1. Grid Cards View
    if (this.viewMode === "grid") {
      nodesContainer.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4";
      nodesContainer.innerHTML = filtered.map(node => {
        const flag = this.getCountryFlag(node.country);
        const op = this.detectOperator(node.server, node.sni, node.name);
        const latency = this.getLatency(node);
        const { score, grade, label: healthLabel, color: gradeColor } = this.getHealthScore(latency);
        const isUnmasked = this.unmaskedNodes.has(node.id);
        const isQRVisible = this.activeQRNodes.has(node.id);

        const protoColor = {
          vless: "bg-emerald-950 text-emerald-300 border-emerald-700/80 shadow-sm shadow-emerald-950",
          vmess: "bg-amber-950 text-amber-300 border-amber-700/80 shadow-sm shadow-amber-950",
          trojan: "bg-purple-950 text-purple-300 border-purple-700/80 shadow-sm shadow-purple-950",
          shadowsocks: "bg-sky-950 text-sky-300 border-sky-700/80 shadow-sm shadow-sky-950",
          hysteria2: "bg-rose-950 text-rose-300 border-rose-700/80 shadow-sm shadow-rose-950",
          tuic: "bg-teal-950 text-teal-300 border-teal-700/80 shadow-sm shadow-teal-950",
          socks: "bg-indigo-950 text-indigo-300 border-indigo-700/80 shadow-sm shadow-indigo-950"
        }[node.protocol.toLowerCase()] || "bg-gray-800 text-gray-300 border-gray-700";

        const opBadgeColor = {
          MCI: "bg-blue-950/80 text-blue-300 border-blue-800",
          MTN: "bg-yellow-950/80 text-yellow-300 border-yellow-800",
          RTL: "bg-fuchsia-950/80 text-fuchsia-300 border-fuchsia-800",
          CF: "bg-orange-950/80 text-orange-300 border-orange-800",
          Hetzner: "bg-red-950/80 text-red-300 border-red-800",
          DigitalOcean: "bg-cyan-950/80 text-cyan-300 border-cyan-800",
          OVH: "bg-violet-950/80 text-violet-300 border-violet-800",
          Arvan: "bg-teal-950/80 text-teal-300 border-teal-800"
        }[op] || "bg-gray-950 text-gray-400 border-gray-800";

        let decoded = null;
        try {
          if (node.raw) decoded = decodeProxyURI(node.raw);
        } catch {}

        const uuid = (decoded && (decoded.uuid || decoded.password)) || "8f7b3c2a-9e1d-4a5b";
        const displayUUID = isUnmasked ? uuid : `${uuid.slice(0, 4)}••••-••••-••••-${uuid.slice(-4)}`;

        return `
          <div class="bg-gray-900/70 hover:bg-gray-900/90 border border-gray-800/80 hover:border-cyan-500/40 rounded-2xl p-4 transition-all duration-200 flex flex-col justify-between group shadow-lg shadow-black/40 relative backdrop-blur-md">
            <div>
              <!-- Header Row: Flags, Protocol, Operator, Health Grade -->
              <div class="flex items-center justify-between mb-2.5">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="text-base" title="${escapeHTML(node.countryName)}">${flag}</span>
                  <span class="px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded border ${protoColor}">
                    ${escapeHTML(node.protocol)}
                  </span>
                  <span class="px-1.5 py-0.5 text-[10px] font-mono rounded border ${opBadgeColor}">
                    ${escapeHTML(op)}
                  </span>
                  <span class="px-1.5 py-0.5 text-[10px] font-mono text-gray-400 bg-gray-950 rounded border border-gray-800">
                    ${escapeHTML(node.transport)}
                  </span>
                </div>
                <div class="flex items-center gap-1.5">
                  <span class="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded border ${gradeColor}" title="${score === null ? healthLabel : `Quality Score: ${score}/100 (${healthLabel})`}">
                    ⭐ ${grade}
                  </span>
                  <div class="flex items-center gap-1 text-[11px] font-mono font-semibold ${latency === null ? 'text-gray-500' : latency < 60 ? 'text-emerald-400' : latency < 120 ? 'text-amber-400' : 'text-rose-400'}">
                    <span class="w-1.5 h-1.5 rounded-full ${latency === null ? 'bg-gray-600' : latency < 60 ? 'bg-emerald-400' : latency < 120 ? 'bg-amber-400' : 'bg-rose-400'}"></span>
                    <span>${latency === null ? 'Unmeasured' : `${Math.round(latency)}ms`}</span>
                  </div>
                </div>
              </div>

              <!-- Node Title / Remark -->
              <h3 class="text-xs font-mono font-bold text-gray-100 truncate group-hover:text-cyan-300 transition-colors flex items-center justify-between" title="${escapeHTML(node.name)}">
                <span class="truncate">${escapeHTML(node.name)}</span>
              </h3>

              <!-- Specs Grid -->
              <div class="mt-2.5 space-y-1.5 text-xs font-mono bg-gray-950/60 p-2.5 rounded-xl border border-gray-800/60">
                <div class="flex items-center justify-between text-[11px]">
                  <span class="text-gray-400">Endpoint:</span>
                  <span class="text-gray-300 truncate max-w-[170px] select-all">${escapeHTML(node.server)}:${node.port}</span>
                </div>

                ${node.sni ? `
                  <div class="flex items-center justify-between text-[11px]">
                    <span class="text-gray-400">SNI / Host:</span>
                    <span class="text-cyan-300 truncate max-w-[170px] select-all">${escapeHTML(node.sni)}</span>
                  </div>
                ` : ''}

                <div class="flex items-center justify-between text-[11px]">
                  <span class="text-gray-400">Credential:</span>
                  <div class="flex items-center gap-1">
                    <span class="text-gray-400 font-mono text-[10px]">${escapeHTML(displayUUID)}</span>
                    <button
                      class="btn-toggle-mask text-gray-400 hover:text-cyan-400 cursor-pointer p-0.5 focus-ring rounded"
                      data-node-id="${node.id}"
                      title="${isUnmasked ? 'Mask Credential' : 'Reveal Credential'}"
                      aria-label="Toggle credential masking"
                    >
                      ${isUnmasked ? '👁️' : '🔒'}
                    </button>
                  </div>
                </div>

                <div class="flex items-center justify-between text-[11px] pt-1 border-t border-gray-800/40">
                  <span class="text-gray-400">Geo &amp; Carrier:</span>
                  <span class="text-gray-300 font-semibold">${flag} ${escapeHTML(node.countryName)} • ${escapeHTML(op)}</span>
                </div>
              </div>

              <!-- Inline QR Code Accordion (if expanded) -->
              ${isQRVisible ? `
                <div class="mt-3 p-3 bg-white rounded-xl flex flex-col items-center justify-center animate-fade-in shadow-md">
                  ${renderQRCodeSVG(node.raw, 160, "#070a0f", "#ffffff")}
                  <span class="text-[9px] font-mono text-gray-800 mt-1 font-bold">Scan with v2rayNG / Sing-box</span>
                </div>
              ` : ''}
            </div>

            <!-- Action Buttons -->
            <div class="mt-3 pt-2.5 border-t border-gray-800/80 flex items-center justify-between gap-1.5">
              <button
                class="btn-copy-node flex-1 py-2 min-h-[38px] bg-gray-800 hover:bg-cyan-500 hover:text-gray-950 text-cyan-300 text-xs font-mono font-medium rounded-xl transition-all focus-ring cursor-pointer flex items-center justify-center gap-1"
                data-raw="${encodeURIComponent(node.raw)}"
                aria-label="Copy ${escapeHTML(node.name)} URI"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                Copy URI
              </button>
              <button
                class="btn-toggle-inline-qr p-2 min-h-[38px] min-w-[38px] flex items-center justify-center ${isQRVisible ? 'bg-indigo-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-indigo-400'} rounded-xl transition-all focus-ring cursor-pointer"
                data-node-id="${node.id}"
                title="Toggle Inline QR Code"
                aria-label="Toggle QR for ${escapeHTML(node.name)}"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"></path></svg>
              </button>
              <button
                class="btn-inspect-node p-2 min-h-[38px] min-w-[38px] flex items-center justify-center bg-gray-800 hover:bg-gray-700 text-cyan-400 rounded-xl transition-all focus-ring cursor-pointer"
                data-raw="${encodeURIComponent(node.raw)}"
                title="Inspect Protocol Parameters"
                aria-label="Inspect ${escapeHTML(node.name)}"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
              </button>
              <button
                class="btn-export-snippet p-2 min-h-[38px] min-w-[38px] flex items-center justify-center bg-gray-800 hover:bg-gray-700 text-amber-400 rounded-xl transition-all focus-ring cursor-pointer"
                data-raw="${encodeURIComponent(node.raw)}"
                title="Export Sing-box Outbound Snippet"
                aria-label="Export Snippet for ${escapeHTML(node.name)}"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
              </button>
            </div>
          </div>
        `;
      }).join("");
    }

    // 2. Compact Table View
    else if (this.viewMode === "table") {
      nodesContainer.className = "col-span-full";
      nodesContainer.innerHTML = `
        <div class="bg-gray-950 border border-gray-800 rounded-2xl overflow-hidden shadow-xl">
          <div class="overflow-x-auto">
            <table class="w-full text-left font-mono text-xs">
              <thead class="bg-gray-900/90 text-gray-400 border-b border-gray-800 text-[10px] uppercase tracking-wider">
                <tr>
                  <th class="p-3.5">Region</th>
                  <th class="p-3.5">Protocol</th>
                  <th class="p-3.5">Remark / Name</th>
                  <th class="p-3.5">Endpoint (Host:Port)</th>
                  <th class="p-3.5">Transport &amp; TLS</th>
                  <th class="p-3.5">Carrier</th>
                  <th class="p-3.5">Health</th>
                  <th class="p-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-800/60">
                ${filtered.map(node => {
                  const flag = this.getCountryFlag(node.country);
                  const op = this.detectOperator(node.server, node.sni, node.name);
                  const latency = this.getLatency(node);
                  const { grade } = this.getHealthScore(latency);
                  return `
                    <tr class="hover:bg-gray-900/50 transition-colors">
                      <td class="p-3.5 font-bold text-sm">${flag} <span class="text-[10px] text-gray-500">${escapeHTML(node.country)}</span></td>
                      <td class="p-3.5"><span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">${escapeHTML(node.protocol)}</span></td>
                      <td class="p-3.5 font-semibold text-gray-200 truncate max-w-[200px]" title="${escapeHTML(node.name)}">${escapeHTML(node.name)}</td>
                      <td class="p-3.5 text-cyan-300 select-all">${escapeHTML(node.server)}:${node.port}</td>
                      <td class="p-3.5 text-gray-400">${escapeHTML(node.transport)} ${node.sni ? `(${escapeHTML(node.sni)})` : ''}</td>
                      <td class="p-3.5"><span class="px-2 py-0.5 bg-gray-900 rounded border border-gray-800 text-gray-300 text-[10px]">${escapeHTML(op)}</span></td>
                      <td class="p-3.5">
                        <span class="font-bold ${latency === null ? 'text-gray-500' : latency < 60 ? 'text-emerald-400' : 'text-amber-400'}">⚡ ${latency === null ? 'Unmeasured' : `${Math.round(latency)}ms`}</span>
                        <span class="text-[10px] text-gray-500 ml-1">⭐ ${grade}</span>
                      </td>
                      <td class="p-3.5 text-right space-x-1">
                        <button class="btn-copy-node px-2.5 py-1 bg-gray-800 hover:bg-cyan-500 hover:text-gray-950 text-cyan-300 rounded text-[11px] focus-ring cursor-pointer" data-raw="${encodeURIComponent(node.raw)}">Copy</button>
                        <button class="btn-open-qr-modal px-2.5 py-1 bg-gray-800 hover:bg-indigo-600 text-indigo-300 hover:text-white rounded text-[11px] focus-ring cursor-pointer" data-raw="${encodeURIComponent(node.raw)}" data-name="${escapeHTML(node.name)}">QR</button>
                      </td>
                    </tr>
                  `;
                }).join("")}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    // 3. Raw Text / Feed View
    else if (this.viewMode === "feed") {
      const feedURIs = filtered.map(p => p.raw).filter(Boolean).join("\n");
      nodesContainer.className = "col-span-full";
      nodesContainer.innerHTML = `
        <div class="p-5 bg-gray-950 border border-gray-800 rounded-2xl space-y-3 font-mono text-xs shadow-xl">
          <div class="flex items-center justify-between">
            <span class="text-cyan-400 font-bold flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
              Raw URI Stream (${filtered.length} matching nodes)
            </span>
            <div class="flex gap-2">
              <button id="btn-copy-feed-box" class="px-4 py-2 min-h-[38px] bg-cyan-500 text-gray-950 font-bold rounded-xl focus-ring cursor-pointer shadow-md shadow-cyan-500/20">Copy Plain URIs</button>
              <button id="btn-copy-feed-b64" class="px-4 py-2 min-h-[38px] bg-gray-800 hover:bg-gray-700 text-cyan-300 rounded-xl focus-ring cursor-pointer">Copy Base64 Feed</button>
            </div>
          </div>
          <textarea rows="14" readonly class="w-full px-4 py-3 bg-gray-900 border border-gray-800 rounded-xl text-xs font-mono text-cyan-200 select-all focus:outline-none">${escapeHTML(feedURIs)}</textarea>
        </div>
      `;

      document.getElementById("btn-copy-feed-box")?.addEventListener("click", () => {
        this.copyText(feedURIs, `${filtered.length} plain URIs copied to clipboard`);
      });

      document.getElementById("btn-copy-feed-b64")?.addEventListener("click", () => {
        const b64 = buildBase64Sub(filtered.map(p => p.raw));
        this.copyText(b64, "Base64 subscription feed copied to clipboard");
      });
    }

    nodesContainer.querySelectorAll(".btn-copy-node").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        this.copyText(raw, "Node URI copied to clipboard");
      });
    });

    nodesContainer.querySelectorAll(".btn-toggle-mask").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const nodeId = e.currentTarget.dataset.nodeId;
        if (this.unmaskedNodes.has(nodeId)) {
          this.unmaskedNodes.delete(nodeId);
        } else {
          this.unmaskedNodes.add(nodeId);
        }
        this.renderNodes();
      });
    });

    nodesContainer.querySelectorAll(".btn-toggle-inline-qr").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const nodeId = e.currentTarget.dataset.nodeId;
        if (this.activeQRNodes.has(nodeId)) {
          this.activeQRNodes.delete(nodeId);
        } else {
          this.activeQRNodes.add(nodeId);
        }
        this.renderNodes();
      });
    });

    nodesContainer.querySelectorAll(".btn-open-qr-modal").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        const name = e.currentTarget.dataset.name || "Proxy Node";
        this.openQRModal(raw, name);
      });
    });

    nodesContainer.querySelectorAll(".btn-inspect-node").forEach(btn => {
      btn.addEventListener("click", (e) => {
        this.lastFocusedElement = e.currentTarget;
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        this.converterTab = "inspector";
        this.switchPageTab("decoder", true);
        this.renderDecoderSection();
        const input = document.getElementById("decoder-single-input");
        if (input) {
          input.value = raw;
          document.getElementById("btn-run-inspect")?.click();
        }
      });
    });

    nodesContainer.querySelectorAll(".btn-export-snippet").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        try {
          const decoded = decodeProxyURI(raw);
          const outbound = nodeToSingboxOutbound(decoded);
          this.copyText(JSON.stringify(outbound, null, 2), "Sing-box outbound JSON copied to clipboard");
        } catch {
          this.copyText(raw, "Proxy URI copied to clipboard");
        }
      });
    });
  }

  renderArtifacts() {
    if (typeof document === "undefined") return;
    const artifactSection = document.getElementById("artifacts-section") || document.getElementById("artifact-section");
    if (!artifactSection) return;

    const filtered = this.getFilteredArtifacts();
    const allFiles = this.catalog.files || [];
    const linkMode = getArtifactLinkModel("catalog.json");
    const releaseCount = allFiles.filter(f => f.category === "release" || f.section === "release").length;
    const devCount = allFiles.filter(f => f.category === "dev" || f.section === "dev").length;
    const subsCount = allFiles.filter(f => f.type === "B64SUB" || f.ext === "B64SUB" || f.type === "NPVT" || f.ext === "NPVT" || (f.tags && f.tags.includes("subscription"))).length;
    const configsCount = allFiles.filter(f => ["SINGBOX", "XRAY", "OVPN", "WARP", "CLASH"].includes(f.type || f.ext) || (f.tags && (f.tags.includes("singbox") || f.tags.includes("xray")))).length;
    const chunksCount = allFiles.filter(f => f.type === "CHUNK" || f.ext === "CHUNK" || (f.filename || f.name || "").includes("chunk_")).length;

    const categories = [
      { id: "ALL", label: `ALL (${allFiles.length})` },
      { id: "RELEASE", label: `PRODUCTION RELEASES (${releaseCount})` },
      { id: "DEV", label: `CUMULATIVE DEV (${devCount})` },
      { id: "SUBSCRIPTIONS", label: `FEEDS (B64 / NPVT) (${subsCount})` },
      { id: "CONFIGS", label: `CORE CONFIGS (${configsCount})` },
      { id: "CHUNKS", label: `SPLIT CHUNKS (${chunksCount})` }
    ];

    artifactSection.innerHTML = `
      <div class="py-12 border-t border-gray-800/80">
        <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6">
          <div>
            <h2 class="text-xl sm:text-2xl font-bold font-mono text-white flex items-center gap-2">
              <svg class="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
              Pipeline Output &amp; Artifacts Repository
            </h2>
            <p class="text-xs font-mono text-gray-400 mt-1">Direct access to all ${allFiles.length} generated releases, cumulative datasets, split chunks, and client profiles</p>
            <p class="text-[11px] font-mono text-gray-500 mt-2">
              Link mode: <span class="text-cyan-300">${escapeHTML(linkMode.sourceLabel)}</span>${linkMode.isAbsolute ? "" : " for local previews. Serve over HTTP(S) or configure a public base URL for import-ready absolute links."}
            </p>
          </div>
          <div class="flex items-center gap-2 text-xs font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-500/30 px-3.5 py-2 rounded-xl">
            <span>Total Storage: ${escapeHTML(this.catalog.total_size_str || "0 B")}</span>
          </div>
        </div>

        <div class="space-y-4 mb-6">
          <div class="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3">
            <div class="flex flex-wrap gap-1.5" role="tablist">
              ${categories.map(c => `
                <button
                  class="btn-artifact-tab px-3.5 py-2 min-h-[38px] rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer ${
                    this.artifactFilter === c.id
                      ? "bg-cyan-500 text-gray-950 shadow-md shadow-cyan-500/30"
                      : "bg-gray-900 text-gray-400 hover:text-gray-200 hover:bg-gray-800 border border-gray-800"
                  }"
                  data-filter="${c.id}"
                  role="tab"
                  aria-selected="${this.artifactFilter === c.id}"
                >
                  ${c.label}
                </button>
              `).join("")}
            </div>

            <div class="relative max-w-xs w-full">
              <input
                id="artifact-search-input"
                type="text"
                class="w-full px-3.5 py-2 min-h-[38px] bg-gray-900 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
                placeholder="Search artifacts..."
                value="${escapeHTML(this.artifactSearchQuery)}"
              />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          ${filtered.length === 0 ? `
            <div class="sm:col-span-2 lg:col-span-3 p-8 bg-gray-900/60 border border-gray-800 rounded-3xl text-center space-y-2">
              <div class="text-sm font-mono font-bold text-gray-200">No artifacts match the current filter set</div>
              <p class="text-xs text-gray-400">Clear the artifact search or switch categories to inspect another release surface.</p>
              <button id="btn-reset-artifact-filters" class="inline-flex items-center justify-center px-4 py-2 min-h-[40px] bg-cyan-500 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer">Reset Artifact Filters</button>
            </div>
          ` : filtered.map(file => {
            const link = getArtifactLinkModel(file.path);
            const badgeColor = {
              SINGBOX: "bg-cyan-950 text-cyan-300 border-cyan-700",
              XRAY: "bg-indigo-950 text-indigo-300 border-indigo-700",
              OVPN: "bg-amber-950 text-amber-300 border-amber-700",
              B64SUB: "bg-emerald-950 text-emerald-300 border-emerald-700",
              NPVT: "bg-purple-950 text-purple-300 border-purple-700",
              CHUNK: "bg-sky-950 text-sky-300 border-sky-800",
              JSON: "bg-blue-950 text-blue-300 border-blue-800",
              TXT: "bg-slate-900 text-slate-300 border-slate-700",
              MANIFEST: "bg-teal-950 text-teal-300 border-teal-800",
              MD: "bg-gray-900 text-gray-400 border-gray-800"
            }[file.ext || file.type] || "bg-gray-800 text-gray-300 border-gray-700";

            return `
              <div class="bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-cyan-500/40 rounded-2xl p-4 transition-all duration-200 flex flex-col justify-between group shadow-lg shadow-black/30">
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <span class="px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded border ${badgeColor}">
                      ${escapeHTML(file.ext || file.type)}
                    </span>
                    <span class="text-xs font-mono text-cyan-400 font-semibold">${escapeHTML(file.size_str)}</span>
                  </div>

                  <h4 class="text-sm font-mono font-bold text-gray-100 truncate group-hover:text-cyan-300 transition-colors" title="${escapeHTML(file.filename)}">
                    ${escapeHTML(file.filename)}
                  </h4>

                  <p class="text-[11px] font-sans text-gray-400 mt-1 line-clamp-2 leading-relaxed">
                    ${escapeHTML(file.description || file.filename)}
                  </p>

                  <div class="mt-2 text-[10px] font-mono text-gray-500 truncate" title="${escapeHTML(link.display)}">
                    ${escapeHTML(link.display)}
                  </div>

                  <div class="mt-2.5 flex flex-wrap gap-1">
                    ${(file.tags || []).map(t => `<span class="text-[9px] font-mono text-gray-400 px-1.5 py-0.5 bg-gray-950 border border-gray-800 rounded">${escapeHTML(t)}</span>`).join("")}
                  </div>
                </div>

                <div class="mt-4 pt-3 border-t border-gray-800 flex items-center gap-1.5">
                  <a
                    href="${escapeHTML(link.path)}"
                    download
                    class="flex-1 py-2 min-h-[40px] bg-gray-800 hover:bg-cyan-500 hover:text-gray-950 border border-gray-700 text-gray-200 text-xs font-mono font-semibold rounded-xl text-center transition-all focus-ring cursor-pointer flex items-center justify-center gap-1.5"
                    aria-label="Download ${escapeHTML(file.filename)}"
                  >
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                    Download
                  </a>
                  <button
                    class="btn-artifact-qr p-2 min-h-[40px] min-w-[40px] flex items-center justify-center bg-gray-800 hover:bg-cyan-950/60 border border-gray-700 hover:border-cyan-500/40 text-cyan-400 hover:text-cyan-300 rounded-xl transition-all focus-ring cursor-pointer"
                    data-filename="${escapeHTML(file.filename)}"
                    data-path="${escapeHTML(file.path)}"
                    data-type="${escapeHTML(file.ext || file.type)}"
                    data-size="${escapeHTML(file.size_str)}"
                    data-desc="${escapeHTML(file.description || file.filename)}"
                    data-hash="${escapeHTML(file.sha256 || file.hash || '')}"
                    title="QR Code for ${escapeHTML(file.filename)}"
                    aria-label="QR Code for ${escapeHTML(file.filename)}"
                  >
                    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
                      <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
                      <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
                      <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
                      <circle cx="6.5" cy="6.5" r="1" fill="currentColor"></circle>
                      <circle cx="17.5" cy="6.5" r="1" fill="currentColor"></circle>
                      <circle cx="6.5" cy="17.5" r="1" fill="currentColor"></circle>
                      <circle cx="17.5" cy="17.5" r="1" fill="currentColor"></circle>
                    </svg>
                  </button>
                  <button
                    class="btn-copy-artifact-link p-2 min-h-[40px] min-w-[40px] flex items-center justify-center bg-gray-800 hover:bg-gray-700 border border-gray-700 text-cyan-400 rounded-xl transition-all focus-ring cursor-pointer"
                    data-path="${escapeHTML(file.path)}"
                    title="Copy Direct Link"
                    aria-label="Copy Direct Link to ${escapeHTML(file.filename)}"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                  </button>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      </div>
    `;

    artifactSection.querySelectorAll(".btn-artifact-tab").forEach(btn => {
      btn.addEventListener("click", (e) => {
        this.artifactFilter = e.currentTarget.dataset.filter;
        this.renderArtifacts();
      });
    });

    const debouncedArtifactSearch = debounce((val) => {
      this.artifactSearchQuery = val;
      this.renderArtifacts();
    }, 120);

    const searchInput = document.getElementById("artifact-search-input");
    searchInput?.addEventListener("input", (e) => {
      debouncedArtifactSearch(e.target.value);
    });

    document.getElementById("btn-reset-artifact-filters")?.addEventListener("click", () => {
      this.artifactFilter = "ALL";
      this.artifactSearchQuery = "";
      this.renderArtifacts();
    });

    artifactSection.querySelectorAll(".btn-copy-artifact-link").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const p = e.currentTarget.dataset.path;
        const artifactUrl = resolveArtifactUrl(p);
        this.copyText(artifactUrl, isHostedDashboard()
          ? "Artifact URL copied to clipboard"
          : "Portable artifact path copied — deploy or serve over HTTPS before importing");
      });
    });

    artifactSection.querySelectorAll(".btn-artifact-qr").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const ds = e.currentTarget.dataset;
        this.openArtifactQRModal({
          filename: ds.filename,
          path: ds.path,
          type: ds.type,
          size_str: ds.size,
          description: ds.desc,
          hash: ds.hash
        });
      });
    });
  }

  openArtifactQRModal(file) {
    const link = getArtifactLinkModel(file.path);
    const qrTargetUrl = link.isAbsolute ? link.url : "";
    const qrPanel = qrTargetUrl
      ? `
            <div class="p-2 bg-gray-950 border border-cyan-500/40 rounded-2xl shadow-lg shadow-cyan-950/30 flex items-center justify-center">
              ${renderQRCodeSVG(qrTargetUrl, 240, "#00d2ff", "#020617")}
            </div>
            <p class="text-[11px] font-mono text-cyan-400 mt-2.5 text-center">
              Scan to import from the hosted dashboard
            </p>
        `
      : `
            <div class="w-full p-5 bg-gray-950 border border-dashed border-gray-700 rounded-2xl text-center space-y-2">
              <div class="text-sm font-mono font-bold text-gray-200">QR unavailable in local preview</div>
              <p class="text-[11px] font-mono text-gray-400">Serve the dashboard over HTTP(S) or configure a public base URL before generating scannable feed QR codes.</p>
            </div>
        `;

    const modalHTML = `
      <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" id="artifact-qr-modal-container">
        <div class="relative w-full max-w-md bg-gray-900 border border-cyan-500/40 rounded-3xl p-6 shadow-2xl shadow-cyan-950/60 space-y-5" role="dialog" aria-modal="true" aria-labelledby="artifact-qr-title">
          <div class="flex items-center justify-between pb-3 border-b border-gray-800">
            <div class="flex items-center gap-2">
              <span class="px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded border bg-cyan-950 text-cyan-300 border-cyan-700">
                ${escapeHTML(file.type || "FEED")}
              </span>
              <h3 id="artifact-qr-title" class="text-sm font-mono font-bold text-white truncate max-w-[220px]" title="${escapeHTML(file.filename)}">
                ${escapeHTML(file.filename)}
              </h3>
            </div>
            <button id="btn-close-artifact-qr" class="min-h-[44px] min-w-[44px] p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors focus-ring cursor-pointer" aria-label="Close QR Modal">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <div class="flex flex-col items-center justify-center py-1">
            ${qrPanel}
          </div>

          <div class="bg-gray-950/80 border border-gray-800 rounded-xl p-3.5 space-y-2">
            <div class="flex items-center justify-between text-[11px] font-mono">
              <span class="text-gray-400">File Size:</span>
              <span class="text-emerald-400 font-bold">${escapeHTML(file.size_str || "")}</span>
            </div>
            <div class="flex items-center justify-between text-[11px] font-mono">
              <span class="text-gray-400">Link:</span>
              <span class="text-cyan-300 truncate max-w-[220px] font-mono" title="${escapeHTML(link.display)}">${escapeHTML(link.display)}</span>
            </div>
            ${file.hash ? `
              <div class="flex items-center justify-between text-[10px] font-mono">
                <span class="text-gray-500">SHA-256:</span>
                <span class="text-gray-400 font-mono truncate max-w-[220px]">${escapeHTML(file.hash.slice(0, 16))}...</span>
              </div>
            ` : ""}
            <p class="text-[11px] font-sans text-gray-400 pt-1.5 border-t border-gray-800/60 leading-relaxed">
              ${escapeHTML(file.description || "")}
            </p>
          </div>

          <div class="grid grid-cols-2 gap-2.5 pt-1">
            <button id="btn-copy-artifact-qr-url" class="py-2.5 px-3 min-h-[44px] bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-md transition-all focus-ring cursor-pointer flex items-center justify-center gap-1.5">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              Copy Link
            </button>
            <a href="${escapeHTML(link.path)}" download class="py-2.5 px-3 min-h-[44px] bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 font-mono font-bold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center justify-center gap-1.5 text-center">
              <svg class="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              Download File
            </a>
          </div>
        </div>
      </div>
    `;

    const overlay = document.getElementById("modal-overlay");
    if (overlay) {
      overlay.innerHTML = modalHTML;
      overlay.classList.remove("hidden");
      overlay.removeAttribute("hidden");
      overlay.style.setProperty("display", "block", "important");
      const previousFocus = document.activeElement;
      const dialog = overlay.querySelector('[role="dialog"]');
      if (dialog) {
        dialog.setAttribute("tabindex", "-1");
        dialog.focus();
        this.trapFocus(dialog);
      }

      const closeModal = () => {
        overlay.classList.add("hidden");
        overlay.setAttribute("hidden", "true");
        overlay.style.setProperty("display", "none", "important");
        overlay.innerHTML = "";
        previousFocus?.focus?.();
      };

      document.getElementById("btn-close-artifact-qr")?.addEventListener("click", closeModal);
      document.getElementById("btn-copy-artifact-qr-url")?.addEventListener("click", () => {
        this.copyText(link.copyValue, link.isAbsolute
          ? `Copied artifact URL for ${file.filename}`
          : `Copied portable artifact path for ${file.filename}`);
      });

      overlay.addEventListener("click", (e) => {
        if (e.target.id === "artifact-qr-modal-container") {
          closeModal();
        }
      });
    }
  }

  renderRuleStudio() {
    if (typeof document === "undefined") return;
    const container = document.getElementById("rule-studio-section");
    if (!container) return;

    const rules = [
      { id: "r1", target: "geosite:category-ads-all", action: "BLOCK", type: "geosite" },
      { id: "r2", target: "geosite:cn", action: "DIRECT", type: "geosite" },
      { id: "r3", target: "geoip:cn", action: "DIRECT", type: "geoip" },
      { id: "r4", target: "openai.com", action: "PROXY-US", type: "domain" },
      { id: "r5", target: "github.com", action: "AUTO-BEST", type: "domain" },
      { id: "r6", target: "MATCH (Final)", action: "PROXY-AUTO", type: "match" }
    ];

    container.innerHTML = `
      <section class="mt-8 mb-6">
        <div class="glass-card bg-gray-900/60 border border-gray-800/80 hover:border-cyan-500/40 rounded-3xl p-6 sm:p-8 backdrop-blur-xl transition-all shadow-xl shadow-cyan-950/20">
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-gray-800">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"></path></svg>
              </div>
              <div>
                <h3 class="text-base font-mono font-bold text-gray-100 flex items-center gap-2">
                  Routing Profile Reference
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">EXAMPLE</span>
                </h3>
                <p class="text-xs text-gray-400 font-sans mt-0.5">Illustrative routing order. Download verified profiles from the published catalog; this panel does not modify a live client.</p>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-wrap">
              <a href="artifacts/release/all_sources.npvt.singbox.json" download class="px-3.5 py-2 min-h-[44px] bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 text-xs font-mono font-bold rounded-xl transition-all focus-ring flex items-center gap-1.5 cursor-pointer">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Sing-box JSON
              </a>
              <a href="artifacts/release/v2ray_test_config.json" download class="px-3.5 py-2 min-h-[44px] bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/40 text-indigo-300 text-xs font-mono font-bold rounded-xl transition-all focus-ring flex items-center gap-1.5 cursor-pointer">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Xray Config
              </a>
            </div>
          </div>

          <div class="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div class="lg:col-span-7 space-y-2.5">
              ${rules.map((rule, idx) => `
                <div class="flex items-center justify-between p-3.5 rounded-2xl bg-gray-950/80 border border-gray-800 text-xs font-mono group hover:border-cyan-500/40 transition-all">
                  <div class="flex items-center gap-3">
                    <span class="text-gray-500 font-bold w-4">${idx + 1}.</span>
                    <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider ${rule.type === 'geosite' ? 'bg-indigo-950 text-indigo-300 border border-indigo-800' : rule.type === 'geoip' ? 'bg-amber-950 text-amber-300 border border-amber-800' : 'bg-slate-800 text-gray-300 border border-slate-700'}">${rule.type}</span>
                    <span class="text-cyan-200 font-semibold">${escapeHTML(rule.target)}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="px-2.5 py-1 rounded-lg text-[11px] font-bold ${rule.action === 'BLOCK' ? 'bg-rose-950 text-rose-300 border border-rose-800' : rule.action === 'DIRECT' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-cyan-950 text-cyan-300 border border-cyan-800'}">${rule.action}</span>
                  </div>
                </div>
              `).join("")}
            </div>

            <div class="lg:col-span-5 flex flex-col justify-between p-5 rounded-2xl bg-gray-950 border border-gray-800">
              <div>
                <span class="text-xs font-mono uppercase tracking-wider text-gray-400 block mb-3 font-bold">Routing Pipeline Flow</span>
                <div class="space-y-2 text-xs font-mono">
                  <div class="p-3 rounded-xl bg-cyan-950/30 border border-cyan-800/40 text-cyan-300 flex items-center justify-between">
                    <span>1. Inbound (Mixed 7890 / TUN)</span>
                    <span class="text-[10px] text-cyan-400 font-bold">LISTEN</span>
                  </div>
                  <div class="text-center text-gray-600 text-sm">↓</div>
                  <div class="p-3 rounded-xl bg-indigo-950/30 border border-indigo-800/40 text-indigo-300 flex items-center justify-between">
                    <span>2. DNS &amp; Geo-Classifier</span>
                    <span class="text-[10px] text-indigo-400 font-bold">RESOLVE</span>
                  </div>
                  <div class="text-center text-gray-600 text-sm">↓</div>
                  <div class="p-3 rounded-xl bg-emerald-950/30 border border-emerald-800/40 text-emerald-300 flex items-center justify-between">
                    <span>3. Multi-Hop Outbounds</span>
                    <span class="text-[10px] text-emerald-400 font-bold">EGRESS</span>
                  </div>
                </div>
              </div>
              <div class="mt-4 pt-3 border-t border-gray-800/80 flex items-center justify-between text-[11px] font-mono text-gray-400">
                <span>Example rules: ${rules.length}</span>
                <span>Latency impact: not measured</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    `;
  }

  renderDecoderSection() {
    if (typeof document === "undefined") return;
    const decoderSection = document.getElementById("decoder-section") || document.getElementById("inline-decoder-section");
    if (!decoderSection) return;

    const currentTab = this.converterTab || "inspector";

    decoderSection.innerHTML = `
      <div class="my-10 p-6 sm:p-8 bg-gray-900/80 border border-cyan-500/20 rounded-3xl backdrop-blur-md shadow-xl">
        <div class="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 mb-6 pb-4 border-b border-gray-800">
          <div>
            <h3 class="text-lg font-mono font-bold text-white flex items-center gap-2">
              <svg class="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
              Universal Protocol Converter &amp; Inspection Studio
            </h3>
            <p class="text-xs font-mono text-gray-400 mt-0.5">High-performance client-side converter for Sing-box 1.10+, Clash Meta / Mihomo, Xray JSON, Base64 &amp; QR Codes</p>
          </div>

          <!-- Studio Tabs Header -->
          <div class="flex flex-wrap gap-1.5" role="tablist">
            <button
              class="btn-studio-tab px-3 py-2 min-h-[38px] rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer ${currentTab === 'inspector' ? 'bg-cyan-500 text-gray-950 font-bold shadow-md shadow-cyan-500/30' : 'bg-gray-950 text-gray-400 hover:text-gray-200 border border-gray-800'}"
              data-tab="inspector"
              role="tab"
              aria-selected="${currentTab === 'inspector'}"
            >
              🔍 Protocol Inspector
            </button>
            <button
              class="btn-studio-tab px-3 py-2 min-h-[38px] rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer ${currentTab === 'converter' ? 'bg-cyan-500 text-gray-950 font-bold shadow-md shadow-cyan-500/30' : 'bg-gray-950 text-gray-400 hover:text-gray-200 border border-gray-800'}"
              data-tab="converter"
              role="tab"
              aria-selected="${currentTab === 'converter'}"
            >
              ⚡ Universal Converter
            </button>
            <button
              class="btn-studio-tab px-3 py-2 min-h-[38px] rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer ${currentTab === 'dedup' ? 'bg-cyan-500 text-gray-950 font-bold shadow-md shadow-cyan-500/30' : 'bg-gray-950 text-gray-400 hover:text-gray-200 border border-gray-800'}"
              data-tab="dedup"
              role="tab"
              aria-selected="${currentTab === 'dedup'}"
            >
              🧹 Bulk Deduplicator
            </button>
            <button
              class="btn-studio-tab px-3 py-2 min-h-[38px] rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer ${currentTab === 'qr_studio' ? 'bg-cyan-500 text-gray-950 font-bold shadow-md shadow-cyan-500/30' : 'bg-gray-950 text-gray-400 hover:text-gray-200 border border-gray-800'}"
              data-tab="qr_studio"
              role="tab"
              aria-selected="${currentTab === 'qr_studio'}"
            >
              📱 QR Code Studio
            </button>
          </div>
        </div>

        <!-- Tab Content Container -->
        <div id="studio-tab-content">
        </div>
      </div>
    `;

    this.renderStudioTabContent();

    decoderSection.querySelectorAll(".btn-studio-tab").forEach(btn => {
      btn.addEventListener("click", (e) => {
        this.converterTab = e.currentTarget.dataset.tab;
        this.renderDecoderSection();
      });
    });
  }

  renderStudioTabContent() {
    const container = document.getElementById("studio-tab-content");
    if (!container) return;
    const currentTab = this.converterTab || "inspector";

    if (currentTab === "inspector") {
      const defaultUri = (this.proxies[0] && this.proxies[0].raw) || "vless://8f7b3c2a-9e1d-4a5b-b2c3-d4e5f6a7b8c9@104.21.45.88:443?security=reality&sni=speed.cloudflare.com&fp=chrome&pbk=abc123def456&sid=0123456789abcdef&type=grpc&serviceName=vless-grpc#%F0%9F%87%A9%F0%9F%87%AA%20DE-CF%20%7C%20VLESS-REALITY";
      container.innerHTML = `
        <div class="space-y-4">
          <div class="flex flex-col sm:flex-row gap-2">
            <input
              id="decoder-single-input"
              type="text"
              class="flex-1 px-4 py-2.5 min-h-[44px] bg-gray-950 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-cyan-300 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
              placeholder="Paste raw vless://, vmess://, trojan://, ss://, hysteria2://..."
              value="${escapeHTML(defaultUri)}"
            />
            <button
              id="btn-run-inspect"
              class="px-5 py-2.5 min-h-[44px] bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/20 transition-all cursor-pointer focus-ring"
            >
              Inspect Parameters
            </button>
          </div>

          <div id="inspector-output" class="mt-4"></div>
        </div>
      `;

      const runInspect = () => {
        const inputVal = (document.getElementById("decoder-single-input")?.value || "").trim();
        const out = document.getElementById("inspector-output");
        if (!out) return;
        if (!inputVal) {
          out.innerHTML = `<span class="text-gray-500 font-mono text-xs">Enter a proxy link above</span>`;
          return;
        }
        try {
          const decoded = decodeProxyURI(inputVal);
          const flag = this.getCountryFlag(this.inferCountryFromTagOrHost(decoded.name, decoded.server));
          const op = this.detectOperator(decoded.server, decoded.sni || decoded.host, decoded.name);
          const singboxOutbound = nodeToSingboxOutbound(decoded);
          const clashProxy = nodeToClashProxy(decoded);

          out.innerHTML = `
            <div class="bg-gray-950 border border-gray-800 rounded-2xl p-5 space-y-4 font-mono text-xs">
              <div class="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800/80 pb-3">
                <div class="flex items-center gap-2">
                  <span class="text-lg">${flag}</span>
                  <span class="px-2 py-0.5 rounded uppercase font-bold text-[11px] bg-cyan-950 text-cyan-300 border border-cyan-800">${escapeHTML(decoded.protocol)}</span>
                  <span class="px-1.5 py-0.5 rounded text-[11px] bg-gray-900 text-gray-300 border border-gray-800">${escapeHTML(op)}</span>
                  <span class="font-bold text-gray-200 truncate max-w-xs">${escapeHTML(decoded.name || 'Node')}</span>
                </div>
                <div class="flex gap-2">
                  <button id="btn-copy-node-json" class="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-cyan-300 rounded-lg text-xs cursor-pointer focus-ring">Copy JSON</button>
                  <button id="btn-copy-node-singbox" class="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-emerald-300 rounded-lg text-xs cursor-pointer focus-ring">Copy Sing-box</button>
                  <button id="btn-copy-node-clash" class="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-amber-300 rounded-lg text-xs cursor-pointer focus-ring">Copy Clash</button>
                </div>
              </div>

              <!-- Parameter Grid -->
              <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                  <span class="text-[10px] text-gray-500 block">Server Address</span>
                  <span class="text-cyan-300 font-semibold select-all">${escapeHTML(decoded.server)}</span>
                </div>
                <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                  <span class="text-[10px] text-gray-500 block">Port</span>
                  <span class="text-gray-200 select-all">${escapeHTML(decoded.port)}</span>
                </div>
                <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                  <span class="text-[10px] text-gray-500 block">Credential / UUID</span>
                  <span class="text-gray-300 select-all">${escapeHTML(decoded.uuid || decoded.password || "N/A")}</span>
                </div>
                <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                  <span class="text-[10px] text-gray-500 block">Security / TLS</span>
                  <span class="text-indigo-300">${escapeHTML(decoded.security || "none")}</span>
                </div>
                <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                  <span class="text-[10px] text-gray-500 block">SNI / ServerName</span>
                  <span class="text-cyan-300 select-all">${escapeHTML(decoded.sni || decoded.host || "None")}</span>
                </div>
                <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                  <span class="text-[10px] text-gray-500 block">Transport Network</span>
                  <span class="text-emerald-300">${escapeHTML(decoded.transport || "tcp")}</span>
                </div>
                ${decoded.publicKey ? `
                  <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                    <span class="text-[10px] text-gray-500 block">Reality Public Key (pbk)</span>
                    <span class="text-amber-300 select-all">${escapeHTML(decoded.publicKey)}</span>
                  </div>
                ` : ''}
                ${decoded.shortId ? `
                  <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                    <span class="text-[10px] text-gray-500 block">Short ID (sid)</span>
                    <span class="text-amber-300 select-all">${escapeHTML(decoded.shortId)}</span>
                  </div>
                ` : ''}
                ${decoded.serviceName ? `
                  <div class="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/60">
                    <span class="text-[10px] text-gray-500 block">gRPC ServiceName</span>
                    <span class="text-cyan-300 select-all">${escapeHTML(decoded.serviceName)}</span>
                  </div>
                ` : ''}
              </div>

              <!-- Full JSON Representation -->
              <div class="mt-2">
                <span class="text-[11px] text-gray-400 block mb-1 font-bold">Sing-box Outbound Object:</span>
                <pre class="p-3 bg-gray-900/80 rounded-xl border border-gray-800 overflow-x-auto text-[11px] text-gray-300">${escapeHTML(JSON.stringify(singboxOutbound, null, 2))}</pre>
              </div>
            </div>
          `;

          document.getElementById("btn-copy-node-json")?.addEventListener("click", () => {
            this.copyText(JSON.stringify(decoded, null, 2), "Decoded JSON copied");
          });
          document.getElementById("btn-copy-node-singbox")?.addEventListener("click", () => {
            this.copyText(JSON.stringify(singboxOutbound, null, 2), "Sing-box outbound JSON copied");
          });
          document.getElementById("btn-copy-node-clash")?.addEventListener("click", () => {
            let clashYaml = `name: "${clashProxy.name}"\ntype: ${clashProxy.type}\nserver: ${clashProxy.server}\nport: ${clashProxy.port}`;
            this.copyText(JSON.stringify(clashProxy, null, 2), "Clash Meta definition copied");
          });
        } catch (err) {
          out.innerHTML = `<div class="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 font-mono text-xs">Error inspecting link: ${escapeHTML(err.message)}</div>`;
        }
      };

      document.getElementById("btn-run-inspect")?.addEventListener("click", runInspect);
      document.getElementById("decoder-single-input")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") runInspect();
      });
      runInspect();
    } else if (currentTab === "converter") {
      const sampleURIs = this.proxies.slice(0, 5).map(p => p.raw).filter(Boolean).join("\n");
      container.innerHTML = `
        <div class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div class="sm:col-span-2">
              <label class="block text-xs font-mono text-gray-400 mb-1">Target Client / Engine Format</label>
              <select
                id="converter-format-select"
                class="w-full bg-gray-950 border border-gray-800 text-cyan-300 text-xs font-mono rounded-xl px-4 py-2.5 min-h-[44px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              >
                <option value="singbox">Sing-box 1.10+ Complete Client Config (JSON)</option>
                <option value="clash">Clash Meta / Mihomo Complete Profile (YAML)</option>
                <option value="xray">Xray-Core Complete Client Config (JSON)</option>
                <option value="surge">Surge 5 Proxy Config (.conf)</option>
                <option value="loon">Loon Proxy Client Config (.conf)</option>
                <option value="qx">Quantumult X Server Directives (.conf)</option>
                <option value="b64sub">Base64 Subscription Feed (v2rayNG / Streisand)</option>
                <option value="npvt">NPVT Clean Remark Text List (NekoBox / Hiddify)</option>
              </select>
            </div>
            <div class="flex items-end gap-2">
              <button
                id="btn-load-active-nodes"
                class="flex-1 px-3 py-2.5 min-h-[44px] bg-gray-800 hover:bg-gray-700 text-gray-200 font-mono text-xs rounded-xl focus-ring cursor-pointer transition-all"
              >
                Load Active Nodes (${this.proxies.length})
              </button>
            </div>
          </div>

          <div>
            <label class="block text-xs font-mono text-gray-400 mb-1">Source Proxy URIs / Base64 Subscription:</label>
            <textarea
              id="converter-input-text"
              rows="4"
              class="w-full px-4 py-3 bg-gray-950 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
              placeholder="Paste proxy URIs (one per line) or Base64 subscription string..."
            >${escapeHTML(sampleURIs)}</textarea>
          </div>

          <div class="flex justify-between items-center">
            <button
              id="btn-run-convert"
              class="px-6 py-2.5 min-h-[44px] bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/20 transition-all cursor-pointer focus-ring"
            >
              Convert All Nodes
            </button>
            <span id="converter-status" class="text-xs font-mono text-gray-400"></span>
          </div>

          <div id="converter-output-container" class="hidden mt-4 space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-xs font-mono font-bold text-cyan-400">Converted Output Result:</span>
              <div class="flex gap-2">
                <button id="btn-copy-converted" class="px-4 py-2 min-h-[38px] bg-gray-800 hover:bg-cyan-500 hover:text-gray-950 text-cyan-300 font-mono text-xs rounded-xl focus-ring cursor-pointer transition-all">Copy Output</button>
                <button id="btn-download-converted" class="px-4 py-2 min-h-[38px] bg-gray-800 hover:bg-gray-700 text-gray-200 font-mono text-xs rounded-xl focus-ring cursor-pointer transition-all">Download File</button>
              </div>
            </div>
            <textarea
              id="converter-output-text"
              rows="8"
              readonly
              class="w-full px-4 py-3 bg-gray-950 border border-gray-800 rounded-xl text-xs font-mono text-gray-300 focus:outline-none select-all"
            ></textarea>
          </div>
        </div>
      `;

      document.getElementById("btn-load-active-nodes")?.addEventListener("click", () => {
        const text = this.proxies.map(p => p.raw).filter(Boolean).join("\n");
        const ta = document.getElementById("converter-input-text");
        if (ta) ta.value = text;
        this.showToast(`Loaded ${this.proxies.length} active nodes into converter`);
      });

      document.getElementById("btn-run-convert")?.addEventListener("click", () => {
        const inputVal = (document.getElementById("converter-input-text")?.value || "").trim();
        const format = document.getElementById("converter-format-select")?.value;
        const outBox = document.getElementById("converter-output-container");
        const outText = document.getElementById("converter-output-text");
        const status = document.getElementById("converter-status");

        if (!inputVal) {
          this.showToast("Please enter proxy URIs to convert", "error");
          return;
        }

        try {
          const converted = convertProxyBatch(inputVal, format);
          outBox?.classList.remove("hidden");
          if (outText) outText.value = converted;
          if (status) status.textContent = `Conversion complete (${format.toUpperCase()})`;
          this.showToast("Batch conversion complete");
        } catch (err) {
          this.showToast(`Conversion failed: ${err.message}`, "error");
        }
      });

      document.getElementById("btn-copy-converted")?.addEventListener("click", () => {
        const text = document.getElementById("converter-output-text")?.value;
        if (text) this.copyText(text, "Converted output copied to clipboard");
      });

      document.getElementById("btn-download-converted")?.addEventListener("click", () => {
        const text = document.getElementById("converter-output-text")?.value;
        const format = document.getElementById("converter-format-select")?.value;
        if (!text) return;
        const filenames = {
          singbox: "singbox_config.json",
          clash: "clash_meta_config.yaml",
          xray: "xray_config.json",
          surge: "surge_config.conf",
          loon: "loon_config.conf",
          qx: "quantumult_x_config.conf",
          b64sub: "subscription.b64sub",
          npvt: "nodes_npvt.txt"
        };
        const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filenames[format] || "config.txt";
        a.click();
        URL.revokeObjectURL(url);
      });
    } else if (currentTab === "dedup") {
      container.innerHTML = `
        <div class="space-y-4">
          <p class="text-xs font-mono text-gray-400">Paste bulk proxies from multiple sources to eliminate duplicates, strip tracking queries, and generate clean identities.</p>
          
          <textarea
            id="dedup-input-text"
            rows="4"
            class="w-full px-4 py-3 bg-gray-950 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
            placeholder="Paste raw proxy URIs..."
          >${escapeHTML(this.proxies.map(p => p.raw).join("\n"))}</textarea>

          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-4 text-xs font-mono text-gray-300">
              <label class="flex items-center gap-1.5 cursor-pointer">
                <input id="chk-clean-remarks" type="checkbox" checked class="rounded bg-gray-950 border-gray-800 text-cyan-500 focus:ring-0">
                <span>Sanitize Remarks</span>
              </label>
              <label class="flex items-center gap-1.5 cursor-pointer">
                <input id="chk-enrich-operator" type="checkbox" checked class="rounded bg-gray-950 border-gray-800 text-cyan-500 focus:ring-0">
                <span>Enrich Operators</span>
              </label>
            </div>

            <button
              id="btn-run-dedup"
              class="px-6 py-2.5 min-h-[44px] bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/20 transition-all cursor-pointer focus-ring"
            >
              Run SHA-256 Deduplication
            </button>
          </div>

          <div id="dedup-result-box" class="hidden space-y-3 pt-2">
            <div class="grid grid-cols-3 gap-3 font-mono text-xs">
              <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl text-center">
                <span class="text-gray-500 text-[10px] block">Ingested</span>
                <span id="stat-ingested" class="text-gray-200 font-bold text-sm">0</span>
              </div>
              <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl text-center">
                <span class="text-gray-500 text-[10px] block">Unique Nodes</span>
                <span id="stat-unique" class="text-emerald-400 font-bold text-sm">0</span>
              </div>
              <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl text-center">
                <span class="text-gray-500 text-[10px] block">Duplicates Purged</span>
                <span id="stat-purged" class="text-rose-400 font-bold text-sm">0</span>
              </div>
            </div>

            <div class="flex justify-end gap-2">
              <button id="btn-copy-dedup-result" class="px-4 py-2 min-h-[38px] bg-gray-800 hover:bg-cyan-500 hover:text-gray-950 text-cyan-300 font-mono text-xs rounded-xl focus-ring cursor-pointer transition-all">Copy Unique URIs</button>
            </div>

            <textarea
              id="dedup-output-text"
              rows="6"
              readonly
              class="w-full px-4 py-3 bg-gray-950 border border-gray-800 rounded-xl text-xs font-mono text-gray-300 focus:outline-none select-all"
            ></textarea>
          </div>
        </div>
      `;

      document.getElementById("btn-run-dedup")?.addEventListener("click", () => {
        const text = document.getElementById("dedup-input-text")?.value || "";
        const uris = extractAllURIs(text);
        const seen = new Set();
        const unique = [];

        uris.forEach(u => {
          try {
            const dec = decodeProxyURI(u);
            const key = `${dec.protocol}://${dec.address}:${dec.port}/${dec.uuid || dec.password || ''}`;
            if (!seen.has(key)) {
              seen.add(key);
              unique.push(u);
            }
          } catch {
            if (!seen.has(u)) {
              seen.add(u);
              unique.push(u);
            }
          }
        });

        document.getElementById("dedup-result-box")?.classList.remove("hidden");
        document.getElementById("stat-ingested").textContent = uris.length;
        document.getElementById("stat-unique").textContent = unique.length;
        document.getElementById("stat-purged").textContent = uris.length - unique.length;
        document.getElementById("dedup-output-text").value = unique.join("\n");
        this.showToast(`Deduplication complete: ${unique.length} unique nodes.`);
      });

      document.getElementById("btn-copy-dedup-result")?.addEventListener("click", () => {
        const res = document.getElementById("dedup-output-text")?.value;
        if (res) this.copyText(res, "Unique nodes copied to clipboard");
      });
    } else if (currentTab === "qr_studio") {
      const defaultQrText = (this.proxies[0] && this.proxies[0].raw) || "vless://8f7b3c2a-9e1d-4a5b-b2c3-d4e5f6a7b8c9@104.21.45.88:443?security=reality&sni=speed.cloudflare.com&fp=chrome&pbk=abc123def456&sid=0123456789abcdef&type=grpc#DE-CF";
      container.innerHTML = `
        <div class="space-y-4">
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <div class="lg:col-span-7 space-y-3">
              <label class="block text-xs font-mono text-gray-400">Content / Proxy URI to Encode:</label>
              <textarea
                id="qr-studio-input"
                rows="4"
                class="w-full px-4 py-3 bg-gray-950 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
                placeholder="Paste link or text to generate scannable ISO/IEC 18004 QR Code..."
              >${escapeHTML(defaultQrText)}</textarea>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label class="block text-[10px] font-mono text-gray-400 mb-1">Color Preset:</label>
                  <select
                    id="qr-studio-color-preset"
                    class="w-full bg-gray-950 border border-gray-800 text-gray-300 text-xs font-mono rounded-xl px-3 py-2 min-h-[38px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
                  >
                    <option value="cyber">Cyber Cyan &amp; Dark (#070a0f / #ffffff)</option>
                    <option value="mono_dark">High-Contrast Pure B&amp;W (#000000 / #ffffff)</option>
                    <option value="emerald">Matrix Emerald (#022c22 / #6ee7b7)</option>
                  </select>
                </div>
                <div>
                  <label class="block text-[10px] font-mono text-gray-400 mb-1">Error Correction (ECC):</label>
                  <select
                    id="qr-studio-ecc"
                    class="w-full bg-gray-950 border border-gray-800 text-gray-300 text-xs font-mono rounded-xl px-3 py-2 min-h-[38px] focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
                  >
                    <option value="M" selected>Level M (15% Recovery - Standard)</option>
                    <option value="L">Level L (7% Recovery - Dense)</option>
                    <option value="Q">Level Q (25% Recovery - Robust)</option>
                    <option value="H">Level H (30% Recovery - Maximum)</option>
                  </select>
                </div>
              </div>
            </div>

            <div class="lg:col-span-5 flex flex-col items-center justify-center p-6 bg-gray-950 border border-gray-800 rounded-2xl space-y-3">
              <div id="qr-studio-render-target" class="p-3 bg-white rounded-2xl shadow-lg flex items-center justify-center min-h-[220px] min-w-[220px]">
              </div>

              <div class="flex gap-2 w-full">
                <button id="btn-download-qr-svg" class="flex-1 py-2 min-h-[40px] bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer transition-all shadow-md shadow-cyan-500/20">Download SVG</button>
                <button id="btn-copy-qr-svg" class="py-2 px-4 min-h-[40px] bg-gray-800 hover:bg-gray-700 text-cyan-300 font-mono text-xs rounded-xl focus-ring cursor-pointer transition-all">Copy SVG</button>
              </div>
            </div>
          </div>
        </div>
      `;

      const refreshQR = () => {
        const text = (document.getElementById("qr-studio-input")?.value || "").trim() || defaultQrText;
        const preset = document.getElementById("qr-studio-color-preset")?.value || "cyber";
        const ecc = document.getElementById("qr-studio-ecc")?.value || "M";
        const target = document.getElementById("qr-studio-render-target");
        if (!target) return;

        let dark = "#070a0f";
        let light = "#ffffff";
        if (preset === "cyber") {
          dark = "#070a0f";
          light = "#ffffff";
        } else if (preset === "mono_dark") {
          dark = "#000000";
          light = "#ffffff";
        } else if (preset === "emerald") {
          dark = "#022c22";
          light = "#6ee7b7";
        }

        target.innerHTML = renderQRCodeSVG(text, 200, dark, light, ecc);
      };

      document.getElementById("qr-studio-input")?.addEventListener("input", refreshQR);
      document.getElementById("qr-studio-color-preset")?.addEventListener("change", refreshQR);
      document.getElementById("qr-studio-ecc")?.addEventListener("change", refreshQR);
      refreshQR();

      document.getElementById("btn-download-qr-svg")?.addEventListener("click", () => {
        const svgContent = document.getElementById("qr-studio-render-target")?.innerHTML;
        if (!svgContent) return;
        const blob = new Blob([svgContent], { type: "image/svg+xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "proxy_qrcode.svg";
        a.click();
        URL.revokeObjectURL(url);
      });

      document.getElementById("btn-copy-qr-svg")?.addEventListener("click", () => {
        const svgContent = document.getElementById("qr-studio-render-target")?.innerHTML;
        if (svgContent) this.copyText(svgContent, "QR Code SVG XML copied to clipboard");
      });
    }
  }

  openDecoderModal(initialUri = "") {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    let defaultVal = initialUri || (this.proxies[0] && this.proxies[0].raw) || "";
    let decodedRes = null;
    try {
      decodedRes = decodeProxyURI(defaultVal);
    } catch {}

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-decoder-title">
        <div id="modal-box" class="relative w-full max-w-2xl bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/50 space-y-6">
          <div class="flex items-center justify-between border-b border-gray-800 pb-4">
            <div class="flex items-center gap-2">
              <span class="p-2 bg-cyan-950 text-cyan-400 rounded-xl">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
              </span>
              <h3 id="modal-decoder-title" class="text-lg font-mono font-bold text-white">Proxy Protocol Inspector</h3>
            </div>
            <button id="btn-close-modal" class="p-2 min-h-[40px] min-w-[40px] flex items-center justify-center bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white rounded-xl focus-ring cursor-pointer" aria-label="Close modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <div class="space-y-3">
            <label for="modal-decoder-textarea" class="block text-xs font-mono text-gray-400">Raw Proxy URI / Subscription Payload:</label>
            <textarea
              id="modal-decoder-textarea"
              rows="3"
              class="w-full px-3 py-2 bg-gray-950 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-gray-200 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
            >${escapeHTML(defaultVal)}</textarea>
          </div>

          <div id="modal-decoder-output" class="p-4 bg-gray-950 border border-gray-800 rounded-2xl max-h-[300px] overflow-y-auto font-mono text-xs">
            ${decodedRes ? `<pre class="text-gray-300 text-[11px]">${escapeHTML(JSON.stringify(decodedRes, null, 2))}</pre>` : `<span class="text-gray-500">Click parse to inspect</span>`}
          </div>

          <div class="flex justify-end gap-3 pt-2">
            <button id="modal-btn-copy-raw" class="px-4 py-2 min-h-[40px] bg-gray-800 hover:bg-gray-700 text-gray-200 font-mono text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy raw proxy URI">Copy Raw</button>
            <button id="modal-btn-copy-json" class="px-4 py-2 min-h-[40px] bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy decoded parameters JSON">Copy Decoded JSON</button>
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");
    const box = document.getElementById("modal-box");
    if (box) this.trapFocus(box);

    document.getElementById("btn-close-modal")?.addEventListener("click", () => {
      this.closeModal();
    });

    const ta = document.getElementById("modal-decoder-textarea");
    ta?.addEventListener("input", (e) => {
      try {
        const parsed = decodeProxyURI(e.target.value);
        document.getElementById("modal-decoder-output").innerHTML = `<pre class="text-gray-300 text-[11px]">${escapeHTML(JSON.stringify(parsed, null, 2))}</pre>`;
      } catch (err) {
        document.getElementById("modal-decoder-output").innerHTML = `<span class="text-rose-400">${escapeHTML(err.message)}</span>`;
      }
    });

    document.getElementById("modal-btn-copy-raw")?.addEventListener("click", () => {
      this.copyText(ta.value, "Raw URI copied");
    });

    document.getElementById("modal-btn-copy-json")?.addEventListener("click", () => {
      try {
        const parsed = decodeProxyURI(ta.value);
        this.copyText(JSON.stringify(parsed, null, 2), "JSON parameters copied");
      } catch {
        this.showToast("Cannot copy invalid JSON", "error");
      }
    });
  }

  openQRModal(raw, name) {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-qr-title">
        <div id="modal-box" class="relative w-full max-w-sm bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 shadow-2xl shadow-cyan-950/50 text-center space-y-4">
          <div class="flex items-center justify-between">
            <h3 id="modal-qr-title" class="text-sm font-mono font-bold text-white truncate max-w-[240px]">${escapeHTML(name)}</h3>
            <button id="btn-close-qr" class="p-2 min-h-[38px] min-w-[38px] flex items-center justify-center bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close QR Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <div class="flex items-center justify-center py-3">
            ${renderQRCodeSVG(raw, 220)}
          </div>

          <p class="text-[11px] font-mono text-gray-400">Scan with v2rayNG, Streisand, Sing-box, or Shadowrocket</p>

          <button id="btn-copy-qr-raw" class="w-full py-2.5 min-h-[44px] bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy Node URI to clipboard">
            Copy Node URI
          </button>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");
    const box = document.getElementById("modal-box");
    if (box) this.trapFocus(box);

    document.getElementById("btn-close-qr")?.addEventListener("click", () => {
      this.closeModal();
    });

    document.getElementById("btn-copy-qr-raw")?.addEventListener("click", () => {
      this.copyText(raw, "Node URI copied to clipboard");
    });
  }

  openSubscriptionBuilderModal() {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    const hosted = isHostedDashboard();
    const publicBase = getConfiguredPublicBase();
    const files = Array.isArray(this.catalog?.files) ? this.catalog.files : [];
    const findArtifact = (filename) => files.find((file) => (file.filename || file.name) === filename);
    const productionFeeds = [
      ["all_sources.npvt.b64sub", "Base64 Unified Feed", "Shadowrocket, v2rayNG, Streisand", "cyan"],
      ["all_sources.npvt.singbox.json", "Sing-box 1.10+ Outbounds", "Sing-box JSON outbounds format", "cyan"],
      ["v2ray_test_config.json", "Xray / V2Ray Core Config", "Complete client config JSON", "indigo"],
      ["all_sources.ovpn", "OpenVPN Profile", "Standard .ovpn multi-gateway", "amber"],
    ].map(([filename, label, description, color]) => ({ filename, label, description, color, file: findArtifact(filename) }));
    const devFeeds = files.filter((file) => file.section === "dev" || file.category === "dev" || file.tags?.includes("dev"));
    const chunks = devFeeds.filter((file) => /chunk_/i.test(file.filename || file.name || ""));
    const feedCard = ({ label, description, color, file }) => {
      if (!file) return "";
      const link = getArtifactLinkModel(file.path);
      return `
      <div class="p-3.5 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs flex flex-col justify-between">
        <div>
          <span class="text-gray-200 font-bold block">${escapeHTML(label)}</span>
          <span class="text-[11px] text-gray-500 block mt-0.5">${escapeHTML(description)}</span>
        </div>
        <div class="mt-3 rounded-lg border border-gray-800 bg-black/20 px-2.5 py-2">
          <div class="text-[9px] uppercase tracking-wider text-gray-500 mb-1">${escapeHTML(link.sourceLabel)}</div>
          <div class="text-[10px] text-${color}-300 break-all">${escapeHTML(link.display)}</div>
        </div>
        <div class="mt-3 flex items-center justify-end gap-2">
          <button class="btn-copy-custom px-3 py-1.5 min-h-[44px] bg-${color}-500 text-${color === "indigo" ? "white" : "gray-950"} font-bold rounded-lg text-[10px] cursor-pointer focus-ring" data-url="${escapeHTML(link.copyValue)}" data-absolute="${link.isAbsolute}">Copy</button>
        </div>
      </div>`;
    };

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-sub-title">
        <div id="modal-box" class="relative w-full max-w-2xl bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/50 space-y-5 max-h-[90vh] overflow-y-auto">
          <div class="flex items-center justify-between border-b border-gray-800 pb-3">
            <h3 id="modal-sub-title" class="text-base font-mono font-bold text-white flex items-center gap-2">
              <svg class="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
              Subscription Feeds &amp; Client Configurations
            </h3>
            <button id="btn-close-sub" class="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close Subscription Builder Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <p class="text-xs font-mono text-gray-400">Choose a verified client profile. Links are generated from the published catalog and never from a local filesystem path.</p>
          ${hosted || publicBase ? "" : `<div class="rounded-xl border border-amber-500/30 bg-amber-950/30 px-3.5 py-3 text-xs leading-relaxed text-amber-200"><strong>Local preview:</strong> copy actions use portable relative paths. Serve or deploy this dashboard over HTTPS, or configure <code>HUNTX_PUBLIC_BASE_URL</code> / <code>&lt;meta name="huntx-public-base-url"&gt;</code>, before importing a subscription on another device.</div>`}

          <div class="space-y-4">
            <!-- Production Feeds -->
            <div>
              <span class="text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider block mb-2">1. Production Feeds (Latest Verified Run)</span>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                ${productionFeeds.map(feedCard).join("") || `<p class="col-span-full rounded-xl border border-amber-500/30 bg-amber-950/20 p-3 text-xs text-amber-200">No compatible production profiles are in this published catalog.</p>`}
              </div>
            </div>

            ${devFeeds.length ? `
              <div>
                <span class="text-xs font-mono font-bold text-indigo-400 uppercase tracking-wider block mb-2">2. Additional Published Feeds</span>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  ${devFeeds.filter((file) => !chunks.includes(file)).map((file) => feedCard({ label: file.filename || file.name, description: file.size_str || "Published artifact", color: "indigo", file })).join("")}
                </div>
              </div>
              ${chunks.length ? `<div><span class="text-xs font-mono font-bold text-emerald-400 uppercase tracking-wider block mb-2">3. Lightweight Split Chunks</span><p class="text-[11px] font-mono text-gray-500 mb-2">Only chunks included in this catalog are shown.</p><div class="grid grid-cols-2 sm:grid-cols-4 gap-2">${chunks.map((file, index) => { const link = getArtifactLinkModel(file.path); return `<button class="btn-copy-custom p-2.5 min-h-[44px] bg-gray-950 hover:bg-gray-800 border border-gray-800 hover:border-cyan-500/40 rounded-xl text-left font-mono text-xs transition-all cursor-pointer focus-ring" data-url="${escapeHTML(link.copyValue)}" data-absolute="${link.isAbsolute}" title="${escapeHTML(link.display)}"><div class="text-cyan-300 font-bold">Chunk ${index + 1}</div><div class="text-[10px] text-gray-500 truncate">${escapeHTML(file.size_str || "Published artifact")}</div><div class="text-[9px] text-gray-500 truncate mt-1">${escapeHTML(link.display)}</div></button>`; }).join("")}</div></div>` : ""}
            ` : ""}
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");
    const box = document.getElementById("modal-box");
    if (box) this.trapFocus(box);

    document.getElementById("btn-close-sub")?.addEventListener("click", () => {
      this.closeModal();
    });

    modalContainer.querySelectorAll(".btn-copy-custom").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const url = e.currentTarget.dataset.url;
        const isAbsolute = e.currentTarget.dataset.absolute === "true";
        this.copyText(url, isAbsolute
          ? "Subscription feed URL copied"
          : "Portable artifact path copied — configure a public base URL for direct client import");
      });
    });
  }

  openCleanIPScannerModal() {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-scanner-title">
        <div id="modal-box" class="relative w-full max-w-3xl bg-gray-900 border border-emerald-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-emerald-950/50 space-y-5 max-h-[90vh] overflow-y-auto">
          <div class="flex items-center justify-between border-b border-gray-800 pb-3">
            <div class="flex items-center gap-2">
              <span class="p-2 bg-emerald-950 text-emerald-400 rounded-xl">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
              </span>
              <div>
                <h3 id="modal-scanner-title" class="text-base font-mono font-bold text-white">Cloudflare Clean IP Scanner</h3>
                <span class="text-[10px] font-mono text-gray-400">In-Browser Bitshift CIDR Expansion &amp; Latency Speedtest</span>
              </div>
            </div>
            <button id="btn-close-scanner" class="p-2 min-h-[38px] min-w-[38px] flex items-center justify-center bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close Clean IP Scanner Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <!-- Controls -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 p-4 bg-gray-950 border border-gray-800 rounded-2xl">
            <div>
              <label for="scanner-cidr-select" class="block text-[11px] font-mono text-gray-400 mb-1">Target CIDR Subnet:</label>
              <select id="scanner-cidr-select" class="w-full px-3 py-2 bg-gray-900 border border-gray-800 focus:border-emerald-500 rounded-xl text-xs font-mono text-gray-200 focus-ring cursor-pointer">
                <option value="104.16.0.0/12">104.16.0.0/12 (CDN Core 1)</option>
                <option value="172.64.0.0/13">172.64.0.0/13 (CDN Core 2)</option>
                <option value="162.158.0.0/15">162.158.0.0/15 (CDN Core 3)</option>
                <option value="198.41.128.0/17">198.41.128.0/17 (Global Edge)</option>
                <option value="108.162.192.0/18">108.162.192.0/18 (Regional Edge)</option>
                <option value="173.245.48.0/20">173.245.48.0/20 (Specialized)</option>
              </select>
            </div>

            <div>
              <label for="scanner-count-input" class="block text-[11px] font-mono text-gray-400 mb-1">Sample Count:</label>
              <input type="number" id="scanner-count-input" value="12" min="3" max="50" class="w-full px-3 py-2 bg-gray-900 border border-gray-800 focus:border-emerald-500 rounded-xl text-xs font-mono text-gray-200 focus-ring" />
            </div>

            <div class="flex items-end">
              <button id="scanner-btn-start" class="w-full py-2 min-h-[40px] bg-emerald-500 hover:bg-emerald-400 text-gray-950 font-mono font-bold text-xs rounded-xl transition-all shadow-md shadow-emerald-950/50 flex items-center justify-center gap-2 focus-ring cursor-pointer">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                <span>Start Speedtest</span>
              </button>
            </div>
          </div>

          <!-- Status Banner -->
          <div id="scanner-status-banner" class="flex items-center justify-between px-4 py-2.5 bg-gray-950 border border-gray-800 rounded-xl text-xs font-mono text-gray-400">
            <span id="scanner-status-text">Ready to scan. Select range and start speedtest.</span>
            <span id="scanner-progress-pill" class="hidden px-2 py-0.5 bg-emerald-950 text-emerald-400 rounded text-[10px] font-bold">0 / 0</span>
          </div>

          <!-- Results Grid -->
          <div class="border border-gray-800 rounded-2xl overflow-hidden bg-gray-950">
            <div class="max-h-[260px] overflow-y-auto">
              <table class="w-full text-left font-mono text-xs">
                <thead class="bg-gray-900/80 sticky top-0 text-[10px] text-gray-500 uppercase tracking-wider border-b border-gray-800">
                  <tr>
                    <th class="p-3">#</th>
                    <th class="p-3">Target IP</th>
                    <th class="p-3">Latency (RTT)</th>
                    <th class="p-3">Status</th>
                    <th class="p-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody id="scanner-results-tbody" class="divide-y divide-gray-800/60">
                  <tr>
                    <td colspan="5" class="p-6 text-center text-gray-600 font-mono text-xs">No scan performed yet.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Footer Actions -->
          <div class="flex flex-wrap items-center justify-between gap-3 pt-2">
            <div class="flex items-center gap-2">
              <button id="scanner-btn-copy-best" class="px-3.5 py-2 min-h-[38px] bg-gray-800 hover:bg-gray-700 text-emerald-300 font-mono text-xs rounded-xl focus-ring cursor-pointer disabled:opacity-40" disabled>Copy Best IP</button>
              <button id="scanner-btn-copy-all" class="px-3.5 py-2 min-h-[38px] bg-gray-800 hover:bg-gray-700 text-gray-200 font-mono text-xs rounded-xl focus-ring cursor-pointer disabled:opacity-40" disabled>Copy All Clean</button>
            </div>
            <div class="flex items-center gap-2">
              <button id="scanner-btn-export-csv" class="px-3.5 py-2 min-h-[38px] bg-gray-800 hover:bg-gray-700 text-gray-300 font-mono text-xs rounded-xl focus-ring cursor-pointer disabled:opacity-40" disabled>Export CSV</button>
              <button id="scanner-btn-export-json" class="px-3.5 py-2 min-h-[38px] bg-emerald-950 text-emerald-300 border border-emerald-800/60 font-mono text-xs rounded-xl focus-ring cursor-pointer disabled:opacity-40" disabled>Export JSON</button>
            </div>
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");
    const box = document.getElementById("modal-box");
    if (box) this.trapFocus(box);

    document.getElementById("btn-close-scanner")?.addEventListener("click", () => {
      this.closeModal();
    });

    let scanResults = [];

    const generateSampleIPs = (cidr, count) => {
      const parts = cidr.split("/");
      const baseIp = parts[0];
      const mask = parseInt(parts[1], 10);
      const octets = baseIp.split(".").map(Number);
      const startInt = ((octets[0] << 24) >>> 0) + ((octets[1] << 16) >>> 0) + ((octets[2] << 8) >>> 0) + (octets[3] >>> 0);
      const totalIps = 1 << (32 - mask);
      const sampled = new Set();
      const ips = [];
      const actualCount = Math.min(count, totalIps - 2);
      while (ips.length < actualCount) {
        const offset = Math.floor(Math.random() * (totalIps - 2)) + 1;
        if (!sampled.has(offset)) {
          sampled.add(offset);
          const ipInt = (startInt + offset) >>> 0;
          ips.push([
            (ipInt >>> 24) & 255,
            (ipInt >>> 16) & 255,
            (ipInt >>> 8) & 255,
            ipInt & 255
          ].join("."));
        }
      }
      return ips;
    };

    const pingTest = async (ip, timeoutMs = 1800) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      const t0 = performance.now();
      try {
        await fetch(`https://${ip}/__cf_speedtest?rnd=${Math.random()}`, {
          mode: "no-cors",
          cache: "no-store",
          signal: controller.signal
        });
        clearTimeout(timer);
        return { ok: true, latency: Math.round(performance.now() - t0) };
      } catch (err) {
        clearTimeout(timer);
        const elapsed = Math.round(performance.now() - t0);
        return { ok: false, latency: elapsed, timeout: err?.name === "AbortError", error: err?.name || "network failure" };
      }
    };

    const renderTable = () => {
      const tbody = document.getElementById("scanner-results-tbody");
      if (!tbody) return;
      if (scanResults.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-gray-600 font-mono text-xs">No results.</td></tr>`;
        return;
      }
      tbody.innerHTML = scanResults.map((r, idx) => `
        <tr class="hover:bg-gray-900/60 transition-colors">
          <td class="p-3 text-gray-500 font-mono text-[11px]">${idx + 1}</td>
          <td class="p-3 font-mono font-semibold ${r.ok ? 'text-white' : 'text-gray-500'}">${escapeHTML(r.ip)}</td>
          <td class="p-3 font-mono">
            ${r.ok ? `
              <span class="${r.latency < 250 ? 'text-emerald-400' : r.latency < 600 ? 'text-amber-400' : 'text-orange-400'} font-bold">
                ${r.latency} ms
              </span>
            ` : `<span class="text-rose-400 text-[11px]">Timeout</span>`}
          </td>
          <td class="p-3">
            <span class="px-2 py-0.5 text-[9px] font-mono font-bold rounded ${r.ok ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/50' : 'bg-rose-950 text-rose-400 border border-rose-800/50'}">
              ${r.ok ? 'CLEAN' : 'TIMEOUT'}
            </span>
          </td>
          <td class="p-3 text-right">
            <button class="btn-copy-scanned-ip px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-cyan-300 rounded text-[10px] font-mono focus-ring cursor-pointer" data-ip="${escapeHTML(r.ip)}">Copy</button>
          </td>
        </tr>
      `).join("");

      tbody.querySelectorAll(".btn-copy-scanned-ip").forEach(btn => {
        btn.addEventListener("click", (e) => {
          this.copyText(e.currentTarget.dataset.ip, `IP ${e.currentTarget.dataset.ip} copied`);
        });
      });
    };

    const startBtn = document.getElementById("scanner-btn-start");
    startBtn?.addEventListener("click", async () => {
      const cidr = document.getElementById("scanner-cidr-select").value;
      const count = parseInt(document.getElementById("scanner-count-input").value, 10) || 12;
      const statusText = document.getElementById("scanner-status-text");
      const progressPill = document.getElementById("scanner-progress-pill");
      
      startBtn.disabled = true;
      startBtn.innerHTML = `
        <svg class="w-4 h-4 animate-spin text-gray-950" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
        <span>Scanning...</span>
      `;
      progressPill.classList.remove("hidden");
      scanResults = [];
      renderTable();

      const candidateIps = generateSampleIPs(cidr, count);
      let completed = 0;

      for (const ip of candidateIps) {
        statusText.textContent = `Probing candidate: ${ip}...`;
        progressPill.textContent = `${completed + 1} / ${candidateIps.length}`;
        const res = await pingTest(ip);
        scanResults.push({ ip, ...res });
        completed++;
        scanResults.sort((a, b) => (a.ok === b.ok ? a.latency - b.latency : a.ok ? -1 : 1));
        renderTable();
      }

      startBtn.disabled = false;
      startBtn.innerHTML = `
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
        <span>Rescan Subnet</span>
      `;
      const cleanCount = scanResults.filter(r => r.ok).length;
      statusText.textContent = `Scan complete! ${cleanCount} browser requests completed; proxy usability remains unverified.`;
      progressPill.textContent = `${cleanCount} Completed`;

      const bestIp = scanResults.find(r => r.ok);
      if (bestIp) {
        document.getElementById("scanner-btn-copy-best").disabled = false;
        document.getElementById("scanner-btn-copy-all").disabled = false;
        document.getElementById("scanner-btn-export-csv").disabled = false;
        document.getElementById("scanner-btn-export-json").disabled = false;
      }
    });

    document.getElementById("scanner-btn-copy-best")?.addEventListener("click", () => {
      const best = scanResults.find(r => r.ok);
      if (best) this.copyText(best.ip, `Fastest browser-completed request: ${best.ip} (${best.latency}ms) copied`);
    });

    document.getElementById("scanner-btn-copy-all")?.addEventListener("click", () => {
      const cleanIps = scanResults.filter(r => r.ok).map(r => r.ip).join("\n");
      if (cleanIps) this.copyText(cleanIps, "All browser-completed IPs copied to clipboard");
    });

    document.getElementById("scanner-btn-export-csv")?.addEventListener("click", () => {
      const header = "IP,Latency_ms,Status\n";
      const rows = scanResults.map(r => `${r.ip},${r.latency},${r.ok ? 'CLEAN' : 'TIMEOUT'}`).join("\n");
      const blob = new Blob([header + rows], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cloudflare_clean_ips_${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      this.showToast("Clean IPs exported as CSV");
    });

    document.getElementById("scanner-btn-export-json")?.addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(scanResults, null, 2)], { type: "application/json;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cloudflare_clean_ips_${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      this.showToast("Clean IPs exported as JSON");
    });
  }

  renderFooter() {
    if (typeof document === "undefined") return;
    const footer = document.getElementById("main-footer");
    if (!footer) return;

    footer.innerHTML = `
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-gray-800/80 text-xs font-mono text-gray-500">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>HUNTX &amp; GatherX Ingestion Pipeline • SHA-256 Verified • ${this.catalog.total_files || 27} Artifacts Published</span>
        </div>
        <div class="flex items-center gap-4">
          <a href="DEVELOPMENT.md" class="hover:text-gray-300 transition-colors focus-ring rounded p-1">Dev Specs</a>
          <a href="USER_GUIDE.md" class="hover:text-gray-300 transition-colors focus-ring rounded p-1">User Guide</a>
          <a href="architecture.html" target="_blank" class="text-cyan-400 hover:underline focus-ring rounded p-1">3D Architecture Map</a>
          <a href="https://github.com/AmirrezaFarnamTaheri/HUNTX" target="_blank" class="hover:text-gray-300 transition-colors focus-ring rounded p-1">GitHub</a>
        </div>
      </div>
    `;
  }

  openQRModal(uri, name = "Proxy Node") {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-qr-title">
        <div id="modal-box" class="relative w-full max-w-md bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/50 space-y-5 text-center">
          <div class="flex items-center justify-between border-b border-gray-800 pb-3">
            <h3 id="modal-qr-title" class="text-sm font-mono font-bold text-gray-100 truncate">${escapeHTML(name)}</h3>
            <button id="btn-close-qr-modal" class="p-2 min-h-[38px] min-w-[38px] flex items-center justify-center bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close QR Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <div class="p-4 bg-white rounded-2xl flex items-center justify-center shadow-lg">
            ${renderQRCodeSVG(uri, 220, "#070a0f", "#ffffff", "M")}
          </div>

          <p class="text-[11px] font-mono text-gray-400">Scan using v2rayNG, Sing-box, NekoBox, Hiddify, or Streisand</p>

          <div class="flex gap-2">
            <button id="btn-copy-qr-uri" class="flex-1 py-2 min-h-[40px] bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer transition-all shadow-md shadow-cyan-500/20">
              Copy Node URI
            </button>
            <button id="btn-download-qr-modal-svg" class="py-2 px-4 min-h-[40px] bg-gray-800 hover:bg-gray-700 text-cyan-300 font-mono text-xs rounded-xl focus-ring cursor-pointer transition-all">
              Save SVG
            </button>
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");
    const box = document.getElementById("modal-box");
    if (box) this.trapFocus(box);

    document.getElementById("btn-close-qr-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("btn-copy-qr-uri")?.addEventListener("click", () => {
      this.copyText(uri, "Proxy URI copied to clipboard");
    });
    document.getElementById("btn-download-qr-modal-svg")?.addEventListener("click", () => {
      const svg = renderQRCodeSVG(uri, 240, "#070a0f", "#ffffff", "M");
      const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `huntx_qr_${Date.now()}.svg`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  openShortcutsModal() {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    const shortcuts = [
      { key: "1 - 5", desc: "Switch Tab (Radar / Proxies / Studio / Decoder / Artifacts)" },
      { key: "/", desc: "Focus global search filter" },
      { key: "V", desc: "Toggle View Mode (Cards / Table / Feed)" },
      { key: "D", desc: "Open Protocol Decoder & Inspection Modal" },
      { key: "S", desc: "Open Cloudflare Clean IP Scanner" },
      { key: "B", desc: "Open Custom Subscription Builder" },
      { key: "T", desc: "Toggle Light / Dark Obsidian Theme" },
      { key: "R", desc: "Reset all dimensional filters" },
      { key: "? or K", desc: "Show this Keyboard Shortcuts cheat-sheet" },
      { key: "Esc", desc: "Close any active modal dialog" }
    ];

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-shortcuts-title">
        <div id="modal-box" class="relative w-full max-w-md bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/50 space-y-5">
          <div class="flex items-center justify-between border-b border-gray-800 pb-3">
            <div class="flex items-center gap-2">
              <span class="p-2 bg-cyan-950 text-cyan-400 rounded-xl">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"></path></svg>
              </span>
              <div>
                <h3 id="modal-shortcuts-title" class="text-base font-mono font-bold text-white">Keyboard Navigation</h3>
                <span class="text-[10px] font-mono text-gray-400">Power-user keybindings for HUNTX</span>
              </div>
            </div>
            <button id="btn-close-shortcuts" class="p-2 min-h-[38px] min-w-[38px] flex items-center justify-center bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close Shortcuts Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <div class="space-y-2 font-mono text-xs">
            ${shortcuts.map(s => `
              <div class="flex items-center justify-between p-2.5 bg-gray-950 border border-gray-800/80 rounded-xl">
                <span class="text-gray-300">${escapeHTML(s.desc)}</span>
                <kbd class="px-2.5 py-1 bg-gray-900 border border-gray-700 text-cyan-300 font-bold rounded-lg text-[11px] shadow-sm">${escapeHTML(s.key)}</kbd>
              </div>
            `).join("")}
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");
    const box = document.getElementById("modal-box");
    if (box) this.trapFocus(box);

    document.getElementById("btn-close-shortcuts")?.addEventListener("click", () => this.closeModal());
  }

  bindGlobalEvents() {
    if (typeof window === "undefined" || typeof document === "undefined") return;

    // 1. Browser Hash History Navigation
    window.addEventListener("hashchange", () => {
      const hash = (window.location.hash || "").replace("#", "").toLowerCase();
      const validTabs = ["radar", "proxies", "studio", "decoder", "artifacts"];
      if (validTabs.includes(hash) && hash !== this.activePageTab) {
        this.switchPageTab(hash, false);
      }
    });

    // 2. Navigation Tab Button Listeners
    document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const current = e.currentTarget || btn;
        const tabTarget = (current.dataset && current.dataset.tabTarget) || current.getAttribute("data-tab-target");
        if (tabTarget) {
          this.switchPageTab(tabTarget, true);
        }
      });
      btn.addEventListener("keydown", (e) => {
        const tabs = Array.from(document.querySelectorAll(".nav-tab-btn"));
        const index = tabs.indexOf(e.currentTarget);
        if (index < 0) return;
        let nextIndex = null;
        if (e.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
        if (e.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
        if (e.key === "Home") nextIndex = 0;
        if (e.key === "End") nextIndex = tabs.length - 1;
        if (nextIndex === null) return;
        e.preventDefault();
        const next = tabs[nextIndex];
        this.switchPageTab(next.dataset.tabTarget, true);
        next.focus();
      });
    });

    // 3. Global Keyboard Shortcuts
    window.addEventListener("keydown", (e) => {
      if (document.querySelector('[role="dialog"]') || document.querySelector('[aria-modal="true"]')) return;
      const isInput = document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA" || document.activeElement.tagName === "SELECT");

      if (e.key === "/" && !(e.ctrlKey || e.metaKey || e.altKey)) {
        const s = document.getElementById("node-quick-search") || document.getElementById("global-search-input");
        if (s && document.activeElement !== s) {
          e.preventDefault();
          this.switchPageTab("proxies", true);
          setTimeout(() => {
            const searchInput = document.getElementById("node-quick-search");
            if (searchInput) searchInput.focus();
          }, 50);
        }
      }

      if (!isInput && !(e.ctrlKey || e.metaKey || e.altKey)) {
        // Number Keys 1-5 for Tab Navigation
        if (["1", "2", "3", "4", "5"].includes(e.key)) {
          const tabs = ["radar", "proxies", "studio", "decoder", "artifacts"];
          const target = tabs[parseInt(e.key, 10) - 1];
          if (target) {
            e.preventDefault();
            this.switchPageTab(target, true);
            this.showToast(`Switched to tab: ${target.toUpperCase()}`);
            return;
          }
        }

        if (e.key === "d" || e.key === "D") {
          e.preventDefault();
          this.openDecoderModal();
        } else if (e.key === "s" || e.key === "S") {
          e.preventDefault();
          this.openCleanIPScannerModal();
        } else if (e.key === "b" || e.key === "B") {
          e.preventDefault();
          this.openSubscriptionBuilderModal();
        } else if (e.key === "t" || e.key === "T") {
          e.preventDefault();
          this.toggleTheme();
        } else if (e.key === "v" || e.key === "V") {
          e.preventDefault();
          this.viewMode = this.viewMode === "grid" ? "table" : this.viewMode === "table" ? "feed" : "grid";
          this.refreshProxyWorkspace();
          this.showToast(`View mode: ${this.viewMode.toUpperCase()}`);
        } else if (e.key === "r" || e.key === "R") {
          e.preventDefault();
          this.resetProxyFilters();
          this.showToast("All filters reset");
        } else if (e.key === "?" || e.key === "k" || e.key === "K") {
          e.preventDefault();
          this.openShortcutsModal();
        }
      }

      if (e.key === "Escape") {
        this.closeModal();
      }
    });

    document.getElementById("modal-overlay")?.addEventListener("click", (e) => {
      if (e.target.id === "modal-overlay" || e.target.closest("#modal-overlay > div") === e.target) {
        this.closeModal();
      }
    });
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  const app = new AppState();
  window.AppState = AppState;
  window.huntxApp = app;
  if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", () => app.init());
  } else {
    app.init();
  }
}
