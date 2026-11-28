/* Checks for the basic family password (docs/basic-access.md), in a browser, against made-up sites built from the sample family.
 *
 *   node tests/check-basic-access.js           SHOTS=dir also saves screenshots
 *
 * The password here is made up. The checks are about what the script does: hold the page back, take the right password,
 * remember the device, forget it when the password changes, and leave other pages alone when the scope says so.
 * They do not claim the files are protected: they are not, and the last section says so by fetching one.
 */
const fs = require('fs'), path = require('path'), cp = require('child_process');
const { chromium } = require('playwright');
const H = require('./helpers');
const { check, section } = H;
const SHOTS = process.env.SHOTS && path.resolve(process.env.SHOTS);
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const PASSWORD = 'plum lantern harbour quiet 47';
const OTHER = 'a different made up passphrase';
const KEY = 'fse-basic-access';

// the hash is made by the real tool's function, so this also checks that Python and the browser agree
function settings(password, extra) {
    const code = 'import sys, json; sys.path.insert(0, "tools"); import importlib.util as u; s = u.spec_from_file_location("bp", "tools/basic-password.py"); m = u.module_from_spec(s); s.loader.exec_module(m); print(json.dumps(m.make(sys.argv[1])))';
    const made = JSON.parse(cp.execFileSync('python3', ['-c', code, password], { cwd: H.ROOT }).toString());
    return Object.assign({ enabled: true, scope: 'home', days: 30 }, made, extra || {});
}
function site(tmp, name, block) {
    const src = path.join(tmp, name + '-src'), out = path.join(tmp, name);
    cp.execFileSync('cp', ['-r', path.join(H.ROOT, 'sample'), src]);
    const p = path.join(src, 'site.config.json'), cfg = JSON.parse(fs.readFileSync(p, 'utf8'));
    cfg.basicAccess = block;
    fs.writeFileSync(p, JSON.stringify(cfg, null, 1));
    cp.execFileSync('python3', [path.join(H.ROOT, 'build', 'build_site.py'), '--site', src, '--out', out], { stdio: 'pipe' });
    return out;
}

