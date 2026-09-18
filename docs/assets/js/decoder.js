// HUNTX Client-Side Proxy Protocol Decoder & Parser
// Hardened, IPv6-compliant, malformed URI resilient, and fully zero-dependency.

// ---------------------------------------------------------------------------
// Serialization guards
//
// Node metadata — names, SNI values, hosts, transport paths — arrives from
// public channels and is attacker controlled. The generated Clash, Surge, Loon
// and Quantumult X profiles are line- and comma-delimited formats, so a value
// carrying a newline, a quote or a delimiter does not merely corrupt the
// output: it appends directives the user never asked for to a config they are
// about to load into a proxy client. Every untrusted value must pass through
// one of these before it is interpolated.
// ---------------------------------------------------------------------------

/**
 * Render a value as a double-quoted YAML scalar.
 *
 * Double-quoted YAML is the only style that can carry arbitrary text, and it
 * needs backslash, quote and control characters escaped. Escaping newlines
 * rather than stripping them keeps the value faithful while making it
 * impossible to open a new YAML node.
 *
 * @param {unknown} value
 * @returns {string} A quoted scalar, safe to place after `key: `.
 */
export function yamlQuote(value) {
  const text = value === undefined || value === null ? "" : String(value);
  const escaped = text
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\r/g, "\\r")
    .replace(/\n/g, "\\n")
    .replace(/\t/g, "\\t")
    // Remaining C0 controls and DEL have no literal double-quoted form.
    // eslint-disable-next-line no-control-regex -- matching controls is the point
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, (c) =>
      `\\x${c.charCodeAt(0).toString(16).padStart(2, "0")}`
    );
  return `"${escaped}"`;
}

/**
 * Sanitize a value for the comma-delimited, line-oriented config formats used
 * by Surge, Loon and Quantumult X.
 *
 * These formats have no escaping mechanism at all, so the only safe transform
 * is to remove the characters that carry structural meaning.
 *
 * @param {unknown} value
 * @param {{ allowComma?: boolean }} [options]
 * @returns {string}
 */
export function iniValue(value, { allowComma = false } = {}) {
  const text = value === undefined || value === null ? "" : String(value);
  // eslint-disable-next-line no-control-regex -- matching controls is the point
  const stripped = text.replace(/[\r\n\u0000-\u001f\u007f]/g, "");
  return allowComma ? stripped : stripped.replace(/,/g, "_");
}

/**
 * Sanitize a node name for use as a Surge/Loon/QX entry label or tag.
 *
 * `=` separates the label from the directive body and `,` separates fields, so
 * both are replaced in addition to the control characters handled above. An
 * empty result would produce a nameless directive, so a placeholder is used.
 *
 * @param {unknown} value
 * @returns {string}
 */
export function iniTag(value) {
  const cleaned = iniValue(value).replace(/=/g, "_").trim();
  return cleaned === "" ? "huntx-node" : cleaned;
}

function safeDecodeURI(str, fallback = "") {
  if (!str) return fallback;
  try {
    return decodeURIComponent(str);
  } catch (e) {
    return str;
  }
}

function safeAtob(b64Str) {
  if (!b64Str || typeof b64Str !== "string") return "";
  let clean = b64Str.trim().replace(/[\r\n\s]/g, "").replace(/-/g, "+").replace(/_/g, "/");
  while (clean.length % 4 !== 0) {
    clean += "=";
  }
  try {
    let binary = "";
    if (typeof atob !== "undefined") {
      binary = atob(clean);
    } else if (typeof Buffer !== "undefined") {
      return Buffer.from(clean, "base64").toString("utf-8");
    } else {
      return "";
    }
    // atob yields one character per byte; multi-byte UTF-8 payloads (Cyrillic,
    // CJK, emoji node names) must be decoded explicitly or they render as
    // Latin-1 mojibake.
    if (typeof TextDecoder !== "undefined") {
      const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
      // Strict first: a payload that is not valid UTF-8 is corruption,
      // and silently replacing bad bytes with U+FFFD would let a
      // corrupted node name reach the dashboard as if it were real.
      // Fall back to replacement so a noisy-but-decodable payload still
      // renders instead of being dropped.
      try {
        return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      } catch (e) {
        return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
      }
    }
    return decodeURIComponent(escape(binary));
  } catch (e) {
    throw new Error("Invalid Base64 payload");
  }
}

