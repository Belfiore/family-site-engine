/* Checks for the private access gate: the real _worker.js the build writes, run in Node behind a stand-in for
 * Cloudflare Pages (tests/gate-server.js). No browser needed.
 *
 *   node tests/check-gate.js                  builds a made-up protected site (tests/access_fixtures.py), then checks it
 *   DIST=path PASSWORD=x node tests/check-gate.js   checks a protected build that is already made
 *
 * The points: nothing is served without the cookie (pages, data, pictures, scripts, Stuart's index), however the
 * address is written; a wrong password gets nothing and is slowed; the right one gets a cookie no script can read;
 * a new password cancels every old cookie; an expired or altered cookie is refused; with no password set the gate
 * refuses everything; the password is not in any file of the build.
 */
const fs = require('fs'), path = require('path'), os = require('os'), cp = require('child_process');
const { startGate } = require('./gate-server');
const ROOT = path.dirname(__dirname);

let failures = 0;
const ok = m => console.log('  ok   ' + m);
const fail = m => { failures++; console.log('  FAIL ' + m); };
const check = (c, m, detail) => c ? ok(m) : fail(m + (detail !== undefined ? ': ' + detail : ''));
const section = t => console.log('\n' + t);

let DIST = process.env.DIST, PASSWORD = process.env.PASSWORD || 'correct horse battery staple';
if (!DIST) {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-gate-'));
    cp.execFileSync('python3', [path.join(ROOT, 'tests', 'access_fixtures.py'), path.join(tmp, 'site')], { stdio: 'pipe' });
    DIST = path.join(tmp, '_site');
    cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', path.join(tmp, 'site'), '--out', DIST], { stdio: 'pipe' });
}
DIST = path.resolve(DIST);
const BUILD = JSON.parse(fs.readFileSync(path.join(DIST, 'engine-build.json')));

const PAGE = { headers: { Accept: 'text/html', 'Sec-Fetch-Dest': 'document' } };
const login = (g, password, extra) => fetch(g.url + '/__gate/login', Object.assign({ method: 'POST', body: JSON.stringify({ password }), headers: { 'content-type': 'application/json' } }, extra || {}));
const cookieOf = r => (r.headers.getSetCookie()[0] || '').split(';')[0];
const walk = d => fs.readdirSync(d, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);

