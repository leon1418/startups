// Lambda@Edge viewer-request: Midway SSO gate for the kb-autoupdate operator console.
//
// Why self-vended: there is no maintained drop-in Midway interceptor for Lambda@Edge
// (@amzn/mote-interceptor and its CDK wrapper are deprecated); the recommended pattern is a
// small viewer-request function that validates the Midway id_token directly against Midway's
// JWKS, which is what this is. No dependencies — Node's crypto verifies RS256 and JWK import
// is native (crypto.createPublicKey({format:'jwk'})).
//
// Flow (implicit id_token, the same one Midway-gated CloudFront sites use):
//   1. valid console cookie                 -> pass through, x-forwarded-user set from `sub`
//   2. ?id_token=... in the query string    -> validate, set cookie, 302 to the clean path
//   3. otherwise                            -> 302 to midway-auth.amazon.com/SSO/redirect
//
// Security notes, each load-bearing:
//   * the JWT is verified: RS256 signature against https://midway-auth.amazon.com/jwks.json
//     (cached in module scope, refetched once on kid miss), iss, exp, and aud == this host.
//     Several internal examples skip verification — fine for read-only sites, not for a
//     console whose POST starts a paid build.
//   * inbound x-forwarded-user is ALWAYS dropped; only this function may set it. CloudFront
//     does not strip it for us.
//   * `state` (the post-login return path) must decode to a path starting with "/" — anything
//     else is an open-redirect attempt and collapses to "/".
//   * authorization is a DynamoDB-backed allowlist (config:operators in the pipeline's state
//     table), so adding or removing an operator is a config edit, never a redeploy —
//     Lambda@Edge has no environment variables, so the table/region are baked in.

import { createPublicKey, verify as cryptoVerify, randomBytes } from "crypto";
import { DynamoDBClient, GetItemCommand } from "@aws-sdk/client-dynamodb";

const JWKS_URL = "https://midway-auth.amazon.com/jwks.json";
const ISSUER = "https://midway-auth.amazon.com";
const COOKIE = "kbc_auth";
const MAX_AGE = 43200; // 12h, capped by token exp below
const STATE_TABLE = "kb-autoupdate-state";
const STATE_REGION = "us-east-1";

let jwksCache = { keys: null, at: 0 };
let opsCache = { aliases: null, at: 0 };
const ddb = new DynamoDBClient({ region: STATE_REGION });

async function allowedAliases() {
  const now = Date.now();
  if (opsCache.aliases && now - opsCache.at < 60_000) return opsCache.aliases;
  try {
    const r = await ddb.send(new GetItemCommand({
      TableName: STATE_TABLE,
      Key: { pk: { S: "config:operators" } },
    }));
    const aliases = JSON.parse(r.Item.value.S).aliases;
    opsCache = { aliases, at: now };
    return aliases;
  } catch (e) {
    // Serve stale rather than lock everyone out on a transient DynamoDB blip; with no cache
    // at all, fail CLOSED (null -> caller denies).
    return opsCache.aliases || null;
  }
}

async function getJwks(force) {
  const now = Date.now();
  if (!force && jwksCache.keys && now - jwksCache.at < 3600_000) return jwksCache.keys;
  const r = await fetch(JWKS_URL);
  if (!r.ok) throw new Error(`jwks ${r.status}`);
  jwksCache = { keys: (await r.json()).keys, at: now };
  return jwksCache.keys;
}

function b64urlJson(s) {
  return JSON.parse(Buffer.from(s, "base64url").toString());
}

async function verifyToken(token, host) {
  const [h, p, sig] = token.split(".");
  if (!h || !p || !sig) return null;
  const header = b64urlJson(h);
  if (header.alg !== "RS256") return null; // no algorithm confusion
  let keys = await getJwks(false);
  let jwk = keys.find((k) => k.kid === header.kid);
  if (!jwk) {
    keys = await getJwks(true); // one refetch on kid miss (key rotation)
    jwk = keys.find((k) => k.kid === header.kid);
    if (!jwk) return null;
  }
  const key = createPublicKey({ key: jwk, format: "jwk" });
  const ok = cryptoVerify("RSA-SHA256", Buffer.from(`${h}.${p}`), key, Buffer.from(sig, "base64url"));
  if (!ok) return null;
  const c = b64urlJson(p);
  const aud = Array.isArray(c.aud) ? c.aud : [c.aud];
  const me = [`https://${host}:443`, `https://${host}`, host];
  if (c.iss !== ISSUER) return null;
  if (!c.exp || c.exp <= Date.now() / 1000) return null;
  if (!aud.some((a) => me.includes(a))) return null;
  if (!c.sub) return null;
  return c;
}