function parseHostAndPort(hostAndPort, defaultPort = 443) {
  if (!hostAndPort) return { server: "", port: defaultPort };

  // IPv6 bracket format: [2001:db8::1]:443 or [2001:db8::1]
  if (hostAndPort.startsWith("[")) {
    const endBracket = hostAndPort.indexOf("]");
    if (endBracket !== -1) {
      const server = hostAndPort.slice(0, endBracket + 1);
      const remainder = hostAndPort.slice(endBracket + 1);
      let port = defaultPort;
      if (remainder.startsWith(":")) {
        port = parseInt(remainder.slice(1), 10) || defaultPort;
      }
      return { server, port };
    }
  }

  // IPv4 or domain name: host:port
  const lastColon = hostAndPort.lastIndexOf(":");
  if (lastColon !== -1) {
    const server = hostAndPort.slice(0, lastColon);
    const port = parseInt(hostAndPort.slice(lastColon + 1), 10) || defaultPort;
    return { server, port };
  }

  return { server: hostAndPort, port: defaultPort };
}

export function decodeProxyURI(rawUri) {
  if (!rawUri || typeof rawUri !== "string") {
    throw new Error("Invalid URI input");
  }

  const str = rawUri.trim();

  // 1. VMess (Base64 JSON)
  if (str.startsWith("vmess://")) {
    const b64 = str.slice(8);
    try {
      const jsonStr = safeAtob(b64);
      const parsed = JSON.parse(jsonStr);
      return {
        protocol: "vmess",
        name: parsed.ps || "VMess-Node",
        server: parsed.add || parsed.host || "",
        port: parseInt(parsed.port, 10) || 443,
        uuid: parsed.id || "",
        alterId: parsed.aid || 0,
        security: parsed.scy || "auto",
        transport: parsed.net || "tcp",
        type: parsed.type || "none",
        host: parsed.host || "",
        path: parsed.path || "",
        tls: parsed.tls || "none",
        sni: parsed.sni || "",
        alpn: parsed.alpn || "",
        raw: str
      };
    } catch (e) {
      throw new Error("Failed to decode VMess Base64 payload: " + e.message);
    }
  }

  // 2. VLESS (vless://uuid@host:port?query#name)
  if (str.startsWith("vless://")) {
    const withoutScheme = str.slice(8);
    const hashIdx = withoutScheme.indexOf("#");
    const name = hashIdx !== -1 ? safeDecodeURI(withoutScheme.slice(hashIdx + 1), "VLESS-Node") : "VLESS-Node";
    const mainPart = hashIdx !== -1 ? withoutScheme.slice(0, hashIdx) : withoutScheme;

    const [authAndHost, queryString] = mainPart.split("?");
    const [uuid, hostAndPort] = (authAndHost || "").split("@");
    const { server, port } = parseHostAndPort(hostAndPort, 443);

    const params = new URLSearchParams(queryString || "");

    return {
      protocol: "vless",
      name: name,
      server: server || "",
      port: port || 443,
      uuid: uuid || "",
      flow: params.get("flow") || "",
      encryption: params.get("encryption") || "none",
      security: params.get("security") || "none",
      transport: params.get("type") || "tcp",
      headerType: params.get("headerType") || "none",
      host: params.get("host") || "",
      path: params.get("path") || "",
      sni: params.get("sni") || "",
      alpn: params.get("alpn") || "",
      fingerprint: params.get("fp") || "",
      publicKey: params.get("pbk") || "",
      shortId: params.get("sid") || "",
      spiderX: params.get("spx") || "",
      serviceName: params.get("serviceName") || "",
      mode: params.get("mode") || "",
      raw: str
    };
  }

  // 3. Trojan (trojan://password@host:port?query#name)
  if (str.startsWith("trojan://")) {
    const withoutScheme = str.slice(9);
    const hashIdx = withoutScheme.indexOf("#");
    const name = hashIdx !== -1 ? safeDecodeURI(withoutScheme.slice(hashIdx + 1), "Trojan-Node") : "Trojan-Node";
    const mainPart = hashIdx !== -1 ? withoutScheme.slice(0, hashIdx) : withoutScheme;

    const [authAndHost, queryString] = mainPart.split("?");
    const [password, hostAndPort] = (authAndHost || "").split("@");
    const { server, port } = parseHostAndPort(hostAndPort, 443);

    const params = new URLSearchParams(queryString || "");

    return {
      protocol: "trojan",
      name: name,
      server: server || "",
      port: port || 443,
      password: password || "",
      security: params.get("security") || "tls",
      transport: params.get("type") || "tcp",
      host: params.get("host") || "",
      path: params.get("path") || "",
      sni: params.get("sni") || "",
      alpn: params.get("alpn") || "",
      fingerprint: params.get("fp") || "",
      raw: str
    };
  }

  // 4. Shadowsocks (ss://...)
  if (str.startsWith("ss://")) {
    const withoutScheme = str.slice(5);
    const hashIdx = withoutScheme.indexOf("#");
    const name = hashIdx !== -1 ? safeDecodeURI(withoutScheme.slice(hashIdx + 1), "Shadowsocks-Node") : "Shadowsocks-Node";
    const mainPart = hashIdx !== -1 ? withoutScheme.slice(0, hashIdx) : withoutScheme;

    let method = "unknown";
    let password = "";
    let server = "";
    let port = 8388;

    if (mainPart.includes("@")) {
      const [authB64, hostPort] = mainPart.split("@");
      try {
        const decodedAuth = safeAtob(authB64);
        const splitAt = decodedAuth.indexOf(":");
        method = splitAt === -1 ? "unknown" : decodedAuth.slice(0, splitAt);
        password = splitAt === -1 ? "" : decodedAuth.slice(splitAt + 1);
      } catch (e) {
        method = "raw";
        password = authB64;
      }
      const parsedHP = parseHostAndPort(hostPort, 8388);
      server = parsedHP.server;
      port = parsedHP.port;
    } else {
      try {
        const decoded = safeAtob(mainPart);
        const [auth, hostPort] = decoded.split("@");
        const splitAt = (auth || "").indexOf(":");
        method = splitAt === -1 ? "unknown" : auth.slice(0, splitAt);
        password = splitAt === -1 ? "" : auth.slice(splitAt + 1);
        const parsedHP = parseHostAndPort(hostPort, 8388);
        server = parsedHP.server;
        port = parsedHP.port;
      } catch (e) {
        server = mainPart;
      }
    }

    return {
      protocol: "shadowsocks",
      name: name,
      server: server,
      port: port,
      cipher: method,
      password: password,
      security: method,
      raw: str
    };
  }

  // 5. Hysteria / Hysteria2 (hysteria2://... or hy2://...)
  if (str.startsWith("hysteria2://") || str.startsWith("hy2://")) {
    const scheme = str.startsWith("hysteria2://") ? "hysteria2://" : "hy2://";
    const withoutScheme = str.slice(scheme.length);
    const hashIdx = withoutScheme.indexOf("#");
    const name = hashIdx !== -1 ? safeDecodeURI(withoutScheme.slice(hashIdx + 1), "Hysteria2-Node") : "Hysteria2-Node";
    const mainPart = hashIdx !== -1 ? withoutScheme.slice(0, hashIdx) : withoutScheme;

    const [authAndHost, queryString] = mainPart.split("?");
    const [auth, hostAndPort] = (authAndHost || "").split("@");
    const { server, port } = parseHostAndPort(hostAndPort, 443);
    const params = new URLSearchParams(queryString || "");

    return {
      protocol: "hysteria2",
      name: name,
      server: server || "",
      port: port || 443,
      auth: auth || "",
      sni: params.get("sni") || server,
      insecure: params.get("insecure") === "1",
      obfs: params.get("obfs") || "none",
      raw: str
    };
  }

  // 6. Generic Base64 Subscription
  try {
    const decodedSub = safeAtob(str);
    const lines = decodedSub.split(/\r?\n/).filter(l => l.trim().length > 0);
    if (lines.length > 0 && (lines[0].includes("://"))) {
      return {
        protocol: "subscription",
        name: "Base64 Subscription",
        count: lines.length,
        lines: lines,
        decodedItems: lines.map(line => {
          try {
            return decodeProxyURI(line);
          } catch {
            return { protocol: "raw", raw: line };
          }
        }),
        raw: str
      };
    }
  } catch (e) {
    // Not a valid base64 subscription
  }

  return {
    protocol: "raw",
    name: "Raw Proxy / Config",
    raw: str
  };
}


