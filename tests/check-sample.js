/* Checks for the engine against the sample site: Stuart in Node, then every page in a browser.
 *
 *   node tests/check-sample.js              builds the sample into a temporary folder, then checks it
 *   DIST=path/to/_site node tests/check-sample.js   checks a build that is already made
 *   SHOTS=dir node tests/check-sample.js    also saves a screenshot of each page to dir
 *
 * Needs Node 18 or later and Playwright with Chromium (npm install, then npx playwright install chromium).
 * Map tiles and anything else off the machine are blocked, so the map runs on its own fallback map.
 */
const fs = require('fs'), path = require('path'), http = require('http'), os = require('os'), cp = require('child_process');
const ROOT = path.dirname(__dirname);

let DIST = process.env.DIST;
if (!DIST) {
    DIST = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'engine-sample-')), '_site');
    cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', path.join(ROOT, 'sample'), '--out', DIST], { stdio: 'inherit' });
}
DIST = path.resolve(DIST);
const BUILD = JSON.parse(fs.readFileSync(path.join(DIST, 'engine-build.json')));
const ENGINE = path.join(DIST, 'engine', BUILD.engine);

let failures = 0;
const ok = m => console.log('  ok   ' + m);
const fail = m => { failures++; console.log('  FAIL ' + m); };
const check = (c, m, detail) => c ? ok(m) : fail(m + (detail ? ': ' + detail : ''));
const section = t => console.log('\n' + t);

// ------------------------------------------------------------------ Stuart, in Node
section('Stuart, from the index the build made');
const Kin = require(path.join(ENGINE, 'archive-kin.js'));
const Core = require(path.join(ENGINE, 'archive-core.js'));
const man = JSON.parse(fs.readFileSync(path.join(DIST, 'archive', 'manifest.json')));
const kb = JSON.parse(fs.readFileSync(path.join(DIST, 'archive', man.kb)));
const A = Core.create(kb);
const plain = r => [].concat(r.paras, r.bullets || [], r.paras2 || [], r.after ? r.after.bullets : [], (r.list || []).map(x => A.nameOf(x.id) + ' ' + (x.note || '')), (r.choices || []).map(c => A.nameOf(c.id)))
    .join(' ').replace(/\{\{p:([a-z0-9-]+)\}\}/g, (m, id) => A.nameOf(id));
const QUESTIONS = [
    ["Who was Arthur Hartley's father?", ['William Hartley']],
    ['How was Thomas Hartley related to Grandpa Arthur?', ['grandfather']],
    ['Who came from France?', ['Jean-Baptiste Moreau']],
    ['How old was Arthur Hartley when he married?', ['28']],
    ['What did Henri Moreau do?', ['Tailor']],
    ['Where did Jean-Baptiste Moreau live?', ['Greek Street']],
    ["Who are Grandma Margot's grandchildren?", ['Daniel Hartley', 'Kate Hartley']],
    // living people are answered like anyone else
    ['Who is Daniel Hartley?', ['is living', 'Peter Hartley', 'Janet Hartley']],
    ['When was Susan Hartley born?', ['1938']],
    ['When did Susan Hartley die?', ['is living']],
    ['Who was Pierre Moreau?', ['Pierre Moreau']],
    // passage search, with a word the sample adds to Stuart's own (weaver is also silk)
    ['Where can I read about the weavers?', ['Moreau']],
];
QUESTIONS.forEach(([q, want]) => {
    const t = plain(A.ask(q, {}));
    const missing = want.filter(w => t.indexOf(w) < 0);
    check(!missing.length, q, 'missing ' + missing.join(', ') + ' in: ' + t.slice(0, 240));
});
const kin = Kin.create(kb.people);
check(kin.relate('daniel-hartley', 'arthur-hartley').label === 'grandfather', 'Arthur is Daniel\'s grandfather', kin.relate('daniel-hartley', 'arthur-hartley').label);
check(kin.relate('kate-hartley', 'daniel-hartley').label === '1st cousin', 'Kate and Daniel are first cousins', kin.relate('kate-hartley', 'daniel-hartley').label);
check(!kb.people.some(p => p.id === 'auguste-de-moreau'), 'the legend (a hidden region) is not in Stuart\'s index');
check(!/[\u2013\u2014]/.test(JSON.stringify(kb)), 'no em or en dashes in the index');

