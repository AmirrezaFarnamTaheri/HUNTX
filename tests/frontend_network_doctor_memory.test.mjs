import test from 'node:test';
import assert from 'node:assert/strict';
import {
  LOCAL_RECOVERY_STORAGE_KEY,
  rememberManualResult,
  recallManualResult,
  forgetManualResult
} from '../docs/assets/js/network-doctor-memory.js';

function fakeStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
    values
  };
}
const at = Date.parse('2026-10-14T10:00:00Z');
const base = { platform: 'android', network: 'wifi', symptom: 'timeout', outcomeCode: 'reported-original', tlsVerificationDisabled: false };

test('opt-in memory persists only a small allowlist, never proxy or network secrets', () => {
  const storage = fakeStorage();
  assert.equal(rememberManualResult(storage, {
    ...base, ssid: 'PrivateWiFi', uri: 'trojan://secret@host:443', ip: '10.0.0.3', token: 'private-key', verified: true
  }, { now: at }), true);
  const raw = storage.getItem(LOCAL_RECOVERY_STORAGE_KEY);
  assert.ok(raw);
  assert.doesNotMatch(raw, /PrivateWiFi|trojan|secret|10\.0\.0\.3|private-key|verified/);
  const parsed = JSON.parse(raw);
  assert.deepEqual(Object.keys(parsed).sort(), ['entries', 'version']);
  assert.deepEqual(Object.keys(parsed.entries[0]).sort(), ['network', 'outcomeCode', 'platform', 'savedAt', 'symptom']);
  const note = recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at });
  assert.equal(note.verified, false);
  assert.equal(note.outcomeCode, 'reported-original');
});

test('separate local records for Wi-Fi and mobile, no SSID detection', () => {
  const storage = fakeStorage();
  rememberManualResult(storage, base, { now: at });
  rememberManualResult(storage, { ...base, network: 'mobile', outcomeCode: 'reported-alternative' }, { now: at + 1 });
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at + 2 }).outcomeCode, 'reported-original');
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'mobile' }, { now: at + 2 }).outcomeCode, 'reported-alternative');
  assert.equal(recallManualResult(storage, { platform: 'ios', network: 'wifi' }, { now: at + 2 }), null);
});

test('unsafe, unresolved and invalid results never become remembered successes', () => {
  const storage = fakeStorage();
  assert.equal(rememberManualResult(storage, { ...base, tlsVerificationDisabled: true }, { now: at }), false);
  assert.equal(rememberManualResult(storage, { ...base, outcomeCode: 'unsafe' }, { now: at }), false);
  assert.equal(rememberManualResult(storage, { ...base, outcomeCode: 'unresolved' }, { now: at }), false);
  assert.equal(storage.getItem(LOCAL_RECOVERY_STORAGE_KEY), null);
  assert.throws(() => rememberManualResult(storage, { ...base, platform: '__proto__' }, { now: at }), TypeError);
  assert.throws(() => rememberManualResult(storage, { ...base, symptom: 'evil' }, { now: at }), TypeError);
});

test('old or future-dated notes are not shown as current evidence', () => {
  const storage = fakeStorage();
  rememberManualResult(storage, base, { now: at });
  assert.ok(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at + 29 * 86400000 }));
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at + 31 * 86400000 }), null);
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at - 10 * 60000 }), null);
});

test('corrupt, oversized or forged local storage cannot claim a verified recovery', () => {
  const storage = fakeStorage();
  storage.setItem(LOCAL_RECOVERY_STORAGE_KEY, '{bad-json');
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at }), null);
  storage.setItem(LOCAL_RECOVERY_STORAGE_KEY, 'x'.repeat(9000));
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at }), null);
  storage.setItem(LOCAL_RECOVERY_STORAGE_KEY, JSON.stringify({ version: 1, entries: [{ ...base, savedAt: at, outcomeCode: 'verified-original', verified: true }] }));
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at }), null);
});

test('forget only the selected network, leave the other profile alone', () => {
  const storage = fakeStorage();
  rememberManualResult(storage, base, { now: at });
  rememberManualResult(storage, { ...base, network: 'mobile' }, { now: at });
  assert.equal(forgetManualResult(storage, { platform: 'android', network: 'wifi' }), true);
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at }), null);
  assert.ok(recallManualResult(storage, { platform: 'android', network: 'mobile' }, { now: at }));
  assert.equal(forgetManualResult(storage, { platform: 'android', network: 'mobile' }), true);
  assert.equal(storage.getItem(LOCAL_RECOVERY_STORAGE_KEY), null);
});

test('private browsing and blocked storage do not break the recovery flow', () => {
  const blocked = { getItem() { throw new Error('disabled'); }, setItem() { throw new Error('disabled'); }, removeItem() { throw new Error('disabled'); } };
  assert.equal(rememberManualResult(blocked, base, { now: at }), false);
  assert.equal(recallManualResult(blocked, { platform: 'android', network: 'wifi' }, { now: at }), null);
  assert.equal(forgetManualResult(blocked, { platform: 'android', network: 'wifi' }), false);
});

test('expired notes are purged from device storage when revisited', () => {
  const storage = fakeStorage();
  rememberManualResult(storage, base, { now: at });
  assert.equal(recallManualResult(storage, { platform: 'android', network: 'wifi' }, { now: at + 31 * 86400000 }), null);
  assert.equal(storage.getItem(LOCAL_RECOVERY_STORAGE_KEY), null);
});