export function extractAllURIs(text) {
  if (!text || typeof text !== "string") return [];
  const lines = text.split(/\r?\n/);
  const uris = [];
  const schemes = ["vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://", "tuic://", "socks5://", "http://", "https://"];

  for (let line of lines) {
    line = line.trim();
    if (!line || line.startsWith("#") || line.startsWith("//")) continue;

    // Check if line contains a supported scheme
    for (const s of schemes) {
      const idx = line.indexOf(s);
      if (idx !== -1) {
        // Extract substring until whitespace
        const sub = line.slice(idx).split(/\s+/)[0];
        uris.push(sub);
        break;
      }
    }
  }

  // If no direct scheme found, try base64 decode
  if (uris.length === 0 && text.trim().length > 20) {
    try {
      const decoded = safeAtob(text.trim());
      return extractAllURIs(decoded);
    } catch {
      // The input simply was not a base64 subscription. Fall through and
      // return whatever the direct scheme scan found, which may be nothing.
    }
  }

  return uris;
}

export function nodeToSingboxOutbound(node) {
  if (!node) return null;
  const tag = node.name || `${node.protocol}-${node.server}`;
  const proto = (node.protocol || "vless").toLowerCase();

  if (proto === "vless") {
    const outbound = {
      type: "vless",
      tag: tag,
      server: node.server,
      server_port: node.port,
      uuid: node.uuid,
      flow: node.flow || undefined
    };
    if (node.security === "reality" || node.publicKey) {
      outbound.tls = {
        enabled: true,
        server_name: node.sni || node.server,
        reality: {
          enabled: true,
          public_key: node.publicKey || "",
          short_id: node.shortId || ""
        },
        utls: {
          enabled: true,
          fingerprint: node.fingerprint || "chrome"
        }
      };
    } else if (node.security === "tls") {
      outbound.tls = {
        enabled: true,
        server_name: node.sni || node.server,
        insecure: node.insecure || false
      };
    }
    if (node.transport === "ws" || node.transport === "websocket") {
      outbound.transport = {
        type: "ws",
        path: node.path || "/",
        headers: node.host ? { Host: node.host } : undefined
      };
    } else if (node.transport === "grpc") {
      outbound.transport = {
        type: "grpc",
        service_name: node.serviceName || ""
      };
    }
    return outbound;
  }

  if (proto === "vmess") {
    const outbound = {
      type: "vmess",
      tag: tag,
      server: node.server,
      server_port: node.port,
      uuid: node.uuid,
      alter_id: node.alterId || 0,
      security: node.security || "auto"
    };
    if (node.tls === "tls") {
      outbound.tls = {
        enabled: true,
        server_name: node.sni || node.server
      };
    }
    if (node.transport === "ws" || node.transport === "websocket") {
      outbound.transport = {
        type: "ws",
        path: node.path || "/",
        headers: node.host ? { Host: node.host } : undefined
      };
    }
    return outbound;
  }

  if (proto === "trojan") {
    return {
      type: "trojan",
      tag: tag,
      server: node.server,
      server_port: node.port,
      password: node.password,
      tls: {
        enabled: true,
        server_name: node.sni || node.server
      }
    };
  }

  if (proto === "shadowsocks") {
    return {
      type: "shadowsocks",
      tag: tag,
      server: node.server,
      server_port: node.port,
      method: node.cipher || "aes-128-gcm",
      password: node.password
    };
  }

  if (proto === "hysteria2") {
    return {
      type: "hysteria2",
      tag: tag,
      server: node.server,
      server_port: node.port,
      password: node.auth || node.password,
      tls: {
        enabled: true,
        server_name: node.sni || node.server,
        insecure: node.insecure || false
      }
    };
  }

  return {
    type: proto,
    tag: tag,
    server: node.server,
    server_port: node.port
  };
}

