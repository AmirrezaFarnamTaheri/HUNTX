/**
 * Optional, device-local manual recovery notes.
 * Never store endpoints, credentials, SSIDs, IPs, or browsing destinations.
 * These notes are self-reported and must never be treated as health evidence.
 */
export const LOCAL_RECOVERY_STORAGE_KEY = 'huntx.network-doctor.manual-notes.v1';
const VERSION = 1;
const MAX_BYTES = 8192;
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;
const CLOCK_SKEW_MS = 5 * 60 * 1000;
const PLATFORMS = new Set(['android', 'ios', 'desktop']);
const NETWORKS = new Set(['wifi', 'mobile']);
const SYMPTOMS = new Set(['subscription', 'timeout', 'no_traffic', 'tls', 'slow', 'network_only']);
const OUTCOMES = new Set(['reported-original', 'reported-alternative']);

function validateScope({ platform, network } = {}) {
  if (!PLATFORMS.has(platform) || !NETWORKS.has(network)) {
    throw new TypeError('Unsupported device or network category');
  }
}

function validEntry(entry) {
  return entry && typeof entry === 'object' &&
    PLATFORMS.has(entry.platform) && NETWORKS.has(entry.network) &&
    SYMPTOMS.has(entry.symptom) && OUTCOMES.has(entry.outcomeCode) &&
    Number.isSafeInteger(entry.savedAt) && entry.savedAt >= 0;
}

function readEntries(storage) {
  try {
    const raw = storage?.getItem(LOCAL_RECOVERY_STORAGE_KEY);
    if (typeof raw !== 'string' || raw.length > MAX_BYTES) return [];
    const doc = JSON.parse(raw);
    if (doc?.version !== VERSION || !Array.isArray(doc.entries)) return [];
    // Rebuild each record from allowlisted fields, even when storage was tampered with.
    return doc.entries.filter(validEntry).slice(0, 6).map((entry) => ({
      platform: entry.platform,
      network: entry.network,
      symptom: entry.symptom,
      outcomeCode: entry.outcomeCode,
      savedAt: entry.savedAt
    }));
  } catch {
    return [];
  }
}

function validNow(now) {
  if (!Number.isSafeInteger(now) || now < 0) throw new TypeError('Invalid timestamp');
}

/** Save only after an explicit user click; a successful note is NOT verified. */
export function rememberManualResult(storage, result, { now = Date.now() } = {}) {
  validateScope(result);
  validNow(now);
  if (!SYMPTOMS.has(result.symptom)) throw new TypeError('Unsupported symptom');
  if (result.tlsVerificationDisabled !== false || !OUTCOMES.has(result.outcomeCode)) return false;
  const entries = readEntries(storage).filter((entry) =>
    !(entry.platform === result.platform && entry.network === result.network)
  );
  entries.unshift({
    platform: result.platform,
    network: result.network,
    symptom: result.symptom,
    outcomeCode: result.outcomeCode,
    savedAt: now
  });
  try {
    storage?.setItem(LOCAL_RECOVERY_STORAGE_KEY, JSON.stringify({ version: VERSION, entries: entries.slice(0, 6) }));
    return typeof storage?.setItem === 'function';
  } catch {
    return false;
  }
}

/** Recall an explicitly selected Wi-Fi/mobile category; never detect the SSID. */
export function recallManualResult(storage, scope, { now = Date.now() } = {}) {
  validateScope(scope);
  validNow(now);
  const entries = readEntries(storage);
  const fresh = entries.filter((entry) =>
    entry.savedAt <= now + CLOCK_SKEW_MS && now - entry.savedAt <= MAX_AGE_MS
  );
  // Expiry is enforced when the user next opens the page; no background tracking.
  if (fresh.length !== entries.length) {
    try {
      if (fresh.length) {
        storage?.setItem(LOCAL_RECOVERY_STORAGE_KEY, JSON.stringify({ version: VERSION, entries: fresh }));
      } else {
        storage?.removeItem(LOCAL_RECOVERY_STORAGE_KEY);
      }
    } catch { /* storage may be disabled; still do not surface expired notes */ }
  }
  const entry = fresh.find((item) =>
    item.platform === scope.platform && item.network === scope.network
  );
  return entry ? { ...entry, verified: false, evidence: 'self-reported' } : null;
}

/** Remove only the selected local category; no network identifiers are used. */
export function forgetManualResult(storage, scope) {
  validateScope(scope);
  const entries = readEntries(storage);
  const remaining = entries.filter((entry) =>
    !(entry.platform === scope.platform && entry.network === scope.network)
  );
  if (remaining.length === entries.length) return false;
  try {
    if (remaining.length) {
      storage?.setItem(LOCAL_RECOVERY_STORAGE_KEY, JSON.stringify({ version: VERSION, entries: remaining }));
    } else {
      storage?.removeItem(LOCAL_RECOVERY_STORAGE_KEY);
    }
    return true;
  } catch {
    return false;
  }
}
