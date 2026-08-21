// HUNTX Client-Side Proxy Protocol Decoder & Parser
// Hardened, IPv6-compliant, malformed URI resilient, and fully zero-dependency.

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
    if (typeof atob !== "undefined") {
      return atob(clean);
    }
    if (typeof Buffer !== "undefined") {
      return Buffer.from(clean, "base64").toString("utf-8");
    }
    return "";
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
      encryption: params.get("encryption") || "none",
      security: params.get("security") || "none",
      transport: params.get("type") || "tcp",
      headerType: params.get("headerType") || "none",
      host: params.get("host") || "",
      path: safeDecodeURI(params.get("path")),
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
      path: safeDecodeURI(params.get("path")),
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
        const [m, p] = decodedAuth.split(":");
        method = m || "unknown";
        password = p || "";
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
        const [m, p] = (auth || "").split(":");
        method = m || "unknown";
        password = p || "";
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


let wasmWorkerInstance = null;
let messageIdCounter = 0;
const pendingWorkerRequests = new Map();

export function getWasmWorker() {
  if (typeof Worker === "undefined") return null;
  if (!wasmWorkerInstance) {
    try {
      wasmWorkerInstance = new Worker(new URL("./wasm-worker.js", import.meta.url));
      wasmWorkerInstance.onmessage = function (e) {
        const { id, type, data, error } = e.data || {};
        if (pendingWorkerRequests.has(id)) {
          const { resolve, reject } = pendingWorkerRequests.get(id);
          pendingWorkerRequests.delete(id);
          if (error) {
            reject(new Error(error));
          } else {
            resolve(data);
          }
        }
      };
    } catch (err) {
      console.warn("Could not initialize Wasm Web Worker, falling back to main-thread JS:", err);
    }
  }
  return wasmWorkerInstance;
}

export async function decodeSubscriptionAsync(rawPayload) {
  const worker = getWasmWorker();
  if (!worker) {
    return decodeProxyURI(rawPayload);
  }
  const id = ++messageIdCounter;
  return new Promise((resolve, reject) => {
    pendingWorkerRequests.set(id, { resolve, reject });
    worker.postMessage({ action: "DECODE_SUBSCRIPTION", payload: rawPayload, id });
  });
}