(async () => {
    const tmp = H.tmpdir('engine-basic-');
    const dirs = {
        home: site(tmp, 'home', settings(PASSWORD)),
        all: site(tmp, 'all', settings(PASSWORD, { scope: 'all' })),
        plain: H.buildSample(tmp),
    };
    const srv = {};
    for (const k of Object.keys(dirs)) srv[k] = await H.serveStatic(dirs[k]);
    const browser = await chromium.launch();
    const errors = [];
    async function open(key, p, ctx) {
        const c = ctx || await browser.newContext({ viewport: { width: 1100, height: 760 } });
        const page = await c.newPage();
        page.on('pageerror', e => errors.push(key + p + ': ' + e.message));
        await page.goto(srv[key].url + p, { waitUntil: 'load' });
        return page;
    }
    const gated = page => page.locator('.fse-gate').count().then(n => n > 0);
    const visible = page => page.evaluate(() => document.body.innerText);
    async function type(page, pw) {
        await page.locator('#fse-gate-password').fill(pw);
        await page.locator('.fse-gate button').click();
    }

    section('The home page asks for the password');
    {
        const page = await open('home', '/index.html');
        check(await gated(page), 'the entrance is shown');
        const t = await visible(page);
        check(!/Hartley|Moreau|Family Tree|Family Map/.test(t.replace(/Hartley & Moreau/, '')), 'nothing of the page shows behind it', t.slice(0, 120));
        check(await page.locator('html.fse-locked').count() === 1, 'the page is marked locked');
        check((await page.locator('.fse-gate h1').textContent()).trim() === 'Hartley & Moreau', 'it carries the site name only');
        check(await page.locator('#fse-gate-password').getAttribute('type') === 'password', 'the field hides what is typed');
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'basic-entrance.png') });

        await type(page, OTHER);
        await page.waitForFunction(() => document.querySelector('.fse-gate-msg').textContent.length > 0, null, { timeout: 8000 });
        check((await page.locator('.fse-gate-msg').textContent()).includes('not the password'), 'a wrong password gets a plain message');
        check(await gated(page) && await page.locator('#fse-gate-password').inputValue() === '', 'and the entrance stays, with the field cleared');
        check(await page.evaluate(k => localStorage.getItem(k), KEY) === null, 'nothing is remembered');

        await type(page, PASSWORD);
        await page.waitForFunction(() => !document.querySelector('.fse-gate'), null, { timeout: 8000 });
        await page.waitForLoadState('load');
        check(!(await gated(page)), 'the right password opens the page');
        check(/family tree/i.test(await visible(page)), 'and the page is there');
        const kept = JSON.parse(await page.evaluate(k => localStorage.getItem(k), KEY));
        check(kept && kept.until > Date.now() + 29 * 86400000 && kept.until < Date.now() + 31 * 86400000, 'the device is remembered for 30 days');
        check(!JSON.stringify(kept).includes(PASSWORD), 'what is kept is not the password');
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'basic-open.png') });

        await page.reload();
        check(!(await gated(page)), 'the next visit goes straight in');

        section('Other pages, when the scope is the home page');
        const tree = await open('home', '/family-tree.html', page.context());
        await tree.waitForTimeout(500);
        check(!(await gated(tree)), 'the tree page has no entrance');
        const fresh = await browser.newContext();
        const tree2 = await open('home', '/family-tree.html', fresh);
        check(!(await gated(tree2)) && (await tree2.locator('script[src*="basic-gate"]').count()) === 0, 'and carries no gate script, even for a new visitor');
        await fresh.close();

        section('Forgetting');
        await page.evaluate(k => { const v = JSON.parse(localStorage.getItem(k)); v.until = Date.now() - 1000; localStorage.setItem(k, JSON.stringify(v)); }, KEY);
        await page.reload();
        check(await gated(page), 'an expired choice asks again');
        await page.evaluate(k => localStorage.setItem(k, JSON.stringify({ h: 'bm90IHRoZSBoYXNo', until: Date.now() + 1e9 })), KEY);
        await page.reload();
        check(await gated(page), 'a choice made for another password (another hash) asks again');
        await page.evaluate(k => localStorage.setItem(k, '{not json'), KEY);
        await page.reload();
        check(await gated(page), 'a damaged saved choice asks again, with no error');
        await page.context().close();
    }

    section('Scope: all pages');
    {
        const page = await open('all', '/family-tree.html');
        check(await gated(page), 'the tree page asks too');
        await type(page, PASSWORD);
        await page.waitForFunction(() => !document.querySelector('.fse-gate'), null, { timeout: 8000 });
        await page.waitForLoadState('load');
        await page.waitForSelector('.card', { timeout: 10000 });
        check(true, 'and the tree draws once the password is right');
        const map = await open('all', '/map.html', page.context());
        check(!(await gated(map)), 'the same device is let in to the map without asking again');
        const other = await browser.newContext();
        const m2 = await open('all', '/map.html', other);
        check(await gated(m2), 'a new device is asked on the map');
        await other.close();
        await page.context().close();
    }

    section('A site without it');
    {
        const page = await open('plain', '/index.html');
        check(!(await gated(page)) && (await page.locator('script[src*="basic-gate"]').count()) === 0, 'no entrance and no script');
        const r = await page.evaluate(() => fetch('engine/' + window.FamilySite.engine.version + '/basic-gate.js').then(x => x.status));
        check(r === 404, 'the gate script is not even published', r);
        await page.context().close();
    }

    section('The settings hold no password');
    {
        const dir = dirs.home, bad = [];
        (function walk(d) {
            fs.readdirSync(d, { withFileTypes: true }).forEach(e => {
                const p = path.join(d, e.name);
                if (e.isDirectory()) return walk(p);
                if (/\.(html|js|json|css|txt|xml)$/.test(e.name) && fs.readFileSync(p, 'utf8').includes(PASSWORD)) bad.push(path.relative(dir, p));
            });
        })(dir);
        check(bad.length === 0, 'the password is in no built file', bad.join(', '));
        const cfg = fs.readFileSync(path.join(tmp, 'home-src', 'site.config.json'), 'utf8');
        check(!cfg.includes(PASSWORD), 'nor in the settings');
    }

    section('The browser makes a hash the tool accepts');
    {
        const page = await open('home', '/index.html');
        const made = await page.evaluate(pw => window.FamilyBasicAccess.make(pw, 150000), 'another made up phrase');
        const code = 'import sys, json; sys.path.insert(0, "tools"); import importlib.util as u; s = u.spec_from_file_location("bp", "tools/basic-password.py"); m = u.module_from_spec(s); s.loader.exec_module(m); import base64; print(m.make(sys.argv[1], int(sys.argv[2]), base64.b64decode(sys.argv[3]))["hash"])';
        const py = cp.execFileSync('python3', ['-c', code, 'another made up phrase', '150000', made.salt], { cwd: H.ROOT }).toString().trim();
        check(py === made.hash, 'the same salt and password give the same hash in Python and in the browser');
        const accented = await page.evaluate(() => window.FamilyBasicAccess.derive('Straße café', 'c2FsdHNhbHRzYWx0c2FsdA==', 120000));
        const py2 = cp.execFileSync('python3', ['-c', code.replace('sys.argv[1]', '"Stra\\u00dfe caf\\u00e9"'), 'x', '120000', 'c2FsdHNhbHRzYWx0c2FsdA=='], { cwd: H.ROOT }).toString().trim();
        check(py2 === accented, 'and for a password with accents');
        await page.context().close();
    }

    section('What it is not');
    {
        const r = await fetch(srv.home.url + '/family-tree.html');
        const t = await r.text();
        check(r.status === 200 && t.includes('Family Tree'), 'the other pages are served in full to anyone who asks (it is not protection)');
        const home = await (await fetch(srv.home.url + '/index.html')).text();
        check(home.includes('The Moreaus') || home.includes('Hartley'), 'and so is the home page source');
    }

    section('Nothing else');
    check(errors.length === 0, 'no script errors on any page', errors.join(' | '));
    await browser.close();
    for (const k of Object.keys(srv)) await srv[k].close();
    fs.rmSync(tmp, { recursive: true, force: true });
    console.log(H.state.failures ? '\n' + H.state.failures + ' failed' : '\nall passed');
    process.exit(H.state.failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
