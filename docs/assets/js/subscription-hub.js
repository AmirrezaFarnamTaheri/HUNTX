/**
 * HUNTX historical subscription directory and visual direction chooser.
 * Independent of the existing telemetry, converter and artifact renderer.
 * The metadata is untrusted until the expected publisher schema is checked.
 */
export const CORE_PROTOCOLS = Object.freeze([
  "vless", "vmess", "trojan", "anytls", "hysteria", "hysteria2",
  "socks", "http", "shadowsocks", "shadowsocksr", "tuic",
  "wireguard", "ssh", "shadowtls", "naive", "juicity",
  "mieru", "warp", "dns", "dnstt"
]);

const PROTOCOL_NAME = /^[a-z][a-z0-9-]{0,39}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const VISUAL_DIRECTIONS = new Set(["signal", "ledger", "orbit"]);
const STORAGE_KEY = "huntx_visual_direction";
const LABELS = Object.freeze({
  vless: "VLESS",
  vmess: "VMess",
  trojan: "Trojan",
  anytls: "AnyTLS",
  hysteria: "Hysteria",
  hysteria2: "Hysteria 2",
  socks: "SOCKS",
  http: "HTTP(S)",
  shadowsocks: "Shadowsocks",
  shadowsocksr: "ShadowsocksR",
  tuic: "TUIC",
  wireguard: "WireGuard",
  ssh: "SSH",
  shadowtls: "ShadowTLS",
  naive: "Naive",
  juicity: "Juicity",
  mieru: "Mieru",
  warp: "WARP",
  dns: "DNS",
  dnstt: "DNSTT"
});

export function normalizeDirection(value) {
  return VISUAL_DIRECTIONS.has(value) ? value : "signal";
}

export function subscriptionHref(name, format = "plain") {
  if (name === "index" && format === "json") return "subscriptions/latest/index.json";
  if (!PROTOCOL_NAME.test(name) || name === "index" || name === "others") {
    throw new Error("Invalid subscription protocol");
  }
  if (format === "plain") return "subscriptions/latest/" + name + ".txt";
  if (format === "base64") return "subscriptions/latest/" + name + "_base64.txt";
  throw new Error("Invalid subscription format");
}

function checkEntry(name, entry, isAggregate = false, limit = 200) {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
    throw new Error("Invalid subscription entry");
  }
  const expectedFile = name + ".txt";
  const expectedBase64 = name + "_base64.txt";
  if (
    entry.file !== expectedFile || entry.base64_file !== expectedBase64 ||
    !Number.isSafeInteger(entry.count) || entry.count < 0 ||
    (!isAggregate && entry.count > limit) ||
    typeof entry.sha256 !== "string" || !DIGEST.test(entry.sha256)
  ) {
    throw new Error("Invalid subscription count, file or checksum");
  }
  return { count: entry.count, published: true };
}

export function normalizeSubscriptionIndex(payload) {
  if (
    !payload || typeof payload !== "object" || Array.isArray(payload) ||
    payload.schema_version !== 1 ||
    payload.scope !== "all_time_cumulative" ||
    payload.health_status !== "historical_unverified" ||
    payload.latest_by !== "first_seen" ||
    payload.limit_per_protocol !== 200 ||
    !payload.protocol_limits || typeof payload.protocol_limits !== "object" ||
    Array.isArray(payload.protocol_limits) ||
    payload.protocol_limits.vless !== 150 ||
    payload.protocol_limits.shadowsocks !== 150 ||
    Object.keys(payload.protocol_limits).length !== 2 ||
    typeof payload.generated_at !== "string" ||
    !Number.isFinite(Date.parse(payload.generated_at)) ||
    !payload.protocols || typeof payload.protocols !== "object" ||
    Array.isArray(payload.protocols)
  ) {
    throw new Error("Invalid historical subscription index");
  }
  const categoryLimit = (name) => Object.hasOwn(payload.protocol_limits, name)
    ? payload.protocol_limits[name] : payload.limit_per_protocol;
  const keys = Object.keys(payload.protocols);
  if (keys.length > 128 || keys.some((name) =>
    !PROTOCOL_NAME.test(name) || name === "others" || name === "all" || name === "index"
  )) {
    throw new Error("Invalid subscription protocol category");
  }
  const aggregate = checkEntry("all", payload.aggregate, true);
  const extra = keys.filter((key) => !CORE_PROTOCOLS.includes(key)).sort();
  const categories = [...CORE_PROTOCOLS, ...extra].map((name) => {
    const entry = payload.protocols[name];
    const limit = Object.hasOwn(payload.protocol_limits, name)
      ? payload.protocol_limits[name] : payload.limit_per_protocol;
    const meta = entry === undefined
      ? { count: null, published: false }
      : checkEntry(name, entry, false, categoryLimit(name));
    return { name, label: Object.hasOwn(LABELS, name) ? LABELS[name] : name,
      limit, ...meta };
  });
  const sum = categories.reduce((acc, item) => acc + (item.count || 0), 0);
  if (aggregate.count !== sum) {
    throw new Error("Invalid aggregate count");
  }
  return {
    categories,
    aggregate,
    generatedAt: payload.generated_at,
    healthStatus: payload.health_status,
    latestBy: payload.latest_by,
    limit: payload.limit_per_protocol
  };
}

