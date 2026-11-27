/* Checks for private access (the family password) and the first visit with both features, in a browser.
 * The site runs behind tests/gate-server.js, which runs the real _worker.js the build wrote.
 *
 *   node tests/check-access.js                  builds the made-up sites it needs, then checks them
 *   SHOTS=dir node tests/check-access.js        also saves screenshots of the first visit (desktop and phone) to dir
 *   VIDEO=dir node tests/check-access.js        also records the first visit, start to finish, as .webm (desktop and phone)
 *
 * Needs Node 18 or later and Playwright with Chromium. Nothing off the machine is reached.
 */
const fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const H = require('./helpers');
const { startGate } = require('./gate-server');
const { check, section } = H;
const SHOTS = process.env.SHOTS && path.resolve(process.env.SHOTS);
const VIDEO = process.env.VIDEO && path.resolve(process.env.VIDEO);
for (const d of [SHOTS, VIDEO]) if (d) fs.mkdirSync(d, { recursive: true });
const PASSWORD = 'correct horse battery staple';
const KEY = 'fs.visitor.v1:/';

(async () => {
    const tmp = H.tmpdir('engine-access-');
    const both = H.buildFixture(tmp, 'both', []);
    const accessOnly = H.buildFixture(tmp, 'access-only', ['--no-visitor']);
    const browser = await chromium.launch();
    const errors = [], external = [];
    async function ctx(opts) {
        const c = await browser.newContext(Object.assign({ viewport: { width: 1280, height: 800 } }, opts || {}));
        c.on('request', r => { if (!/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(r.url())) external.push(r.url()); });
        await c.route(u => !/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(u.href), r => r.abort());
        return c;
    }
    const treeReady = page => page.waitForFunction(() => document.documentElement.classList.contains('tc-ready'));
    const enter = async (page, pw) => { await page.fill('#pw', pw); await page.keyboard.press('Enter'); };
    const cookieNames = async c => (await c.cookies()).map(x => x.name);

    let g = await startGate({ dir: both, password: PASSWORD });
    const port = g.port;

    // ---------------------------------------------------------------------------------------------
    section('The entrance');
    {
        const c = await ctx(), page = await c.newPage();
        page.on('pageerror', e => errors.push(e.message));
        const requests = [];
        page.on('request', r => requests.push(new URL(r.url()).pathname));
        const resp = await page.goto(g.url + '/family-tree.html#/person/arthur-hartley');
        check(resp.status() === 401, 'a page address gives the entrance, not the page (401)', resp.status());
        check(await page.locator('form input[type=password]').count() === 1 && await page.locator('#pw').isVisible(), 'there is a password field');
        const text = await page.evaluate(() => document.body.innerText);
        check(/private family archive/i.test(text) && /Hartley & Moreau/.test(text), 'it says what this is and names the site');
        check(!/Arthur|Susan|Kate|Moreau\b(?!$)|Family Tree|Family Map/.test(text.replace('Hartley & Moreau', '')), 'it shows nothing of the family: no names, no menu');
        check(/Ask a family member for it/.test(text), 'the optional hint line is there');
        check(requests.every(p => ['/family-tree.html', '/favicon.ico'].includes(p)), 'nothing but the entrance was requested (no data, no pictures, no scripts)', requests.join(', '));
        check(await page.evaluate(() => !document.querySelector('img')), 'no picture before the password');
        check(await page.title() === 'Hartley & Moreau', 'the tab is titled with the site name only', await page.title());
        check(await page.evaluate(() => document.querySelector('meta[name=robots]') && /noindex/.test(document.querySelector('meta[name=robots]').content)), 'the page asks search engines not to index it');
        check(await page.evaluate(() => document.activeElement && document.activeElement.id) === 'pw' || await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'pw').then(() => true), 'the field has the focus');
        // show and hide
        await page.fill('#pw', 'abc');
        check(await page.locator('#pw').getAttribute('type') === 'password', 'typing is hidden by default');
        await page.locator('#show').click();
        check(await page.locator('#pw').getAttribute('type') === 'text', '"Show" shows it');
        await page.locator('#show').click();
        // wrong password
        await page.fill('#pw', 'not the password'); await page.keyboard.press('Enter');
        await page.locator('#msg', { hasText: 'not the family password' }).waitFor({ timeout: 5000 });
        check(true, 'a wrong password is said plainly, in a live region');
        check(await page.locator('#msg').getAttribute('aria-live') !== null, 'and announced to a screen reader');
        check(!(await cookieNames(c)).length && await page.locator('#pw').isVisible(), 'no cookie, and the field is still there');
        check(page.url().endsWith('#/person/arthur-hartley'), 'the address is kept');
        // the right one
        await enter(page, PASSWORD);
        await page.waitForFunction(() => !!document.querySelector('.main-nav'), null, { timeout: 8000 });
        check(true, 'the right password opens the page that was asked for');
        await page.waitForSelector('.fv-root');
        check(page.url().endsWith('#/person/arthur-hartley'), 'the deep link survives the entrance');
        const names = await cookieNames(c);
        const ck = (await c.cookies())[0];
        check(names.join() === '__Host-fs_access' && ck.httpOnly && ck.secure && ck.sameSite === 'Lax' && ck.path === '/', 'one cookie, __Host-, HttpOnly, Secure, SameSite=Lax', JSON.stringify(ck));
        check(await page.evaluate(() => document.cookie === ''), 'no script on the page can read it');
        check(await page.evaluate(p => JSON.stringify([localStorage, sessionStorage]).indexOf(p) < 0, PASSWORD), 'the password is not kept in the browser\'s storage');
        check(!JSON.stringify(ck).includes(PASSWORD) && !JSON.stringify(ck).includes('correct'), 'nor in the cookie');
        // skip the visitor question for now
        await page.getByRole('button', { name: 'Continue without choosing' }).click();
        await treeReady(page);
        await page.waitForFunction(() => __tree.S.sel === 'arthur-hartley');
        check(true, 'then the person in the link is open on the tree');

        // remembered access
        const p2 = await c.newPage();
        const r2 = await p2.goto(g.url + '/index.html');
        check(r2.status() === 200 && await p2.locator('form input[type=password]').count() === 0, 'back again on this device: straight in, no entrance');
        await p2.close(); await page.close();
        const p3 = await c.newPage();
        check((await p3.goto(g.url + '/family-tree.html')).status() === 200, 'still in after the page was closed');
        await p3.close();
        // another device
        const other = await ctx(), po = await other.newPage();
        check((await po.goto(g.url + '/data/people.json')).status() === 401, 'another browser is not let in by this one\'s cookie');
        await other.close();
        // direct attempts from an open page once the cookie is gone
        const p4 = await c.newPage(); await p4.goto(g.url + '/index.html');
        await c.clearCookies();
        const probe = await p4.evaluate(async () => {
            const out = {};
            for (const u of ['/data/people.json', '/images/people/arthur-hartley.png', '/site-config.js', '/archive/manifest.json', '/family-tree.html'])
                out[u] = (await fetch(u)).status;
            out.img = await new Promise(res => { const i = new Image(); i.onload = () => res('loaded'); i.onerror = () => res('blocked'); i.src = '/images/people/arthur-hartley.png?x=' + Date.now(); });
            return out;
        });
        check(Object.values(probe).every(v => v === 401 || v === 'blocked'), 'once the cookie is gone every file is refused, even from a page that was open', JSON.stringify(probe));
        await p4.close();
        await c.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('Access, identity and the site stay separate');
    {
        const c = await ctx(), page = await c.newPage();
        await page.goto(g.url + '/index.html'); await enter(page, PASSWORD);
        await page.waitForSelector('.fv-root');
        await page.fill('#fv-input', 'kate'); await page.locator('.fv-opt').first().click();
        await page.getByRole('button', { name: 'Yes, that is me' }).click();
        await page.waitForSelector('.fv-root', { state: 'detached', timeout: 8000 });
        check(JSON.parse(await page.evaluate(k => localStorage.getItem(k), KEY)).id === 'kate-hartley', 'the visitor chose who they are after getting in');
        // forgetting who you are does not lock the device
        await page.locator('.fv-chip').click(); await page.getByRole('button', { name: 'Forget me on this device' }).click();
        check((await cookieNames(c)).length === 1 && await page.evaluate(k => localStorage.getItem(k), KEY) === null, '"Forget me" clears the identity and keeps the access');
        const still = await c.newPage(); check((await still.goto(g.url + '/data/people.json')).status() === 200, 'the data is still open to this device'); await still.close();
        // choose again, then lock: the identity stays, the access goes
        await page.reload(); await page.waitForSelector('.fv-root');
        await page.fill('#fv-input', 'susan'); await page.locator('.fv-opt').first().click();
        await page.getByRole('button', { name: 'Yes, that is me' }).click();
        await page.waitForSelector('.fv-root', { state: 'detached', timeout: 8000 });
        await page.locator('.fv-chip').click();
        check(await page.getByRole('button', { name: 'Lock this device' }).isVisible(), 'the menu offers "Lock this device" on a protected site');
        await Promise.all([page.waitForNavigation(), page.getByRole('button', { name: 'Lock this device' }).click()]);
        check(await page.locator('form input[type=password]').count() === 1 && !(await cookieNames(c)).length, 'locking clears the access: the entrance is back');
        check(await page.evaluate(k => localStorage.getItem(k), KEY) !== null, 'and leaves the identity alone: they are different things');
        await c.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('Changing the password');
    {
        const c = await ctx(), page = await c.newPage();
        await page.goto(g.url + '/index.html'); await enter(page, PASSWORD);
        await page.waitForSelector('.fv-root'); await page.getByRole('button', { name: 'Continue without choosing' }).click();
        check((await cookieNames(c)).length === 1, 'in with the old password');
        await g.close();
        g = await startGate({ dir: both, password: 'a new family password', port });
        const r = await page.goto(g.url + '/index.html');
        check(r.status() === 401 && await page.locator('form input[type=password]').count() === 1, 'after the password changes, the old cookie no longer lets anyone in');
        await enter(page, PASSWORD);
        await page.locator('#msg', { hasText: 'not the family password' }).waitFor({ timeout: 5000 });
        check(true, 'and the old password is refused');
        await enter(page, 'a new family password');
        await page.waitForFunction(() => !!document.querySelector('.main-nav'), null, { timeout: 8000 });
        check(true, 'the new one works');
        await c.close();
        await g.close();
        g = await startGate({ dir: both, password: PASSWORD, port });
    }

    // ---------------------------------------------------------------------------------------------
    section('Access without visitor identity');
    {
        const g2 = await startGate({ dir: accessOnly, password: PASSWORD });
        const c = await ctx(), page = await c.newPage();
        await page.goto(g2.url + '/family-tree.html'); await enter(page, PASSWORD);
        await treeReady(page);
        check(await page.locator('.fv-root, .fv-chip').count() === 0 && await page.evaluate(() => typeof window.FamilyVisitor === 'undefined'), 'in with the password, and no "Who are you?"');
        check(await page.evaluate(() => !!window.FamilySite.access && !window.FamilySite.visitor), 'the page knows about access only');
        const base = await H.treeView(page);
        check(base.viewpoint === 'daniel-hartley', 'the tree opens as it always did');
        await c.close(); await g2.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('Reduced motion and a phone');
    {
        const c = await ctx({ reducedMotion: 'reduce' }), page = await c.newPage();
        await page.goto(g.url + '/');
        const anim = await page.evaluate(() => [...document.querySelectorAll('.g-tree path, .g-word, .g-kicker, form')].map(e => getComputedStyle(e).animationName));
        check(anim.length && anim.every(a => a === 'none'), 'with reduced motion the entrance does not animate', JSON.stringify(anim));
        check(await page.locator('#pw').isVisible(), 'and the password field is there at once');
        await enter(page, PASSWORD);
        await page.waitForFunction(() => !!document.querySelector('.main-nav'), null, { timeout: 4000 });
        check(true, 'and entering is quick');
        await c.close();

        const m = await ctx({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }), mp = await m.newPage();
        await mp.goto(g.url + '/');
        await mp.waitForTimeout(3500);
        check(await mp.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'the entrance does not scroll sideways on a phone');
        check(await mp.evaluate(() => parseFloat(getComputedStyle(document.getElementById('pw')).fontSize)) >= 16, 'the field is 16px or more, so a phone does not zoom in');
        const b = await mp.locator('.g-enter').boundingBox();
        check(b.height >= 44 && b.x >= 0 && b.x + b.width <= 390, 'the button is big enough to tap and on the screen', JSON.stringify(b));
        await m.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('A first visit, start to finish');
    const stills = [];
    async function journey(name, opts, withVideo) {
        const o = Object.assign({}, opts);
        if (withVideo && VIDEO) o.recordVideo = { dir: path.join(VIDEO, '.tmp-' + name), size: opts.viewport };
        const c = await ctx(o), page = await c.newPage();
        page.on('pageerror', e => errors.push(name + ': ' + e.message));
        const shot = async n => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'journey-' + n + '-' + name + '.png') }); };
        const tap = (loc) => opts.hasTouch ? loc.tap() : loc.click();
        const pause = ms => withVideo ? page.waitForTimeout(ms) : Promise.resolve();
        await page.goto(g.url + '/family-tree.html');      // a link someone sent: the tree
        await page.waitForTimeout(withVideo ? 4200 : 3600);                      // the entrance draws itself
        await shot('1-entrance');
        await page.locator('#pw').click(); await page.keyboard.type('the wrong one', { delay: withVideo ? 70 : 0 });
        await pause(400); await page.keyboard.press('Enter');
        await page.locator('#msg', { hasText: 'not the family password' }).waitFor();
        await pause(900); await shot('2-wrong-password');
        await page.fill('#pw', ''); await page.keyboard.type(PASSWORD, { delay: withVideo ? 60 : 0 });
        await shot('2b-password-entry');
        await pause(500); await page.keyboard.press('Enter');
        await page.waitForSelector('.fv-root', { timeout: 8000 });
        await pause(1400); await shot('3-who-are-you');
        await page.keyboard.type('dan', { delay: withVideo ? 140 : 0 });
        await pause(1200); await shot('4-typeahead');
        await tap(page.locator('.fv-opt', { hasText: 'Susan' }));
        await page.getByRole('button', { name: 'Yes, that is me' }).waitFor();
        await pause(1200); await shot('5-confirm');
        await tap(page.getByRole('button', { name: 'Yes, that is me' }));
        await page.waitForTimeout(1300); await shot('6-welcome');
        await page.waitForSelector('.fv-root', { state: 'detached', timeout: 8000 });
        await treeReady(page);
        await page.waitForTimeout(withVideo ? 2500 : 700);
        await shot('7-personalised-tree');
        const pos = await H.cardAt(page, 'daniel-hartley-2');
        check(pos && pos.x > 0.15 && pos.x < 0.85 && pos.y > 0.1 && pos.y < 0.9, name + ': the first visit ends on the tree, centred on the visitor', JSON.stringify(pos));
        await pause(1500);
        const vid = page.video();
        await c.close();
        if (vid && VIDEO) {
            const to = path.join(VIDEO, 'first-visit-' + name + '.webm');
            await vid.saveAs(to);
            fs.rmSync(path.join(VIDEO, '.tmp-' + name), { recursive: true, force: true });
            check(fs.statSync(to).size > 10000, name + ': the recording was saved', to);
        }
    }
    await journey('desktop', { viewport: { width: 1280, height: 800 } }, true);
    await journey('mobile', { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, true);

    check(!errors.length, 'no script errors on any page', errors.slice(0, 3).join(' | '));
    check(!external.length, 'nothing off the machine was requested, no analytics', external.join(', '));
    await browser.close();
    await g.close();
    console.log('\n' + (H.state.failures ? H.state.failures + ' FAILED' : 'all passed'));
    process.exit(H.state.failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
