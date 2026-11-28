/* Checks for languages in a browser, against made-up sites built from the sample family (tests/i18n_fixtures.py).
 *
 *   node tests/check-i18n.js               builds the sites it needs into a temporary folder, then checks them
 *   SHOTS=dir node tests/check-i18n.js     also saves screenshots to dir
 *
 * Needs Node 18 or later and Playwright with Chromium. Nothing off the machine is reached; the checks fail if the page tries.
 */
const fs = require('fs'), path = require('path'), cp = require('child_process');
const { chromium } = require('playwright');
const H = require('./helpers');
const { check, section } = H;
const SHOTS = process.env.SHOTS && path.resolve(process.env.SHOTS);
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const DIR = path.join(H.ROOT, 'engine', 'i18n');
const EN = JSON.parse(fs.readFileSync(path.join(DIR, 'en.json'), 'utf8'));
const DE = JSON.parse(fs.readFileSync(path.join(DIR, 'de.json'), 'utf8'));
const KEY = 'fse-language';
const STORY_DE = 'Dieser Text steht nur in der deutschen Fassung.';

function fixture(tmp, name, flags) {
    const src = path.join(tmp, name + '-src'), out = path.join(tmp, name);
    cp.execFileSync('python3', [path.join(H.ROOT, 'tests', 'i18n_fixtures.py'), src].concat(flags || []), { stdio: 'pipe' });
    cp.execFileSync('python3', [path.join(H.ROOT, 'build', 'build_site.py'), '--site', src, '--out', out], { stdio: 'pipe' });
    return out;
}

// the Discovery Timeline needs a history, so the seven made-up publications are built one after another (as check-timeline.js does)
function timelineSite(tmp) {
    const src = path.join(tmp, 'tl-src');
    cp.execFileSync('python3', [path.join(H.ROOT, 'tests', 'timeline_fixtures.py'), src], { stdio: 'pipe' });
    const versions = fs.readdirSync(src).filter(n => /^v\d+$/.test(n)).sort((a, b) => a.slice(1) - b.slice(1));
    const when = JSON.parse(cp.execFileSync('python3', ['-c', 'import sys, json; sys.path.insert(0, "tests"); import timeline_fixtures as F; print(json.dumps({n: t for n, t, _ in F.VERSIONS}))'], { cwd: H.ROOT }).toString());
    let prev = 'none';
    for (const v of versions) {
        const cfgPath = path.join(src, v, 'site.config.json');
        const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
        cfg.language = { default: 'en', available: ['en', 'de'] };
        fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 1));
        const out = path.join(tmp, 'tl-out', v);
        cp.execFileSync('python3', [path.join(H.ROOT, 'build', 'build_site.py'), '--site', path.join(src, v), '--out', out, '--previous', prev, '--now', when[v]], { stdio: 'pipe' });
        prev = out;
    }
    return prev;
}

