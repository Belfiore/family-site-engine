/* The Family Map: "Relationships to", no Street View message, and the source preview and drawer.
 *
 *   node tests/check-map-relations.js              builds the made-up sample (and a German copy) into temporary folders
 *   SHOTS=dir node tests/check-map-relations.js    also saves screenshots to dir
 *
 * Needs Node 18 or later and Playwright with Chromium. Everything off the machine is blocked.
 * Only the made-up sample family (sample/) is used.
 */
const fs = require('fs'), path = require('path'), http = require('http'), cp = require('child_process');
const { ROOT, check, section, state, tmpdir } = require('./helpers');
const { chromium } = require('playwright');

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.pdf': 'application/pdf' };
// the built site, plus two pages that behave badly in a frame: one refused by the server, one that never answers
function serve(dir) {
    return new Promise(res => {
        const srv = http.createServer((req, rsp) => {
            const p = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
            if (p === '/blocked.html') { rsp.writeHead(200, { 'content-type': 'text/html', 'x-frame-options': 'DENY' }); return rsp.end('<p>refused in a frame</p>'); }
            if (p === '/slow.html') return;                                           // never answers
            const f = path.join(dir, p === '/' ? 'index.html' : p);
            if (!f.startsWith(dir) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { rsp.writeHead(404); return rsp.end('not found'); }
            rsp.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' });
            fs.createReadStream(f).pipe(rsp);
        });
        srv.listen(0, '127.0.0.1', () => res({ url: 'http://127.0.0.1:' + srv.address().port + '/', close: () => srv.closeAllConnections && srv.closeAllConnections() || srv.close() }));
    });
}
function build(tmp, name, lang) {
    const out = path.join(tmp, name);
    let site = path.join(ROOT, 'sample');
    if (lang) { site = path.join(tmp, name + '-src'); cp.execFileSync('python3', [path.join(ROOT, 'tests', 'i18n_fixtures.py'), site, '--default', lang], { stdio: 'pipe' }); }
    cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', out], { stdio: 'pipe' });
    return out;
}
const json = (f, fn) => { const d = JSON.parse(fs.readFileSync(f, 'utf8')); fn(d); fs.writeFileSync(f, JSON.stringify(d)); };

(async () => {
    const tmp = tmpdir('engine-map-rel-');
    const dist = build(tmp, 'en'), distDe = build(tmp, 'de', 'de');
    const srv = await serve(dist), srvDe = await serve(distDe);
    const URL = srv.url, URL_DE = srvDe.url;

    // sources the sample does not have: a PDF, web pages, and one with neither a file nor a link
    fs.mkdirSync(path.join(dist, 'docs'), { recursive: true });
    fs.writeFileSync(path.join(dist, 'docs', 'made-up.pdf'), '%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n');
    fs.writeFileSync(path.join(dist, 'docs', 'page.html'), '<!doctype html><title>A made-up page</title><h1>A made-up page</h1><p>Text.</p>');
    json(path.join(dist, 'data', 'sources.json'), d => d.sources.push(
        { id: 't-pdf', title: 'A made-up PDF', type: 'document', repository: 'Test archive', date: '1900', file: 'docs/made-up.pdf', note: 'One line that says what this is.' },
        { id: 't-web', title: 'A made-up web page', type: 'web', repository: 'Test web', url: URL + 'docs/page.html', note: 'A page on the web.' },
        { id: 't-blocked', title: 'A page that refuses to be framed', type: 'web', url: URL + 'blocked.html' },
        { id: 't-slow', title: 'A page that never answers', type: 'web', url: URL + 'slow.html' },
        { id: 't-plain', title: 'A source with no file and no link', type: 'family testimony', repository: 'The family' }));
    json(path.join(dist, 'data', 'places.json'), d => {
        const pl = d.places.find(p => p.id === 'leeds');
        pl.blurb = 'A made-up note about the place.';
        pl.blurbSourceIds = ['marriage-hartley-briggs', 't-pdf', 't-web', 't-blocked', 't-slow', 't-plain'];
        d.places.forEach(p => { p.streetView = null; p.streetViewReason = 'No Street View for this place.'; });
    });

    const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
    async function open(base, file, opts) {
        const ctx = await browser.newContext(Object.assign({ viewport: { width: 1440, height: 900 } }, opts || {}));
        await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
        const page = await ctx.newPage();
        page.errors = [];
        page.on('pageerror', e => page.errors.push(e.message));
        await page.goto(base + file, { waitUntil: 'load' });
        return page;
    }
    const mapReady = async page => { await page.waitForFunction(() => window.FM && FM.DATA && FM.rel, null, { timeout: 30000 }); await page.waitForTimeout(800); };
    const shot = async (page, name) => { if (process.env.SHOTS) { fs.mkdirSync(process.env.SHOTS, { recursive: true }); await page.screenshot({ path: path.join(process.env.SHOTS, name + '.png') }); } };

    // ================================================================== no Street View message
    section('A place with no Street View says nothing about it');
    {
        const page = await open(URL, 'map.html');
        await mapReady(page);
        const seen = await page.evaluate(() => {
            const out = { text: false, nosv: false, thenNow: 0, places: 0 };
            Object.keys(FM.DATA.places).forEach(id => {
                FM.openPlace(id, { push: false });
                const p = document.getElementById('panelBody');
                out.places++;
                if (/No Street View/i.test(p.textContent)) out.text = true;
                if (p.querySelector('.pn-nosv, .ec-nosv')) out.nosv = true;
                out.thenNow += p.querySelectorAll('.pn-tn button').length;
            });
            if (/No Street View/i.test(document.body.textContent)) out.text = true;
            return out;
        });
        check(seen.places > 3 && !seen.text && !seen.nosv, 'no panel says "No Street View" (even with the site\'s own streetViewReason set), ' + seen.places + ' places opened');
        check(seen.thenNow > 0, 'the Then and Today buttons are still there (they switch the map style, not Street View)');
        check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        await page.context().close();
    }

    // ================================================================== relationships
    section('Relationships to: nothing chosen, nothing changes');
    let relOf = {};
    {
        const page = await open(URL, 'map.html');
        await mapReady(page);
        const s = await page.evaluate(() => ({ box: !document.getElementById('vpBox').hidden, value: document.getElementById('vpSel').value,
            options: document.querySelectorAll('#vpSel option').length, label: document.querySelector('#vpBox label').textContent,
            first: document.querySelector('#vpSel option').textContent, inKey: !!document.querySelector('#key #vpBox'),
            above: document.getElementById('vpBox').compareDocumentPosition(document.getElementById('familyBox')) & Node.DOCUMENT_POSITION_FOLLOWING ? true : false }));
        check(s.box && s.value === '' && s.options > 20, 'the control is in the sidebar with nobody chosen', JSON.stringify(s));
        check(s.label === 'Relationships to' && s.first === 'No one', 'it uses the tree page\'s words', JSON.stringify(s));
        check(s.inKey && s.above, 'it is at the top of the sidebar, above the family filter');
        await page.evaluate(() => FM.openPlace('leeds', { push: false }));
        await page.click('#listOpen'); await page.waitForTimeout(300);
        const none = await page.evaluate(() => ({ chips: document.querySelectorAll('.chip-vp').length, pk: document.querySelectorAll('.pk-rel, .mk-rel').length,
            labels: [...document.querySelectorAll('.mk-wrap')].some(w => /\byour\b/.test(w.getAttribute('aria-label') || '')) }));
        check(none.chips === 0 && none.pk === 0 && !none.labels, 'no relationship words anywhere on the page', JSON.stringify(none));
        check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        await page.context().close();
    }

    section('Relationships to: chosen on the map, shown everywhere a name is, and the same as the tree page');
    {
        const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
        await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
        const page = await ctx.newPage(); page.errors = [];
        page.on('pageerror', e => page.errors.push(e.message));
        await page.goto(URL + 'map.html', { waitUntil: 'load' });
        await mapReady(page);
        await page.selectOption('#vpSel', 'daniel-hartley');
        await page.waitForTimeout(300);
        relOf = await page.evaluate(() => { const o = {}; Object.keys(FM.DATA.people).forEach(id => { o[id] = FM.rel.of(id); }); return o; });
        const known = Object.keys(relOf).filter(id => relOf[id]);
        check(known.length > 10, known.length + ' people have a relationship to Daniel', known.length);
        check(relOf['daniel-hartley'] === null, 'the chosen person has none to themselves');

        // a panel
        const placeId = await page.evaluate(() => Object.keys(FM.DATA.places).find(id => (FM.DATA.placeEvents[id] || []).some(e => e.personIds.some(p => FM.rel.of(p)))));
        await page.evaluate(id => FM.openPlace(id, { push: false }), placeId);
        const chips = await page.$$eval('#panelBody .pn-events .chip[data-person]', cs => cs.map(c => ({ id: c.dataset.person, vp: (c.querySelector('.chip-vp') || {}).textContent || null })));
        check(chips.length > 0 && chips.every(c => (relOf[c.id] ? c.vp && c.vp.replace(/^\W+/, '') === 'your ' + relOf[c.id] : c.vp === null)),
            'every name chip under "At this place" has its relationship, or nothing', JSON.stringify(chips.slice(0, 4)));
        const aria = await page.$eval('#panelBody .chip[data-person] .chip-vp', e => e.closest('button').textContent);
        check(/your /.test(aria), 'the words are inside the chip, so a screen reader reads them with the name', aria);
        await shot(page, 'map-relationships-panel');

        // pins, hover card, list
        const pins = await page.evaluate(() => [...document.querySelectorAll('.mk-wrap')].map(w => w.getAttribute('aria-label') || ''));
        check(pins.some(l => /\(.*, your /.test(l)), 'a pin\'s label names the relationship', pins.find(l => /your /.test(l)));
        await page.evaluate(() => { const w = [...document.querySelectorAll('.mk-wrap')].find(x => /\(.*, your /.test(x.getAttribute('aria-label') || '')); w.dataset.t = '1'; });
        await page.click('#panelClose'); await page.waitForTimeout(400);
        // the pointer arriving on the pin (not a real mouse move: on a small CI screen something else can sit over it)
        await page.evaluate(() => document.querySelector('.mk-wrap[data-t="1"]').dispatchEvent(new PointerEvent('pointerenter', { pointerType: 'mouse' })));
        await page.waitForTimeout(600);
        const pk = await page.evaluate(() => ({ shown: !document.getElementById('peek').hidden, rel: [...document.querySelectorAll('#peek .pk-rel li')].map(l => l.textContent) }));
        check(pk.shown && pk.rel.length > 0 && pk.rel.every(t => /your /.test(t)), 'the hover card on a pin lists them with their relationship', JSON.stringify(pk));
        await page.mouse.move(5, 5);
        await page.evaluate(() => document.getElementById('peek').hidden = true);
        await page.click('#listOpen'); await page.waitForTimeout(300);
        const lv = await page.$$eval('#listView .lv-people .chip-vp', e => e.length);
        check(lv > 0, '"View as list" has them too (' + lv + ')');
        await page.click('#listClose');

        // the choice is kept, and the tree page agrees on every pair
        const stored = await page.evaluate(() => localStorage.getItem('tc_viewpoint'));
        check(stored === 'daniel-hartley', 'it is kept where the tree page keeps it (tc_viewpoint)', stored);
        await page.goto(URL + 'family-tree.html', { waitUntil: 'load' });
        await page.waitForFunction(() => document.getElementById('viewpoint') && document.getElementById('viewpoint').value, null, { timeout: 20000 });
        check(await page.$eval('#viewpoint', s => s.value) === 'daniel-hartley', 'the tree page opens with the same person chosen');
        const mism = [];
        for (const id of Object.keys(relOf)) {
            await page.evaluate(id => { location.hash = '#/person/' + id; }, id);
            await page.waitForTimeout(120);
            const txt = await page.evaluate(id => {
                const name = (document.getElementById('drawerName') || {}).textContent || '';
                if (!window.__tree || !__tree.D || !__tree.D.byId[id]) return 'NOT ON THE TREE';
                const d = [...document.querySelectorAll('#drawerBody .dr-rel, #drawerBody .pf-variants')].find(x => x.classList.contains('dr-rel') || /Relationship to|Verwandtschaft zu/.test(x.textContent));
                if (!d) return null;
                return d.classList.contains('dr-rel') ? d.lastChild.textContent : d.textContent.replace(/^[^:]*:\s*/, '');
            }, id);
            const want = relOf[id];
            if (txt === 'NOT ON THE TREE') { if (want !== null) mism.push(id + ': the map has words for someone the tree does not draw'); continue; }
            if ((txt || null) === null ? want !== null : !want || txt.toLowerCase() !== want.toLowerCase()) mism.push(id + ': map "' + want + '" tree "' + txt + '"');
        }
        check(mism.length === 0, 'the map and the tree page give the same words for all ' + Object.keys(relOf).length + ' people', mism.slice(0, 4).join(' | '));

        // the other way: chosen on the tree page, there on the map
        await page.evaluate(() => { location.hash = ''; });
        await page.selectOption('#viewpoint', 'susan-hartley');
        await page.goto(URL + 'map.html', { waitUntil: 'load' });
        await mapReady(page);
        check(await page.$eval('#vpSel', s => s.value) === 'susan-hartley', 'a choice made on the tree page is the choice on the map');
        await page.selectOption('#vpSel', '');
        check(await page.evaluate(() => localStorage.getItem('tc_viewpoint')) === null && await page.evaluate(() => document.querySelectorAll('.chip-vp').length) === 0, '"No one" clears it and the words go');
        check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        await ctx.close();
    }

    section('Relationships to: the same in German, and a person the tree does not know shows nothing');
    {
        const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
        await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
        const page = await ctx.newPage(); page.errors = [];
        page.on('pageerror', e => page.errors.push(e.message));
        await page.goto(URL_DE + 'map.html', { waitUntil: 'load' });
        await mapReady(page);
        await page.selectOption('#vpSel', 'daniel-hartley');
        const de = await page.evaluate(() => { const o = {}; Object.keys(FM.DATA.people).forEach(id => { o[id] = FM.rel.of(id); }); return { o, label: document.querySelector('#vpBox label').textContent, none: document.querySelector('#vpSel option').textContent, ph: FM.rel.phrase('peter-hartley') }; });
        check(de.label === 'Verwandtschaft zu' && de.none === 'Niemand', 'the control is in German', JSON.stringify([de.label, de.none]));
        check(de.o['peter-hartley'] && de.ph === de.o['peter-hartley'] && !/^your /.test(de.ph), 'German words come from the same code (' + de.ph + ')');
        await page.goto(URL_DE + 'family-tree.html', { waitUntil: 'load' });
        await page.waitForFunction(() => document.getElementById('viewpoint') && document.getElementById('viewpoint').value, null, { timeout: 20000 });
        const mism = [];
        for (const id of Object.keys(de.o)) {
            await page.evaluate(id => { location.hash = '#/person/' + id; }, id);
            await page.waitForTimeout(120);
            const txt = await page.evaluate(id => {
                const name = (document.getElementById('drawerName') || {}).textContent || '';
                if (!window.__tree || !__tree.D || !__tree.D.byId[id]) return 'NOT ON THE TREE';
                const d = [...document.querySelectorAll('#drawerBody .dr-rel, #drawerBody .pf-variants')].find(x => x.classList.contains('dr-rel') || /Relationship to|Verwandtschaft zu/.test(x.textContent));
                if (!d) return null;
                return d.classList.contains('dr-rel') ? d.lastChild.textContent : d.textContent.replace(/^[^:]*:\s*/, '');
            }, id);
            const want = de.o[id];
            if (txt === 'NOT ON THE TREE') { if (want !== null) mism.push(id + ': the map has words for someone the tree does not draw'); continue; }
            if ((txt || null) === null ? want !== null : !want || txt.toLowerCase() !== want.toLowerCase()) mism.push(id + ': map "' + want + '" tree "' + txt + '"');
        }
        check(mism.length === 0, 'German: the map and the tree page agree for everyone', mism.slice(0, 3).join(' | '));
        await ctx.close();
        const page2 = await open(URL, 'map.html'); await mapReady(page2);
        const unknown = await page2.evaluate(() => { localStorage.setItem('tc_viewpoint', 'thomas-hartley'); return [FM.rel.of('nobody-here'), FM.rel.phrase('nobody-here'), FM.rel.chip('nobody-here'), FM.rel.names(['nobody-here'])]; });
        check(unknown.every(v => !v), 'a person who is not on the tree gets no words, and no guess', JSON.stringify(unknown));
        await page2.context().close();
    }

    // ================================================================== sources
    section('Sources: a clear title, a preview on hover or focus, a drawer on click');
    let mapMoved = null;
    {
        const page = await open(URL, 'map.html');
        await mapReady(page);
        await page.evaluate(() => FM.openPlace('leeds', { push: false }));
        await page.waitForTimeout(300);
        const list = await page.$$eval('#panelBody .pn-src li', ls => ls.map(l => ({ link: !!l.querySelector('a.sp-link'), plain: !!l.querySelector('.sp-plain'), text: l.textContent })));
        const mine = ['Marriage of Thomas Hartley and Mary Ann Briggs', 'A made-up PDF', 'A made-up web page', 'refuses to be framed', 'never answers'].map(t => list.find(l => l.text.includes(t)));
        const plain = list.find(l => l.text.includes('no file and no link'));
        check(mine.every(l => l && l.link) && plain && plain.plain && !plain.link, 'every source with a file or a link has a title link; the one without is plain text');
        check(list.every(l => l.link || l.plain), 'every source line in the panel is either a link or plain text (' + list.length + ' of them)');
        const fnMarks = await page.$$eval('#panelBody .pn-blurb sup a.fn', a => a.length);
        check(fnMarks === 6, 'the note has its six footnote markers');
        await page.waitForTimeout(2500);
        const centre = () => page.evaluate(() => { const c = FM.map.getCenter(); return [+c.lng.toFixed(5), +c.lat.toFixed(5), +FM.map.getZoom().toFixed(3)].join(','); });
        const before = await centre();

        // hover: nothing for 300 ms, then the card; it stays while the pointer is on it
        const L = t => page.locator('#panelBody .pn-src a.sp-link', { hasText: t });
        const link = L('Marriage of Thomas Hartley and Mary Ann Briggs');     // an image
        await link.hover();
        await page.waitForTimeout(150);
        check(await page.evaluate(() => { const c = document.getElementById('sp-card'); return !c || c.hidden; }), 'no card before about 300 ms');
        await page.waitForTimeout(350);
        const card = await page.evaluate(() => { const c = document.getElementById('sp-card'); const r = c.getBoundingClientRect(); return { shown: !c.hidden, role: c.getAttribute('role'), img: !!c.querySelector('.sp-thumb img'), title: (c.querySelector('.sp-t') || {}).textContent, pub: (c.querySelector('.sp-pub') || {}).textContent, tr: getComputedStyle(c).transitionProperty + ' ' + getComputedStyle(c).transitionDuration + ' ' + getComputedStyle(c).transitionTimingFunction, inView: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight, describedby: document.querySelector('a.sp-link[aria-describedby]') ? 'sp-card' : null }; });
        check(card.shown && card.role === 'tooltip' && card.img && /Marriage of Thomas Hartley/.test(card.title) && /Sample archive/.test(card.pub || ''), 'after 300 ms the card shows a thumbnail of the document, the title and the publisher', JSON.stringify(card));
        check(/opacity/.test(card.tr) && /0\.15s/.test(card.tr) && /ease-out/.test(card.tr), 'it fades in over 150 ms, ease-out', card.tr);
        check(card.inView && card.describedby === 'sp-card', 'it sits inside the window and is tied to its link for screen readers');
        await shot(page, 'source-card');
        const cb = await page.locator('#sp-card').boundingBox();
        await page.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2);
        await page.waitForTimeout(500);
        check(await page.evaluate(() => !document.getElementById('sp-card').hidden), 'it stays open while the pointer is over the card');
        await page.mouse.move(2, 400);
        await page.waitForTimeout(500);
        check(await page.evaluate(() => document.getElementById('sp-card').hidden), 'it goes when the pointer leaves');
        // Escape closes the card
        await link.hover(); await page.waitForTimeout(600);
        await page.keyboard.press('Escape'); await page.waitForTimeout(300);
        check(await page.evaluate(() => document.getElementById('sp-card').hidden), 'Escape closes it');
        await page.mouse.move(2, 400);
        // a PDF: an icon, a web page: its address and a favicon fallback
        await L('A made-up PDF').hover(); await page.waitForTimeout(600);
        const pdf = await page.evaluate(() => { const c = document.getElementById('sp-card'); return { thumb: !!c.querySelector('.sp-thumb--icon'), img: !!c.querySelector('.sp-thumb img'), kind: c.querySelector('.sp-kind').textContent, sum: (c.querySelector('.sp-sum') || {}).textContent }; });
        check(pdf.thumb && !pdf.img && /PDF/.test(pdf.kind) && /One line/.test(pdf.sum), 'a PDF gets an icon (no made-up thumbnail) and its one-line summary', JSON.stringify(pdf));
        await page.mouse.move(2, 400); await page.waitForTimeout(400);
        await L('A made-up web page').hover(); await page.waitForTimeout(700);
        const web = await page.evaluate(() => { const c = document.getElementById('sp-card'); return { kind: c.querySelector('.sp-kind').textContent, fav: !!c.querySelector('.sp-fav'), title: c.querySelector('.sp-t').textContent }; });
        check(/Web page/.test(web.kind) && /127\.0\.0\.1/.test(web.kind) && web.title === 'A made-up web page', 'a web page shows its address and its title', JSON.stringify(web));
        await page.mouse.move(2, 400); await page.waitForTimeout(400);

        // keyboard focus shows it too
        await page.keyboard.press('Shift');
        await page.evaluate(() => [...document.querySelectorAll('#panelBody .pn-src a.sp-link')].find(a => /Marriage of Thomas Hartley/.test(a.textContent)).focus());
        await page.waitForTimeout(300);
        check(await page.evaluate(() => !document.getElementById('sp-card').hidden), 'keyboard focus shows the card');
        await page.evaluate(() => document.activeElement.blur()); await page.waitForTimeout(300);

        // click: the drawer
        await page.evaluate(() => [...document.querySelectorAll('#panelBody .pn-src a.sp-link')].find(a => /Marriage of Thomas Hartley/.test(a.textContent)).focus());
        await page.keyboard.press('Enter');
        await page.waitForTimeout(500);
        const dr = await page.evaluate(() => { const d = document.querySelector('.sp-drawer'); const r = d.getBoundingClientRect(); const cs = getComputedStyle(d); return { open: !d.hidden && d.classList.contains('is-open'), role: d.getAttribute('role'), modal: d.getAttribute('aria-modal'), title: document.getElementById('sp-d-title').textContent, img: !!d.querySelector('.sp-d-img img'), right: Math.round(r.right) === innerWidth, tall: Math.round(r.height) === innerHeight, tr: cs.transitionProperty + '|' + cs.transitionDuration + '|' + cs.transitionTimingFunction, focus: document.activeElement.id, openBtn: document.getElementById('sp-d-open').getAttribute('href') }; });
        check(dr.open && dr.role === 'dialog' && dr.modal === 'true' && dr.img && dr.right && dr.tall, 'Enter opens a right-hand drawer with the image inline', JSON.stringify(dr));
        check(/transform/.test(dr.tr) && /0\.22s/.test(dr.tr) && /cubic-bezier\(0\.2, 0\.8, 0\.2, 1\)/.test(dr.tr), 'it slides over 220 ms on the given curve', dr.tr);
        check(dr.focus === 'sp-d-close' && /marriage-1874/.test(dr.openBtn), 'focus is on the close button and "Open in new tab" points at the document', dr.focus + ' ' + dr.openBtn);
        await shot(page, 'source-drawer');
        for (let i = 0; i < 6; i++) await page.keyboard.press('Tab');
        check(await page.evaluate(() => !!document.activeElement.closest('.sp-drawer')), 'Tab stays inside the drawer');
        await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Shift+Tab');
        check(await page.evaluate(() => !!document.activeElement.closest('.sp-drawer')), 'and so does Shift+Tab');
        await page.keyboard.press('Escape'); await page.waitForTimeout(450);
        const closed = await page.evaluate(() => ({ hidden: document.querySelector('.sp-drawer').hidden, back: /Marriage of Thomas Hartley/.test(document.activeElement.textContent) && document.activeElement.classList.contains('sp-link'), place: FM && document.querySelector('#panelTitle') && document.querySelector('#panelTitle').textContent }));
        check(closed.hidden && closed.back, 'Escape closes it and focus goes back to the title link that opened it', JSON.stringify(closed));
        check(await centre() === before, 'the map did not move (' + before + ')', await centre());

        // close button, outside click
        await link.click(); await page.waitForTimeout(400);
        await page.click('#sp-d-close'); await page.waitForTimeout(450);
        check(await page.evaluate(() => document.querySelector('.sp-drawer').hidden), 'the close button closes it');
        await link.click(); await page.waitForTimeout(400);
        await page.mouse.click(100, 450); await page.waitForTimeout(450);
        check(await page.evaluate(() => document.querySelector('.sp-drawer').hidden), 'a click outside closes it');

        // PDF, web page, refused page, page that never answers
        await L('A made-up PDF').click(); await page.waitForTimeout(400);
        check(await page.evaluate(() => !!document.querySelector('.sp-drawer iframe.sp-frame[src$="made-up.pdf"]')), 'a PDF is shown inline');
        await page.click('#sp-d-close'); await page.waitForTimeout(450);
        await L('A made-up web page').click(); await page.waitForTimeout(800);
        const w = await page.evaluate(() => { const f = document.querySelector('.sp-drawer iframe[data-web]'); return { frame: !!f, sandbox: f && f.getAttribute('sandbox'), hint: !!document.querySelector('.sp-hint a[target="_blank"]'), open: !!document.getElementById('sp-d-open').href }; });
        check(w.frame && /allow-scripts/.test(w.sandbox) && !/allow-top-navigation/.test(w.sandbox) && w.hint && w.open, 'a web page is shown in a sandboxed frame, with a way to open it in a new tab', JSON.stringify(w));
        await page.click('#sp-d-close'); await page.waitForTimeout(450);
        await page.evaluate(() => { FamilySourcePreview.frameTimeout = 700; });
        await L('never answers').click(); await page.waitForTimeout(1500);
        const fb = await page.evaluate(() => ({ card: !!document.querySelector('.sp-drawer .sp-fb'), btn: !!document.querySelector('.sp-drawer .sp-fb a[target="_blank"]'), frame: !!document.querySelector('.sp-drawer iframe') }));
        check(fb.card && fb.btn && !fb.frame, 'a page that never loads is replaced by a card with an "Open in new tab" button', JSON.stringify(fb));
        await page.click('#sp-d-close'); await page.waitForTimeout(450);
        mapMoved = await centre();
        check(mapMoved === before, 'after all of that the map is exactly where it was');

        // footnote markers
        const third = page.locator('#panelBody .pn-blurb a.fn').nth(2);
        const num = await third.getAttribute('data-fn');
        await third.click(); await page.waitForTimeout(500);
        const fn = await page.evaluate(n => ({ focus: document.activeElement.id, flash: document.getElementById('fm-src-' + n).classList.contains('is-flash'), n }), num);
        check(fn.focus === 'fm-src-' + num && fn.flash, 'a footnote marker scrolls to its source, highlights it and moves focus there', JSON.stringify(fn));
        check(!page.errors.length, 'no page errors', page.errors.join(' | '));
        await page.context().close();
    }

    section('Sources: a phone gets a full-height bottom sheet; reduced motion turns the slide off');
    {
        const page = await open(URL, 'map.html', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
        await mapReady(page);
        await page.evaluate(() => FM.openPlace('leeds', { push: false }));
        await page.waitForTimeout(400);
        await page.locator('#panelBody .pn-src a.sp-link', { hasText: 'Marriage of Thomas' }).tap(); await page.waitForTimeout(500);
        const sh = await page.evaluate(() => { const r = document.querySelector('.sp-drawer').getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), vw: innerWidth, vh: innerHeight, card: document.getElementById('sp-card') ? !document.getElementById('sp-card').hidden : false }; });
        check(sh.x === 0 && sh.y === 0 && sh.w === sh.vw && sh.h === sh.vh && !sh.card, 'a tap opens a sheet that fills the screen, with no hover card first', JSON.stringify(sh));
        await shot(page, 'source-sheet-phone');
        await page.context().close();
        const rm = await open(URL, 'map.html', { reducedMotion: 'reduce' });
        await mapReady(rm);
        await rm.evaluate(() => FM.openPlace('leeds', { push: false })); await rm.waitForTimeout(300);
        const link = rm.locator('#panelBody .pn-src a.sp-link', { hasText: 'Marriage of Thomas' });
        await link.click(); await rm.waitForTimeout(150);
        const t = await rm.evaluate(() => getComputedStyle(document.querySelector('.sp-drawer')).transitionDuration);
        check(/^0s/.test(t) && await rm.evaluate(() => document.querySelector('.sp-drawer').classList.contains('is-open')), 'with prefers-reduced-motion the drawer does not animate', t);
        await rm.keyboard.press('Escape'); await rm.waitForTimeout(50);
        check(await rm.evaluate(() => document.querySelector('.sp-drawer').hidden), 'and it closes at once');
        await rm.context().close();
    }

    await browser.close(); srv.close(); srvDe.close();
    console.log(state.failures ? '\n' + state.failures + ' check(s) failed.' : '\nAll checks passed.');
    process.exit(state.failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
