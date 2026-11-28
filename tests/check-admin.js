/* Checks for the settings page (/admin/), in a browser, against a pretend GitHub.
 *
 *   node tests/check-admin.js                  builds the sample site with the settings page on, then checks it
 *   SHOTS=dir node tests/check-admin.js        also saves screenshots to dir (the settings page, and a navigation bar with a page off)
 *
 * Needs Node 18 or later and Playwright with Chromium (npm install, then npx playwright install chromium).
 * GitHub is never contacted: every request to api.github.com is answered by the small fake below, which also records what the
 * page sent, so the checks can say exactly what would have been committed and where the token went.
 */
const fs = require('fs'), path = require('path'), http = require('http'), os = require('os'), cp = require('child_process');
const ROOT = path.dirname(__dirname);
const REPO = 'Belfiore/sample-site';
const GOOD = 'github_pat_TEST_good_token_000000000000', READ_ONLY = 'github_pat_TEST_read_only_0000000000', BAD = 'github_pat_TEST_bad_0000000000000000';

let failures = 0;
const ok = m => console.log('  ok   ' + m);
const fail = m => { failures++; console.log('  FAIL ' + m); };
const check = (c, m, detail) => c ? ok(m) : fail(m + (detail !== undefined ? ': ' + detail : ''));
const section = t => console.log('\n' + t);