(async () => {
    const tmp = H.tmpdir('engine-i18n-');
    const sites = {
        plain: H.buildSample(tmp),                                    // the sample as it is: English only
        both: fixture(tmp, 'both'),                                   // English by default, German available
        german: fixture(tmp, 'german', ['--only', 'de']),             // German only
        deDefault: fixture(tmp, 'dedefault', ['--default', 'de']),    // German by default, English available
        visitor: fixture(tmp, 'visitor', ['--visitor']),              // two languages and "Who are you?"
        timeline: timelineSite(tmp),                                  // two languages and the Discovery Timeline
    };
    const srv = {};
    for (const k of Object.keys(sites)) srv[k] = await H.serveStatic(sites[k]);
    const browser = await chromium.launch();
    const external = [], errors = [];
    async function open(key, p, init) {
        const c = await browser.newContext({ viewport: { width: 1280, height: 800 } });
        // the map asks for its tiles and style from the net (refused here, as in the other checks); that is not language work
        c.on('request', r => { if (!/^(http:\/\/127\.0\.0\.1|data:|blob:|https:\/\/tiles\.openfreemap\.org\/)/.test(r.url())) external.push(r.url()); });
        await c.route(u => !/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(u.href), r => r.abort());
        const page = await c.newPage();
        page.on('pageerror', e => errors.push(key + p + ': ' + e.message));
        if (init) await page.addInitScript(init.fn, init.arg);
        await page.goto(srv[key].url + p, { waitUntil: 'load' });
        return page;
    }
    const lang = page => page.evaluate(() => document.documentElement.getAttribute('lang'));
    const stored = page => page.evaluate(k => { try { return localStorage.getItem(k); } catch (e) { return 'error'; } }, KEY);
    const navText = page => page.locator('.nav-links a').allTextContents().then(a => a.map(s => s.trim()));
    const store = l => ({ fn: v => { try { localStorage.setItem('fse-language', v); } catch (e) { /* none */ } }, arg: l });
    const treeReady = page => page.waitForFunction(() => document.documentElement.classList.contains('tc-ready'));
    const drawer = async (page, id) => {
        await page.evaluate(id => { location.hash = '#/person/' + id; }, id);
        await page.waitForSelector('#drawer:not([hidden]) .tc-drawer-body *', { timeout: 8000 });
        await page.waitForTimeout(400);
        return page.evaluate(() => document.getElementById('drawer').innerText);
    };

    section('An English-only site: nothing changes');
    {
        const page = await open('plain', '/family-tree.html', store('de'));
        check(await page.locator('.lang-switch').count() === 0, 'no switcher');
        check(await lang(page) === 'en-GB', 'the html lang is the site\'s own', await lang(page));
        check((await navText(page)).includes('Family Tree') && !(await navText(page)).includes('Stammbaum'), 'a saved German choice is ignored where German is not offered');
        check((await page.locator('h1').first().textContent()).trim() === EN['tree.heading'], 'the tree heading is the English words');
        await page.context().close();
    }

    section('Two languages: the switcher');
    {
        const page = await open('both', '/family-tree.html');
        const sw = page.locator('.lang-switch');
        check(await sw.count() === 1, 'one switcher in the header');
        check((await sw.locator('button').allTextContents()).map(s => s.trim()).join('|') === 'EN|DE', 'it reads EN | DE', await sw.textContent());
        check(await sw.locator('button[aria-pressed="true"]').textContent().then(s => s.trim()) === 'EN', 'English is pressed by default');
        check(await lang(page) === 'en-GB', 'the html lang stays English', await lang(page));
        check(await stored(page) === null, 'nothing is saved before a choice is made');
        check(!(await navText(page)).includes('Stammbaum'), 'the bar is in English');
        await page.locator('.lang-switch button', { hasText: 'DE' }).click();
        await page.waitForLoadState('load');
        await treeReady(page);
        check(await stored(page) === 'de', 'the choice is saved in localStorage', await stored(page));
        check(await lang(page) === 'de', '<html lang> follows the choice', await lang(page));
        const nav = await navText(page);
        check(nav.includes(DE['nav.tree']) && nav.includes('Die Moreaus') && nav.includes(DE['nav.ask']), 'the bar is in German, with the site\'s own German label', nav.join(','));
        check((await page.locator('h1').first().textContent()).trim() === DE['tree.heading'], 'the tree heading is German');
        check(await page.locator('.lang-switch button[aria-pressed="true"]').textContent().then(s => s.trim()) === 'DE', 'DE is pressed');
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'tree-de.png') });
        // the choice carries to the other pages and survives a reload
        await page.goto(srv.both.url + '/map.html', { waitUntil: 'load' });
        await page.waitForSelector('h1');
        check(await lang(page) === 'de', 'the map page is German too');
        check((await page.locator('h1').first().textContent()).trim() === DE['map.heading'], 'the map heading is German', await page.locator('h1').first().textContent());
        await page.goto(srv.both.url + '/ask.html', { waitUntil: 'load' });
        await page.waitForSelector('h1');
        check((await page.locator('h1').first().textContent()).trim() === DE['ask.heading'], 'the Stuart page is German');
        await page.goto(srv.both.url + '/index.html', { waitUntil: 'load' });
        check((await navText(page)).includes(DE['nav.home']), 'the home page bar is German');
        // and back
        await page.locator('.lang-switch button', { hasText: 'EN' }).click();
        await page.waitForLoadState('load');
        check(await stored(page) === 'en' && await lang(page) === 'en-GB', 'back to English restores the page language', await lang(page));
        check((await navText(page)).includes('Family Tree'), 'and the English bar');
        await page.context().close();
    }

    section('A saved choice beats the default');
    {
        const page = await open('deDefault', '/family-tree.html');
        check(await lang(page) === 'de', 'German by default: <html lang="de">');
        check((await navText(page)).includes(DE['nav.tree']), 'German bar without any choice');
        await page.locator('.lang-switch button', { hasText: 'EN' }).click();
        await page.waitForLoadState('load');
        check(await stored(page) === 'en' && (await navText(page)).includes('Family Tree'), 'a visitor can choose English over a German default');
        await page.context().close();
        const only = await open('german', '/family-tree.html', store('en'));
        check(await only.locator('.lang-switch').count() === 0 && await lang(only) === 'de', 'a German-only site has no switcher and ignores a saved English choice');
        await only.context().close();
    }

    section('Research content: translated fields and fallback');
    {
        const en = await open('both', '/family-tree.html', store('en'));
        await treeReady(en);
        let text = await drawer(en, 'thomas-hartley');
        check(text.includes('traded wool in Leeds for forty years') && !text.includes(STORY_DE), 'English: the story as written');
        check(text.includes('2 March 1912'), 'English: dates as written', text.slice(0, 200));
        await en.context().close();

        const de = await open('both', '/family-tree.html', store('de'));
        await treeReady(de);
        text = await drawer(de, 'thomas-hartley');
        check(text.includes(STORY_DE), 'German: story_de is shown');
        check(!text.includes('traded wool in Leeds for forty years'), 'German: the original story is not shown beside it');
        check(text.includes('2. März 1912'), 'German: 2. März 1912', text.slice(0, 300));
        check(!text.includes('2 March 1912'), 'German: no English date left');
        text = await drawer(de, 'mary-ann-briggs');
        check(text.includes('Mary Ann Briggs was born in Bradford'), 'German: a story with no story_de falls back to the original');
        check(/Daniels direkte Linie/i.test(text) && !/Daniel's direct line/i.test(text), 'German: the label from the data meta (directLineLabel_de) is used');
        check(text.includes('geborene Briggs, die Frau von Thomas'), 'German: her disambiguator_de is shown');
        if (SHOTS) await de.screenshot({ path: path.join(SHOTS, 'drawer-de.png') });
        await de.context().close();
    }

    section('The map and Stuart in German');
    {
        const page = await open('both', '/map.html', store('de'));
        await page.waitForSelector('.fm-chip, .fm-switch, #listOpen', { timeout: 10000 });
        await page.waitForTimeout(800);
        const body = await page.evaluate(() => document.body.innerText);
        const low = body.toLowerCase();          // some labels are set in capitals by the stylesheet
        check(low.includes(DE['map.modeExplore'].toLowerCase()) && low.includes(DE['map.timeline'].toLowerCase()), 'the map modes are German', body.slice(0, 200));
        check(!/Explore|Timeline mode/.test(body.split('\n').slice(0, 12).join(' ')), 'the top of the map has no English chrome');
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'map-de.png') });
        await page.context().close();
        const ask = await open('both', '/ask.html', store('de'));
        await ask.waitForTimeout(800);
        const t = await ask.evaluate(() => document.body.innerText);
        check(t.includes(DE['stuart.languageNote'] || DE['ask.heading']), 'Stuart\'s page shows the German note');
        await ask.context().close();
    }

    section('Who are you? in German');
    {
        const page = await open('visitor', '/family-tree.html', store('de'));
        await page.waitForSelector('.fv-title', { timeout: 10000 });
        check((await page.locator('.fv-title').first().textContent()).trim() === DE['visitor.question'], 'the question is German', await page.locator('.fv-title').first().textContent());
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, 'visitor-de.png') });
        await page.context().close();
        const en = await open('visitor', '/family-tree.html', store('en'));
        await en.waitForSelector('.fv-title', { timeout: 10000 });
        check((await en.locator('.fv-title').first().textContent()).trim() === EN['visitor.question'], 'and English when English is chosen');
        await en.context().close();
    }

    section('The Discovery Timeline in German');
    {
        const files = fs.readdirSync(sites.timeline).filter(f => /discover|timeline/i.test(f) && f.endsWith('.html'));
        const pageName = files[0];
        check(!!pageName, 'the timeline page is built', files.join(','));
        const en = await open('timeline', '/' + pageName, store('en'));
        await en.waitForSelector('h1');
        const enH = (await en.locator('h1').first().textContent()).trim();
        check(enH === EN['timeline.heading'], 'English heading', enH);
        await en.context().close();
        const de = await open('timeline', '/' + pageName, store('de'));
        await de.waitForSelector('h1');
        await de.waitForTimeout(800);
        const deH = (await de.locator('h1').first().textContent()).trim();
        check(deH === DE['timeline.heading'], 'German heading', deH);
        check(await lang(de) === 'de', 'html lang is de');
        const txt = await de.evaluate(() => document.body.innerText);
        check(/Donnerstag, 26\. November 2026/.test(txt), 'the day header is a German date', txt.slice(0, 300));
        check(/beginnt am 2\. November 2026/.test(txt), 'the start note has a German date');
        check(/Found Walter Ogden/.test(txt), 'finds written by the engine stay in English (docs/languages.md says so)');
        if (SHOTS) await de.screenshot({ path: path.join(SHOTS, 'timeline-de.png') });
        await de.context().close();
    }

    section('Nothing else');
    check(errors.length === 0, 'no script errors on any page', errors.join(' | '));
    check(external.length === 0, 'nothing off the machine was requested', external.join(', '));

    await browser.close();
    for (const k of Object.keys(srv)) await srv[k].close();
    fs.rmSync(tmp, { recursive: true, force: true });
    console.log(H.state.failures ? '\n' + H.state.failures + ' failed' : '\nall passed');
    process.exit(H.state.failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
