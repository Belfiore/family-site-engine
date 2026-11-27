/* Checks for the Discovery Timeline page, in a browser, against the made-up family in tests/timeline_fixtures.py.
 *
 *   node tests/check-timeline.js                 builds seven publications one after another, then checks the last
 *   SHOTS=dir node tests/check-timeline.js       also saves screenshots (desktop and phone) to dir
 *   DIST=path node tests/check-timeline.js       checks a build that is already made (a real site's, say). Only the
 *                                                checks that do not depend on the made-up data run: no JavaScript,
 *                                                links, banner, filters, and the phone layout.
 *
 * Needs Node 18 or later and Playwright with Chromium (npm install, then npx playwright install chromium).
 * The clock is fixed at 26 November 2026 so the dates read the same on every day this is run.
 */
const fs = require('fs'), path = require('path'), http = require('http'), os = require('os'), cp = require('child_process');
const ROOT = path.dirname(__dirname);
const NOW = new Date('2026-11-26T18:00:00Z');

let failures = 0;
const ok = m => console.log('  ok   ' + m);
const fail = m => { failures++; console.log('  FAIL ' + m); };
const check = (c, m, detail) => c ? ok(m) : fail(m + (detail !== undefined ? ': ' + detail : ''));
const section = t => console.log('\n' + t);

