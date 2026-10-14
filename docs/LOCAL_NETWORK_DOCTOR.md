# Local Network Doctor: HTTPS-through-client check

This is an **advanced, opt-in local diagnostic**, separate from the browser-only Network Doctor. It sends a small HTTPS request through an already running **local HTTP or SOCKS5 proxy client**, using only the Go standard library. It does not import or repair remote proxies, change device settings, disable TLS verification, or contact an HUNTX telemetry service.

## Three steps

1. Start your own proxy client (for example, Mihomo or sing-box) and select a candidate node in that client. Ensure the client exposes a local HTTP or SOCKS5 listener. This tool **does not** configure or authenticate your proxy client.
2. From a checkout of HUNTX, run one of the following commands, substituting your client's actual local listener port:

   `go run ./cmd/huntx-tools local-probe --proxy http://127.0.0.1:7890 --json`

   `go run ./cmd/huntx-tools local-probe --proxy socks5h://127.0.0.1:1080 --attempts 3 --timeout 8s --json`

3. Read the `client_path_usable` result. It is true only if **all** bounded attempts successfully complete a TLS-verified HTTPS request through the selected local listener. A failure is **inconclusive**: the client, target, network or remote node could be responsible. Compare with your client's own proxy-specific tests.

## Evidence boundaries

- The fixed HTTPS target is `https://www.gstatic.com/generate_204`. If it is unavailable or filtered on your network, this test can fail even when the proxy is functional.
- The tool checks the **local client path**, not the remote node's identity. A client might route through a fallback group or DIRECT; consequently `node_attributed` and `original_recovered` are **always false**. Do not promote this result to a globally healthy node.
- A successful TCP connection, DNS lookup, import, or catalog check is **not** used as the success condition. An HTTPS response with certificate verification is required.
- The probe transport is configured to use the local proxy and has **no direct fallback**. The proxy client itself must be configured by the user not to route the test directly.
- Only loopback proxy addresses (`127.0.0.0/8`, `::1`, or `localhost`) are accepted. `localhost` is pinned to `127.0.0.1` before dialing. Proxy credentials, query strings and paths are rejected.
- Attempts are sequential and limited to 1–3, with 1–15 seconds per attempt. No full proxy URI, password, SSID, IP address, browsing history or detailed network log is written to the JSON result or uploaded.
- The tool does not open a listening API or permit a web page to control a local client. Authenticated Mihomo/sing-box node attribution, reversible settings changes and automated recovery require a separately reviewed local pairing component.

## Test

`go test ./internal/localprobe ./cmd/huntx-tools`

The tests include a real local HTTP CONNECT tunnel to an HTTPS test server, a failed proxy with no direct fallback, a rejected untrusted TLS certificate, invalid loopback/credential inputs, and bounded privacy-safe summaries.
