/**
 * HUNTX subscription library: a metadata-only, progressive UI for immutable
 * historical latest-100 feeds. Never download, store or render proxy secrets.
 */
export const REQUIRED_PROTOCOLS = Object.freeze([
  "vless", "vmess", "trojan", "anytls", "hysteria", "hysteria2",
  "socks", "http", "shadowsocks", "shadowsocksr", "tuic",
  "wireguard", "ssh", "shadowtls", "naive", "juicity",
  "mieru", "warp", "dns", "dnstt"
]);
const SLUG = /^[a-z][a-z0-9-]{0,39}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const DIRECTIONS = Object.freeze({
  signal: "Signal · technical control room",
  canvas: "Canvas · bright, spacious workspace",
  ledger: "Ledger · editorial data library"
});

function validSlug(name) {
  return typeof name === "string" && SLUG.test(name) && name !== "others";
}

export function subscriptionURL(name, format = "text", locationHref) {
  if (!(validSlug(name) || name === "all" || name === "index")) {
    throw new TypeError("Invalid subscription protocol");
  }
  if (!["text", "base64", "json"].includes(format) || (format === "json") !== (name === "index")) {
    throw new TypeError("Invalid subscription format");
  }
  const filename = format === "json" ? "index.json"
    : `${name}${format === "base64" ? "_base64" : ""}.txt`;
  const base = locationHref || (typeof window === "undefined"
    ? "https://example.invalid/subscriptions.html" : window.location.href);
  return new URL("subscriptions/latest/" + filename, base).href;
}

export function parseSubscriptionIndex(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)
      || raw.schema_version !== 1 || raw.scope !== "all_time_cumulative"
      || raw.health_status !== "historical_unverified"
      || raw.limit_per_protocol !== 100
      || raw.latest_by !== "first_seen"
      || !raw.protocols || typeof raw.protocols !== "object" || Array.isArray(raw.protocols)) {
    throw new TypeError("Invalid historical subscription index");
  }
  const entries = Object.entries(raw.protocols);
  if (entries.length > 256) throw new TypeError("Too many protocol categories");
  let total = 0;
  const records = entries.map(([name, record]) => {
    if (!validSlug(name) || name === "all") throw new TypeError("Invalid protocol category");
    if (!record || typeof record !== "object"
      || !Number.isInteger(record.count) || record.count < 0 || record.count > 100) {
      throw new TypeError("Invalid protocol count");
    }
    if (record.file !== name + ".txt"
      || record.base64_file !== name + "_base64.txt"
      || typeof record.sha256 !== "string" || !DIGEST.test(record.sha256)) {
      throw new TypeError("Invalid protocol file or checksum");
    }
    total += record.count;
    return Object.freeze({ name, count: record.count });
  });
  const master = raw.aggregate;
  if (!master || !Number.isInteger(master.count) || master.count !== total
    || master.file !== "all.txt" || master.base64_file !== "all_base64.txt"
    || typeof master.sha256 !== "string" || !DIGEST.test(master.sha256)) {
    throw new TypeError("Invalid aggregate count or checksum");
  }
  if (typeof raw.generated_at !== "string" || !Number.isFinite(Date.parse(raw.generated_at))) {
    throw new TypeError("Invalid publication time");
  }
  // Preserve the conventional family order and append future supported types
  // individually, never as a misleading catch-all "Others" category.
  records.sort((a, b) => {
    const ai = REQUIRED_PROTOCOLS.indexOf(a.name);
    const bi = REQUIRED_PROTOCOLS.indexOf(b.name);
    if (ai < 0 && bi < 0) return a.name.localeCompare(b.name);
    return (ai < 0 ? Number.MAX_SAFE_INTEGER : ai) - (bi < 0 ? Number.MAX_SAFE_INTEGER : bi);
  });
  return Object.freeze({
    records: Object.freeze(records),
    protocolCount: records.length,
    total,
    scope: raw.health_status,
    publishedAt: raw.generated_at
  });
}

export function filterProtocols(records, query = "", availableOnly = false) {
  const match = String(query).trim().toLowerCase();
  return records.filter(({ name, count }) =>
    (!availableOnly || count > 0) && name.includes(match));
}

function node(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content != null) element.textContent = content;
  return element;
}

function addLink(parent, label, slug, format, className) {
  const link = node("a", className, label);
  const file = `${slug}${format === "base64" ? "_base64" : ""}.txt`;
  link.href = "subscriptions/latest/" + file;
  link.download = file;
  parent.append(link);
  return link;
}

