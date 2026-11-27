// The access gate for a private family site. Written into the built site as _worker.js by the family site engine
// (build/access.py); do not edit the copy. It runs on Cloudflare Pages (advanced mode): every request to the site
// comes here first, and nothing is served from the site's files unless the request carries a valid cookie.
//
//   SITE_PASSWORD   the family password. A Cloudflare secret, set by the deploy workflow from a GitHub secret.
//                   It is never in this file, in the site's files or in the repository.
//
// Visitors who have not entered the password get the entrance page (status 401) or a bare 401, never a file.
// A visitor who enters the password gets a cookie that no script can read (HttpOnly), signed with a key made from
// the password. Change the password and every cookie made with the old one stops working at once.
/*__CONFIG__*/

const COOKIE = '__Host-fs_access';
const enc = new TextEncoder();

function b64url(bytes) {
  let s = '';
  new Uint8Array(bytes).forEach((b) => { s += String.fromCharCode(b); });
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function unb64url(s) {
  const t = String(s).replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(t + '='.repeat((4 - (t.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function hmac(keyBytes, data) {
  const key = await crypto.subtle.importKey('raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(data)));
}

// the signing key is made from the password, so a new password makes every old cookie invalid
let keyCache = { password: null, key: null };
async function signingKey(password) {
  if (keyCache.password === password && keyCache.key) return keyCache.key;
  const raw = await hmac(enc.encode(password), 'family-site-gate/v1/cookie');
  const key = await crypto.subtle.importKey('raw', raw, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);
  keyCache = { password, key };
  return key;
}

// compares two strings in time that does not depend on where they differ
async function sameString(a, b) {
  const k = enc.encode('family-site-gate/v1/compare');
  const x = await hmac(k, a);
  const y = await hmac(k, b);
  let d = 0;
  for (let i = 0; i < x.length; i++) d |= x[i] ^ y[i];
  return d === 0;
}

async function makeToken(password, nowMs) {
  const payload = 'v1.' + (Math.floor(nowMs / 1000) + CONFIG.days * 86400);
  const sig = new Uint8Array(await crypto.subtle.sign('HMAC', await signingKey(password), enc.encode(payload)));
  return payload + '.' + b64url(sig);
}

async function tokenIsGood(token, password, nowMs) {
  const parts = String(token || '').split('.');
  if (parts.length !== 3 || parts[0] !== 'v1' || !/^\d{1,12}$/.test(parts[1])) return false;
  if (Number(parts[1]) * 1000 <= nowMs) return false;
  let sig;
  try { sig = unb64url(parts[2]); } catch (e) { return false; }
  return crypto.subtle.verify('HMAC', await signingKey(password), sig, enc.encode(parts[0] + '.' + parts[1]));
}

function cookieValue(request) {
  const header = request.headers.get('Cookie') || '';
  for (const part of header.split(';')) {
    const i = part.indexOf('=');
    if (i > 0 && part.slice(0, i).trim() === COOKIE) return part.slice(i + 1).trim();
  }
  return '';
}

function cookieHeader(value, maxAge) {
  return COOKIE + '=' + value + '; Path=/; Max-Age=' + maxAge + '; Secure; HttpOnly; SameSite=Lax';
}

function baseHeaders(extra) {
  const h = new Headers(extra || {});
  h.set('X-Robots-Tag', 'noindex, nofollow, noarchive');
  h.set('X-Content-Type-Options', 'nosniff');
  h.set('Referrer-Policy', 'same-origin');
  return h;
}

function plain(status, text) {
  return new Response(text, { status, headers: baseHeaders({ 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' }) });
}

function json(status, body, extra) {
  const h = baseHeaders(Object.assign({ 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }, extra || {}));
  return new Response(JSON.stringify(body), { status, headers: h });
}

function wantsPage(request) {
  if (request.method !== 'GET') return false;
  const dest = request.headers.get('Sec-Fetch-Dest');
  if (dest) return dest === 'document' || dest === 'iframe';
  return (request.headers.get('Accept') || '').includes('text/html');
}

function entrance() {
  return new Response(GATE_HTML, {
    status: 401,
    headers: baseHeaders({
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'Content-Security-Policy': GATE_CSP,
      'X-Family-Gate': '1',
      'Vary': 'Cookie',
    }),
  });
}

function denied(request) {
  if (wantsPage(request)) return entrance();
  const r = plain(401, 'This family archive is private.');
  r.headers.set('X-Family-Gate', '1');
  r.headers.set('Vary', 'Cookie');
  return r;
}

async function login(request, env) {
  if (request.method !== 'POST') return plain(405, 'Method not allowed');
  const origin = request.headers.get('Origin');
  if (origin && origin !== new URL(request.url).origin) return plain(403, 'Not allowed');
  let body = null;
  try { body = await request.json(); } catch (e) { return json(400, { ok: false }); }
  const given = typeof (body && body.password) === 'string' ? body.password.slice(0, 256).trim() : '';
  const good = await sameString(given, String(env.SITE_PASSWORD).trim());
  if (!good) {
    await new Promise((r) => setTimeout(r, CONFIG.failDelayMs));
    return json(401, { ok: false });
  }
  const token = await makeToken(String(env.SITE_PASSWORD).trim(), Date.now());
  return json(200, { ok: true }, { 'Set-Cookie': cookieHeader(token, CONFIG.days * 86400) });
}

function logout(request) {
  if (request.method !== 'POST') return plain(405, 'Method not allowed');
  const origin = request.headers.get('Origin');
  if (origin && origin !== new URL(request.url).origin) return plain(403, 'Not allowed');
  return json(200, { ok: true }, { 'Set-Cookie': cookieHeader('', 0) });
}

export default {
  async fetch(request, env) {
    // not set up: refuse everything rather than serve the site open
    if (!env || !env.SITE_PASSWORD || !String(env.SITE_PASSWORD).trim()) return plain(503, 'This site is not set up yet.');
    const path = new URL(request.url).pathname;
    if (path === '/__gate/login') return login(request, env);
    if (path === '/__gate/logout') return logout(request);
    if (request.method !== 'GET' && request.method !== 'HEAD') return plain(405, 'Method not allowed');

    // the few files anyone may fetch: robots.txt, and the entrance picture if the site approved one
    if (CONFIG.open.indexOf(path) >= 0) {
      const r = await env.ASSETS.fetch(request);
      const h = baseHeaders(r.headers);
      return new Response(r.body, { status: r.status, statusText: r.statusText, headers: h });
    }

    const password = String(env.SITE_PASSWORD).trim();
    if (!(await tokenIsGood(cookieValue(request), password, Date.now()))) return denied(request);

    const r = await env.ASSETS.fetch(request);
    const h = baseHeaders(r.headers);
    h.set('Cache-Control', 'private, no-cache');
    h.set('Vary', 'Cookie');
    return new Response(r.body, { status: r.status, statusText: r.statusText, headers: h });
  },
};
