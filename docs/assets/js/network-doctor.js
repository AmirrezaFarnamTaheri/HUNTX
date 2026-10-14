const HINTS={android:"Check VPN permission and stop conflicting VPN apps.",ios:"Check the active VPN configuration and possible VPN conflicts.",desktop:"Check system proxy/TUN routing and VPN conflicts."};const SYMPTOMS={subscription:"Subscription fails to import",timeout:"Proxy times out",no_traffic:"Connected, but websites do not load",tls:"TLS or certificate error",slow:"Proxy is slow or unstable",network_only:"Works on another network"};const action=(title,description)=>({title,description});export function createRecoveryPlan({platform,network,symptom}){if(!Object.hasOwn(HINTS,platform)||!["wifi","mobile"].includes(network)||!Object.hasOwn(SYMPTOMS,symptom))throw new TypeError("Unsupported selection");const compare=action("Compare on "+(network==="wifi"?"mobile data":"Wi-Fi"),"Test the same proxy through your client on the other network, if available.");const plans={subscription:[action("Refresh subscription","Update from the trusted HUNTX subscription."),action("Check import format","Use the format supported by your client."),action("Test through the client","Import success alone does not prove connectivity.")],timeout:[action("Refresh and retry","Update the subscription and retest the original node."),compare,action("Try another node","Test a published alternative end-to-end.")],no_traffic:[action("Check routing","Ensure the test browser actually uses the proxy."),action("Test HTTPS","Load a neutral HTTPS page through the proxy client."),compare],tls:[action("Restore trusted configuration","Refresh without modifying credentials or TLS identity."),action("Check device clock","Enable automatic date and time."),action("Report persistent TLS failure","Do not disable certificate verification.")],slow:[action("Test a small node sample","Use your client's real URL test with bounded concurrency."),action("Choose a stable node","Prefer repeated end-to-end success over one low latency result."),compare],network_only:[compare,action("Compare DNS and IPv4/IPv6","Use supported client settings temporarily and preserve TLS verification."),action("Choose a local fallback","Test a different published node on this network.")]};return{title:SYMPTOMS[symptom],deviceHint:HINTS[platform],actions:plans[symptom],safety:"Never disable TLS certificate verification or share proxy credentials."};}export function classifyManualOutcome({originalWorks="unknown",alternativeWorks="unknown",tlsVerificationDisabled=false}={}){if(!["yes","no","unknown"].includes(originalWorks)||!["yes","no","unknown"].includes(alternativeWorks)||typeof tlsVerificationDisabled!=="boolean")throw new TypeError("Invalid result");if(tlsVerificationDisabled)return{code:"unsafe",verified:false,message:"Restore TLS verification. This is not a safe recovery."};if(originalWorks==="yes")return{code:"reported-original",verified:false,message:"Original proxy appears restored (user-reported, not independently verified)."};if(alternativeWorks==="yes")return{code:"reported-alternative",verified:false,message:"A working replacement is reported; the original proxy is not confirmed recovered."};return{code:"unresolved",verified:false,message:"No recovery confirmed. Keep original settings or seek operator assistance."};}export function formatSupportSummary({platform,network,symptom,originalWorks="unknown",alternativeWorks="unknown",tlsVerificationDisabled=false}){const plan=createRecoveryPlan({platform,network,symptom});const result=classifyManualOutcome({originalWorks,alternativeWorks,tlsVerificationDisabled});return["HUNTX Network Doctor — manual report","Device: "+platform,"Network: "+network,"Problem: "+plan.title,"Outcome: "+result.code,"Evidence: self-reported; not independently verified","No credentials, endpoint addresses, or network identifiers included."].join("\n");}export function summarizeCatalog(catalog, { now = Date.now(), maxAgeMs = 48 * 60 * 60 * 1000 } = {}) {
  if (!catalog || typeof catalog !== "object" || !Array.isArray(catalog.files) ||
      typeof catalog.generated_at !== "string" || !catalog.generated_at.trim()) {
    throw new TypeError("Invalid catalog");
  }
  const generatedMs = Date.parse(catalog.generated_at);
  if (!Number.isFinite(generatedMs) || !Number.isFinite(now) ||
      !Number.isFinite(maxAgeMs) || maxAgeMs <= 0) {
    throw new TypeError("Invalid catalog timestamp or freshness window");
  }
  const listedSubscriptions = catalog.files.filter(
    (file) => file && Array.isArray(file.tags) && file.tags.includes("subscription")
  ).length;
  // Contradictory publication metadata is not evidence of an available feed.
  if (catalog.intentional_empty && listedSubscriptions) {
    throw new TypeError("Inconsistent intentionally empty catalog");
  }
  const ageMs = now - generatedMs;
  const freshness = ageMs < -5 * 60 * 1000 ? "clock-skew" :
    ageMs > maxAgeMs ? "stale" : "recent";
  const state = catalog.intentional_empty || !listedSubscriptions ? "empty" : "available";
  const availability = listedSubscriptions
    ? listedSubscriptions + " subscription format(s) listed."
    : "No published subscriptions listed.";
  const freshnessMessage = freshness === "stale"
    ? "Catalog snapshot may be stale; update your subscription and check the publication time."
    : freshness === "clock-skew"
      ? "Catalog timestamp is in the future; check the device clock and publication time."
      : "Catalog snapshot timestamp is recent.";
  return {
    state,
    freshness,
    subscriptionCount: listedSubscriptions,
    generatedAt: catalog.generated_at,
    message: availability + " " + freshnessMessage +
      " Catalog metadata does not verify proxy connectivity."
  };
}

export async function checkPublishedCatalog({ fetcher = fetch, now = Date.now(), timeoutMs = 8000 } = {}) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new TypeError("Invalid catalog timeout");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher("./catalog.json", {
      cache: "no-store",
      signal: controller.signal
    });
    if (!response?.ok) throw new Error("Catalog unavailable");
    return summarizeCatalog(await response.json(), { now });
  } catch {
    return {
      state: "unavailable",
      freshness: "unknown",
      subscriptionCount: 0,
      generatedAt: null,
      message: "Catalog unavailable; no proxy health conclusion can be made."
    };
  } finally {
    clearTimeout(timer);
  }
}