// ------------------------------------------------------------------ the sites
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-admin-'));
function build(name, edit) {
    const src = path.join(tmp, name + '-src'), out = path.join(tmp, name);
    cp.execFileSync('cp', ['-r', path.join(ROOT, 'sample'), src]);
    const p = path.join(src, 'site.config.json'), cfg = JSON.parse(fs.readFileSync(p, 'utf8'));
    edit(cfg);
    fs.writeFileSync(p, JSON.stringify(cfg, null, 1));
    cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', src, '--out', out, '--previous', 'none'], { stdio: 'pipe' });
    return { src, out, config: fs.readFileSync(p, 'utf8') };
}
const SITE = build('admin', c => { c.admin = { enabled: true, repo: REPO }; c.pages.records = true; });
const OFF = build('off', c => { c.pages.map = false; c.pages.ask = false; });
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml' };
function serve(dist) {
    return new Promise(res => {
        const srv = http.createServer((req, rsp) => {
            let p = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
            if (p.endsWith('/')) p += 'index.html';
            const f = path.join(dist, p);
            if (!f.startsWith(dist) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { rsp.writeHead(404); return rsp.end('not found'); }
            rsp.writeHead(200, { 'content-type': TYPES[path.extname(f).toLowerCase()] || 'application/octet-stream' });
            fs.createReadStream(f).pipe(rsp);
        });
        srv.listen(0, '127.0.0.1', () => res(srv));
    });
}

// ------------------------------------------------------------------ a pretend GitHub
class FakeGitHub {
    constructor(configText) { this.reset(configText); }
    reset(configText) {
        this.text = configText; this.sha = 'sha-1'; this.requests = []; this.puts = []; this.conflict = false; this.runAfter = 0; this.runCalls = 0;
    }
    handle(route) {
        const req = route.request(), url = new URL(req.url()), auth = req.headers()['authorization'] || '';
        this.requests.push({ method: req.method(), path: url.pathname + url.search, auth });
        const send = (status, body) => route.fulfill({ status, contentType: 'application/json', headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' }, body: JSON.stringify(body) });
        if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' } });
        const token = auth.replace(/^Bearer /, '');
        if (auth && token === BAD) return send(401, { message: 'Bad credentials' });
        const canPush = token === GOOD;
        const p = url.pathname;
        if (p === '/user') return send(200, { login: 'tester' });
        if (p === '/repos/' + REPO) return send(200, { default_branch: 'main', permissions: auth ? { push: canPush, pull: true } : undefined });
        if (p === '/repos/' + REPO + '/contents/site.config.json' && req.method() === 'GET')
            return send(200, { sha: this.sha, content: Buffer.from(this.text, 'utf8').toString('base64'), encoding: 'base64' });
        if (p === '/repos/' + REPO + '/contents/site.config.json' && req.method() === 'PUT') {
            const body = JSON.parse(req.postData());
            this.puts.push({ body, auth });
            if (!canPush) return send(403, { message: 'Resource not accessible by personal access token' });
            if (this.conflict || body.sha !== this.sha) return send(409, { message: 'site.config.json does not match ' + this.sha });
            this.text = Buffer.from(body.content, 'base64').toString('utf8'); this.sha = 'sha-' + (this.puts.length + 1);
            return send(200, { content: { sha: this.sha }, commit: { sha: 'c0ffee', html_url: 'https://github.com/' + REPO + '/commit/c0ffee' } });
        }
        if (p === '/repos/' + REPO + '/actions/runs') {
            this.runCalls++;
            return send(200, { workflow_runs: this.runCalls > this.runAfter ? [{ html_url: 'https://github.com/' + REPO + '/actions/runs/42' }] : [] });
        }
        return send(404, { message: 'Not Found' });
    }
}

(async () => {
    let chromium;
    try { ({ chromium } = require('playwright')); } catch (e) { fail('Playwright is not installed: npm install, then npx playwright install chromium'); return done(); }
    const srv = await serve(SITE.out), srvOff = await serve(OFF.out);
    const URL = 'http://127.0.0.1:' + srv.address().port + '/';
    const browser = await chromium.launch();
    const gh = new FakeGitHub(SITE.config);
    const shot = async (page, name, full) => { if (process.env.SHOTS) { fs.mkdirSync(process.env.SHOTS, { recursive: true }); await page.screenshot({ path: path.join(process.env.SHOTS, name + '.png'), fullPage: !!full }); } };

    async function open(opts) {
        const ctx = await browser.newContext(Object.assign({ viewport: { width: 1100, height: 900 } }, opts || {}));
        const external = [];
        await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, route => {
            const u = new globalThis.URL(route.request().url());
            if (u.hostname === 'api.github.com') return gh.handle(route);
            external.push(u.hostname);
            return route.abort();
        });
        const page = await ctx.newPage();
        page.errors = []; page.logs = []; page.external = external;
        page.on('pageerror', e => page.errors.push(e.message));
        page.on('console', m => { page.logs.push(m.text()); if (m.type() === 'error') page.errors.push(m.text()); });
        await page.goto(URL + 'admin/');
        await page.waitForSelector('#ad-app:not([hidden])');
        await page.waitForTimeout(250);
        return page;
    }
    const status = page => page.locator('.ad-out').innerText();
    const sw = (page, key) => page.locator('#ad-page-' + key);
    async function signIn(page, token) {
        await page.fill('#ad-token', token);
        await page.click('text=Sign in with a token');
        await page.waitForTimeout(300);
    }

    // ---------------------------------------------------------------- the page itself
    section('The page is hidden from the site and from search engines');
    {
        const page = await open();
        const html = await page.content();
        check(/<meta name="robots" content="noindex, nofollow, noarchive">/.test(html), 'it says noindex');
        check(await page.locator('nav.main-nav').count() === 0, 'it has no navigation bar of the site');
        check(await page.locator('#stuart-widget, [data-widget], .stuart-btn').count() === 0, 'it has no Stuart button');
        const home = await browser.newPage();
        await home.goto(URL + 'index.html');
        check(!(await home.locator('nav.main-nav').innerHTML()).includes('admin'), 'no page of the site links to it from the navigation bar');
        check(!fs.readFileSync(path.join(SITE.out, 'site-config.js'), 'utf8').includes('admin'), 'the site settings do not mention it');
        check(page.errors.length === 0, 'no errors in the page', page.errors.join(' | '));
        await home.close(); await page.context().close();
    }

    section('Someone who is not signed in sees it read only');
    {
        gh.reset(SITE.config);
        const page = await open();
        check((await page.locator('.ad-ro').innerText()).includes('Read only'), 'it says "Read only"');
        const boxes = await page.locator('.ad-row input[role=switch]').count();
        check(boxes === 6, 'all six page switches are shown', String(boxes));
        check(await page.locator('.ad-row input:not([disabled])').count() === 0, 'every switch is locked');
        check(await page.locator('#ad-name').isDisabled() && await page.locator('#ad-tagline').isDisabled() && await page.locator('#ad-channel').isDisabled(), 'the title, tagline and channel are locked');
        check(await page.locator('text=Review changes').count() === 0, 'there is no save button');
        check(await sw(page, 'home').isChecked() && await sw(page, 'home').isDisabled(), 'Home is on and cannot be turned off');
        check(await sw(page, 'tree').isChecked() && !(await sw(page, 'discoveries').isChecked()) && await sw(page, 'records').isChecked(), 'the switches show what the site is built with');
        check(gh.requests.every(r => !r.auth), 'nothing was sent with a token');
        check(gh.puts.length === 0, 'nothing was saved');
        check((await page.locator('#ad-name').inputValue()) === 'Hartley & Moreau', 'the title is the site\'s');
        await shot(page, 'admin-read-only');
        await page.context().close();
    }

    section('A token that cannot write is read only too');
    {
        gh.reset(SITE.config);
        const page = await open();
        await signIn(page, READ_ONLY);
        check((await page.locator('.ad-ro').innerText()).includes('does not have write access'), 'it says the token cannot write');
        check(await page.locator('.ad-row input:not([disabled])').count() === 0, 'the switches stay locked');
        check(gh.puts.length === 0, 'nothing was saved');
        await page.context().close();
    }

    section('A token GitHub refuses is forgotten');
    {
        gh.reset(SITE.config);
        const page = await open();
        await signIn(page, BAD);
        check((await status(page)).includes('did not accept the token'), 'it says so');
        check(await page.evaluate(() => sessionStorage.length) === 0, 'and the token is not kept');
        await page.context().close();
    }

    section('Someone with write access changes the settings');
    {
        gh.reset(SITE.config);
        const page = await open();
        await signIn(page, GOOD);
        check((await page.locator('.ad-ok').first().innerText()).includes('Signed in as tester'), 'it says who is signed in');
        check(await sw(page, 'home').isDisabled(), 'Home stays locked');
        check(await sw(page, 'stories').isEnabled(), 'the other switches work');
        check(await page.locator('text=Review changes').isDisabled(), 'there is nothing to save yet');
        await shot(page, 'admin-signed-in');

        await sw(page, 'stories').uncheck({ force: true });
        await sw(page, 'discoveries').check({ force: true });
        await page.fill('#ad-name', 'Hartley and Moreau');
        await page.selectOption('#ad-channel', 'beta');
        check(await page.locator('text=Review changes').isEnabled(), 'changing something turns the button on');
        await page.click('text=Review changes');
        const list = (await page.locator('.ad-changes').innerText()).replace(/\s+/g, ' ');
        check(/Stories: on to off/.test(list) && /Discoveries: off to on/.test(list) && /Site title: "Hartley & Moreau" to "Hartley and Moreau"/.test(list) && /Engine channel: stable to beta/.test(list), 'it lists exactly what will change', list);
        check(!/Family Tree|Map|Records/.test(list), 'and nothing else');
        check(gh.puts.length === 0, 'nothing is saved before the person confirms');
        await shot(page, 'admin-review');

        await page.click('text=Go back');
        check(await page.locator('.ad-review').isHidden(), 'going back closes the review');
        await page.click('text=Review changes');
        await page.click('text=Save and rebuild');
        await page.waitForTimeout(500);
        check(gh.puts.length === 1, 'one commit was made', String(gh.puts.length));
        const put = gh.puts[0];
        check(put.body.branch === 'main' && put.body.sha === 'sha-1', 'to the default branch, on top of the file it read');
        check(/^Update site settings: /.test(put.body.message), 'with a message that says what it is', put.body.message);
        const saved = Buffer.from(put.body.content, 'base64').toString('utf8'), before = JSON.parse(SITE.config), after = JSON.parse(saved);
        check(after.pages.stories === false && after.pages.discoveries === true && after.site.name === 'Hartley and Moreau' && after.engine.channel === 'beta', 'the file says what was asked');
        const same = ['theme', 'tree', 'map', 'nav', 'stuart', 'head', 'data', 'admin'].every(k => JSON.stringify(before[k]) === JSON.stringify(after[k]));
        check(same, 'and nothing else in it changed');
        const was = new Set(SITE.config.split('\n')), added = saved.split('\n').filter(l => !was.has(l));
        check(added.length <= 5 && saved.split('\n').length - SITE.config.split('\n').length <= 2, 'only a few lines differ (' + added.length + ' new)', added.join(' | '));
        check(!saved.includes('github_pat'), 'the token is not in the file');
        const out = await status(page);
        check(/Saved/.test(out), 'it says it is saved', out);
        check(await page.locator('.ad-out a[href$="/commit/c0ffee"]').count() === 1, 'with a link to the change');
        check(await page.locator('.ad-out a[href$="/actions/runs/42"]').count() === 1, 'and a link to the build run');
        check(await sw(page, 'stories').isChecked() === false && await sw(page, 'discoveries').isChecked(), 'the switches show the new settings');
        await shot(page, 'admin-saved');

        // the same tab, reloaded: still signed in; then sign out
        await page.reload();
        await page.waitForSelector('#ad-app:not([hidden])');
        await page.waitForTimeout(300);
        check((await page.locator('.ad-ok').first().innerText()).includes('Signed in'), 'a reload in the same tab is still signed in');
        check(!(await sw(page, 'stories').isChecked()), 'and shows the settings that were saved');
        await page.click('text=Sign out');
        await page.waitForTimeout(300);
        check((await page.locator('.ad-ro').innerText()).includes('Read only') && await page.evaluate(() => sessionStorage.length) === 0, 'signing out clears the token and locks the page');

        // where the token went
        const all = JSON.stringify(gh.requests.map(r => r.path)) + JSON.stringify(page.logs) + page.url() + await page.content();
        check(!all.includes('github_pat'), 'the token is not in any address, the page, the log or the console');
        check(gh.requests.filter(r => r.auth).every(r => r.auth === 'Bearer ' + GOOD), 'it was sent only as an Authorization header, to api.github.com');
        check(page.external.length === 0, 'the page reached no other site', page.external.join(','));
        const cookies = await page.context().cookies();
        check(cookies.length === 0, 'no cookie holds it');
        check(await page.evaluate(() => localStorage.length) === 0, 'and nothing is kept after the tab closes');
        check(page.errors.length === 0, 'no errors in the page', page.errors.join(' | '));
        await page.context().close();
    }

    section('Language and site style are two separate settings on the same page');
    {
        gh.reset(SITE.config);
        const page = await open();
        const html = await page.content();
        check(await page.locator('.ad-lang').count() === 1 && await page.locator('.ad-style').count() === 1, 'the page has a Language section and a Site style section');
        check(await page.locator('.ad-style-card').count() === 11, 'there is a card for the Classic Archive and each of the ten styles', String(await page.locator('.ad-style-card').count()));
        check(await page.locator('#ad-style-classic').isChecked(), 'the site\'s own style (the Classic Archive) is the one picked');
        check(await page.locator('.ad-badge').count() >= 1 && (await page.locator('.ad-style-card:has(.ad-badge)').first().innerText()).includes('Suggested for this family'), 'one card says "Suggested for this family"');
        check(/places|birthplaces|data/i.test(await page.locator('.ad-suggest').innerText()), 'with the reasons in plain words');
        check(await page.evaluate(() => document.documentElement.getAttribute('data-heritage')) === null, 'and suggesting changes nothing: the page still has no style');
        check(!new RegExp('[' + String.fromCharCode(0x2013, 0x2014) + ']').test(await page.locator('.ad-style').innerText()), 'no long dashes in the section');
        check(await page.locator('#ad-style-texture').isHidden(), 'the texture option is hidden for the Classic Archive');
        check(await page.locator('#ad-lang-default option').count() >= 2, 'the language selector lists the engine\'s languages');
        check(await page.locator('#ad-lang-default').isDisabled(), 'and is locked until someone signs in');

        await signIn(page, GOOD);
        // try, cancel
        await page.click('label[for=ad-style-italian]');
        await page.waitForFunction(() => document.documentElement.getAttribute('data-heritage') === 'italian');
        check(true, 'clicking a card shows that style at once, without saving');
        check(await page.locator('.ad-stylebar').isVisible() && /not saved|Nothing is saved/.test(await page.locator('.ad-say').innerText()), 'with a note that nothing is saved yet');
        check(await page.locator('#h-preview').count() === 0, 'and no second banner on the settings page');
        check(gh.puts.length === 0, 'nothing was sent to GitHub');
        const swatch = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--h-accent').trim());
        check(/^#[0-9a-f]{6}$/i.test(swatch), 'the page really took the style\'s colours', swatch);
        await shot(page, 'admin-style-preview');
        // the preview follows the tab to the rest of the site
        await page.goto(URL + 'family-tree.html');
        await page.waitForFunction(() => document.documentElement.getAttribute('data-heritage') === 'italian');
        check(await page.locator('#h-preview').count() === 1, 'the site\'s pages show it too, with a bar that says it is a trial');
        await page.goBack();
        await page.waitForSelector('#ad-app:not([hidden])'); await page.waitForTimeout(400);
        check(await page.locator('#ad-style-italian').isChecked(), 'coming back to the settings page, the trial is still the one picked');
        await page.click('text=Cancel');
        await page.waitForFunction(() => document.documentElement.getAttribute('data-heritage') === null);
        check(await page.locator('#ad-style-classic').isChecked() && await page.locator('.ad-stylebar').isHidden(), 'Cancel puts the page back and hides the bar');
        check(await page.evaluate(() => sessionStorage.getItem('family-style-preview')) === null, 'and forgets the trial');

        // apply a style
        await page.click('label[for=ad-style-english]');
        await page.waitForFunction(() => document.documentElement.getAttribute('data-heritage') === 'english');
        check(await page.locator('#ad-style-texture').isVisible() && await page.locator('#ad-style-texture').isChecked(), 'a style with a texture shows the texture option, on by default');
        await page.click('text=Apply this style');
        const list = (await page.locator('.ad-changes').innerText()).replace(/\s+/g, ' ');
        check(/Site style: Classic Archive to English/.test(list) && !/Language|texture/i.test(list), 'Apply lists only the style change for review', list);
        check(gh.puts.length === 0, 'and saves nothing before the person confirms');
        await page.click('text=Save and rebuild');
        await page.waitForTimeout(500);
        check(gh.puts.length === 1, 'one commit was made', String(gh.puts.length));
        const a1 = JSON.parse(Buffer.from(gh.puts[0].body.content, 'base64').toString('utf8')), b1 = JSON.parse(SITE.config);
        check(a1.style && a1.style.heritage === 'english' && !('language' in a1) && JSON.stringify(a1.pages) === JSON.stringify(b1.pages), 'the file now has style.heritage and nothing else changed');
        check(Object.keys(b1).every(k => k === 'style' || JSON.stringify(b1[k]) === JSON.stringify(a1[k])), 'no other setting moved');

        // texture off, a separate option
        await page.click('#ad-style-texture', { force: true }).catch(() => {});
        await page.locator('#ad-style-texture').uncheck({ force: true });
        await page.waitForTimeout(250);
        check(await page.evaluate(() => document.documentElement.getAttribute('data-h-texture')) === 'off', 'turning the texture off is shown at once');
        await page.click('text=Apply this style');
        check(/Paper texture: on to off/.test((await page.locator('.ad-changes').innerText()).replace(/\s+/g, ' ')), 'and is its own change in the review');
        await page.click('text=Save and rebuild');
        await page.waitForTimeout(500);
        const a2 = JSON.parse(Buffer.from(gh.puts[1].body.content, 'base64').toString('utf8'));
        check(a2.style.heritage === 'english' && a2.style.options && a2.style.options.texture === false, 'saved as style.options.texture false');

        // back to the Classic Archive
        await page.click('label[for=ad-style-classic]');
        await page.waitForFunction(() => document.documentElement.getAttribute('data-heritage') === null);
        await page.click('text=Apply this style');
        await page.click('text=Save and rebuild');
        await page.waitForTimeout(500);
        const a3 = JSON.parse(Buffer.from(gh.puts[2].body.content, 'base64').toString('utf8'));
        check(a3.style.heritage === 'classic', 'choosing the Classic Archive again is saved as classic');

        // language, on its own
        await page.selectOption('#ad-lang-default', 'de');
        check(await page.locator('#ad-lang-de').isChecked() && await page.locator('#ad-lang-de').isDisabled(), 'the default language is always one visitors can use');
        await page.locator('#ad-lang-en').check({ force: true });
        await page.click('text=Review changes');
        const list2 = (await page.locator('.ad-changes').innerText()).replace(/\s+/g, ' ');
        check(/Default language: English to Deutsch/.test(list2) && /Languages visitors can choose/.test(list2) && !/Site style/.test(list2), 'language changes are listed on their own', list2);
        await page.click('text=Save and rebuild');
        await page.waitForTimeout(500);
        const a4 = JSON.parse(Buffer.from(gh.puts[3].body.content, 'base64').toString('utf8'));
        check(a4.language && a4.language.default === 'de' && JSON.stringify(a4.language.available.slice().sort()) === '["de","en"]' && a4.style.heritage === 'classic', 'saved as language.default and language.available, the style untouched');
        check(!JSON.stringify(gh.requests.map(r => r.path)).includes('github_pat'), 'no token in any address');
        check(page.errors.length === 0, 'no errors in the page', page.errors.join(' | '));
        await page.context().close();
    }

    section('Someone who cannot save can still look at a style');
    {
        const page = await open();
        await page.click('label[for=ad-style-scottish]');
        await page.waitForFunction(() => document.documentElement.getAttribute('data-heritage') === 'scottish');
        check(await page.locator('text=Apply this style').isDisabled(), 'but cannot apply it');
        check(/sign in/i.test(await page.locator('.ad-say').innerText()), 'and is told why');
        await page.context().close();
    }

    section('When the file changed on GitHub meanwhile, nothing is overwritten');
    {
        gh.reset(SITE.config);
        const page = await open();
        await signIn(page, GOOD);
        await sw(page, 'tree').uncheck({ force: true });
        await page.click('text=Review changes');
        gh.sha = 'sha-other'; gh.text = gh.text.replace('"Hartley & Moreau"', '"Someone else"');
        await page.click('text=Save and rebuild');
        await page.waitForTimeout(400);
        check((await status(page)).includes('changed on GitHub'), 'it says the file changed and asks for a reload', await status(page));
        check(gh.text.includes('Someone else'), 'their change is still there');
        await page.context().close();
    }

    section('Mistakes are caught before anything is sent');
    {
        gh.reset(SITE.config);
        const page = await open();
        await signIn(page, GOOD);
        await page.fill('#ad-name', 'Hartley ' + String.fromCharCode(0x2014) + ' Moreau');
        check(await page.locator('text=Review changes').isDisabled(), 'a long dash in the title blocks saving');
        check((await page.locator('.ad-error').innerText()).includes('long dash'), 'and says why');
        await page.fill('#ad-name', '');
        check((await page.locator('.ad-error').innerText()).includes('needs a title'), 'an empty title is refused');
        await page.fill('#ad-name', 'Hartley & Moreau');
        check(await page.locator('text=Review changes').isDisabled(), 'putting it back means no change');
        await page.context().close();
    }

    section('The phone layout');
    {
        gh.reset(SITE.config);
        const page = await open({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
        await signIn(page, GOOD);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        check(overflow <= 1, 'nothing runs off the side of the screen', String(overflow));
        await shot(page, 'admin-phone', true);
        await page.context().close();
    }

    // ---------------------------------------------------------------- a navigation bar with pages off
    section('A site with pages turned off');
    {
        const u = 'http://127.0.0.1:' + srvOff.address().port + '/';
        const ctx = await browser.newContext({ viewport: { width: 1500, height: 520 } });
        const page = await ctx.newPage();
        await page.goto(u + 'index.html');
        const links = await page.$$eval('.nav-links a', as => as.map(a => a.getAttribute('href')));
        check(!links.includes('map.html') && !links.includes('ask.html') && links.includes('family-tree.html'), 'the bar leaves out the pages that are off', links.join(' '));
        check((await page.goto(u + 'map.html')).status() === 404, 'the page that is off has no address');
        await page.goto(u + 'index.html');
        await shot(page, 'nav-with-pages-off');
        await page.setViewportSize({ width: 390, height: 700 });
        await page.click('#navToggle');
        await page.waitForTimeout(200);
        await shot(page, 'nav-with-pages-off-phone');
        await ctx.close();
    }

    await browser.close(); srv.close(); srvOff.close();
    done();
})();

function done() {
    console.log(failures ? '\n' + failures + ' check' + (failures === 1 ? '' : 's') + ' failed.' : '\nAll checks passed.');
    process.exit(failures ? 1 : 0);
}