(async () => {
    const g = await startGate({ dir: DIST, password: PASSWORD });

    section('The build');
    check(fs.existsSync(path.join(DIST, '_worker.js')), '_worker.js is in the build');
    check(BUILD.access && BUILD.access.project, 'engine-build.json says the site is protected', JSON.stringify(BUILD.access));
    const robots = fs.readFileSync(path.join(DIST, 'robots.txt'), 'utf8');
    check(/Disallow: \//.test(robots), 'robots.txt blocks every crawler');
    const leaks = walk(DIST).filter(f => fs.readFileSync(f).includes(PASSWORD));
    check(!leaks.length, 'the password is in no file of the build', leaks.join(', '));
    const worker = fs.readFileSync(path.join(DIST, '_worker.js'), 'utf8');
    check(!/SITE_PASSWORD\s*=\s*['"]/.test(worker) && !worker.includes(PASSWORD), 'the worker reads the password from the environment, never from its own text');
    const gateHtml = (worker.match(/const GATE_HTML = (".*");/) || [])[1];
    check(gateHtml && !gateHtml.includes('Hartley &amp; Moreau<\\/a>') && gateHtml.includes('Hartley'), 'the entrance page names the site and carries none of its content');

    section('Without the password nothing is served');
    const secret = ['Arthur Hartley', 'Kate Hartley', 'Daniel Hartley', 'Zoë'];
    const PATHS = ['/', '/index.html', '/family-tree.html', '/map.html', '/ask.html', '/moreau.html', '/data/people.json', '/data/sources.json', '/data/places.json',
        '/images/people/arthur-hartley.png', '/images/people/zoe-hartley.png', '/site-config.js', '/site-theme.css', '/styles.css', '/engine-build.json',
        '/engine/' + BUILD.engine + '/tree-canvas.js', '/engine/' + BUILD.engine + '/visitor.js', '/archive/manifest.json', '/_worker.js', '/_routes.json'];
    for (const p of PATHS) {
        const asPage = await fetch(g.url + p, PAGE), asFile = await fetch(g.url + p);
        const t1 = await asPage.text(), t2 = await asFile.text();
        check(asPage.status === 401 && asFile.status === 401 && !secret.some(s => t1.includes(s) || t2.includes(s)), 'GET ' + p + ' is refused (401) and shows no family', asPage.status + '/' + asFile.status);
        if (p === '/') check(asPage.headers.get('referrer-policy') === 'same-origin', 'the entrance does not pass the private address on to a font host or any other site');
    }
    const TRICKS = ['/data/people.json/', '/DATA/people.json', '/data//people.json', '//data/people.json', '/data/./people.json', '/data/../data/people.json', '/%2e%2e/data/people.json',
        '/data%2Fpeople.json', '/data/people.json%00', '/data/people.json?x=1', '/data/people.json#x', '/.%2e/site.config.json', '/site.config.json', '/%5cdata/people.json', '/data/people.json;a=b', '/index.html/', '/images/../data/people.json'];
    for (const p of TRICKS) {
        const r = await fetch(g.url + p), t = await r.text();
        check(r.status !== 200 && !secret.some(s => t.includes(s)), 'GET ' + p + ' gives no data', r.status);
    }
    for (const method of ['HEAD', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS']) {
        const r = await fetch(g.url + '/data/people.json', { method, body: ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) ? '{}' : undefined });
        check(r.status !== 200, method + ' /data/people.json gives no data', r.status);
    }
    {
        const r = await fetch(g.url + '/', PAGE), h = r.headers;
        check(h.get('x-robots-tag') === 'noindex, nofollow, noarchive', 'the entrance is marked noindex');
        check(/default-src 'none'/.test(h.get('content-security-policy') || '') && /script-src 'sha256-/.test(h.get('content-security-policy') || ''), 'the entrance has a strict content security policy', h.get('content-security-policy'));
        check(h.get('cache-control') === 'no-store', 'the entrance is not cached');
        const t = await r.text();
        check(/<form/.test(t) && /type="password"/.test(t) && /autocomplete="current-password"/.test(t), 'the entrance has a password field');
        check(!/<img/.test(t), 'the entrance has no picture unless the site approved one');
    }
    {
        const r = await fetch(g.url + '/robots.txt');
        check(r.status === 200 && (await r.text()).includes('Disallow: /'), 'robots.txt is the one file anyone can fetch');
    }

    section('The password');
    {
        const t0 = Date.now();
        const r = await login(g, 'not the password');
        check(r.status === 401 && !r.headers.getSetCookie().length && (await r.json()).ok === false, 'a wrong password gets 401 and no cookie');
        check(Date.now() - t0 >= 600, 'a wrong password is slowed down', (Date.now() - t0) + ' ms');
        for (const bad of ['', ' ', PASSWORD.slice(0, -1), PASSWORD + 'x', PASSWORD.toUpperCase(), 'x'.repeat(5000)]) {
            const rr = await login(g, bad);
            check(rr.status === 401 && !rr.headers.getSetCookie().length, 'refused: ' + JSON.stringify(bad.slice(0, 20)));
        }
        check((await login(g, null)).status === 401, 'a missing password is refused');
        check((await fetch(g.url + '/__gate/login', { method: 'POST', body: 'not json' })).status === 400, 'a body that is not JSON is refused');
        check((await fetch(g.url + '/__gate/login')).status === 405, 'logging in by GET is refused');
        check((await login(g, PASSWORD, { headers: { 'content-type': 'application/json', Origin: 'https://elsewhere.example' } })).status === 403, 'a login from another site is refused');
    }
    let cookie;
    {
        const r = await login(g, PASSWORD);
        const raw = r.headers.getSetCookie()[0] || '';
        cookie = cookieOf(r);
        check(r.status === 200, 'the right password is accepted');
        check(/^__Host-fs_access=/.test(raw) && /HttpOnly/i.test(raw) && /Secure/i.test(raw) && /SameSite=Lax/i.test(raw) && /Path=\//.test(raw) && !/Domain=/i.test(raw), 'the cookie is __Host-, HttpOnly, Secure, SameSite and has no Domain', raw);
        check(/Max-Age=7776000/.test(raw), 'the cookie lasts the configured 90 days');
        check(!raw.includes(PASSWORD) && !Buffer.from(cookie.split('=')[1].split('.')[2] || '', 'base64').toString('latin1').includes(PASSWORD), 'the cookie does not contain the password');
        check(!(await r.text()).includes(PASSWORD), 'the reply does not contain the password');
    }

    section('With the cookie');
    const withCookie = (p, init) => fetch(g.url + p, Object.assign({}, init, { headers: Object.assign({ cookie }, (init || {}).headers) }));
    for (const [p, want] of [['/', 'Hartley'], ['/family-tree.html', 'tc-'], ['/data/people.json', 'arthur-hartley'], ['/site-config.js', 'FamilySite']]) {
        const r = await withCookie(p, PAGE), t = await r.text();
        check(r.status === 200 && t.includes(want), 'GET ' + p + ' is served', r.status);
        check(r.headers.get('cache-control') === 'private, no-cache' && /Cookie/.test(r.headers.get('vary') || ''), p + ' is marked private and varies by cookie');
        check(r.headers.get('x-robots-tag') === 'noindex, nofollow, noarchive', p + ' is marked noindex');
        check(r.headers.get('referrer-policy') === 'same-origin', p + ' does not pass the private address on to other sites (Referrer-Policy)');
    }
    {
        const img = await withCookie('/images/people/arthur-hartley.png');
        check(img.status === 200 && /image\/png/.test(img.headers.get('content-type')), 'a picture is served');
        const w = await withCookie('/_worker.js');
        check(w.status === 404, 'the worker itself is never served, even with the cookie', w.status);
    }

    section('A cookie that is not good');
    {
        const [name, value] = cookie.split('=');
        const parts = value.split('.');
        const tampered = [
            name + '=' + parts[0] + '.' + parts[1] + '.' + parts[2].slice(0, -2) + (parts[2].endsWith('AA') ? 'BB' : 'AA'),
            name + '=' + parts[0] + '.' + (Number(parts[1]) + 86400 * 365) + '.' + parts[2],
            name + '=' + parts[0] + '.' + parts[1],
            name + '=' + parts[0] + '.' + parts[1] + '.',
            name + '=garbage', name + '=', 'other=' + value, name + 'x=' + value,
            name + '=v2.' + parts[1] + '.' + parts[2],
        ];
        for (const c of tampered) {
            const r = await fetch(g.url + '/data/people.json', { headers: { cookie: c } });
            check(r.status === 401, 'refused: ' + c.slice(0, 50) + (c.length > 50 ? '...' : ''), r.status);
        }
        const realNow = Date.now;
        Date.now = () => realNow() + 91 * 86400 * 1000;
        const late = await fetch(g.url + '/data/people.json', { headers: { cookie } });
        Date.now = realNow;
        check(late.status === 401, 'a cookie older than its 90 days is refused', late.status);
        check((await fetch(g.url + '/data/people.json', { headers: { cookie } })).status === 200, 'and the same cookie works before then');
    }

    section('Changing the password');
    {
        const g2 = await startGate({ dir: DIST, password: PASSWORD + ' (new)' });
        const r = await fetch(g2.url + '/data/people.json', { headers: { cookie } });
        check(r.status === 401, 'a cookie made with the old password is refused once the password changes', r.status);
        check((await login(g2, PASSWORD)).status === 401, 'the old password no longer works');
        const n = await login(g2, PASSWORD + ' (new)');
        check(n.status === 200 && (await fetch(g2.url + '/data/people.json', { headers: { cookie: cookieOf(n) } })).status === 200, 'the new password works and gets in');
        check((await fetch(g.url + '/data/people.json', { headers: { cookie: cookieOf(n) } })).status === 401, 'and its cookie does not work on the old password');
        const trim = await startGate({ dir: DIST, password: '  ' + PASSWORD + '\n' });
        check((await login(trim, PASSWORD)).status === 200, 'spaces around the secret are ignored');
        await g2.close(); await trim.close();
    }

    section('Locking a device');
    {
        const r = await fetch(g.url + '/__gate/logout', { method: 'POST' });
        check(r.status === 200 && /Max-Age=0/.test(r.headers.getSetCookie()[0] || ''), 'logging out clears the cookie');
        check((await fetch(g.url + '/__gate/logout', { method: 'POST', headers: { Origin: 'https://elsewhere.example' } })).status === 403, 'logging out from another site is refused');
    }

    section('Not set up');
    {
        for (const pw of [undefined, '', '   ']) {
            const open = await startGate({ dir: DIST, password: pw });
            const r = await fetch(open.url + '/data/people.json'), t = await r.text();
            const rr = await fetch(open.url + '/');
            check(r.status === 503 && rr.status === 503 && !t.includes('arthur'), 'with the password ' + (pw === undefined ? 'unset' : JSON.stringify(pw)) + ' the gate refuses everything (503), never serves the site open');
            await open.close();
        }
    }

    await g.close();
    console.log('\n' + (failures ? failures + ' FAILED' : 'all passed'));
    process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