export function filterProtocols(categories, query = "", availability = "all") {
  const needle = String(query).trim().toLocaleLowerCase();
  return categories.filter((category) => {
    if (availability === "available" && (!category.published || category.count === 0)) return false;
    if (availability === "empty" && (!category.published || category.count !== 0)) return false;
    return !needle ||
      category.label.toLocaleLowerCase().includes(needle) ||
      category.name.toLocaleLowerCase().includes(needle);
  });
}

function element(doc, tag, className, value) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = value;
  return node;
}

function createAction(doc, name, label, format) {
  const anchor = element(doc, "a", "sub-action", label);
  anchor.href = subscriptionHref(name, format);
  anchor.setAttribute("download", "");
  anchor.setAttribute("aria-label", "Download " + name + " " + label + " subscription");
  return anchor;
}

function createProtocolCard(doc, category) {
  const card = element(doc, "article", "sub-protocol-card");
  card.id = "sub-protocol-" + category.name;

  const header = element(doc, "div", "sub-card-head");
  const code = element(doc, "span", "sub-card-code", category.name + "://");
  const count = element(doc, "span", "sub-card-count", category.published
    ? String(category.count) : "—");
  count.setAttribute("aria-label", category.published
    ? String(category.count) + " historical connections" : "Count unavailable");
  header.append(code, count);

  const title = element(doc, "h3", "sub-card-title", category.label);
  const subtitle = element(doc, "p", "sub-card-description",
    category.published
      ? category.count + " of " + category.limit + " newest discoveries"
      : "Awaiting publication");
  const controls = element(doc, "div", "sub-card-actions");

  if (category.published) {
    controls.append(
      createAction(doc, category.name, "Plain text", "plain"),
      createAction(doc, category.name, "Base64", "base64")
    );
    const copy = element(doc, "button", "sub-action sub-action-copy", "Copy URL");
    copy.type = "button";
    copy.dataset.subCopy = category.name;
    copy.setAttribute("aria-label", "Copy " + category.label + " subscription URL");
    controls.append(copy);
  } else {
    const unavailable = element(doc, "span", "sub-card-unavailable",
      "Download links appear after a verified publication");
    controls.append(unavailable);
  }

  card.append(header, title, subtitle, controls);
  return card;
}