export function nodeToClashProxy(node) {
  if (!node) return null;
  const proto = (node.protocol || "vless").toLowerCase();
  const name = node.name || `${proto}-${node.server}:${node.port}`;

  if (proto === "vless") {
    const proxy = {
      name: name,
      type: "vless",
      server: node.server,
      port: node.port,
      uuid: node.uuid,
      network: node.transport || "tcp",
      tls: node.security === "tls" || node.security === "reality",
      servername: node.sni || node.server,
      "client-fingerprint": node.fingerprint || "chrome"
    };
    if (node.security === "reality" || node.publicKey) {
      proxy["reality-opts"] = {
        "public-key": node.publicKey || "",
        "short-id": node.shortId || ""
      };
    }
    if (node.transport === "ws" || node.transport === "websocket") {
      proxy["ws-opts"] = {
        path: node.path || "/",
        headers: node.host ? { Host: node.host } : undefined
      };
    } else if (node.transport === "grpc") {
      proxy["grpc-opts"] = {
        "grpc-service-name": node.serviceName || ""
      };
    }
    return proxy;
  }

  if (proto === "vmess") {
    return {
      name: name,
      type: "vmess",
      server: node.server,
      port: node.port,
      uuid: node.uuid,
      alterId: node.alterId || 0,
      cipher: node.security || "auto",
      network: node.transport || "tcp",
      tls: node.tls === "tls",
      servername: node.sni || node.server,
      "ws-opts": (node.transport === "ws") ? { path: node.path || "/" } : undefined
    };
  }

  if (proto === "trojan") {
    return {
      name: name,
      type: "trojan",
      server: node.server,
      port: node.port,
      password: node.password,
      sni: node.sni || node.server,
      "skip-cert-verify": node.insecure || false
    };
  }

  if (proto === "shadowsocks") {
    return {
      name: name,
      type: "ss",
      server: node.server,
      port: node.port,
      cipher: node.cipher || "aes-128-gcm",
      password: node.password
    };
  }

  if (proto === "hysteria2") {
    return {
      name: name,
      type: "hysteria2",
      server: node.server,
      port: node.port,
      password: node.auth || node.password,
      sni: node.sni || node.server,
      "skip-cert-verify": node.insecure || false
    };
  }

  return {
    name: name,
    type: proto,
    server: node.server,
    port: node.port
  };
}

