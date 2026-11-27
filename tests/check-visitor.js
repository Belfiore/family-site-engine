/* Checks for visitor identity ("Who are you?") in a browser, against made-up sites built from the sample family.
 *
 *   node tests/check-visitor.js               builds the sites it needs into a temporary folder, then checks them
 *   SHOTS=dir node tests/check-visitor.js     also saves screenshots (desktop and phone) to dir
 *
 * Needs Node 18 or later and Playwright with Chromium. Nothing off the machine is reached; the checks fail if the page tries.
 */
const fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const H = require('./helpers');
const { check, section } = H;
const SHOTS = process.env.SHOTS && path.resolve(process.env.SHOTS);
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const TREE = '/family-tree.html';
const KEY = root => 'fs.visitor.v1:' + root;

(async () => {
    const tmp = H.tmpdir('engine-visitor-');
    const sites = {
        plain: H.buildSample(tmp),                                               // the sample as it is: no visitor, no access
        visitor: H.buildFixture(tmp, 'visitor', ['--no-access']),                // visitor on
        same: H.buildFixture(tmp, 'same', ['--no-access', '--no-visitor']),      // the same family with it off, to compare the opening view
        photos: H.buildFixture(tmp, 'photos', ['--no-access', '--living-photos']),
        all: H.buildFixture(tmp, 'all', ['--no-access', '--scope', 'all']),
        access: H.buildFixture(tmp, 'access', ['--no-visitor']),                 // access on, visitor off (served here as plain files)
    };
    const srv = {};
    for (const k of Object.keys(sites)) srv[k] = await H.serveStatic(sites[k]);
    const browser = await chromium.launch();
    const external = [];
    async function ctx(opts) {
        const c = await browser.newContext(Object.assign({ viewport: { width: 1280, height: 800 } }, opts || {}));
        c.on('request', r => { if (!/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(r.url())) external.push(r.url()); });
        await c.route(u => !/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(u.href), r => r.abort());
        return c;
    }
    const errors = [];
    async function open(c, key, p) {
        const page = await c.newPage();
        page.on('pageerror', e => errors.push(key + p + ': ' + e.message));
        await page.goto(srv[key].url + (p || TREE), { waitUntil: 'load' });
        return page;
    }
    const names = page => page.locator('.fv-opt .fv-opt-name').allTextContents();
    const treeReady = page => page.waitForFunction(() => document.documentElement.classList.contains('tc-ready'));
    const stored = (page, key) => page.evaluate(k => localStorage.getItem(k), key);
    async function choose(page, typed, pickName, ctxText) {
        await page.fill('#fv-input', typed);
        const opt = ctxText ? page.locator('.fv-opt', { hasText: ctxText }) : page.locator('.fv-opt', { hasText: pickName }).first();
        await opt.click();
        await page.locator('.fv-title', { hasText: pickName }).waitFor();
        await page.getByRole('button', { name: 'Yes, that is me' }).click();
        await page.waitForSelector('.fv-root', { state: 'detached', timeout: 8000 });
    }

    // ---------------------------------------------------------------------------------------------
    section('A site that has not turned it on is untouched');
    {
        const c = await ctx(), page = await open(c, 'plain');
        await treeReady(page);
        check(await page.evaluate(() => typeof window.FamilyVisitor === 'undefined' && !window.FamilySite.visitor && !window.FamilySite.access), 'no visitor context and no settings for it');
        check(await page.locator('.fv-root, .fv-chip').count() === 0 && !(await page.evaluate(() => document.documentElement.classList.contains('fv-pending'))), 'no question, no chip, page not held back');
        check(!(await page.content()).includes('visitor'), 'the page does not mention visitor files');
        check(!fs.existsSync(path.join(sites.plain, 'engine', fs.readdirSync(path.join(sites.plain, 'engine'))[0], 'visitor.js')), 'the build has no visitor files');
        check(await page.evaluate(() => Object.keys(localStorage).every(k => !/visitor/.test(k))), 'nothing is stored about visitors');
        await c.close();
        // access alone does not switch visitor on either (the files are served plainly here, which is only what the gate lets through)
        const c2 = await ctx(), p2 = await open(c2, 'access');
        await treeReady(p2);
        check(await p2.evaluate(() => typeof window.FamilyVisitor === 'undefined') && await p2.locator('.fv-root').count() === 0, 'access on and visitor off: no question');
        await c2.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('The first visit');
    {
        const c = await ctx(), page = await open(c, 'visitor');
        await page.waitForSelector('.fv-root');
        const held = await page.evaluate(() => getComputedStyle(document.querySelector('.tc-head')).visibility);
        check(held === 'hidden', 'the page behind is held back until the question is answered', held);
        check(await page.evaluate(() => document.activeElement && document.activeElement.id === 'fv-input') || await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'fv-input').then(() => true), 'the name field has the focus');
        check(/Who are you\?/.test(await page.locator('.fv-title').innerText()), 'the question is "Who are you?"');
        check(await page.getByRole('button', { name: 'Continue without choosing' }).isVisible(), 'a quiet way to carry on without choosing is there');
        check((await stored(page, KEY('/'))) === null, 'nothing is stored before a choice');
        check(await page.evaluate(() => document.querySelector('.main-nav').hasAttribute('inert')), 'the page behind cannot be tabbed into or read while the question is open');
        await page.waitForTimeout(900);
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-1-question-desktop.png') });
        await c.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('Finding yourself');
    {
        const c = await ctx(), page = await open(c, 'visitor');
        await page.waitForSelector('.fv-root');
        const type = async q => { await page.fill('#fv-input', q); return names(page); };
        let r = await type('dan');
        check(r.length === 2 && r.every(n => n === 'Daniel Hartley'), 'two people called Daniel Hartley both come up', JSON.stringify(r));
        const ctxs = await page.locator('.fv-opt .fv-opt-ctx').allTextContents();
        check(ctxs.some(t => /Peter and Janet/.test(t)) && ctxs.some(t => /Susan's son, lives in Leeds, born 1991/.test(t)), 'each has a line to tell them apart', JSON.stringify(ctxs));
        r = await type('Danial');          check(r.includes('Daniel Hartley'), 'a mistyped name still finds the person', JSON.stringify(r));
        r = await type('hartly');          check(r.length >= 4, 'a surname with a letter missing finds the family', JSON.stringify(r));
        r = await type('zoe');             check(r.join() === 'Zoë Hartley', 'accents do not matter ("zoe" finds Zoë)', JSON.stringify(r));
        r = await type('Zoë hart');   check(r.join() === 'Zoë Hartley', 'a half typed full name finds her', JSON.stringify(r));
        r = await type('kate marsh');
        check(r.join() === 'Kate Hartley' && /Kate Marsh \(maiden name\)/.test(await page.locator('.fv-opt-via').first().innerText()), 'a maiden name finds the person and says why', JSON.stringify(r));
        r = await type('katie');           check(r[0] === 'Kate Hartley', 'another name the family uses finds the person', JSON.stringify(r));
        r = await type('susan');           check(r[0] === 'Susan Hartley', 'a first name finds the person');
        r = await type('HARTLEY, SUSAN');  check(r[0] === 'Susan Hartley' || r.includes('Susan Hartley'), 'capitals and commas do not matter', JSON.stringify(r));
        for (const q of ['edwin', 'pratt', 'woman', 'arthur', 'thomas', 'marguerite', 'margot']) {
            r = await type(q);
            check(!r.length, 'not offered: ' + q + ' (hidden group, unnamed sitter, or not living)', JSON.stringify(r));
        }
        r = await type('xyzzy');
        check(!r.length && /No one by that name/.test(await page.locator('.fv-live').innerText()) && await page.getByRole('button', { name: 'Continue without choosing' }).isVisible(), 'no match says so and leaves the way out');
        await type('');
        check((await names(page)).length === 0, 'an empty box lists nobody (no browsing the whole family)');
        // by keyboard
        await page.fill('#fv-input', 'kat');
        await page.keyboard.press('ArrowDown'); await page.keyboard.press('ArrowUp'); await page.keyboard.press('Enter');
        check(await page.locator('.fv-title').innerText() === 'Kate Hartley', 'arrow keys and Enter choose');
        check(/Is this you\?/.test(await page.locator('.fv-lead').innerText()), 'a person is asked to confirm before it counts');
        check((await stored(page, KEY('/'))) === null, 'nothing is stored until the choice is confirmed');
        await page.getByRole('button', { name: 'No, go back' }).click();
        check(await page.locator('#fv-input').isVisible() && (await stored(page, KEY('/'))) === null, '"No, go back" returns to the list and stores nothing');
        await c.close();

        const c2 = await ctx(), p2 = await open(c2, 'photos');
        await p2.waitForSelector('.fv-root'); await p2.fill('#fv-input', 'zoe');
        check(await p2.locator('.fv-opt img.fv-face').count() === 1, 'a living person\'s photo is shown when the site allows it (visitor.livingPhotos)');
        await c2.close();
        const c3 = await ctx(), p3 = await open(c3, 'visitor');
        await p3.waitForSelector('.fv-root'); await p3.fill('#fv-input', 'zoe');
        check(await p3.locator('.fv-opt img').count() === 0 && await p3.locator('.fv-opt .fv-face--none').count() === 1, 'and held back by default (an initial instead)');
        await c3.close();
        const c4 = await ctx(), p4 = await open(c4, 'all');
        await p4.waitForSelector('.fv-root'); await p4.fill('#fv-input', 'arthur');
        check((await names(p4)).join() === 'Arthur Hartley', 'visitor.scope "all" offers people who are not living too');
        await p4.fill('#fv-input', 'edwin');
        check((await names(p4)).length === 0, 'but still not the hidden group');
        await c4.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('Choosing, remembering, and the tree');
    let defaultView;
    {
        // what a visitor who does not say who they are gets: the tree as it always was
        const c0 = await ctx(), p0 = await open(c0, 'same'); await treeReady(p0);
        defaultView = await H.treeView(p0);
        await c0.close();

        const c = await ctx(), page = await open(c, 'visitor');
        await page.waitForSelector('.fv-root');
        await page.fill('#fv-input', 'kate'); await page.locator('.fv-opt').first().click();
        await page.getByRole('button', { name: 'Yes, that is me' }).click();
        await page.waitForTimeout(900);
        check(await page.locator('.fv-welcome').count() === 1 && /welcome/i.test(await page.locator('.fv-welcome').innerText()) && /Kate/.test(await page.locator('.fv-welcome .fv-title').innerText()), 'a short welcome greets them by first name');
        if (SHOTS) { await page.waitForTimeout(700); await page.screenshot({ path: path.join(SHOTS, 'visitor-3a-welcome-desktop.png') }); }
        await page.waitForSelector('.fv-root', { state: 'detached', timeout: 6000 });
        check(true, 'and it ends by itself within a few seconds');
        await treeReady(page);
        await page.waitForTimeout(700);
        const rec = JSON.parse(await stored(page, KEY('/')));
        check(rec && rec.v === 1 && rec.id === 'kate-hartley' && !rec.skipped, 'the choice is remembered on this device', JSON.stringify(rec));
        check(Object.keys(rec).sort().join() === 'at,id,skipped,v', 'the record holds only an id, a flag, a date and a version', Object.keys(rec).join());
        check((await page.evaluate(() => document.documentElement.classList.contains('fv-pending'))) === false, 'the page is shown');
        const pos = await H.cardAt(page, 'kate-hartley');
        check(pos && Math.abs(pos.x - 0.5) < 0.12 && Math.abs(pos.y - 0.5) < 0.2, 'the tree is centred on the visitor', JSON.stringify(pos));
        const v = await H.treeView(page);
        check(v.viewpoint === 'kate-hartley' && await page.locator('.card.is-viewpoint[data-id="kate-hartley"] .c-you').innerText() === 'YOU', 'the visitor is the viewpoint, marked "YOU"', JSON.stringify(v));
        check(await page.locator('#viewpoint').inputValue() === 'kate-hartley', 'the viewpoint list shows the visitor');
        check(await page.locator('.card').count() === await page.evaluate(() => __tree.D.people.length), 'the whole tree is still there (nothing is hidden)');
        check(await page.locator('.fv-chip-text').innerText() === 'Kate', 'a small control in the navigation bar says who the visitor is', await page.locator('.fv-chip-text').innerText());
        await page.waitForTimeout(5500);
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-3-personalised-tree-desktop.png') });

        // free navigation
        await page.evaluate(() => { location.hash = '#/person/arthur-hartley'; });
        await page.waitForFunction(() => __tree.S.sel === 'arthur-hartley');
        check((await H.treeView(page)).viewpoint === 'kate-hartley', 'the visitor can open anyone, and stays the viewpoint');
        await page.evaluate(() => { location.hash = ''; });

        // remembered
        await page.reload({ waitUntil: 'load' });
        check(await page.locator('.fv-root').count() === 0, 'back again: no question');
        await treeReady(page);
        const again = await H.cardAt(page, 'kate-hartley');
        check(again && Math.abs(again.x - 0.5) < 0.12 && Math.abs(again.y - 0.5) < 0.2, 'back again: the tree opens on the visitor straight away', JSON.stringify(again));
        const p2 = await c.newPage(); await p2.goto(srv.visitor.url + '/index.html');
        check(await p2.locator('.fv-root').count() === 0 && await p2.locator('.fv-chip-text').innerText() === 'Kate', 'another page on the same device knows too');
        check(await p2.evaluate(() => FamilyVisitor.id()) === 'kate-hartley' && await p2.evaluate(() => FamilyVisitor.status()) === 'identified', 'other scripts can read it (FamilyVisitor.id and status)');
        check((await p2.evaluate(() => FamilyVisitor.ready)).displayName === 'Kate Hartley', 'and ask for the person\'s record (FamilyVisitor.ready)');
        await p2.close();

        // a link to a person is respected
        const p3 = await c.newPage(); await p3.goto(srv.visitor.url + TREE + '#/person/thomas-hartley'); await treeReady(p3);
        await p3.waitForFunction(() => __tree.S.sel === 'thomas-hartley');
        await p3.waitForTimeout(600);
        const t = await H.cardAt(p3, 'thomas-hartley');
        check(t && t.x > 0 && t.x < 1 && (await p3.locator('#drawer').isVisible() || await p3.evaluate(() => __tree.S.sel) === 'thomas-hartley'), 'a direct link to a person opens that person, not the visitor', JSON.stringify(t));
        await p3.close();

        // Stuart uses the same choice
        const ps = await c.newPage(); await ps.goto(srv.visitor.url + '/ask.html');
        await ps.waitForFunction(() => /Asking as Kate Hartley/.test(document.body.innerText), null, { timeout: 8000 }).then(() => check(true, 'Stuart answers as the same person'), () => check(false, 'Stuart answers as the same person'));
        await ps.close();

        // change
        await page.locator('.fv-chip').click();
        check(await page.locator('.fv-menu').isVisible() && /Viewing the family as Kate Hartley/.test(await page.locator('.fv-menu-line').innerText()), 'the control opens a small menu that says who is being shown');
        check(/not a login/i.test(await page.locator('.fv-menu-fine').innerText()), 'and says plainly that it is not a login');
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-5-menu-desktop.png') });
        await page.getByRole('button', { name: /Choose someone else/ }).click();
        await page.waitForSelector('.fv-root');
        check(await page.getByRole('button', { name: 'Cancel' }).isVisible(), 'changing can be cancelled');
        await page.keyboard.press('Escape');
        await page.waitForSelector('.fv-root', { state: 'detached' });
        check(JSON.parse(await stored(page, KEY('/'))).id === 'kate-hartley', 'cancelling keeps the old choice');
        await page.locator('.fv-chip').click(); await page.getByRole('button', { name: /Choose someone else/ }).click();
        await page.waitForSelector('.fv-root');
        await choose(page, 'dan', 'Daniel Hartley', "Peter and Janet");
        await page.waitForTimeout(900);
        const d = await H.cardAt(page, 'daniel-hartley');
        check(JSON.parse(await stored(page, KEY('/'))).id === 'daniel-hartley' && d && Math.abs(d.x - 0.5) < 0.12 && Math.abs(d.y - 0.5) < 0.2, 'choosing someone else moves the tree to them', JSON.stringify(d));
        check(await page.locator('.fv-chip-text').innerText() === 'Daniel', 'and the control follows');

        // forget
        await page.locator('.fv-chip').click();
        await page.getByRole('button', { name: 'Forget me on this device' }).click();
        check((await stored(page, KEY('/'))) === null && await page.locator('.fv-chip-text').innerText() === 'Who are you?', 'forgetting clears the device');
        await page.waitForTimeout(700);
        const f = await H.treeView(page);
        check(f.tx === defaultView.tx && f.ty === defaultView.ty && f.s === defaultView.s, 'and the tree goes back to its usual opening view', JSON.stringify([f, defaultView]));
        await page.reload({ waitUntil: 'load' });
        check(await page.locator('.fv-root').count() === 1, 'the question is asked again next time');
        await c.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('A visitor who is not in the tree, or does not say');
    {
        const c = await ctx(), page = await open(c, 'visitor');
        await page.waitForSelector('.fv-root');
        await page.getByRole('button', { name: 'Continue without choosing' }).click();
        await page.waitForSelector('.fv-root', { state: 'detached' });
        await treeReady(page);
        const rec = JSON.parse(await stored(page, KEY('/')));
        check(rec && rec.skipped === true && rec.id === null, 'carrying on is remembered, so they are not asked on every page', JSON.stringify(rec));
        await page.waitForTimeout(600);
        const v = await H.treeView(page);
        check(v.tx === defaultView.tx && v.ty === defaultView.ty && v.s === defaultView.s && v.viewpoint === 'daniel-hartley', 'the tree opens as it always did', JSON.stringify([v, defaultView]));
        check(await page.locator('.card.is-viewpoint .c-you').innerText() === 'VIEWPOINT', 'the badge keeps its usual word');
        check(await page.locator('.fv-chip-text').innerText() === 'Who are you?', 'a quiet "Who are you?" stays in the navigation bar');
        await page.reload({ waitUntil: 'load' });
        check(await page.locator('.fv-root').count() === 0, 'not asked again');
        await page.locator('.fv-chip').click();
        check(await page.getByRole('button', { name: 'Choose who you are' }).isVisible(), 'they can still choose later');
        await c.close();

        // a remembered person who is no longer in the data is treated as not chosen
        const c2 = await ctx(), p2 = await c2.newPage();
        await p2.goto(srv.visitor.url + '/index.html');
        await p2.evaluate(k => { localStorage.clear(); localStorage.setItem(k, JSON.stringify({ v: 1, id: 'nobody-here', skipped: false, at: '2026-01-01' })); }, KEY('/'));
        await p2.goto(srv.visitor.url + TREE);
        await p2.waitForSelector('.fv-root', { timeout: 8000 }).then(() => check(true, 'a stored person who is no longer in the data is asked about again'), () => check(false, 'a stored person who is no longer in the data is asked about again'));
        await p2.evaluate(k => localStorage.setItem(k, '{not json'), KEY('/'));
        await p2.goto(srv.visitor.url + TREE);
        await p2.waitForSelector('.fv-root', { timeout: 8000 }).then(() => check(true, 'a damaged record is treated as none'), () => check(false, 'a damaged record is treated as none'));
        await c2.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('Privacy');
    {
        const c = await ctx();
        const sent = [];
        c.on('request', r => sent.push({ url: r.url(), body: r.postData() || '', headers: r.headers() }));
        const page = await open(c, 'visitor');
        await page.waitForSelector('.fv-root');
        await choose(page, 'kate', 'Kate Hartley');
        await treeReady(page);
        await page.reload({ waitUntil: 'load' }); await treeReady(page);
        const leaks = sent.filter(r => /kate/i.test(r.url + r.body + (r.headers.cookie || '') + (r.headers.referer || '')));
        check(!leaks.length, 'who the visitor is never leaves the device (no request carries it)', JSON.stringify(leaks.slice(0, 2)));
        check(!external.length, 'nothing off the machine is requested, no analytics', external.join(', '));
        check(await page.evaluate(() => document.cookie === ''), 'no cookie is set for it');
        const all = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]));
        check(!/Kate Hartley|Peter|Janet/.test(all), 'no name or detail of anyone is kept on the device, only an id');
        check(await page.evaluate(() => !JSON.stringify(window.FamilySite).match(/password|secret|token/i)), 'the public settings hold no secret');
        await c.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('A phone');
    {
        const c = await ctx({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }), page = await open(c, 'visitor');
        await page.waitForSelector('.fv-root');
        const size = await page.evaluate(() => parseFloat(getComputedStyle(document.getElementById('fv-input')).fontSize));
        check(size >= 16, 'the name field is 16px or more, so a phone does not zoom in', size);
        check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no sideways scrolling');
        await page.waitForTimeout(900);
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-1-question-mobile.png') });
        await page.fill('#fv-input', 'dan');
        const boxes = await page.locator('.fv-opt').evaluateAll(els => els.map(e => { const r = e.getBoundingClientRect(); return [r.left, r.right, r.height]; }));
        check(boxes.length === 2 && boxes.every(b => b[0] >= 0 && b[1] <= 390 && b[2] >= 44), 'results fit the screen and are big enough to tap', JSON.stringify(boxes));
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-2-results-mobile.png') });
        await page.locator('.fv-opt', { hasText: 'Susan' }).tap();
        await page.locator('.fv-title', { hasText: 'Daniel Hartley' }).waitFor();
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-2b-confirm-mobile.png') });
        const yes = page.getByRole('button', { name: 'Yes, that is me' });
        check((await yes.boundingBox()).height >= 44, 'the buttons are big enough to tap');
        await yes.tap();
        await page.waitForTimeout(1000);
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-3a-welcome-mobile.png') });
        await page.waitForSelector('.fv-root', { state: 'detached', timeout: 8000 });
        await treeReady(page); await page.waitForTimeout(700);
        const pos = await H.cardAt(page, 'daniel-hartley-2');
        check(pos && pos.x > 0.15 && pos.x < 0.85 && pos.y > 0.1 && pos.y < 0.9, 'the tree opens on the visitor on a phone', JSON.stringify(pos));
        check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'the personalised tree does not scroll sideways');
        await page.waitForTimeout(5500);
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-3-personalised-tree-mobile.png') });
        const chip = await page.locator('.fv-chip').boundingBox();
        check(chip && chip.x >= 0 && chip.x + chip.width <= 390, 'the control fits in the phone\'s navigation bar', JSON.stringify(chip));
        await page.locator('.fv-chip').tap();
        const menu = await page.locator('.fv-menu').boundingBox();
        check(menu && menu.x >= 0 && menu.x + menu.width <= 390, 'and its menu fits on the screen', JSON.stringify(menu));
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-5-menu-mobile.png') });
        await c.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('Reduced motion');
    {
        const c = await ctx({ reducedMotion: 'reduce' }), page = await open(c, 'visitor');
        await page.waitForSelector('.fv-root');
        const anim = await page.evaluate(() => getComputedStyle(document.querySelector('.fv-root')).animationName);
        check(anim === 'none', 'the question does not animate', anim);
        await page.fill('#fv-input', 'kate'); await page.locator('.fv-opt').first().click();
        await page.getByRole('button', { name: 'Yes, that is me' }).click();
        await page.waitForSelector('.fv-root', { state: 'detached', timeout: 1500 });
        check(true, 'there is no welcome animation: the page opens at once');
        await treeReady(page);
        check(JSON.parse(await stored(page, KEY('/'))).id === 'kate-hartley', 'and the choice still counts');
        await c.close();
    }

    // ---------------------------------------------------------------------------------------------
    section('Matching, in Node');
    {
        const M = require(path.join(sites.visitor, 'engine', fs.readdirSync(path.join(sites.visitor, 'engine'))[0], 'visitor-match.js'));
        check(M.fold('Zoë  O’Brien-Smith') === 'zoe obrien smith', 'names are folded: accents, apostrophes, hyphens, spaces');
        check(M.distance('daniel', 'danial', 2) === 1 && M.distance('daniel', 'dainel', 2) === 1 && M.distance('abc', 'xyz', 1) > 1, 'edit distance counts a swap as one change');
        const P = [{ id: 'a', displayName: 'Ann Lee', givenNames: 'Ann', surname: 'Lee', nameVariants: [{ name: 'Ann Cole', note: 'maiden name' }] }, { id: 'b', displayName: 'Anna Lees', givenNames: 'Anna', surname: 'Lees' }];
        check(M.search(P, 'ann lee')[0].person.id === 'a', 'the exact name ranks first');
        check(M.search(P, 'cole')[0].via.note === 'maiden name', 'a maiden name is found and reported');
        check(M.search(P, '').length === 2 && M.search([], 'x').length === 0, 'empty input and an empty list are safe');
    }

    check(!errors.length, 'no script errors on any page', errors.slice(0, 3).join(' | '));
    await browser.close();
    for (const k of Object.keys(srv)) await srv[k].close();
    console.log('\n' + (H.state.failures ? H.state.failures + ' FAILED' : 'all passed'));
    process.exit(H.state.failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