export function mountSubscriptionHub(doc = document) {
  const hub = doc.getElementById("subscription-hub");
  const selector = doc.getElementById("design-direction-select");
  if (!hub || !selector) return () => {};
  const html = doc.documentElement;
  const view = doc.defaultView;
  let savedDirection;
  try {
    savedDirection = view?.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Browser storage can be disabled. The design remains selectable for this visit.
  }
  const initialDirection = normalizeDirection(savedDirection);
  html.dataset.huntxDirection = initialDirection;
  selector.value = initialDirection;
  const changeDirection = () => {
    const direction = normalizeDirection(selector.value);
    html.dataset.huntxDirection = direction;
    try {
      view?.localStorage.setItem(STORAGE_KEY, direction);
    } catch {
      // Never block a visual switch because preference storage is unavailable.
    }
  };
  selector.addEventListener("change", changeDirection);

  const status = doc.getElementById("sub-feed-status");
  const total = doc.getElementById("sub-stat-total");
  const types = doc.getElementById("sub-stat-types");
  const updated = doc.getElementById("sub-stat-updated");
  const list = doc.getElementById("sub-protocol-list");
  const search = doc.getElementById("sub-search");
  const clear = doc.getElementById("sub-search-clear");
  const availability = doc.getElementById("sub-availability");
  const empty = doc.getElementById("sub-no-results");
  const retry = doc.getElementById("sub-retry");
  const announce = doc.getElementById("sub-action-status");
  const masterLinks = [
    [doc.getElementById("sub-link-all"), "all", "plain"],
    [doc.getElementById("sub-link-all-base64"), "all", "base64"],
    [doc.getElementById("sub-link-index"), "index", "json"]
  ];
  const copyMaster = doc.getElementById("sub-copy-all");
  let directory = null;
  let pending = null;
  let closed = false;

  const setMasterAvailable = (ready) => {
    for (const [anchor, name, format] of masterLinks) {
      if (!anchor) continue;
      if (ready) {
        anchor.setAttribute("href", subscriptionHref(name, format));
        anchor.removeAttribute("aria-disabled");
      } else {
        anchor.removeAttribute("href");
        anchor.setAttribute("aria-disabled", "true");
      }
    }
    if (copyMaster) copyMaster.disabled = !ready;
  };

  const fallback = CORE_PROTOCOLS.map((name) => ({
    name, label: LABELS[name], published: false, count: null
  }));

  const render = () => {
    if (!list) return;
    const categories = directory?.categories || fallback;
    const visible = filterProtocols(categories, search?.value || "", availability?.value || "all");
    const fragment = doc.createDocumentFragment();
    for (const category of visible) {
      fragment.append(createProtocolCard(doc, category));
    }
    list.replaceChildren(fragment);
    if (empty) empty.hidden = visible.length > 0;
    if (clear) clear.hidden = !search?.value;
  };

  const setLoading = () => {
    if (status) status.textContent = "Checking published subscription index…";
    if (retry) retry.hidden = true;
    setMasterAvailable(false);
  };

  const loadIndex = async () => {
    if (pending) pending.abort();
    const controller = new AbortController();
    pending = controller;
    const timeout = view?.setTimeout(() => controller.abort(), 8000);
    setLoading();
    try {
      const response = await fetch(subscriptionHref("index", "json"), {
        signal: controller.signal, cache: "no-store",
        headers: { Accept: "application/json" }
      });
      if (!response.ok) throw new Error("subscription index HTTP " + response.status);
      const payload = await response.json();
      const next = normalizeSubscriptionIndex(payload);
      if (closed || pending !== controller) return;
      directory = next;
      if (total) total.textContent = next.aggregate.count.toLocaleString();
      if (types) types.textContent =
        String(next.categories.filter((category) => category.published).length);
      if (updated) updated.textContent = new Date(next.generatedAt).toLocaleDateString();
      if (status) status.textContent = "Historical feeds published · " + next.generatedAt.slice(0, 10);
      if (retry) retry.hidden = true;
      setMasterAvailable(true);
    } catch {
      if (closed || pending !== controller) return;
      directory = null;
      if (total) total.textContent = "—";
      if (types) types.textContent = "—";
      if (updated) updated.textContent = "—";
      if (status) status.textContent =
        "Subscription index unavailable. Existing release downloads remain accessible below.";
      if (retry) retry.hidden = false;
      setMasterAvailable(false);
    } finally {
      if (timeout !== undefined) view?.clearTimeout(timeout);
      if (pending === controller) pending = null;
      if (!closed) render();
    }
  };

  const onSearch = () => render();
  const onClear = () => {
    if (search) {
      search.value = "";
      search.focus();
    }
    render();
  };
  const onAvailability = () => render();

  const copyUrl = async (name) => {
    if (!view?.navigator?.clipboard?.writeText) {
      if (announce) announce.textContent = "Clipboard unavailable. Use the direct download link.";
      return;
    }
    try {
      const url = new URL(subscriptionHref(name), doc.baseURI).href;
      await view.navigator.clipboard.writeText(url);
      if (announce) announce.textContent = "Copied " + name + " subscription URL.";
    } catch {
      if (announce) announce.textContent =
        "Unable to copy. Use the direct download link instead.";
    }
  };

  const onCardClick = (event) => {
    const copy = event.target.closest?.("button[data-sub-copy]");
    if (!copy || !list?.contains(copy) || !directory) return;
    const name = copy.dataset.subCopy;
    if (directory.categories.some((c) => c.name === name && c.published)) {
      void copyUrl(name);
    }
  };
  const onMasterClick = () => {
    if (directory) void copyUrl("all");
  };
  const onDownloads = () => {
    doc.getElementById("artifacts-section")?.scrollIntoView({ behavior: "auto" });
  };

  search?.addEventListener("input", onSearch);
  clear?.addEventListener("click", onClear);
  availability?.addEventListener("change", onAvailability);
  list?.addEventListener("click", onCardClick);
  retry?.addEventListener("click", loadIndex);
  copyMaster?.addEventListener("click", onMasterClick);
  doc.getElementById("sub-view-downloads")?.addEventListener("click", onDownloads);
  setMasterAvailable(false);
  render();
  void loadIndex();

  return () => {
    closed = true;
    pending?.abort();
    selector.removeEventListener("change", changeDirection);
    search?.removeEventListener("input", onSearch);
    clear?.removeEventListener("click", onClear);
    availability?.removeEventListener("change", onAvailability);
    list?.removeEventListener("click", onCardClick);
    retry?.removeEventListener("click", loadIndex);
    copyMaster?.removeEventListener("click", onMasterClick);
    doc.getElementById("sub-view-downloads")?.removeEventListener("click", onDownloads);
  };
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountSubscriptionHub(), { once: true });
  } else {
    mountSubscriptionHub();
  }
}
