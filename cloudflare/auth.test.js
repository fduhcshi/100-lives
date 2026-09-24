import assert from "node:assert/strict";
import { test } from "node:test";
import { authorize } from "./auth.js";

const hash = "a".repeat(64);

test("missing secret fails closed", async () => {
  const response = await authorize(new Request("https://example.com/"), undefined);
  assert.equal(response.status, 503);
});

test("all routes require the browser password challenge", async () => {
  for (const path of ["/", "/static/style.css", "/api/simulate"]) {
    const response = await authorize(new Request(`https://example.com${path}`), hash);
    assert.equal(response.status, 401);
    assert.match(response.headers.get("www-authenticate"), /^Basic /);
  }
});

test("valid password is accepted and wrong username is rejected", async () => {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("correct horse"));
  const validHash = Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, "0")).join("");
  const valid = new Request("https://example.com/", { headers: { authorization: `Basic ${btoa("visitor:correct horse")}` } });
  const wrong = new Request("https://example.com/", { headers: { authorization: `Basic ${btoa("someone:correct horse")}` } });
  assert.equal(await authorize(valid, validHash), null);
  assert.equal((await authorize(wrong, validHash)).status, 401);
});