export function buildSingboxConfig(nodes) {
  const outbounds = nodes.map(nodeToSingboxOutbound).filter(Boolean);
  const tags = outbounds.map(o => o.tag);

  return {
    log: { level: "info", timestamp: true },
    dns: {
      servers: [
        { tag: "dns-remote", address: "tls://8.8.8.8", detour: "select-auto" },
        { tag: "dns-direct", address: "https://1.1.1.1/dns-query", detour: "direct" }
      ],
      rules: [
        { outbound: "any", server: "dns-direct" }
      ]
    },
    inbounds: [
      { type: "mixed", tag: "mixed-in", listen: "127.0.0.1", listen_port: 7890 },
      { type: "tun", tag: "tun-in", interface_name: "huntx-tun", inet4_address: "172.19.0.1/30", auto_route: true, strict_route: false }
    ],
    outbounds: [
      {
        type: "urltest",
        tag: "select-auto",
        outbounds: tags,
        url: "https://www.gstatic.com/generate_204",
        interval: "3m",
        tolerance: 50
      },
      {
        type: "selector",
        tag: "select-manual",
        outbounds: ["select-auto", ...tags, "direct", "block"]
      },
      ...outbounds,
      { type: "direct", tag: "direct" },
      { type: "block", tag: "block" }
    ],
    route: {
      rules: [
        { ip_is_private: true, action: "route", outbound: "direct" },
        { protocol: "dns", action: "hijack-dns" }
      ],
      final: "select-manual",
      auto_detect_interface: true
    }
  };
}

/**
 * Serialize one Clash Meta proxy object as a YAML list entry.
 *
 * Extracted so that the dashboard can offer a single node in the same format
 * the full profile uses, and so the quoting rules live in exactly one place.
 * Identifier-shaped fields (`type`, `network`, `cipher`) are emitted bare
 * because they come from HUNTX's own protocol mapping; everything that
 * originates in ingested metadata is quoted.
 *
 * @param {Record<string, any>} proxy A node from `nodeToClashProxy`.
 * @param {string} [indent] Leading indentation for the entry.
 * @returns {string} A YAML fragment ending in a newline, or "" for no proxy.
 */
export function clashProxyToYAML(proxy, indent = "  ") {
  if (!proxy) return "";
  const field = `${indent}  `;
  let out = `${indent}- name: ${yamlQuote(proxy.name)}\n`;
  out += `${field}type: ${proxy.type}\n`;
  out += `${field}server: ${yamlQuote(proxy.server)}\n`;
  out += `${field}port: ${Number(proxy.port) || 0}\n`;
  if (proxy.uuid) out += `${field}uuid: ${yamlQuote(proxy.uuid)}\n`;
  if (proxy.password) out += `${field}password: ${yamlQuote(proxy.password)}\n`;
  if (proxy.cipher) out += `${field}cipher: ${yamlQuote(proxy.cipher)}\n`;
  if (proxy.network) out += `${field}network: ${yamlQuote(proxy.network)}\n`;
  if (proxy.tls !== undefined) out += `${field}tls: ${proxy.tls ? "true" : "false"}\n`;
  if (proxy.servername) out += `${field}servername: ${yamlQuote(proxy.servername)}\n`;
  if (proxy["client-fingerprint"]) {
    out += `${field}client-fingerprint: ${yamlQuote(proxy["client-fingerprint"])}\n`;
  }
  if (proxy["reality-opts"]) {
    out += `${field}reality-opts:\n`;
    out += `${field}  public-key: ${yamlQuote(proxy["reality-opts"]["public-key"])}\n`;
    out += `${field}  short-id: ${yamlQuote(proxy["reality-opts"]["short-id"])}\n`;
  }
  if (proxy["ws-opts"]) {
    out += `${field}ws-opts:\n${field}  path: ${yamlQuote(proxy["ws-opts"].path)}\n`;
    const wsHost = proxy["ws-opts"].headers && proxy["ws-opts"].headers.Host;
    if (wsHost) {
      out += `${field}  headers:\n${field}    Host: ${yamlQuote(wsHost)}\n`;
    }
  }
  if (proxy["grpc-opts"]) {
    out += `${field}grpc-opts:\n`;
    out += `${field}  grpc-service-name: ${yamlQuote(proxy["grpc-opts"]["grpc-service-name"])}\n`;
  }
  return out;
}

