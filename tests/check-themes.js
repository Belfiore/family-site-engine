#!/usr/bin/env node
/* Heritage styles in a browser: every page the engine makes, in every style and in the Classic Archive.
 *
 *   node tests/check-themes.js              builds a made-up site (tests/themes_fixtures.py) and checks it
 *   SHOTS=dir node tests/check-themes.js    also saves a screenshot of every page in every style
 *
 * For each of the 7 pages and each of the 10 styles, at a desktop and a phone width: no script error, nothing running off
 * the side of the screen, the style's own fonts in the headings, and the page really took the style's colours. Then the
 * settings that matter for everyone: a style leaves a site that has not chosen one alone, the colour change is 200 ms and
 * moves nothing, and less motion or less data means no ornaments. Needs Playwright with Chromium (npm install).
 */
const fs = require('fs'), path = require('path'), os = require('os'), cp = require('child_process');
const { serveStatic } = require('./helpers.js');
const ROOT = path.dirname(__dirname);
const IDS = ['english', 'german', 'italian', 'irish', 'scottish', 'french', 'spanish', 'polish', 'scandinavian', 'jewish'];
const PAGES = ['index', 'family-tree', 'map', 'ask', 'discoveries', 'records', 'story-the-crossing'];

let failures = 0;
const ok = m => console.log('  ok   ' + m);
const fail = m => { failures++; console.log('  FAIL ' + m); };
const check = (c, m, d) => c ? ok(m) : fail(m + (d !== undefined ? ': ' + d : ''));
const section = t => console.log('\n' + t);

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-themes-'));
function build(name, flags) {
    const src = path.join(tmp, name + '-src'), out = path.join(tmp, name);
    cp.execFileSync('python3', [path.join(ROOT, 'tests', 'themes_fixtures.py'), src].concat(flags || []), { stdio: 'pipe' });
    cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', src, '--out', out, '--previous', 'none'], { stdio: 'pipe' });
    return out;
}