function renderProtocolCard(record) {
  const card = node("article", "protocol-card");
  card.dataset.protocolCard = record.name;
  const head = node("div", "protocol-card-heading");
  const identity = node("div", "protocol-identity");
  identity.append(node("span", "protocol-symbol", record.name.slice(0, 2).toUpperCase()));
  const identityCopy = node("div", "protocol-card-name");
  identityCopy.append(node("h3", "", record.name), node("p", "", "Latest discovered · no age cutoff"));
  identity.append(identityCopy);
  const count = node("strong", "protocol-count", String(record.count));
  count.setAttribute("aria-label", `${record.count} historical proxies selected`);
  head.append(identity, count);
  const capacity = node("div", "capacity-track");
  const fill = node("span", "capacity-fill");
  fill.style.width = `${record.count}%`;
  capacity.append(fill);
  capacity.setAttribute("aria-hidden", "true");
  const caption = node("p", "capacity-note", `${record.count} of 100 selected · historical, not live-verified`);
  const links = node("div", "protocol-card-actions");
  addLink(links, "Plain text", record.name, "text", "button-link primary-link");
  addLink(links, "Base64", record.name, "base64", "button-link");
  const copy = node("button", "copy-link", "Copy URL");
  copy.type = "button";
  copy.dataset.copySlug = record.name;
  copy.dataset.copyFormat = "text";
  copy.setAttribute("aria-label", `Copy ${record.name} subscription URL`);
  links.append(copy);
  card.append(head, capacity, caption, links);
  return card;
}

export function mountSubscriptionHub(root = document, fetchIndex = fetch) {
  const grid = root.getElementById("protocol-grid");
  if (!grid) return null;

  const find = (id) => root.getElementById(id);
  const search = find("subscription-search");
  const onlyAvailable = find("available-subscriptions");
  const feedback = find("subscription-status");
  const summary = find("protocol-result-summary");
  const retry = find("subscription-retry");
  const copyStatus = find("copy-status");
  const state = { index: null, controller: null };
  const clearSearch = find("clear-subscription-search");

  function render() {
    grid.replaceChildren();
    if (!state.index) return;
    const matches = filterProtocols(state.index.records, search.value, onlyAvailable.checked);
    const fragment = root.createDocumentFragment();
    matches.forEach((record) => fragment.append(renderProtocolCard(record)));
    grid.append(fragment);
    summary.textContent = matches.length
      ? `Showing ${matches.length} of ${state.index.protocolCount} protocol feeds`
      : "No matching protocol feeds. Clear search or change filters.";
    clearSearch.hidden = !search.value;
  }

  function setDesign(name) {
    if (!Object.hasOwn(DIRECTIONS, name)) return;
    root.documentElement.dataset.design = name;
    root.querySelectorAll("[data-design-option]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.designOption === name));
    });
    find("design-description").textContent = DIRECTIONS[name];
  }
  root.querySelectorAll("[data-design-option]").forEach((button) => {
    button.addEventListener("click", () => setDesign(button.dataset.designOption));
  });

  search.addEventListener("input", render);
  onlyAvailable.addEventListener("change", render);
  clearSearch.addEventListener("click", () => {
    search.value = "";
    search.focus();
    render();
  });
  grid.addEventListener("click", async (event) => {
    const target = event.target.closest("button[data-copy-slug]");
    if (!target || !grid.contains(target)) return;
    try {
      await navigator.clipboard.writeText(subscriptionURL(target.dataset.copySlug, "text"));
      copyStatus.textContent = `Copied ${target.dataset.copySlug} subscription URL`;
    } catch {
      copyStatus.textContent = "Clipboard unavailable. Use the Plain text link instead.";
    }
  });
  root.querySelectorAll("[data-master-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(subscriptionURL("all", button.dataset.masterCopy));
        copyStatus.textContent = "Copied aggregate subscription URL";
      } catch {
        copyStatus.textContent = "Clipboard unavailable. Use the download link instead.";
      }
    });
  });

  async function load() {
    if (state.controller) state.controller.abort();
    const controller = new AbortController();
    state.controller = controller;
    feedback.textContent = "Loading published subscription metadata…";
    retry.hidden = true;
    try {
      const response = await fetchIndex("subscriptions/latest/index.json", {
        cache: "no-store", signal: controller.signal
      });
      if (!response.ok) throw new Error("Subscription index is not published");
      const data = parseSubscriptionIndex(await response.json());
      if (state.controller !== controller) return;
      state.index = data;
      find("aggregate-count").textContent = data.total.toLocaleString("en");
      find("protocol-count").textContent = data.protocolCount.toLocaleString("en");
      const date = new Date(data.publishedAt);
      find("published-at").textContent = new Intl.DateTimeFormat("en", {
        dateStyle: "medium", timeStyle: "short", timeZone: "UTC"
      }).format(date) + " UTC";
      feedback.textContent = "Historical subscription index loaded. These URLs are not verified live proxies.";
      render();
    } catch (error) {
      if (controller.signal.aborted || state.controller !== controller) return;
      state.index = null;
      grid.replaceChildren();
      find("aggregate-count").textContent = "—";
      find("protocol-count").textContent = "—";
      find("published-at").textContent = "Not available";
      summary.textContent = "No protocol counts are available.";
      feedback.textContent = "Subscription index unavailable. Retry, or browse the published artifacts.";
      retry.hidden = false;
    }
  }
  retry.addEventListener("click", load);
  setDesign("signal");
  load();
  return { load, setDesign };
}

if (typeof document !== "undefined") {
  mountSubscriptionHub(document);
}