// ------------------------------------------------------------------ the publications
let DIST = process.env.DIST, MADE_UP = false;
if (!DIST) {
    MADE_UP = true;
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-timeline-'));
    const src = path.join(tmp, 'src');
    cp.execFileSync('python3', [path.join(ROOT, 'tests', 'timeline_fixtures.py'), src], { stdio: 'pipe' });
    const versions = fs.readdirSync(src).filter(n => /^v\d+$/.test(n)).sort((a, b) => a.slice(1) - b.slice(1));
    const when = JSON.parse(cp.execFileSync('python3', ['-c', 'import sys, json; sys.path.insert(0, "tests"); import timeline_fixtures as F; print(json.dumps({n: t for n, t, _ in F.VERSIONS}))'], { cwd: ROOT }).toString());
    let prev = 'none';
    for (const v of versions) {
        const out = path.join(tmp, 'out', v);
        cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', path.join(src, v), '--out', out, '--previous', prev, '--now', when[v]], { stdio: 'pipe' });
        prev = out;
    }
    DIST = prev;
}
DIST = path.resolve(DIST);
const HISTORY = JSON.parse(fs.readFileSync(path.join(DIST, 'discoveries', 'history.json'))).entries;
const PAGE = JSON.parse(fs.readFileSync(path.join(DIST, 'engine-build.json'))).timeline.file;
const KEY = 'fse-timeline-visit:/' + PAGE;
const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
const newerThan = iso => HISTORY.filter(e => Date.parse(e.published) > Date.parse(iso));

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };
function serve() {
    return new Promise(res => {
        const srv = http.createServer((req, rsp) => {
            let p = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
            if (p.endsWith('/')) p += 'index.html';
            const f = path.join(DIST, p);
            if (!f.startsWith(DIST) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { rsp.writeHead(404); return rsp.end('not found'); }
            rsp.writeHead(200, { 'content-type': TYPES[path.extname(f).toLowerCase()] || 'application/octet-stream' });
            fs.createReadStream(f).pipe(rsp);
        });
        srv.listen(0, '127.0.0.1', () => res(srv));
    });
}

(async () => {
    let chromium;
    try { ({ chromium } = require('playwright')); } catch (e) { fail('Playwright is not installed: npm install, then npx playwright install chromium'); return done(); }
    const srv = await serve();
    const URL = 'http://127.0.0.1:' + srv.address().port + '/';
    const browser = await chromium.launch();
    const PHONE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
    const DESKTOP = { viewport: { width: 1280, height: 900 } };

    async function open(opts, visit) {
        const ctx = await browser.newContext(Object.assign({}, DESKTOP, opts || {}));
        await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
        const page = await ctx.newPage();
        page.errors = [];
        page.on('pageerror', e => page.errors.push(e.message));
        // requests to other sites (web fonts, say) are refused above on purpose, so their failure is not the page's
        page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource: net::ERR_FAILED/.test(m.text())) page.errors.push(m.text()); });
        if (opts && opts.javaScriptEnabled === false) { await page.goto(URL + PAGE); return page; }
        await page.clock.install({ time: NOW });
        if (visit) {
            // a returning visitor: the earlier visit is in the browser's storage before the page runs
            await page.goto(URL + 'index.html');
            await page.evaluate(([k, v]) => localStorage.setItem(k, v), [KEY, visit]);
        }
        await page.goto(URL + PAGE);
        await page.waitForSelector('.tl-root');
        await page.waitForTimeout(150);
        return page;
    }
    const shot = async (page, name, full) => { if (process.env.SHOTS) { fs.mkdirSync(process.env.SHOTS, { recursive: true }); await page.screenshot({ path: path.join(process.env.SHOTS, 'timeline-' + name + '.png'), fullPage: !!full }); } };
    const visible = (page, sel) => page.$$eval(sel, els => els.filter(e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return s.display !== 'none' && s.visibility !== 'hidden' && !e.hidden && !e.closest('[hidden]') && (r.width || r.height); }).length);

    // ---------------------------------------------------------------- without JavaScript
    section('Without JavaScript the whole page is there');
    {
        const page = await open({ javaScriptEnabled: false });
        const n = await page.locator('.tl-card').count();
        check(n === HISTORY.length, 'every find is in the page (' + HISTORY.length + ')', String(n));
        check(await visible(page, '.tl-card') === HISTORY.length, 'and every one is showing, with none folded away');
        check(await visible(page, '#tlBanner, #tlFilters, .tl-more') === 0, 'the banner, filters and "show all" buttons do nothing without a script, so they are not shown');
        check(await page.locator('h1').count() === 1 && await page.locator('nav.main-nav').count() === 1, 'one heading and one navigation bar');
        await page.context().close();
    }

    // ---------------------------------------------------------------- a first visit
    section('A first visit');
    {
        const page = await open();
        check(await visible(page, '#tlBanner') === 0, 'no "new since" banner: there is no earlier visit to compare with');
        check(await page.locator('.tl-card.is-new').count() === 0, 'nothing is marked new');
        const stored = await page.evaluate(k => localStorage.getItem(k), KEY);
        check(Math.abs(Date.parse(stored) - NOW.getTime()) < 5000, 'the visit is remembered in this browser only', String(stored));
        const cookies = await page.context().cookies();
        check(cookies.length === 0, 'no cookies are set');
        check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        await shot(page, 'desktop-first-visit');
        await page.context().close();
    }

    // ---------------------------------------------------------------- links: one action per find, source addresses, pictures
    section('Finds: one action link at most, never on the headline; sources and pictures are links');
    {
        const page = await open();
        const bad = await page.$$eval('.tl-card', cs => cs.filter(c => c.querySelectorAll('a.tl-action').length > 1).map(c => c.id));
        check(!bad.length, 'no find has more than one link into the tree or the map', bad.join(', '));
        const headlineLinks = await page.locator('.tl-headline a, a .tl-headline').count();
        check(headlineLinks === 0, 'no headline is a link');
        const links = await page.$$eval('.tl-card a.tl-action', as => as.map(a => a.getAttribute('href') + '|' + a.textContent.trim()));
        check(links.every(l => /^(family-tree\.html#\/person\/[a-z0-9-]+|map\.html\?(place|person)=[a-z0-9-]+)\|(See it in the tree|Show on the map)$/.test(l)), 'every such link is to one person or place, in words that say where', links.find(l => !/^(family-tree|map)\.html/.test(l)));
        const other = await page.$$eval('.tl-card a:not(.tl-action):not(.tl-thumb-link):not(.tl-source)', as => as.length);
        const inSource = await page.$$eval('.tl-card .tl-source a', as => as.length);
        check(other === inSource, 'the only other links are a source and a picture');
        // a source address opens in a new tab, and cannot reach back into this page
        const src = await page.$$eval('.tl-card a.tl-source, .tl-card .tl-source a', as => as.map(a => ({ href: a.getAttribute('href'), target: a.target, rel: a.rel })));
        check(src.length > 0 && src.every(a => /^https?:\/\//.test(a.href) && a.target === '_blank' && /noopener/.test(a.rel)), 'a source address is a link that opens in a new tab with rel=noopener', JSON.stringify(src.filter(a => a.target !== '_blank')));
        const thumbs = await page.$$eval('.tl-card', cs => cs.map(c => ({ img: !!c.querySelector('img'), cls: c.classList.contains('tl-has-thumb'), alt: (c.querySelector('img') || {}).alt, link: !!c.querySelector('a.tl-thumb-link img') })));
        check(thumbs.every(t => t.img === t.cls), 'a picture only where a find has one');
        check(thumbs.filter(t => t.img).every(t => t.alt && t.alt.length > 3), 'each picture says what it shows');
        check(thumbs.filter(t => t.img).every(t => t.link), 'each picture is a link to the full-size image');
        // pictures below the fold are loaded lazily: ask for them all, wait, then look
        const broken = await page.$$eval('.tl-thumb', async is => {
            is.forEach(i => { i.loading = 'eager'; });
            await Promise.all(is.map(i => i.decode().catch(() => null)));
            return is.filter(i => !i.complete || i.naturalWidth === 0).length;
        });
        check(broken === 0, 'every picture loads');
        await page.context().close();
    }

    section('A picture opens full size');
    {
        const page = await open();
        const n = await page.locator('a.tl-thumb-link').count();
        if (!n) { check(!MADE_UP, 'there is a picture to open'); }
        else {
            const link = page.locator('a.tl-thumb-link:visible').first();
            await link.scrollIntoViewIfNeeded();
            const href = await link.getAttribute('href');
            const popups = [];
            page.context().on('page', p => popups.push(p));
            await link.click();
            const box = page.locator('.record-lightbox');
            check(await box.count() === 1, 'a click opens the lightbox (and no new tab)', String(await box.count()));
            check(popups.length === 0, 'the click does not also open a tab');
            const big = await box.locator('img').getAttribute('src');
            check(big === href, 'the lightbox shows the full-size file the link names', big + ' vs ' + href);
            await page.waitForFunction(() => { const i = document.querySelector('.record-lightbox img'); return i && i.complete && i.naturalWidth > 0; });
            const fits = await box.locator('img').evaluate(i => { const r = i.getBoundingClientRect(); return r.width <= innerWidth && r.height <= innerHeight; });
            check(fits, 'the full-size picture fits on the screen');
            check(await box.getAttribute('role') === 'dialog' && await box.getAttribute('aria-modal') === 'true', 'the lightbox is a modal dialog for a screen reader');
            await page.keyboard.press('Escape');
            check(await page.locator('.record-lightbox').count() === 0, 'Escape closes it');
            check(await link.evaluate(a => document.activeElement === a), 'focus goes back to the picture');
            await link.click();
            await page.locator('.record-lightbox').click();
            check(await page.locator('.record-lightbox').count() === 0, 'a click closes it');
            // a modified click keeps its normal meaning: it opens the picture in its own tab
            await link.click({ modifiers: ['Control'] });
            check(await page.locator('.record-lightbox').count() === 0, 'a ctrl-click does not open the lightbox');
            check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        }
        await page.context().close();
    }

    section('Confidence is not on the page, and is still in the data');
    {
        const page = await open();
        check(await page.locator('.tl-conf').count() === 0, 'no find shows Confirmed, Probable, Family tradition or Unverified');
        if (MADE_UP) check(HISTORY.some(e => e.confidence), 'the history still has each find\'s confidence');
        await page.context().close();
    }

    // ---------------------------------------------------------------- since the last visit
    section('Since your last visit');
    {
        const visit = '2026-11-12T08:00:00Z';
        const want = newerThan(visit);
        const page = await open({}, visit);
        const text = await page.locator('#tlBannerText').textContent();
        check(await visible(page, '#tlBanner') === 1, 'the banner shows');
        check(text === plural(want.length, 'new find') + ' since your last visit on 12 Nov.', 'it counts finds published since, in plain words', text);
        check(await page.locator('.tl-card.is-new').count() === want.length, 'the new finds are marked (' + want.length + ')');
        check(await page.locator('.tl-card.is-new .tl-new-tag').count() === want.length, 'each says "New"');
        const firstNew = await page.$eval('.tl-card.is-new', c => c.id);
        await page.click('#tlJump');
        await page.waitForTimeout(700);
        const at = await page.evaluate(() => { const c = document.activeElement; const r = c.getBoundingClientRect(); return { id: c.id, top: Math.round(r.top), inView: r.top >= 0 && r.bottom <= innerHeight }; });
        check(at.id === firstNew && at.inView, 'the button jumps to the first new find and moves focus there', JSON.stringify(at));
        await shot(page, 'desktop-new-since');
        await page.reload();
        await page.waitForSelector('.tl-root');
        check(await page.locator('.tl-card.is-new').count() === want.length && await visible(page, '#tlBanner') === 1, 'a reload during the same visit keeps the marks');
        const again = await page.context().newPage();
        await again.clock.install({ time: NOW });
        await again.goto(URL + PAGE);
        await again.waitForSelector('.tl-root');
        check(await again.locator('.tl-card.is-new').count() === 0, 'a later visit, with the first one now remembered, starts clean');
        await page.context().close();
    }

    // ---------------------------------------------------------------- a first new find inside a folded day
    section('The jump reaches a new find inside a folded day');
    if (MADE_UP) {
        const page = await open({}, '2026-11-26T12:00:00Z');
        const want = newerThan('2026-11-26T12:00:00Z');
        check(await page.locator('.tl-card.is-new').count() === want.length && want.length === 3, 'the afternoon\'s three finds are new');
        const folded = await page.$eval('.tl-card.is-new', c => getComputedStyle(c).display === 'none');
        check(folded, 'the first of them starts out folded away behind "Show all"');
        const id = await page.$eval('.tl-card.is-new', c => c.id);
        await page.click('#tlJump');
        await page.waitForTimeout(700);
        const state = await page.evaluate(id => { const c = document.getElementById(id); const r = c.getBoundingClientRect(); return { shown: getComputedStyle(c).display !== 'none', inView: r.top >= 0 && r.bottom <= innerHeight, focused: document.activeElement === c, button: document.querySelector('.tl-day[data-date="2026-11-26"] .tl-more').textContent }; }, id);
        check(state.shown && state.inView && state.focused, 'the day opens and the find is in view and focused', JSON.stringify(state));
        check(state.button === 'Show fewer', 'the day\'s button now offers to fold it again', state.button);
        await page.context().close();
        const hash = await open();
        const last = await hash.$$eval('.tl-day[data-date="2026-11-26"] .tl-card', cs => cs[cs.length - 1].id);
        await hash.goto(URL + PAGE + '#' + last);
        await hash.waitForTimeout(500);
        check(await hash.evaluate(id => getComputedStyle(document.getElementById(id)).display !== 'none', last), 'a link to one find (#' + last + ') opens the day it is in');
        await hash.context().close();
    } else {
        ok('(skipped: needs the made-up data)');
    }

    // ---------------------------------------------------------------- folded days
    section('Busy days fold');
    {
        const page = await open();
        const busy = await page.$$eval('.tl-day', ds => ds.filter(d => d.querySelectorAll('.tl-card').length > 6).map(d => d.dataset.date));
        check(busy.length >= 1, 'a day with more than six finds is folded', busy.join(', '));
        for (const date of busy) {
            const total = await page.locator('.tl-day[data-date="' + date + '"] .tl-card').count();
            const sel = '.tl-day[data-date="' + date + '"]';
            check(await visible(page, sel + ' .tl-card') === 5, date + ': five show', String(await visible(page, sel + ' .tl-card')));
            check((await page.locator(sel + ' .tl-more').textContent()) === 'Show all ' + total + ' finds', date + ': the button says "Show all ' + total + ' finds"');
            await shot(page, 'desktop-folded-day');
            await page.click(sel + ' .tl-more');
            check(await visible(page, sel + ' .tl-card') === total && (await page.locator(sel + ' .tl-more').getAttribute('aria-expanded')) === 'true', date + ': it opens to all ' + total);
            await shot(page, 'desktop-day-open');
            await page.click(sel + ' .tl-more');
            check(await visible(page, sel + ' .tl-card') === 5, date + ': and folds again');
        }
        const quiet = await page.$$eval('.tl-day', ds => ds.filter(d => d.querySelectorAll('.tl-card').length <= 6 && d.querySelector('.tl-more') && !d.querySelector('.tl-more').hidden).length);
        check(quiet === 0, 'quiet days have no button');
        await page.context().close();
    }

    // ---------------------------------------------------------------- filters
    section('Filters');
    {
        const page = await open();
        check(await visible(page, '#tlFilters') === 1, 'the filters are there, closed');
        await page.click('#tlFilters summary');
        const lines = await page.$$eval('.tl-chips[data-filter="line"] .tl-chip', bs => bs.map(b => b.dataset.value));
        check(lines.length >= 3, 'a chip for each family line, and "All lines"', lines.join(','));
        const total = await page.locator('.tl-card').count();
        const line = lines[lines.length - 1];
        const expected = HISTORY.filter(e => (e.lines || []).includes(line)).length;
        await shot(page, 'desktop-filters-open');
        await page.click('.tl-chips[data-filter="line"] .tl-chip[data-value="' + line + '"]');
        check(await visible(page, '.tl-card') === expected, 'one line: ' + expected + ' finds, the rest hidden', String(await visible(page, '.tl-card')));
        const labels = await page.$$eval('.tl-day:not([hidden]) .tl-summary', ss => ss.map(s => s.textContent));
        check(labels.every(l => /^\d+ new finds? in .+\.$/.test(l)), 'each day\'s sentence is written again for what is showing', labels[0]);
        const sum = labels.reduce((n, l) => n + parseInt(l, 10), 0);
        check(sum === expected, 'and the numbers add up', sum + ' vs ' + expected);
        check(await visible(page, '.tl-day') === await page.$$eval('.tl-day:not([hidden])', d => d.length), 'days with nothing left are gone');
        check((await page.locator('#tlFilters').getAttribute('data-active')) !== null, 'the closed filter bar shows that one is on');
        await shot(page, 'desktop-filtered');
        const type = await page.$$eval('.tl-chips[data-filter="type"] .tl-chip', bs => bs.map(b => b.dataset.value));
        check(type.length > 2, 'a chip for each type of find that exists', type.join(','));
        await page.click('.tl-chips[data-filter="type"] .tl-chip[data-value="place"]');
        check(await visible(page, '#tlEmpty') === 1 && await visible(page, '.tl-card') === 0, 'a combination with no finds says so');
        await page.click('.tl-chips[data-filter="line"] .tl-chip[data-value=""]');
        await page.click('.tl-chips[data-filter="type"] .tl-chip[data-value="place"]');
        const placeCount = HISTORY.filter(e => e.type === 'place').length;
        check(await visible(page, '.tl-card') === placeCount, 'type alone: ' + placeCount, String(await visible(page, '.tl-card')));
        await page.click('.tl-chips[data-filter="type"] .tl-chip[data-value=""]');
        check(await visible(page, '.tl-card') === total - (await page.$$eval('.tl-extra.is-folded', e => e.length)), 'clearing both brings every find back (folded days fold again)');
        check((await page.locator('#tlFilters').getAttribute('data-active')) === null, 'and the filter bar stops saying a filter is on');
        const pressed = await page.$$eval('.tl-chip[aria-pressed="true"]', b => b.length);
        check(pressed === 2, 'chips tell assistive technology which are pressed', String(pressed));
        await page.context().close();
    }

    // ---------------------------------------------------------------- the phone
    section('On a phone');
    {
        const page = await open(PHONE, '2026-11-12T08:00:00Z');
        const w = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: innerWidth }));
        check(w.scroll <= w.width, 'nothing runs off the side of the screen', JSON.stringify(w));
        await shot(page, 'phone-new-since');
        const small = await page.$$eval('.tl-more, .tl-chip, .tl-banner-go, .tl-action', els => els.filter(e => e.offsetParent !== null && e.getBoundingClientRect().height < 40).length);
        check(small === 0, 'every button and link is at least 40 pixels tall to tap', String(small));
        await page.evaluate(() => document.querySelector('.tl-day:nth-child(2)').scrollIntoView());
        await page.evaluate(() => window.scrollBy(0, 300));
        await page.waitForTimeout(200);
        const pos = await page.evaluate(() => {
            const nav = document.querySelector('.main-nav').getBoundingClientRect();
            const heads = [...document.querySelectorAll('.tl-day-head')].map(h => h.getBoundingClientRect()).filter(r => r.top < innerHeight && r.bottom > 0);
            return { navBottom: Math.round(nav.bottom), stuck: heads.some(r => Math.abs(r.top - nav.bottom) <= 1), n: heads.length, style: getComputedStyle(document.querySelector('.tl-day-head')).position };
        });
        check(pos.style === 'sticky' && pos.stuck, 'the date header sticks under the navigation bar while its day scrolls', JSON.stringify(pos));
        await shot(page, 'phone-sticky-date');
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.click('#tlFilters summary');
        await shot(page, 'phone-filters');
        await page.click('#tlFilters summary');
        if (MADE_UP) {
            await page.evaluate(() => document.querySelector('.tl-day[data-date="2026-11-26"]').scrollIntoView());
            await page.evaluate(() => window.scrollBy(0, 200));
            await shot(page, 'phone-folded-day');
        }
        await page.context().close();
    }

    section('Without a visit, with images, and with the type filter: the page throws nothing');
    {
        const page = await open(DESKTOP);
        check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        await page.context().close();
    }

    await browser.close();
    srv.close();
    done();
})().catch(e => { console.error(e); failures++; done(); });

function done() {
    console.log('\n' + (failures ? failures + ' check(s) failed' : 'All checks passed'));
    process.exit(failures ? 1 : 0);
}