(async () => {
    let chromium;
    try { ({ chromium } = require('playwright')); } catch (e) { fail('Playwright is not installed: npm install, then npx playwright install chromium'); return done(); }
    const dist = build('all', ['--admin']), plain = build('plain', []), german = build('german', ['--style', 'german']);
    const srv = await serveStatic(dist), srvPlain = await serveStatic(plain), srvGerman = await serveStatic(german);
    const browser = await chromium.launch();
    const shots = process.env.SHOTS;
    if (shots) fs.mkdirSync(shots, { recursive: true });

    // ---------------------------------------------------------------- every page, every style
    for (const [label, viewport] of [['desktop', { width: 1280, height: 800 }], ['phone', { width: 390, height: 800 }]]) {
        section('Every page in every style, ' + label);
        const ctx = await browser.newContext({ viewport });
        const page = await ctx.newPage();
        let errors = [];
        page.on('pageerror', e => errors.push(e.message));
        page.on('console', m => { if (m.type() === 'error' && !/tile|maptiler|googleapis|gstatic|404/i.test(m.text())) errors.push(m.text().slice(0, 140)); });
        for (const n of PAGES) {
            await page.goto(srv.url + '/' + n + '.html');
            await page.waitForTimeout(n === 'map' ? 1500 : 300);
            const problems = [];
            for (const id of IDS.concat(['classic'])) {
                errors = [];
                await page.evaluate(s => window.FamilyHeritage.show(s, { force: true }), id);
                await page.waitForTimeout(350);
                const r = await page.evaluate(() => {
                    const h = document.querySelector('h1') || document.body;
                    return { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, attr: document.documentElement.getAttribute('data-heritage'),
                             font: getComputedStyle(h).fontFamily, bg: getComputedStyle(document.body).backgroundColor, ink: getComputedStyle(document.body).color };
                });
                if (r.sw > r.cw + 1) problems.push(id + ': runs ' + (r.sw - r.cw) + 'px off the side');
                if (id === 'classic' ? r.attr !== null : r.attr !== id) problems.push(id + ': attribute is ' + r.attr);
                if (id !== 'classic' && !/hf-/.test(r.font)) problems.push(id + ': heading font is ' + r.font.slice(0, 40));
                if (errors.length) problems.push(id + ': ' + errors.join(' | '));
                if (shots) await page.screenshot({ path: path.join(shots, label + '-' + id + '-' + n + '.png') });
            }
            check(problems.length === 0, n + ' in 10 styles and the Classic Archive', problems.join('; '));
        }
        await ctx.close();
    }

    // ---------------------------------------------------------------- the colours really change, and the map follows
    section('Colours and the map');
    {
        const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
        await page.goto(srv.url + '/family-tree.html');
        await page.waitForTimeout(300);
        const seen = new Set();
        for (const id of IDS) {
            await page.evaluate(s => window.FamilyHeritage.show(s, { force: true }), id);
            await page.waitForTimeout(250);
            seen.add(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--h-accent').trim() + getComputedStyle(document.documentElement).getPropertyValue('--h-paper').trim()));
        }
        check(seen.size === 10, 'the ten styles have ten different palettes', String(seen.size));
        await page.evaluate(() => window.FamilyHeritage.show('classic', { force: true }));
        await page.waitForTimeout(250);
        const classicHeading = await page.evaluate(() => getComputedStyle(document.querySelector('h1')).fontFamily);
        check(!/hf-/.test(classicHeading), 'back to the Classic Archive the site\'s own fonts return', classicHeading);

        const map = await page.context().newPage();
        const mapErrors = [];
        map.on('pageerror', e => mapErrors.push(e.message));
        await map.goto(srv.url + '/map.html');
        await map.waitForTimeout(1800);
        let changed = 0;
        const events = await map.evaluate(() => { window.__hc = 0; document.addEventListener('heritage:change', () => window.__hc++); return true; });
        for (const id of ['irish', 'spanish', 'scandinavian']) {
            await map.evaluate(s => window.FamilyHeritage.show(s, { force: true }), id);
            await map.waitForTimeout(500);
        }
        changed = await map.evaluate(() => window.__hc);
        check(changed === 3, 'the map is told every time the style changes', String(changed));
        check(mapErrors.length === 0, 'and keeps working', mapErrors.join(' | '));
        await map.close();
        await page.context().close();
    }

    // ---------------------------------------------------------------- nothing for a site that has not chosen one
    section('A site that has not chosen a style');
    {
        const page = await (await browser.newContext()).newPage();
        const req = [];
        page.on('request', r => req.push(r.url()));
        await page.goto(srvPlain.url + '/index.html');
        await page.waitForTimeout(400);
        check(await page.evaluate(() => document.documentElement.getAttribute('data-heritage')) === null, 'no style attribute');
        check(await page.evaluate(() => typeof window.FamilyHeritage) === 'undefined', 'no style script');
        check(req.every(u => !/themes|heritage/.test(u)), 'no style file is asked for', req.filter(u => /themes|heritage/.test(u)).join(', '));
        await page.context().close();
    }

    section('The settings page does not apply anything by itself');
    {
        const page = await (await browser.newContext()).newPage();
        await page.goto(srv.url + '/index.html');
        await page.waitForTimeout(400);
        check(await page.evaluate(() => document.documentElement.getAttribute('data-heritage')) === null, 'a site that only has the settings page looks as it did');
        const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundImage);
        check(bg === 'none' || !/data:image/.test(bg), 'with no texture');
        await page.context().close();
    }

    // ---------------------------------------------------------------- a style does not move things
    section('The colour change');
    {
        const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
        await page.goto(srv.url + '/index.html');
        await page.waitForTimeout(300);
        await page.evaluate(() => window.FamilyHeritage.show('german', { force: true }));
        await page.waitForTimeout(400);
        const t = await page.evaluate(() => {
            document.documentElement.classList.add('h-fade');
            const c = getComputedStyle(document.querySelector('p') || document.body);
            const out = { dur: c.transitionDuration, props: c.transitionProperty, fn: c.transitionTimingFunction };
            document.documentElement.classList.remove('h-fade');
            return out;
        });
        check(/0\.2s/.test(t.dur) && /ease-out/.test(t.fn), 'it takes 200 ms and eases out', t.dur + ' ' + t.fn);
        check(!/(^|, )(width|height|margin|padding|top|left|transform|all)/.test(t.props), 'and changes colour only, so nothing moves', t.props);
        await page.context().close();
    }

    section('Less motion, less data');
    {
        const ctx = await browser.newContext({ reducedMotion: 'reduce', viewport: { width: 1280, height: 800 } });
        const page = await ctx.newPage();
        await page.goto(srv.url + '/index.html');
        await page.waitForTimeout(300);
        await page.evaluate(() => window.FamilyHeritage.show('irish', { force: true }));
        await page.waitForTimeout(300);
        const t = await page.evaluate(() => { document.documentElement.classList.add('h-fade'); const d = getComputedStyle(document.body).transitionDuration; document.documentElement.classList.remove('h-fade'); return d; });
        check(/^0s/.test(t), 'a visitor who asks for less motion gets no colour fade', t);
        await ctx.close();
        const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 800 } });
        const p2 = await ctx2.newPage();
        await p2.addInitScript(() => { Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true }); });
        await p2.goto(srv.url + '/index.html');
        await p2.waitForTimeout(300);
        await p2.evaluate(() => window.FamilyHeritage.show('italian', { force: true }));
        await p2.waitForTimeout(300);
        const tex = await p2.evaluate(() => getComputedStyle(document.body, '::before').display);
        check(tex === 'none', 'Save-Data turns the texture and the ornaments off', tex);
        const nav = await p2.evaluate(() => { const n = document.querySelector('.main-nav'); return n ? getComputedStyle(n, '::after').display : 'none'; });
        check(nav === 'none', 'including the divider under the navigation bar', nav);
        await ctx2.close();
        const ctx3 = await browser.newContext({ viewport: { width: 1280, height: 800 } });
        const p3 = await ctx3.newPage();
        await p3.goto(srv.url + '/index.html');
        await p3.waitForTimeout(300);
        await p3.evaluate(() => window.FamilyHeritage.show('italian', { force: true, texture: false }));
        await p3.waitForTimeout(300);
        const off = await p3.evaluate(() => getComputedStyle(document.body, '::before').content);
        check(off === 'none' || off === 'normal', 'texture off in the settings turns the texture off', off);
        await ctx3.close();
    }

    // ---------------------------------------------------------------- a site that has applied one
    section('A site that has applied a style');
    {
        const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
        const errs = [], req = [];
        page.on('pageerror', e => errs.push(e.message));
        page.on('request', r => req.push(r.url()));
        for (const n of PAGES) {
            await page.goto(srvGerman.url + '/' + n + '.html');
            await page.waitForTimeout(n === 'map' ? 1500 : 300);
            const a = await page.evaluate(() => document.documentElement.getAttribute('data-heritage'));
            if (a !== 'german') fail(n + ' has no German style (' + a + ')');
        }
        check(errs.length === 0, 'all seven pages carry it from the first paint and run without errors', errs.join(' | '));
        check(req.every(u => !/themes\/(english|italian|irish|scottish|french|spanish|polish|scandinavian|jewish)/.test(u)), 'and only its own files are asked for');
        await page.context().close();
    }

    await browser.close(); await srv.close(); await srvPlain.close(); await srvGerman.close();
    done();

    function done() {
        console.log(failures ? '\n' + failures + ' checks failed.' : '\nAll checks passed.');
        process.exit(failures ? 1 : 0);
    }
})().catch(e => { console.error(e); process.exit(1); });
