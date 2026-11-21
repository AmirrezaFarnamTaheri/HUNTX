/**
 * Historical subscriptions within the existing HUNTX Artifacts workspace.
 *
 * Metadata-only: this component never downloads, parses or stores proxy URIs.
 * Each link is generated from a validated protocol slug on the current site.
 */
const PRIORITY = [
  "vless", "vmess", "trojan", "anytls", "hysteria", "hysteria2",
  "socks", "http", "shadowsocks", "shadowsocksr", "tuic",
  "wireguard", "ssh", "shadowtls", "naive", "juicity", "mieru",
  "warp", "dns", "dnstt"
];
const SLUG = /^[a-z][a-z0-9-]{0,50}$/;

export function subscriptionPaths(name) {
  if (typeof name !== "string" || !SLUG.test(name)) {
    throw new TypeError("Invalid subscription protocol name");
  }
  return Object.freeze({
    plain: `subscriptions/latest/${name}.txt`,
    base64: `subscriptions/latest/${name}_base64.txt`
  });
}

export function normalizeSubscriptionIndex(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)
      || raw.schema_version !== 1 || raw.scope !== "all_time_cumulative"
      || raw.health_status !== "historical_unverified"
      || raw.limit_per_protocol !== 100
      || !raw.protocols || typeof raw.protocols !== "object"
      || Array.isArray(raw.protocols)
      || !raw.aggregate || typeof raw.aggregate !== "object") {
    throw new TypeError("Unrecognized historical subscription index");
  }
  const names = Object.keys(raw.protocols);
  if (!names.length || names.length > 100) {
    throw new TypeError("Missing or excessive subscription categories");
  }
  const entries = names.map((name) => {
    const row = raw.protocols[name];
    const paths = subscriptionPaths(name);
    if (!row || typeof row !== "object" || !Number.isSafeInteger(row.count)
        || row.count < 0 || row.count > 100
        || row.file !== `${name}.txt`
        || row.base64_file !== `${name}_base64.txt`) {
      throw new TypeError("Invalid protocol count or filename");
    }
    return { name, count: row.count, ...paths };
  });
  const sum = entries.reduce((acc, item) => acc + item.count, 0);
  if (!Number.isSafeInteger(raw.aggregate.count)
      || raw.aggregate.count !== sum
      || raw.aggregate.file !== "all.txt"
      || raw.aggregate.base64_file !== "all_base64.txt") {
    throw new TypeError("Aggregate does not match protocol subscriptions");
  }
  const order = (name) => {
    const index = PRIORITY.indexOf(name);
    return index < 0 ? PRIORITY.length : index;
  };
  entries.sort((a, b) => order(a.name) - order(b.name) || a.name.localeCompare(b.name, "en"));
  return {
    entries, total: sum, limit: 100, trust: "historical_unverified",
    generatedAt: typeof raw.generated_at === "string" ? raw.generated_at : null
  };
}

export function filterProtocolEntries(entries, search) {
  const query = String(search ?? "").trim().toLocaleLowerCase("en");
  return entries.filter((row) => row.name.toLocaleLowerCase("en").includes(query));
}

function node(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined) element.textContent = String(content);
  return element;
}

function link(label, file, className = "sub-link") {
  const anchor = node("a", className, label);
  // Relative URLs resolve under the same Pages project root (including /HUNTX/).
  anchor.href = new URL(file, document.baseURI).href;
  anchor.setAttribute("download", "");
  return anchor;
}

function copyAction(label, file, description = label) {
  const button = node("button", "sub-link sub-copy", label);
  button.type = "button";
  button.dataset.copySubscription = file;
  button.setAttribute("aria-label", `Copy URL for ${description}`);
  return button;
}

function renderAggregate(root, data) {
  const zone = root.querySelector("#subscription-featured");
  if (!zone) return;
  zone.replaceChildren();
  const master = node("article", "sub-feature sub-feature-primary");
  const eyebrow = node("span", "sub-eyebrow", "HISTORICAL / ALL PROTOCOLS");
  const title = node("h3", "", "One link. Every protocol.");
  const summary = node("p", "", `${data.total.toLocaleString()} unique historical configurations, selected from up to 100 per protocol. Never capped at 100 overall.`);
  const buttons = node("div", "sub-actions");
  const paths = subscriptionPaths("all");
  buttons.append(
    link("Plain-text feed", paths.plain, "sub-link sub-primary-link"),
    link("Base64 feed", paths.base64),
    copyAction("Copy master URL", paths.plain, "master aggregate")
  );
  master.append(eyebrow, title, summary, buttons);
  const live = node("article", "sub-feature sub-feature-release");
  live.append(
    node("span", "sub-eyebrow", "CURRENT RELEASE / SEPARATE"),
    node("h3", "", "Looking for verified releases?"),
    node("p", "", "The current-run release artifacts use separate acceptance checks. Historical subscriptions do not imply current reachability.")
  );
  const releaseLink = link(
    "Download current release (Base64)", "artifacts/release/all_sources_base64.txt"
  );
  live.append(releaseLink);
  zone.append(master, live);
}