export function buildClashMetaYAML(nodes) {
  const proxies = nodes.map(nodeToClashProxy).filter(Boolean);
  const proxyNames = proxies.map(p => p.name);

  let yaml = `# HUNTX Sovereign Proxy Aggregator — Clash Meta / Mihomo Profile\n`;
  yaml += `port: 7890\nsocks-port: 7891\nredir-port: 7892\ntproxy-port: 7893\nmixed-port: 7890\nallow-lan: false\nmode: rule\nlog-level: info\nipv6: false\n\n`;
  yaml += `dns:\n  enable: true\n  listen: 127.0.0.1:1053\n  enhanced-mode: fake-ip\n  nameserver:\n    - 1.1.1.1\n    - 8.8.8.8\n\n`;

  yaml += `proxies:\n`;
  proxies.forEach(p => {
    yaml += clashProxyToYAML(p);
  });

  yaml += `\nproxy-groups:\n`;
  yaml += `  - name: "AUTO-BEST"\n    type: url-test\n    url: http://www.gstatic.com/generate_204\n    interval: 300\n    tolerance: 50\n    proxies:\n`;
  proxyNames.forEach(n => { yaml += `      - ${yamlQuote(n)}\n`; });

  yaml += `  - name: "PROXIES"\n    type: select\n    proxies:\n      - AUTO-BEST\n`;
  proxyNames.forEach(n => { yaml += `      - ${yamlQuote(n)}\n`; });
  yaml += `      - DIRECT\n`;

  yaml += `\nrules:\n  - DOMAIN-SUFFIX,ir,DIRECT\n  - GEOIP,IR,DIRECT\n  - MATCH,PROXIES\n`;
  return yaml;
}

export function nodeToSurgeProxy(node) {
  if (!node) return "";
  const proto = (node.protocol || "vless").toLowerCase();
  const name = iniTag(node.name || `${proto}-${node.server}`);
  const server = iniValue(node.server);
  const port = Number(node.port) || 0;

  if (proto === "vless") {
    let line = `${name} = vless, ${server}, ${port}, username=${iniValue(node.uuid)}`;
    if (node.security === "tls" || node.security === "reality") line += `, tls=true`;
    if (node.sni) line += `, sni=${iniValue(node.sni)}`;
    if (node.publicKey) line += `, reality-public-key=${iniValue(node.publicKey)}`;
    if (node.shortId) line += `, reality-short-id=${iniValue(node.shortId)}`;
    if (node.transport === "ws" || node.transport === "websocket") {
      line += `, ws=true, ws-path=${iniValue(node.path || "/")}`;
      if (node.host) line += `, ws-header=Host:${iniValue(node.host)}`;
    }
    return line;
  }

  if (proto === "trojan") {
    let line = `${name} = trojan, ${server}, ${port}, password=${iniValue(node.password)}`;
    if (node.sni) line += `, sni=${iniValue(node.sni)}`;
    line += `, tls=true`;
    return line;
  }

  if (proto === "shadowsocks") {
    return `${name} = ss, ${server}, ${port}, encrypt-method=${iniValue(node.cipher || "aes-128-gcm")}, password=${iniValue(node.password)}`;
  }

  if (proto === "hysteria2") {
    let line = `${name} = hysteria2, ${server}, ${port}, password=${iniValue(node.auth || node.password)}`;
    if (node.sni) line += `, sni=${iniValue(node.sni)}`;
    return line;
  }

  return `${name} = http, ${server}, ${port}`;
}

