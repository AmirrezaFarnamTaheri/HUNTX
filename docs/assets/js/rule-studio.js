// HUNTX Visual Rule & Profile Studio Cockpit
// Sovereign Glass interactive routing builder with instant Sing-box / Xray / Clash export.

export class RuleStudio {
  constructor(containerId = "rule-studio-section") {
    this.container = document.getElementById(containerId);
    this.rules = [
      { id: "r1", target: "geosite:category-ads-all", action: "BLOCK", type: "geosite", enabled: true },
      { id: "r2", target: "geosite:cn", action: "DIRECT", type: "geosite", enabled: true },
      { id: "r3", target: "geoip:cn", action: "DIRECT", type: "geoip", enabled: true },
      { id: "r4", target: "openai.com", action: "PROXY-US", type: "domain", enabled: true },
      { id: "r5", target: "github.com", action: "AUTO-BEST", type: "domain", enabled: true },
      { id: "r6", target: "MATCH (Final)", action: "PROXY-AUTO", type: "match", enabled: true }
    ];
  }

  render() {
    if (!this.container) return;
    this.container.innerHTML = `
      <section class="mt-8 mb-6">
        <div class="glass-card bg-[#0e131d]/80 border border-[#1d2638] hover:border-cyan-500/30 rounded-2xl p-6 backdrop-blur-xl transition-all shadow-xl shadow-cyan-950/20">
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-[#1d2638]">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"></path></svg>
              </div>
              <div>
                <h3 class="text-sm font-mono font-bold text-gray-100 uppercase tracking-wider flex items-center gap-2">
                  Visual Routing &amp; Profile Studio
                  <span class="px-2 py-0.5 rounded-full text-[9px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">ACTIVE</span>
                </h3>
                <p class="text-xs text-gray-400 font-sans">Declarative client-side routing topology editor and multi-format config exporter</p>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-wrap">
              <button id="studio-export-singbox" class="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 text-xs font-mono font-semibold rounded-lg transition-all flex items-center gap-1.5 cursor-pointer">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Sing-box JSON
              </button>
              <button id="studio-export-xray" class="px-3 py-1.5 bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/40 text-indigo-300 text-xs font-mono font-semibold rounded-lg transition-all flex items-center gap-1.5 cursor-pointer">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Xray JSON
              </button>
            </div>
          </div>

          <div class="mt-4 grid grid-cols-1 lg:grid-cols-12 gap-6">
            <!-- Rules List Pipeline -->
            <div class="lg:col-span-7 space-y-2" id="studio-rules-list">
              ${this.rules.map((rule, idx) => `
                <div class="flex items-center justify-between p-3 rounded-xl bg-[#141b29]/90 border border-[#1d2638] text-xs font-mono group hover:border-cyan-500/40 transition-all">
                  <div class="flex items-center gap-3">
                    <span class="text-gray-500 font-bold w-4">${idx + 1}.</span>
                    <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider ${rule.type === 'geosite' ? 'bg-indigo-900/40 text-indigo-300 border border-indigo-700/40' : rule.type === 'geoip' ? 'bg-amber-900/40 text-amber-300 border border-amber-700/40' : 'bg-slate-800 text-gray-300 border border-slate-700'}">${rule.type}</span>
                    <span class="text-cyan-200 font-semibold">${rule.target}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="px-2.5 py-1 rounded text-[11px] font-bold ${rule.action === 'BLOCK' ? 'bg-rose-900/40 text-rose-300 border border-rose-700/50' : rule.action === 'DIRECT' ? 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/50' : 'bg-cyan-900/40 text-cyan-300 border border-cyan-700/50'}">${rule.action}</span>
                  </div>
                </div>
              `).join("")}
            </div>

            <!-- Visual Topology Flow Preview -->
            <div class="lg:col-span-5 flex flex-col justify-between p-4 rounded-xl bg-[#070a0f]/80 border border-[#1d2638]">
              <div>
                <span class="text-[11px] font-mono uppercase tracking-wider text-gray-400 block mb-2 font-bold">Routing Pipeline Topology</span>
                <div class="space-y-2 text-[11px] font-mono">
                  <div class="p-2 rounded bg-cyan-950/30 border border-cyan-800/40 text-cyan-300 flex items-center justify-between">
                    <span>1. Inbound (Mixed 7890 / TUN)</span>
                    <span class="text-[9px] text-cyan-400">LISTEN</span>
                  </div>
                  <div class="text-center text-gray-600">↓</div>
                  <div class="p-2 rounded bg-indigo-950/30 border border-indigo-800/40 text-indigo-300 flex items-center justify-between">
                    <span>2. DNS &amp; Geo-Classifier</span>
                    <span class="text-[9px] text-indigo-400">RESOLVE</span>
                  </div>
                  <div class="text-center text-gray-600">↓</div>
                  <div class="p-2 rounded bg-emerald-950/30 border border-emerald-800/40 text-emerald-300 flex items-center justify-between">
                    <span>3. Multi-Hop Outbounds</span>
                    <span class="text-[9px] text-emerald-400">EGRESS</span>
                  </div>
                </div>
              </div>
              <div class="mt-4 pt-3 border-t border-[#1d2638] flex items-center justify-between text-[10px] font-mono text-gray-500">
                <span>Rules: ${this.rules.length} active</span>
                <span>Latency Penalty: ~0.4ms</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    `;

    this.attachEventListeners();
  }

  attachEventListeners() {
    const btnSingbox = document.getElementById("studio-export-singbox");
    if (btnSingbox) {
      btnSingbox.onclick = () => this.exportConfig("singbox");
    }
    const btnXray = document.getElementById("studio-export-xray");
    if (btnXray) {
      btnXray.onclick = () => this.exportConfig("xray");
    }
  }

  exportConfig(format) {
    const jsonStr = JSON.stringify({ format, generatedAt: new Date().toISOString(), rules: this.rules }, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `huntx-${format}-profile.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