function renderProtocols(root, entries) {
  const grid = root.querySelector("#subscription-protocol-grid");
  const empty = root.querySelector("#subscription-search-empty");
  if (!grid || !empty) return;
  grid.replaceChildren();
  empty.hidden = entries.length !== 0;
  for (const item of entries) {
    const card = node("article", "sub-protocol-card");
    const top = node("div", "sub-protocol-top");
    const label = node("h4", "sub-protocol-name", item.name);
    const count = node("span", "sub-protocol-count", `${item.count} / 100`);
    count.setAttribute("aria-label", `${item.count} of up to 100 historical proxies`);
    top.append(label, count);
    const note = node(
      "p", "sub-protocol-detail",
      item.count === 0 ? "No archived connections in this category yet." : "Latest discovered · no age expiry"
    );
    const buttons = node("div", "sub-protocol-actions");
    buttons.append(
      link("TXT", item.plain),
      link("Base64", item.base64),
      copyAction("Copy URL", item.plain, item.name)
    );
    card.append(top, note, buttons);
    grid.append(card);
  }
}

function updateStatus(root, text, kind) {
  const status = root.querySelector("#subscription-hub-status");
  if (!status) return;
  status.textContent = text;
  status.dataset.state = kind;
}

function announce(root, message) {
  const live = root.querySelector("#subscription-action-status");
  if (live) live.textContent = message;
}

export function mountSubscriptionHub(root = document) {
  const hub = root.querySelector("#subscription-hub");
  if (!hub) return () => {};
  const search = hub.querySelector("#subscription-protocol-search");
  const clear = hub.querySelector("#subscription-search-clear");
  const retry = hub.querySelector("#subscription-hub-retry");
  const list = hub.querySelector("#subscription-protocols");
  const meta = hub.querySelector("#subscription-summary");
  const controller = { active: null, generation: 0 };
  let entries = [];

  function applySearch() {
    const query = search.value;
    clear.hidden = query.length === 0;
    renderProtocols(hub, filterProtocolEntries(entries, query));
  }

  async function load() {
    controller.active?.abort();
    const request = new AbortController();
    controller.active = request;
    const generation = ++controller.generation;
    retry.disabled = true;
    retry.hidden = true;
    list.hidden = true;
    updateStatus(hub, "Loading historical subscription index…", "loading");
    try {
      const response = await fetch(new URL("subscriptions/latest/index.json", root.baseURI), {
        cache: "no-store", signal: request.signal
      });
      if (!response.ok) throw new Error("Subscription index was not published");
      const data = normalizeSubscriptionIndex(await response.json());
      if (generation !== controller.generation) return;
      entries = data.entries;
      renderAggregate(hub, data);
      meta.textContent = `${data.entries.length} protocol feeds · ${data.total.toLocaleString()} archived configurations · up to 100 per protocol`;
      list.hidden = false;
      applySearch();
      const stamp = data.generatedAt && Number.isFinite(Date.parse(data.generatedAt))
        ? new Date(data.generatedAt).toLocaleString()
        : "timestamp unavailable";
      updateStatus(hub, `Archive published ${stamp}. Discovery is not a live connectivity test.`, "ready");
    } catch {
      if (request.signal.aborted || generation !== controller.generation) return;
      entries = [];
      list.hidden = true;
      updateStatus(hub, "Historical subscriptions are not available in this publication. Existing downloads remain below.", "error");
      retry.hidden = false;
    } finally {
      if (generation === controller.generation) retry.disabled = false;
    }
  }

  const onSearch = () => applySearch();
  const onClear = () => { search.value = ""; applySearch(); search.focus(); };
  const onRetry = () => { void load(); };
  const onCopy = async (event) => {
    const target = event.target.closest?.("[data-copy-subscription]");
    if (!target || !hub.contains(target)) return;
    const path = target.dataset.copySubscription;
    if (!path || !/^subscriptions\/latest\/[a-z][a-z0-9-]*\.txt$/.test(path)) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(new URL(path, root.baseURI).href);
      announce(hub, "Subscription URL copied.");
    } catch {
      announce(hub, "Copy unavailable. Open the feed and copy its URL from the browser.");
    }
  };

  search.addEventListener("input", onSearch);
  clear.addEventListener("click", onClear);
  retry.addEventListener("click", onRetry);
  hub.addEventListener("click", onCopy);
  void load();
  return () => {
    controller.active?.abort();
    search.removeEventListener("input", onSearch);
    clear.removeEventListener("click", onClear);
    retry.removeEventListener("click", onRetry);
    hub.removeEventListener("click", onCopy);
  };
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountSubscriptionHub(), { once: true });
  } else {
    mountSubscriptionHub();
  }
}