// ------------------------------------------------------------------ the pages, in a browser
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.pbf': 'application/x-protobuf', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };
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
    try { ({ chromium } = require('playwright')); } catch (e) { fail('Playwright is not installed: npm install, then npx playwright install chromium'); return finish(); }
    const srv = await serve();
    const URL = 'http://127.0.0.1:' + srv.address().port + '/';
    const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
    async function open(file, opts) {
        const ctx = await browser.newContext(Object.assign({ viewport: { width: 1440, height: 900 } }, opts || {}));
        await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
        const page = await ctx.newPage();
        page.errors = [];
        page.on('pageerror', e => page.errors.push(e.message));
        await page.goto(URL + file, { waitUntil: 'load' });
        return page;
    }
    const shot = async (page, name) => { if (process.env.SHOTS) { fs.mkdirSync(process.env.SHOTS, { recursive: true }); await page.screenshot({ path: path.join(process.env.SHOTS, name + '.png') }); } };

    section('Every page: one bar, the right link lit, Stuart\'s button, no errors');
    const PAGES = ['index.html', 'moreau.html', 'family-tree.html', 'map.html', 'ask.html'];
    let firstBar = null;
    for (const f of PAGES) {
        const page = await open(f);
        await page.waitForTimeout(f === 'map.html' ? 2500 : 1200);
        const bar = await page.evaluate(() => {
            const navs = document.querySelectorAll('nav.main-nav');
            const n = navs[0];
            return { count: navs.length, links: [...n.querySelectorAll('.nav-links a')].map(a => a.getAttribute('href')), lit: [...n.querySelectorAll('a[aria-current="page"]')].map(a => a.getAttribute('href')), top: Math.round(n.getBoundingClientRect().top), height: Math.round(n.getBoundingClientRect().height) };
        });
        if (!firstBar) firstBar = bar;
        check(bar.count === 1 && JSON.stringify(bar.links) === JSON.stringify(firstBar.links), f + ': one bar with the same links', JSON.stringify(bar.links));
        check(bar.top === firstBar.top && bar.height === firstBar.height, f + ': the bar sits in the same place', bar.top + '/' + bar.height);
        check(JSON.stringify(bar.lit) === JSON.stringify([f]), f + ': its own link is lit', bar.lit.join(','));
        const button = await page.locator('.st-launch, .st-widget button').count();
        check(f === 'ask.html' ? button === 0 : button > 0, f + (f === 'ask.html' ? ': no Stuart button on Stuart\'s own page' : ': Stuart\'s button is there'));
        check(!page.errors.length, f + ': no page errors', page.errors.join(' | '));
        await shot(page, f.replace('.html', '') + '-1440');
        await page.context().close();
    }

    section('The menu on a phone');
    {
        const page = await open('moreau.html', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
        const state = () => page.evaluate(() => ({ open: document.querySelector('.nav-links').classList.contains('open'), expanded: document.querySelector('.nav-toggle').getAttribute('aria-expanded') }));
        await page.click('.nav-toggle');
        let s = await state();
        check(s.open && s.expanded === 'true', 'one tap opens the menu', JSON.stringify(s));
        await page.click('.nav-toggle');
        s = await state();
        check(!s.open && s.expanded === 'false', 'a second tap closes it', JSON.stringify(s));
        await page.click('.nav-toggle');
        await page.keyboard.press('Escape');
        s = await state();
        const focus = await page.evaluate(() => document.activeElement && document.activeElement.classList.contains('nav-toggle'));
        check(!s.open && focus, 'Escape closes it and returns to the button');
        await page.context().close();
    }

    section('Family tree');
    {
        const page = await open('family-tree.html');
        await page.waitForSelector('.card[data-id]');
        const t = await page.evaluate(() => {
            const card = id => document.querySelector('.card[data-id="' + id + '"]');
            const box = id => { const c = card(id); return c ? { x: c.offsetLeft, y: c.offsetTop, w: c.offsetWidth } : null; };
            return {
                n: document.querySelectorAll('.card[data-id]').length,
                legend: !!card('auguste-de-moreau'), pierre: !!card('pierre-moreau'),
                pierreUncertain: !!(card('pierre-moreau') && card('pierre-moreau').classList.contains('is-uncertain')),
                maryAnnPhoto: !!(card('mary-ann-briggs') && card('mary-ann-briggs').querySelector('.c-av img')),
                henriPhoto: !!(card('henri-moreau') && card('henri-moreau').querySelector('.c-av img')),
                janetLiving: !!(card('janet-hartley') && card('janet-hartley').querySelector('.c-living')),
                susan: card('susan-hartley') && card('susan-hartley').textContent,
                sides: [...document.querySelectorAll('.tc-side')].map(e => e.textContent.trim()),
                gold: getComputedStyle(document.documentElement).getPropertyValue('--gold').trim(),
                william: box('william-hartley'), alice: box('alice-turner'), arthur: box('arthur-hartley'), margot: box('marguerite-moreau')
            };
        });
        check(t.gold === '#8a6a2f', 'the site\'s theme overrides the engine\'s colours', t.gold);
        check(t.n === 22, '22 people on the tree (everyone but the legend)', t.n);
        check(!t.legend && t.pierre, 'a hidden region is left off, and its suspected relative kept');
        check(t.pierreUncertain, 'the suspected relative is drawn as unproven');
        check(t.maryAnnPhoto && !t.henriPhoto, 'cardPhotos "best": a picture from the media shows when no photo is set');
        check(t.janetLiving && /1938/.test(t.susan || ''), 'living people show as living, with the dates the data has', t.susan);
        check(t.sides.some(s => /Grandpa Arthur's family/.test(s)) && t.sides.some(s => /Grandma Margot's family/.test(s)), 'the two sides are labelled', t.sides.join(' / '));
        const beside = (a, b) => a && b && a.y === b.y && Math.abs(a.x - b.x) <= a.w + 80;
        check(beside(t.william, t.alice), 'coupleBlocks "auto": William and Alice are drawn as one couple');
        check(beside(t.arthur, t.margot), 'the couple at the centre are drawn side by side');
        check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        await page.goto(URL + 'family-tree.html#/person/susan-hartley');
        await page.waitForTimeout(1200);
        const prof = await page.evaluate(() => { const d = document.getElementById('drawer'); return d && !d.hidden ? d.textContent : ''; });
        check(/Susan Hartley/.test(prof) && /Living/.test(prof) && /1938/.test(prof), 'a living person\'s profile opens from the link, with their details', prof.slice(0, 160));
        await page.context().close();
    }

    section('Family map');
    {
        const page = await open('map.html');
        // the map lays itself out once its data has loaded; on a slow machine that takes a while
        await page.waitForFunction(() => /Beyond/.test((document.getElementById('beyondBtn') || {}).textContent || ''), null, { timeout: 30000 }).catch(() => {});
        await page.waitForTimeout(500);
        const m = await page.evaluate(() => ({
            beyond: (document.getElementById('beyondBtn') || {}).textContent,
            families: [...document.querySelectorAll('#famSel option')].map(o => o.value),
            then: !!document.querySelector('[data-style="then"]:not([hidden])')
        }));
        check(/Beyond England: 2 places/.test(m.beyond || ''), 'places outside the home region are counted', m.beyond);
        check(['arthur', 'margot', 'both'].every(f => m.families.includes(f)), 'the family filter has the families from the settings', m.families.join(','));
        await page.click('#listOpen');
        await page.waitForTimeout(400);
        const places = await page.$$eval('#listView .lv-place h3', hs => hs.map(h => h.textContent.trim()));
        check(places.length === 6 && !places.some(p => /Paris/.test(p)), 'the list has the 6 places, and not the legend\'s', places.join(' | '));
        const susan = await page.$$eval('#listView .lv-people', xs => xs.some(x => /Susan Hartley/.test(x.textContent)));
        check(susan, 'living people are on the map like anyone else');
        check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        await page.context().close();
    }

    section('Stuart\'s page and button');
    {
        const page = await open('ask.html');
        await page.waitForFunction(() => window.__ask && window.__ask.archive, null, { timeout: 15000 });
        const n = await page.evaluate(() => Object.keys(window.__ask.archive.byId).length);
        check(n === 22, 'Stuart\'s page loads the index', n);
        await page.context().close();
        const home = await open('index.html');
        await home.waitForTimeout(800);
        await home.click('.st-launch');
        await home.waitForTimeout(800);
        const open1 = await home.evaluate(() => { const p = document.querySelector('.st-panel'); return !!p && p.classList.contains('is-open'); });
        check(open1, 'the button opens Stuart on the home page');
        check(!home.errors.length, 'no page errors', home.errors.join(' | '));
        await home.context().close();
    }

    await browser.close();
    srv.close();
    finish();
})().catch(e => { fail('the checks stopped: ' + (e && e.stack || e)); finish(); });

function finish() {
    console.log('\n' + (failures ? failures + ' check' + (failures === 1 ? '' : 's') + ' failed.' : 'All checks passed.'));
    process.exit(failures ? 1 : 0);
}
