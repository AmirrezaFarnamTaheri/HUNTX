// HUNTX / GatherX Node Intelligence & Telemetry Dashboard Application
// Hardened, accessible, zero-dependency, and XSS-sanitized frontend controller.

import { FALLBACK_CATALOG, SAMPLE_PROXIES, GLOBE_HUBS } from "./data.js";
import { initTelemetryGlobe } from "./globe.js";
import { decodeProxyURI } from "./decoder.js";
import { renderQRCodeSVG } from "./qrcode.js";

function escapeHTML(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
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
    this.searchQuery = "";
    this.selectedProtocol = "ALL";
    this.selectedTransport = "ALL";
    this.selectedCountry = "ALL";
    this.sortBy = "latency_asc";
    this.theme = getStoredTheme();
    this.globeInstance = null;
  }

  async init() {
    this.applyTheme(this.theme);

    try {
      const res = await fetch("./catalog.json", { cache: "no-store" });
      if (res.ok) {
        const liveCatalog = await res.json();
        if (liveCatalog && liveCatalog.files) {
          this.catalog = { ...this.catalog, ...liveCatalog };
          console.log("[HUNTX] Live catalog synchronized.");
        }
      }
    } catch (e) {
      console.log("[HUNTX] Standalone/offline mode with built-in telemetry data.");
    }

    this.renderHeader();
    this.renderHero();
    this.renderFilterBar();
    this.renderNodes();
    this.renderArtifacts();
    this.renderDecoderSection();
    this.renderFooter();
    this.bindGlobalEvents();

    setTimeout(() => {
      this.globeInstance = initTelemetryGlobe("telemetry-globe-canvas", (hub) => {
        this.selectedCountry = hub.code;
        this.renderFilterBar();
        this.renderNodes();
        this.showToast(`Filtered by ${escapeHTML(hub.name)} (${escapeHTML(hub.code)})`);
      });
    }, 100);
  }

  applyTheme(t) {
    this.theme = t;
    setStoredTheme(t);
    if (typeof document !== "undefined") {
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
      result = result.filter(p => p.protocol.toLowerCase() === this.selectedProtocol.toLowerCase());
    }

    if (this.selectedTransport !== "ALL") {
      result = result.filter(p => p.transport.toLowerCase().includes(this.selectedTransport.toLowerCase()));
    }

    if (this.selectedCountry !== "ALL") {
      result = result.filter(p => p.country.toUpperCase() === this.selectedCountry.toUpperCase());
    }

    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase().trim();
      result = result.filter(p =>
        p.name.toLowerCase().includes(q) ||
        p.server.toLowerCase().includes(q) ||
        p.protocol.toLowerCase().includes(q) ||
        p.countryName.toLowerCase().includes(q) ||
        p.transport.toLowerCase().includes(q) ||
        (p.sni && p.sni.toLowerCase().includes(q))
      );
    }

    result.sort((a, b) => {
      if (this.sortBy === "latency_asc") return a.ping - b.ping;
      if (this.sortBy === "name_asc") return a.name.localeCompare(b.name);
      return 0;
    });

    return result;
  }

  showToast(msg, type = "success") {
    if (typeof document === "undefined") return;
    const container = document.getElementById("toast-container");
    if (!container) return;

    const el = document.createElement("div");
    el.className = `toast-pill flex items-center gap-2 px-4 py-2.5 rounded-xl border backdrop-blur-md shadow-2xl text-xs font-mono font-semibold transition-all duration-300 transform translate-y-4 opacity-0 ${
      type === "success"
        ? "bg-emerald-950/90 text-emerald-300 border-emerald-500/40 shadow-emerald-950/50"
        : "bg-cyan-950/90 text-cyan-300 border-cyan-500/40 shadow-cyan-950/50"
    }`;
    el.innerHTML = `
      <svg class="w-4 h-4 text-cyan-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
      <span>${escapeHTML(msg)}</span>
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

  renderHeader() {
    if (typeof document === "undefined") return;
    const header = document.getElementById("main-header");
    if (!header) return;

    header.innerHTML = `
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        <a href="#" class="flex items-center gap-3 group focus-ring rounded-lg p-1" aria-label="HUNTX Home">
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
              <span class="px-1.5 py-0.5 text-[9px] font-mono font-bold bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 rounded">v2.4</span>
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
              class="w-full pl-9 pr-12 py-1.5 bg-gray-900/80 border border-gray-800 focus:border-cyan-500/60 rounded-xl text-xs font-mono text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all focus-ring"
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
          <div class="hidden lg:flex items-center gap-2 px-3 py-1 bg-emerald-950/50 border border-emerald-800/40 rounded-full">
            <span class="relative flex h-2 w-2">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span class="font-mono text-[11px] font-semibold text-emerald-400">PIPELINE ONLINE</span>
          </div>

          <button
            id="btn-open-builder"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-400 text-cyan-300 text-xs font-mono font-medium rounded-xl transition-all shadow-sm focus-ring cursor-pointer"
            title="Open Subscription Builder"
            aria-label="Open Subscription Builder"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            <span class="hidden sm:inline">Sub Builder</span>
          </button>

          <button
            id="btn-open-decoder"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-gray-600 text-gray-200 text-xs font-mono font-medium rounded-xl transition-all focus-ring cursor-pointer"
            title="Open Protocol Decoder (Press D)"
            aria-label="Open Protocol Decoder"
          >
            <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
            <span class="hidden sm:inline">Decoder</span>
          </button>

          <a
            href="architecture.html"
            target="_blank"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-gray-600 text-gray-300 hover:text-white text-xs font-mono rounded-xl transition-all focus-ring"
            title="Open 3D Architecture Topology"
            aria-label="Open 3D Architecture Topology"
          >
            <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
            <span class="hidden md:inline">3D Topology</span>
          </a>

          <a
            href="https://github.com/AmirrezaFarnamTaheri/HUNTX"
            target="_blank"
            class="p-2 bg-gray-900 hover:bg-gray-800 border border-gray-800 text-gray-400 hover:text-white rounded-xl transition-all focus-ring"
            title="GitHub Repository"
            aria-label="GitHub Repository"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"></path></svg>
          </a>
        </div>
      </div>
    `;

    document.getElementById("global-search-input")?.addEventListener("input", (e) => {
      this.searchQuery = e.target.value;
      this.renderNodes();
    });

    document.getElementById("btn-open-decoder")?.addEventListener("click", () => {
      this.openDecoderModal();
    });

    document.getElementById("btn-open-builder")?.addEventListener("click", () => {
      this.openSubscriptionBuilderModal();
    });
  }

  renderHero() {
    if (typeof document === "undefined") return;
    const hero = document.getElementById("hero-section");
    if (!hero) return;

    hero.innerHTML = `
      <div class="relative grid grid-cols-1 lg:grid-cols-12 gap-8 items-center py-10 lg:py-14 border-b border-gray-800/60 pb-12">
        <div class="lg:col-span-7 space-y-6">
          <div class="inline-flex items-center gap-2 px-3 py-1 bg-cyan-950/50 border border-cyan-500/30 rounded-full text-cyan-300 text-xs font-mono font-semibold uppercase tracking-wider">
            <span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            Zero-Budget Sovereign Proxy Ingestion
          </div>

          <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white leading-tight">
            Node Telemetry & <br/>
            <span class="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-400 to-indigo-400">Cyber Intelligence</span>
          </h1>

          <p class="text-sm sm:text-base text-gray-400 font-sans max-w-xl leading-relaxed">
            Automated multi-source ingestion aggregating 30+ proxy URI protocols across 49+ encrypted channels.
            Deduplicated with SHA-256 integrity, decoded client-side, and synchronized continuously.
          </p>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-3.5 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Active Nodes</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-cyan-400">${this.catalog.total_nodes || 616}</span>
                <span class="text-[10px] font-mono text-emerald-400">+12%</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-3.5 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Ingest Sources</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-indigo-400">49+</span>
                <span class="text-[10px] font-mono text-gray-400">TG/Bot</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-3.5 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Parsers</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-emerald-400">12</span>
                <span class="text-[10px] font-mono text-gray-400">formats</span>
              </div>
            </div>

            <div class="bg-gray-900/60 border border-gray-800/80 rounded-2xl p-3.5 backdrop-blur-sm">
              <span class="text-[11px] font-mono text-gray-500 uppercase tracking-wider block">Avg Latency</span>
              <div class="flex items-baseline gap-1.5 mt-1">
                <span class="text-2xl font-mono font-bold text-amber-400">42ms</span>
                <span class="text-[10px] font-mono text-emerald-400">fast</span>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-3 pt-2">
            <button
              id="hero-copy-sub"
              class="px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/25 transition-all focus-ring cursor-pointer flex items-center gap-2"
              aria-label="Copy Unified Subscription URL"
            >
              <svg class="w-4 h-4 text-gray-950" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              Copy Unified Subscription
            </button>

            <button
              id="hero-download-json"
              class="px-4 py-2.5 bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-cyan-500/40 text-gray-200 font-mono font-semibold text-xs rounded-xl transition-all focus-ring cursor-pointer flex items-center gap-2"
              aria-label="Download proxies.json"
            >
              <svg class="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              Download proxies.json
            </button>
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
              <span class="text-[9px] font-mono text-gray-500 block">DRAG TO ROTATE</span>
            </div>
          </div>
        </div>
      </div>
    `;

    document.getElementById("hero-copy-sub")?.addEventListener("click", () => {
      const subUrl = new URL("artifacts/dev/proxies_b64sub.txt", window.location.href).href;
      this.copyText(subUrl, "Subscription URL copied to clipboard");
    });

    document.getElementById("hero-download-json")?.addEventListener("click", () => {
      window.open("artifacts/dev/proxies.json", "_blank");
    });
  }

  renderFilterBar() {
    if (typeof document === "undefined") return;
    const filterContainer = document.getElementById("filter-section");
    if (!filterContainer) return;

    const protocols = ["ALL", "VLESS", "VMESS", "TROJAN", "SHADOWSOCKS", "HYSTERIA2"];
    const transports = ["ALL", "Reality", "WebSocket", "gRPC", "TCP"];
    const countries = ["ALL", "DE", "NL", "FI", "SG", "GB", "US", "TR", "JP"];

    filterContainer.innerHTML = `
      <div class="space-y-4 py-6">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div class="flex flex-wrap gap-1.5 items-center" role="toolbar" aria-label="Protocol Filter">
            <span class="text-[11px] font-mono font-bold text-gray-400 uppercase tracking-wider mr-2 flex items-center gap-1">
              <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path></svg>
              Protocol:
            </span>
            ${protocols.map(proto => `
              <button
                class="btn-proto-tab px-3 py-1 rounded-xl text-xs font-mono font-semibold transition-all focus-ring cursor-pointer ${
                  this.selectedProtocol === proto
                    ? "bg-cyan-500 text-gray-950 shadow-md shadow-cyan-500/30"
                    : "bg-gray-900 text-gray-400 hover:text-gray-200 hover:bg-gray-800 border border-gray-800"
                }"
                data-protocol="${escapeHTML(proto)}"
                aria-pressed="${this.selectedProtocol === proto}"
              >
                ${escapeHTML(proto)}
              </button>
            `).join("")}
          </div>

          <div class="flex flex-wrap gap-2.5 items-center w-full md:w-auto">
            <select
              id="select-transport"
              class="bg-gray-900 border border-gray-800 text-gray-300 text-xs font-mono rounded-xl px-3 py-1.5 focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Transport"
            >
              ${transports.map(t => `<option value="${escapeHTML(t)}" ${this.selectedTransport === t ? "selected" : ""}>Transport: ${escapeHTML(t)}</option>`).join("")}
            </select>

            <select
              id="select-country"
              class="bg-gray-900 border border-gray-800 text-gray-300 text-xs font-mono rounded-xl px-3 py-1.5 focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Filter by Region"
            >
              ${countries.map(c => `<option value="${escapeHTML(c)}" ${this.selectedCountry === c ? "selected" : ""}>Region: ${escapeHTML(c)}</option>`).join("")}
            </select>

            <select
              id="select-sort"
              class="bg-gray-900 border border-gray-800 text-gray-300 text-xs font-mono rounded-xl px-3 py-1.5 focus:border-cyan-500 focus:outline-none cursor-pointer focus-ring"
              aria-label="Sort Order"
            >
              <option value="latency_asc" ${this.sortBy === "latency_asc" ? "selected" : ""}>Sort: Fastest Ping</option>
              <option value="name_asc" ${this.sortBy === "name_asc" ? "selected" : ""}>Sort: Name (A-Z)</option>
            </select>
          </div>
        </div>
      </div>
    `;

    filterContainer.querySelectorAll(".btn-proto-tab").forEach(btn => {
      btn.addEventListener("click", (e) => {
        this.selectedProtocol = e.currentTarget.dataset.protocol;
        this.renderFilterBar();
        this.renderNodes();
      });
    });

    document.getElementById("select-transport")?.addEventListener("change", (e) => {
      this.selectedTransport = e.target.value;
      this.renderNodes();
    });

    document.getElementById("select-country")?.addEventListener("change", (e) => {
      this.selectedCountry = e.target.value;
      this.renderNodes();
    });

    document.getElementById("select-sort")?.addEventListener("change", (e) => {
      this.sortBy = e.target.value;
      this.renderNodes();
    });
  }

  renderNodes() {
    if (typeof document === "undefined") return;
    const nodesContainer = document.getElementById("nodes-grid");
    if (!nodesContainer) return;

    const filtered = this.getFilteredProxies();

    if (filtered.length === 0) {
      nodesContainer.innerHTML = `
        <div class="col-span-full py-16 text-center bg-gray-900/40 border border-dashed border-gray-800 rounded-3xl p-8">
          <svg class="w-12 h-12 text-gray-600 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
          <h3 class="text-base font-mono font-bold text-gray-300">No telemetry nodes found</h3>
          <p class="text-xs text-gray-500 font-mono mt-1 max-w-sm mx-auto">No proxy endpoints matched your active filter or search terms.</p>
          <button id="btn-reset-filters" class="mt-4 px-4 py-2 bg-cyan-950 border border-cyan-600/40 hover:border-cyan-400 text-cyan-300 font-mono text-xs rounded-xl transition-all cursor-pointer focus-ring">Reset All Filters</button>
        </div>
      `;
      document.getElementById("btn-reset-filters")?.addEventListener("click", () => {
        this.selectedProtocol = "ALL";
        this.selectedTransport = "ALL";
        this.selectedCountry = "ALL";
        this.searchQuery = "";
        this.renderHeader();
        this.renderFilterBar();
        this.renderNodes();
      });
      return;
    }

    nodesContainer.innerHTML = filtered.map(node => {
      let protoBadgeColor = "bg-cyan-950 text-cyan-400 border-cyan-800/60";
      if (node.protocol === "vless") protoBadgeColor = "bg-emerald-950/80 text-emerald-400 border-emerald-800/60";
      if (node.protocol === "vmess") protoBadgeColor = "bg-amber-950/80 text-amber-400 border-amber-800/60";
      if (node.protocol === "trojan") protoBadgeColor = "bg-purple-950/80 text-purple-400 border-purple-800/60";
      if (node.protocol === "hysteria2") protoBadgeColor = "bg-rose-950/80 text-rose-400 border-rose-800/60";

      return `
        <div class="node-card group relative bg-gray-900/70 hover:bg-gray-900 border border-gray-800/80 hover:border-cyan-500/40 rounded-2xl p-4 transition-all duration-300 hover:shadow-xl hover:shadow-cyan-950/30 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between gap-2 mb-3">
              <div class="flex items-center gap-1.5">
                <span class="px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded-md border ${protoBadgeColor}">
                  ${escapeHTML(node.protocol)}
                </span>
                <span class="px-1.5 py-0.5 text-[10px] font-mono text-gray-400 bg-gray-800/80 rounded border border-gray-700/50">
                  ${escapeHTML(node.transport)}
                </span>
              </div>

              <div class="flex items-center gap-2">
                <span class="flex items-center gap-1 text-[11px] font-mono font-semibold ${node.ping < 60 ? "text-emerald-400" : "text-amber-400"}">
                  <span class="w-1.5 h-1.5 rounded-full ${node.ping < 60 ? "bg-emerald-400" : "bg-amber-400"}"></span>
                  ${node.ping}ms
                </span>
                <span class="text-xs font-mono text-gray-300 font-bold px-1.5 py-0.5 bg-gray-800 rounded">${escapeHTML(node.country)}</span>
              </div>
            </div>

            <h4 class="text-sm font-mono font-bold text-gray-100 truncate group-hover:text-cyan-300 transition-colors" title="${escapeHTML(node.name)}">
              ${escapeHTML(node.name)}
            </h4>

            <div class="mt-2 space-y-1 font-mono text-[11px] text-gray-400">
              <div class="flex items-center justify-between text-gray-500">
                <span>Host:</span>
                <span class="text-gray-300 truncate max-w-[170px]" title="${escapeHTML(node.server)}:${node.port}">${escapeHTML(node.server)}:${node.port}</span>
              </div>
              ${node.sni ? `
                <div class="flex items-center justify-between text-gray-500">
                  <span>SNI:</span>
                  <span class="text-cyan-400/90 truncate max-w-[170px]" title="${escapeHTML(node.sni)}">${escapeHTML(node.sni)}</span>
                </div>
              ` : ""}
            </div>
          </div>

          <div class="mt-4 pt-3 border-t border-gray-800/80 flex items-center gap-2">
            <button
              class="btn-copy-node flex-1 py-1.5 px-3 bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-400 text-cyan-300 text-xs font-mono font-medium rounded-xl transition-all focus-ring cursor-pointer flex items-center justify-center gap-1.5"
              data-raw="${encodeURIComponent(node.raw)}"
              aria-label="Copy Node URI"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"></path></svg>
              Copy URI
            </button>

            <button
              class="btn-inspect-node p-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 hover:text-white rounded-xl transition-all focus-ring cursor-pointer"
              data-raw="${encodeURIComponent(node.raw)}"
              title="Inspect Node Parameters"
              aria-label="Inspect Node Parameters"
            >
              <svg class="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
            </button>

            <button
              class="btn-qr-node p-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 hover:text-white rounded-xl transition-all focus-ring cursor-pointer"
              data-raw="${encodeURIComponent(node.raw)}"
              data-name="${encodeURIComponent(node.name)}"
              title="Show QR Code"
              aria-label="Show QR Code"
            >
              <svg class="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"></path></svg>
            </button>
          </div>
        </div>
      `;
    }).join("");

    nodesContainer.querySelectorAll(".btn-copy-node").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        this.copyText(raw, "Node URI copied to clipboard");
      });
    });

    nodesContainer.querySelectorAll(".btn-inspect-node").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        this.openDecoderModal(raw);
      });
    });

    nodesContainer.querySelectorAll(".btn-qr-node").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const raw = decodeURIComponent(e.currentTarget.dataset.raw);
        const name = decodeURIComponent(e.currentTarget.dataset.name);
        this.openQRModal(raw, name);
      });
    });
  }

  renderArtifacts() {
    if (typeof document === "undefined") return;
    const artifactSection = document.getElementById("artifact-section");
    if (!artifactSection) return;

    artifactSection.innerHTML = `
      <div class="py-12 border-t border-gray-800/80">
        <div class="flex items-center justify-between mb-6">
          <div>
            <h2 class="text-xl sm:text-2xl font-bold font-mono text-white flex items-center gap-2">
              <svg class="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
              Pipeline Output Catalog
            </h2>
            <p class="text-xs font-mono text-gray-400 mt-1">Aggregated and verified artifacts published by GitHub Actions CI</p>
          </div>
          <span class="text-xs font-mono text-gray-500">${escapeHTML(this.catalog.total_size_str)} total storage</span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          ${this.catalog.files.map(file => `
            <div class="bg-gray-900/60 hover:bg-gray-900 border border-gray-800 rounded-2xl p-4 transition-all duration-200 flex flex-col justify-between">
              <div>
                <div class="flex items-center justify-between mb-2">
                  <span class="px-2 py-0.5 text-[10px] font-mono font-bold bg-cyan-950 text-cyan-400 border border-cyan-800/60 rounded">
                    ${escapeHTML(file.ext)}
                  </span>
                  <span class="text-xs font-mono text-gray-400">${escapeHTML(file.size_str)}</span>
                </div>
                <h4 class="text-sm font-mono font-bold text-gray-100 truncate">${escapeHTML(file.filename)}</h4>
                <div class="mt-2 flex flex-wrap gap-1">
                  ${(file.tags || []).map(t => `<span class="text-[9px] font-mono text-gray-400 px-1.5 py-0.5 bg-gray-800 rounded">${escapeHTML(t)}</span>`).join("")}
                </div>
              </div>

              <div class="mt-4 pt-3 border-t border-gray-800 flex items-center gap-2">
                <a
                  href="${escapeHTML(file.path)}"
                  download
                  class="flex-1 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 text-xs font-mono font-medium rounded-xl text-center transition-all focus-ring cursor-pointer flex items-center justify-center gap-1.5"
                  aria-label="Download ${escapeHTML(file.filename)}"
                >
                  <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                  Download
                </a>
                <button
                  class="btn-copy-artifact-link p-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 rounded-xl transition-all focus-ring cursor-pointer"
                  data-path="${escapeHTML(file.path)}"
                  title="Copy Direct Link"
                  aria-label="Copy Direct Link"
                >
                  <svg class="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                </button>
              </div>
            </div>
          `).join("")}
        </div>
      </div>
    `;

    artifactSection.querySelectorAll(".btn-copy-artifact-link").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const p = e.currentTarget.dataset.path;
        const fullUrl = new URL(p, window.location.href).href;
        this.copyText(fullUrl, "Artifact URL copied to clipboard");
      });
    });
  }

  renderDecoderSection() {
    if (typeof document === "undefined") return;
    const decoderSection = document.getElementById("inline-decoder-section");
    if (!decoderSection) return;

    decoderSection.innerHTML = `
      <div class="my-10 p-6 sm:p-8 bg-gray-900/80 border border-cyan-500/20 rounded-3xl backdrop-blur-md shadow-xl">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h3 class="text-lg font-mono font-bold text-white flex items-center gap-2">
              <svg class="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
              Live Client-Side Protocol Decoder
            </h3>
            <p class="text-xs font-mono text-gray-400">Paste any raw proxy link (vless://, vmess://, trojan://, ss://, base64 sub) for instant client-side inspection</p>
          </div>
        </div>

        <div class="space-y-3">
          <div class="flex gap-2">
            <input
              id="inline-decoder-input"
              type="text"
              class="flex-1 px-4 py-2.5 bg-gray-950 border border-gray-800 focus:border-cyan-500 rounded-xl text-xs font-mono text-cyan-300 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus-ring"
              placeholder="Paste raw vless://, vmess://, trojan://, ss://, or base64..."
              aria-label="Raw Proxy Input for Decoding"
            />
            <button
              id="inline-decoder-btn"
              class="px-5 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/20 transition-all cursor-pointer focus-ring"
              aria-label="Decode Protocol"
            >
              Decode
            </button>
          </div>

          <div id="inline-decoder-result" class="hidden mt-4 p-4 bg-gray-950 border border-gray-800 rounded-2xl font-mono text-xs text-gray-300">
          </div>
        </div>
      </div>
    `;

    const input = document.getElementById("inline-decoder-input");
    const btn = document.getElementById("inline-decoder-btn");
    const out = document.getElementById("inline-decoder-result");

    const doDecode = () => {
      const val = input?.value.trim();
      if (!val) return;
      try {
        const decoded = decodeProxyURI(val);
        out.classList.remove("hidden");
        out.innerHTML = `
          <div class="flex items-center justify-between border-b border-gray-800 pb-2 mb-3">
            <span class="font-bold text-cyan-400 uppercase">${escapeHTML(decoded.protocol)} DECODED PARAMETERS</span>
            <button id="btn-copy-decoded-json" class="px-2 py-1 bg-gray-800 hover:bg-gray-700 text-cyan-300 rounded text-[10px] cursor-pointer focus-ring">Copy JSON</button>
          </div>
          <pre class="overflow-x-auto text-[11px] text-gray-300">${escapeHTML(JSON.stringify(decoded, null, 2))}</pre>
        `;
        document.getElementById("btn-copy-decoded-json")?.addEventListener("click", () => {
          this.copyText(JSON.stringify(decoded, null, 2), "Decoded JSON copied");
        });
      } catch (err) {
        out.classList.remove("hidden");
        out.innerHTML = `<span class="text-rose-400">Error decoding URI: ${escapeHTML(err.message)}</span>`;
      }
    };

    btn?.addEventListener("click", doDecode);
    input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") doDecode();
    });
  }

  openDecoderModal(initialUri = "") {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    let defaultVal = initialUri || this.proxies[0].raw;
    let decodedRes = null;
    try {
      decodedRes = decodeProxyURI(defaultVal);
    } catch {}

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-decoder-title">
        <div class="relative w-full max-w-2xl bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/50 space-y-6">
          <div class="flex items-center justify-between border-b border-gray-800 pb-4">
            <div class="flex items-center gap-2">
              <span class="p-2 bg-cyan-950 text-cyan-400 rounded-xl">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
              </span>
              <h3 id="modal-decoder-title" class="text-lg font-mono font-bold text-white">Proxy Protocol Inspector</h3>
            </div>
            <button id="btn-close-modal" class="p-2 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white rounded-xl focus-ring cursor-pointer" aria-label="Close modal">
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
            <button id="modal-btn-copy-raw" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 font-mono text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy raw proxy URI">Copy Raw</button>
            <button id="modal-btn-copy-json" class="px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy decoded parameters JSON">Copy Decoded JSON</button>
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");

    document.getElementById("btn-close-modal")?.addEventListener("click", () => {
      modalContainer.classList.add("hidden");
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
        <div class="relative w-full max-w-sm bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 shadow-2xl shadow-cyan-950/50 text-center space-y-4">
          <div class="flex items-center justify-between">
            <h3 id="modal-qr-title" class="text-sm font-mono font-bold text-white truncate max-w-[240px]">${escapeHTML(name)}</h3>
            <button id="btn-close-qr" class="p-1.5 bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close QR Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <div class="flex items-center justify-center py-3">
            ${renderQRCodeSVG(raw, 220)}
          </div>

          <p class="text-[11px] font-mono text-gray-400">Scan with v2rayNG, Streisand, Sing-box, or Shadowrocket</p>

          <button id="btn-copy-qr-raw" class="w-full py-2 bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-mono font-bold text-xs rounded-xl focus-ring cursor-pointer" aria-label="Copy Node URI to clipboard">
            Copy Node URI
          </button>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");

    document.getElementById("btn-close-qr")?.addEventListener("click", () => {
      modalContainer.classList.add("hidden");
    });

    document.getElementById("btn-copy-qr-raw")?.addEventListener("click", () => {
      this.copyText(raw, "Node URI copied to clipboard");
    });
  }

  openSubscriptionBuilderModal() {
    if (typeof document === "undefined") return;
    const modalContainer = document.getElementById("modal-overlay");
    if (!modalContainer) return;

    modalContainer.innerHTML = `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" role="dialog" aria-modal="true" aria-labelledby="modal-sub-title">
        <div class="relative w-full max-w-xl bg-gray-900 border border-cyan-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/50 space-y-5">
          <div class="flex items-center justify-between border-b border-gray-800 pb-3">
            <h3 id="modal-sub-title" class="text-base font-mono font-bold text-white flex items-center gap-2">
              <svg class="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
              Custom Subscription URL Builder
            </h3>
            <button id="btn-close-sub" class="p-1.5 bg-gray-800 text-gray-400 hover:text-white rounded-lg cursor-pointer focus-ring" aria-label="Close Subscription Builder Modal">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>

          <p class="text-xs font-mono text-gray-400">Generate a unified Base64 subscription bundle or raw URI list tailored to your client:</p>

          <div class="space-y-3">
            <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs">
              <span class="text-gray-500 block mb-1">Base64 Subscription Feed:</span>
              <div class="flex items-center justify-between gap-2">
                <span class="text-cyan-300 truncate">${escapeHTML(new URL("artifacts/dev/proxies_b64sub.txt", window.location.href).href)}</span>
                <button id="btn-copy-sub-feed" class="px-2.5 py-1 bg-cyan-500 text-gray-950 font-bold rounded text-[10px] cursor-pointer focus-ring" aria-label="Copy Subscription Feed URL">Copy</button>
              </div>
            </div>

            <div class="p-3 bg-gray-950 border border-gray-800 rounded-xl font-mono text-xs">
              <span class="text-gray-500 block mb-1">Raw Config List (txt):</span>
              <div class="flex items-center justify-between gap-2">
                <span class="text-gray-300 truncate">${escapeHTML(new URL("artifacts/dev/proxies.txt", window.location.href).href)}</span>
                <button id="btn-copy-raw-feed" class="px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-gray-200 font-bold rounded text-[10px] cursor-pointer focus-ring" aria-label="Copy Raw Config List URL">Copy</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    modalContainer.classList.remove("hidden");

    document.getElementById("btn-close-sub")?.addEventListener("click", () => {
      modalContainer.classList.add("hidden");
    });

    document.getElementById("btn-copy-sub-feed")?.addEventListener("click", () => {
      this.copyText(new URL("artifacts/dev/proxies_b64sub.txt", window.location.href).href, "Subscription Feed URL copied");
    });

    document.getElementById("btn-copy-raw-feed")?.addEventListener("click", () => {
      this.copyText(new URL("artifacts/dev/proxies.txt", window.location.href).href, "Raw Feed URL copied");
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
          <span>HUNTX & GatherX Ingestion Pipeline • SHA-256 Verified</span>
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

  bindGlobalEvents() {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    window.addEventListener("keydown", (e) => {
      if (e.key === "/" && !(e.ctrlKey || e.metaKey || e.altKey)) {
        const s = document.getElementById("global-search-input");
        if (s && document.activeElement !== s) {
          e.preventDefault();
          s.focus();
        }
      }

      if (e.key === "d" && !(e.ctrlKey || e.metaKey || e.altKey) && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
        e.preventDefault();
        this.openDecoderModal();
      }

      if (e.key === "Escape") {
        document.getElementById("modal-overlay")?.classList.add("hidden");
      }
    });

    document.getElementById("modal-overlay")?.addEventListener("click", (e) => {
      if (e.target.id === "modal-overlay" || e.target.closest("#modal-overlay > div") === e.target) {
        document.getElementById("modal-overlay")?.classList.add("hidden");
      }
    });
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  const app = new AppState();
  window.addEventListener("DOMContentLoaded", () => app.init());
}