export function nodeToLoonProxy(node) {
  if (!node) return "";
  const proto = (node.protocol || "vless").toLowerCase();
  const name = iniTag(node.name || `${proto}-${node.server}`);
  const server = iniValue(node.server);
  const port = Number(node.port) || 0;
  // Loon wraps some values in double quotes but offers no escape sequence, so
  // an embedded quote would terminate the field early. Strip it alongside the
  // structural characters iniValue already removes.
  const quoted = (value) => `"${iniValue(value).replace(/"/g, "")}"`;
  const tlsName = iniValue(node.sni || node.server);

  if (proto === "vless") {
    let line = `${name} = vless, ${server}, ${port}, ${quoted(node.uuid)}, fast-open=false, udp=true`;
    if (node.security === "reality") {
      line += `, tls-name=${tlsName}, reality=true, public-key=${quoted(node.publicKey || "")}, short-id=${quoted(node.shortId || "")}`;
    } else if (node.security === "tls") {
      line += `, tls-name=${tlsName}, tls=true`;
    }
    if (node.transport === "ws" || node.transport === "websocket") {
      line += `, transport=ws, path=${quoted(node.path || "/")}`;
      if (node.host) line += `, host=${quoted(node.host)}`;
    }
    return line;
  }

  if (proto === "trojan") {
    return `${name} = trojan, ${server}, ${port}, ${quoted(node.password)}, tls-name=${tlsName}, tls=true, fast-open=false, udp=true`;
  }

  if (proto === "shadowsocks") {
    return `${name} = shadowsocks, ${server}, ${port}, ${quoted(node.cipher || "aes-128-gcm")}, ${quoted(node.password)}, fast-open=false, udp=true`;
  }

  if (proto === "hysteria2") {
    return `${name} = hysteria2, ${server}, ${port}, ${quoted(node.auth || node.password)}, sni=${tlsName}, fast-open=false, udp=true`;
  }

  return `${name} = http, ${server}, ${port}`;
}

export function nodeToQXServer(node) {
  if (!node) return "";
  const proto = (node.protocol || "vless").toLowerCase();
  const name = iniTag(node.name || `${proto}-${node.server}`);
  const server = iniValue(node.server);
  const port = Number(node.port) || 0;
  const tlsHost = iniValue(node.sni || node.server);

  if (proto === "vless") {
    let line = `vless=${server}:${port}, method=none, password=${iniValue(node.uuid)}, fast-open=false, udp-relay=true, tag=${name}`;
    if (node.security === "reality") {
      line += `, tls=true, tls-host=${tlsHost}, reality-base64=${iniValue(node.publicKey || "")}, reality-short-id=${iniValue(node.shortId || "")}`;
    } else if (node.security === "tls") {
      line += `, tls=true, tls-host=${tlsHost}`;
    }
    if (node.transport === "ws" || node.transport === "websocket") {
      line += `, obfs=ws, obfs-uri=${iniValue(node.path || "/")}`;
      if (node.host) line += `, obfs-host=${iniValue(node.host)}`;
    }
    return line;
  }

  if (proto === "trojan") {
    return `trojan=${server}:${port}, password=${iniValue(node.password)}, over-tls=true, tls-host=${tlsHost}, fast-open=false, udp-relay=true, tag=${name}`;
  }

  if (proto === "shadowsocks") {
    return `shadowsocks=${server}:${port}, method=${iniValue(node.cipher || "aes-128-gcm")}, password=${iniValue(node.password)}, fast-open=false, udp-relay=true, tag=${name}`;
  }

  return `http=${server}:${port}, tag=${name}`;
}