function denied(alias) {
  const body = `<html><body style="font-family:sans-serif;margin:3em"><h2>Not on the operator list</h2>
<p>You authenticated as <b>${alias}</b>, but this console is limited to the aws-cask team and
named operators. Ask <b>genli</b> to add you (a config edit, takes a minute).</p></body></html>`;
  return {
    status: "403",
    statusDescription: "Forbidden",
    headers: { "content-type": [{ key: "Content-Type", value: "text/html" }],
               "cache-control": [{ key: "Cache-Control", value: "no-store" }] },
    body,
  };
}

function getCookie(headers, name) {
  for (const c of headers.cookie || []) {
    for (const part of c.value.split(";")) {
      const [k, ...v] = part.trim().split("=");
      if (k === name) return v.join("=");
    }
  }
  return null;
}

function redirectToMidway(host, path) {
  const cid = encodeURIComponent(`https://${host}:443`);
  const nonce = randomBytes(16).toString("hex");
  const state = Buffer.from(path).toString("base64url");
  const loc =
    `https://midway-auth.amazon.com/SSO/redirect?client_id=${cid}&redirect_uri=${cid}` +
    `&response_type=id_token&scope=openid&nonce=${nonce}&state=${state}`;
  return {
    status: "302",
    statusDescription: "Found",
    headers: {
      location: [{ key: "Location", value: loc }],
      "cache-control": [{ key: "Cache-Control", value: "no-store" }],
    },
  };
}

export const handler = async (event) => {
  const req = event.Records[0].cf.request;
  const headers = req.headers;
  const host = headers.host[0].value;
  delete headers["x-forwarded-user"]; // only we may assert identity downstream

  // 2) Midway callback: token arrives in the query string
  const qs = new URLSearchParams(req.querystring || "");
  const idToken = qs.get("id_token");
  if (idToken) {
    let claims = null;
    try {
      claims = await verifyToken(idToken, host);
    } catch (e) {
      return { status: "503", statusDescription: "Service Unavailable", body: "auth backend unreachable, retry" };
    }
    if (!claims) return { status: "403", statusDescription: "Forbidden", body: "Access denied." };
    const ops = await allowedAliases();
    if (!ops || !ops.includes(claims.sub)) return denied(claims.sub);
    let path = "/";
    const state = qs.get("state");
    if (state) {
      try {
        const d = Buffer.from(state, "base64url").toString();
        if (d.startsWith("/")) path = d;
      } catch {}
    }
    const age = Math.min(MAX_AGE, Math.max(60, Math.floor(claims.exp - Date.now() / 1000)));
    return {
      status: "302",
      statusDescription: "Found",
      headers: {
        location: [{ key: "Location", value: `https://${host}${path}` }],
        "set-cookie": [{ key: "Set-Cookie", value: `${COOKIE}=${idToken}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=${age}` }],
        "cache-control": [{ key: "Cache-Control", value: "no-store" }],
      },
    };
  }

  // 1) Existing session cookie
  const cookie = getCookie(headers, COOKIE);
  if (cookie) {
    let claims = null;
    try {
      claims = await verifyToken(cookie, host);
    } catch (e) {
      return { status: "503", statusDescription: "Service Unavailable", body: "auth backend unreachable, retry" };
    }
    if (claims) {
      const ops = await allowedAliases();
      if (!ops || !ops.includes(claims.sub)) return denied(claims.sub);
      headers["x-forwarded-user"] = [{ key: "X-Forwarded-User", value: claims.sub }];
      return req;
    }
    // fall through: expired/invalid cookie -> fresh login
  }

  // 3) No session: to Midway
  const path = req.uri + (req.querystring ? `?${req.querystring}` : "");
  return redirectToMidway(host, path);
};
