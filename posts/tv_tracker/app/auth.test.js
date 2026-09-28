import { test } from "node:test";
import assert from "node:assert/strict";
import { Auth } from "./auth.js";

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => map.set(k, v), removeItem: (k) => map.delete(k), map };
}

const opts = (storage, t = 1_000_000) => ({ clientId: "CID", scope: "S", storage, now: () => t });

function fakeGoogle(response) {
  const seen = {};
  globalThis.google = {
    accounts: {
      oauth2: {
        initTokenClient: (config) => {
          seen.config = config;
          return { requestAccessToken: (args) => { seen.args = args; config.callback(response); } };
        },
      },
    },
  };
  return seen;
}

test("restores an unexpired saved token and ignores an expired one", () => {
  const fresh = memoryStorage({ "tv-tracker-token": JSON.stringify({ token: "saved", expiresAt: 2_000_000 }) });
  assert.equal(new Auth(opts(fresh)).token, "saved");
  assert.ok(new Auth(opts(fresh)).valid());
  const stale = memoryStorage({ "tv-tracker-token": JSON.stringify({ token: "old", expiresAt: 500 }) });
  assert.equal(new Auth(opts(stale)).token, null);
});

test("valid is false within a minute of expiry", () => {
  const storage = memoryStorage({ "tv-tracker-token": JSON.stringify({ token: "t", expiresAt: 1_030_000 }) });
  assert.ok(!new Auth(opts(storage)).valid());
});

test("connect stores the token from Google", async () => {
  const seen = fakeGoogle({ access_token: "new", expires_in: 3599 });
  const storage = memoryStorage();
  const auth = new Auth(opts(storage));
  await auth.connect();
  assert.equal(seen.config.client_id, "CID");
  assert.equal(seen.config.scope, "S");
  assert.equal(auth.token, "new");
  assert.ok(auth.valid());
  assert.deepEqual(JSON.parse(storage.map.get("tv-tracker-token")), { token: "new", expiresAt: 1_000_000 + 3_599_000 });
});

test("connect rejects on a Google error and expire clears", async () => {
  fakeGoogle({ error: "access_denied" });
  const storage = memoryStorage({ "tv-tracker-token": JSON.stringify({ token: "t", expiresAt: 2_000_000 }) });
  const auth = new Auth(opts(storage));
  await assert.rejects(auth.connect(), /access_denied/);
  auth.expire();
  assert.equal(auth.token, null);
  assert.ok(!storage.map.has("tv-tracker-token"));
});

test("works without storage", () => {
  const auth = new Auth(opts(null));
  assert.equal(auth.token, null);
  auth.expire();
});