export function buildXrayClientConfig(nodes) {
  const outbounds = nodes.map(n => {
    const proto = (n.protocol || "vless").toLowerCase();
    if (proto === "vless") {
      return {
        protocol: "vless",
        tag: n.name || `vless-${n.server}`,
        settings: {
          vnext: [{
            address: n.server,
            port: n.port,
            users: [{ id: n.uuid, encryption: "none", flow: n.flow || undefined }]
          }]
        },
        streamSettings: {
          network: n.transport || "tcp",
          security: n.security || "none",
          realitySettings: n.security === "reality" ? {
            serverName: n.sni || n.server,
            publicKey: n.publicKey || "",
            shortId: n.shortId || "",
            fingerprint: n.fingerprint || "chrome"
          } : undefined,
          tlsSettings: n.security === "tls" ? {
            serverName: n.sni || n.server,
            allowInsecure: n.insecure || false
          } : undefined,
          wsSettings: (n.transport === "ws" || n.transport === "websocket") ? {
            path: n.path || "/",
            headers: n.host ? { Host: n.host } : undefined
          } : undefined,
          grpcSettings: n.transport === "grpc" ? {
            serviceName: n.serviceName || ""
          } : undefined
        }
      };
    }
    return {
      protocol: proto,
      tag: n.name || `${proto}-${n.server}`,
      settings: {}
    };
  });

  return {
    log: { loglevel: "warning" },
    inbounds: [
      { tag: "socks-in", port: 10808, listen: "127.0.0.1", protocol: "socks", settings: { auth: "noauth", udp: true } },
      { tag: "http-in", port: 10809, listen: "127.0.0.1", protocol: "http", settings: {} }
    ],
    outbounds: [
      ...outbounds,
      { protocol: "freedom", tag: "direct", settings: {} },
      { protocol: "blackhole", tag: "block", settings: {} }
    ],
    routing: {
      domainStrategy: "IPIfNonMatch",
      rules: [
        { type: "field", outboundTag: "block", domain: ["geosite:category-ads-all"] },
        { type: "field", outboundTag: "direct", ip: ["geoip:private", "geoip:cn", "geoip:ir"] },
        { type: "field", outboundTag: "direct", domain: ["geosite:cn", "geosite:category-ir"] }
      ]
    }
  };
}

export function buildSurgeConfig(nodes) {
  let out = `[General]\nloglevel = notify\n\n[Proxy]\n`;
  nodes.forEach(n => {
    const line = nodeToSurgeProxy(n);
    if (line) out += `${line}\n`;
  });
  const taggedNodes = nodes.map(n => iniTag(n.name || 'node'));
  out += `\n[Proxy Group]\nAUTO-BEST = url-test, ${taggedNodes.join(', ')}, url=http://www.gstatic.com/generate_204, interval=300\nPROXIES = select, AUTO-BEST, DIRECT, ${taggedNodes.join(', ')}\n\n[Rule]\nGEOIP,IR,DIRECT\nFINAL,PROXIES\n`;
  return out;
}

export function buildLoonConfig(nodes) {
  let out = `[General]\n\n[Proxy]\n`;
  nodes.forEach(n => {
    const line = nodeToLoonProxy(n);
    if (line) out += `${line}\n`;
  });
  const taggedNodes = nodes.map(n => iniTag(n.name || 'node'));
  out += `\n[Proxy Group]\nAUTO-BEST = url-test, ${taggedNodes.join(', ')}, url=http://www.gstatic.com/generate_204, interval=300\n\n[Rule]\nGEOIP,IR,DIRECT\nFINAL,AUTO-BEST\n`;
  return out;
}

export function buildQXConfig(nodes) {
  let out = `[general]\n\n[server_local]\n`;
  nodes.forEach(n => {
    const line = nodeToQXServer(n);
    if (line) out += `${line}\n`;
  });
  const taggedNodes = nodes.map(n => iniTag(n.name || 'node'));
  out += `\n[policy]\nurl-latency-benchmark = AUTO-BEST, ${taggedNodes.join(', ')}, check-interval=300, tolerance=50\n\n[filter_local]\ngeoip, ir, direct\nfinal, AUTO-BEST\n`;
  return out;
}

export function buildBase64Sub(uris) {
  const plain = uris.filter(Boolean).join("\n");
  if (typeof btoa !== "undefined") {
    return btoa(unescape(encodeURIComponent(plain)));
  }
  return Buffer.from(plain).toString("base64");
}

export function convertProxyBatch(rawInput, format = "singbox") {
  const uris = extractAllURIs(rawInput);
  if (uris.length === 0) {
    throw new Error("No valid proxy URIs detected in input payload");
  }

  const nodes = uris.map(u => {
    try {
      return decodeProxyURI(u);
    } catch {
      return null;
    }
  }).filter(Boolean);

  switch (format.toLowerCase()) {
    case "singbox":
    case "sing-box":
      return JSON.stringify(buildSingboxConfig(nodes), null, 2);
    case "clash":
    case "clash-meta":
    case "mihomo":
      return buildClashMetaYAML(nodes);
    case "xray":
    case "v2ray":
      return JSON.stringify(buildXrayClientConfig(nodes), null, 2);
    case "surge":
      return buildSurgeConfig(nodes);
    case "loon":
      return buildLoonConfig(nodes);
    case "quantumultx":
    case "qx":
      return buildQXConfig(nodes);
    case "base64":
    case "b64sub":
      return buildBase64Sub(uris);
    case "raw":
    case "npvt":
    case "txt":
      return uris.join("\n");
    case "json":
    default:
      return JSON.stringify(nodes, null, 2);
  }
}
