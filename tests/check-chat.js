/* The site chat, against the sample family: the button, a question answered from the
 * site's own pages, and a question the site does not cover.
 *
 *   node tests/check-chat.js
 *   SHOTS=dir node tests/check-chat.js
 *
 * Starts tools/chat-proxy.py with no key, so the answer is quoted from the passages.
 * Needs Node 18 or later and Playwright with Chromium.
 */
const fs = require('fs'), path = require('path'), http = require('http'), os = require('os'), cp = require('child_process');
const { chromium } = require('playwright');
const ROOT = path.dirname(__dirname);
const SHOTS = process.env.SHOTS || '/opt/cursor/artifacts';

let failures = 0;
const ok = m => console.log('  ok   ' + m);
const fail = m => { failures++; console.log('  FAIL ' + m); };
const check = (c, m, detail) => c ? ok(m) : fail(m + (detail ? ': ' + detail : ''));

function startProxy() {
    return new Promise((resolve, reject) => {
        const proc = cp.spawn('python3', [path.join(ROOT, 'tools', 'chat-proxy.py'), '--port', '0'], { stdio: ['ignore', 'pipe', 'pipe'] });
        let buf = '', err = '';
        const timer = setTimeout(() => reject(new Error('proxy did not start: ' + err)), 8000);
        proc.stdout.on('data', d => {
            buf += d.toString();
            const m = buf.match(/chat-proxy (\S+):(\d+)/);
            if (m) { clearTimeout(timer); resolve({ proc, port: m[2] }); }
        });
        proc.stderr.on('data', d => { err += d.toString(); });
        proc.on('exit', code => { if (!/chat-proxy/.test(buf)) reject(new Error('proxy exited ' + code + ' ' + err)); });
    });
}

function serve(dist) {
    const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml' };
    return new Promise(res => {
        const srv = http.createServer((req, rsp) => {
            let p = decodeURIComponent(req.url.split('?')[0]);
            if (p.endsWith('/')) p += 'index.html';
            const f = path.join(dist, p);
            if (!f.startsWith(dist) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { rsp.writeHead(404); return rsp.end('not found'); }
            rsp.writeHead(200, { 'content-type': types[path.extname(f).toLowerCase()] || 'application/octet-stream' });
            fs.createReadStream(f).pipe(rsp);
        });
        srv.listen(0, '127.0.0.1', () => res(srv));
    });
}

function status(port) {
    return new Promise((resolve, reject) => {
        http.get('http://127.0.0.1:' + port + '/status', res => {
            let b = '';
            res.on('data', d => { b += d; });
            res.on('end', () => { try { resolve(JSON.parse(b)); } catch (e) { reject(e); } });
        }).on('error', reject);
    });
}

async function ask(page, q, pattern) {
    const box = page.locator('#site-chat');
    await box.getByLabel('Question', { exact: true }).fill(q);
    await box.getByRole('button', { name: 'Send' }).click();
    await page.waitForFunction(re => new RegExp(re, 'i').test(document.querySelector('#site-chat .sc-log').innerText), pattern, { timeout: 10000 });
}

(async () => {
    fs.mkdirSync(SHOTS, { recursive: true });
    const proxy = await startProxy();
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-chat-'));
    const site = path.join(tmp, 'site');
    fs.cpSync(path.join(ROOT, 'sample'), site, { recursive: true });
    const cfg = JSON.parse(fs.readFileSync(path.join(site, 'site.config.json'), 'utf8'));
    cfg.chat = {
        enabled: true,
        name: 'Guide',
        greeting: 'Ask a question about this family. I answer only from the pages and records on this site.',
        endpoint: 'http://127.0.0.1:' + proxy.port + '/chat'
    };
    fs.writeFileSync(path.join(site, 'site.config.json'), JSON.stringify(cfg, null, 1));
    const dist = path.join(tmp, '_site');
    cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', dist], { stdio: 'inherit' });

    const build = JSON.parse(fs.readFileSync(path.join(dist, 'engine-build.json'), 'utf8'));
    const chat = require(path.join(dist, 'engine', build.engine, 'chat.js'));
    const idx = JSON.parse(fs.readFileSync(path.join(dist, 'chat', 'index.json'), 'utf8'));
    const hits = chat.rank(idx.passages, 'Where did Thomas Hartley live?');
        check(hits.some(h => /Park Row|Leeds/.test(h.text)), 'the index search finds Park Row or Leeds', hits.map(h => h.title).join(', '));
        check(chat.rank(idx.passages, 'What is the capital of Japan?').length === 0, 'an unrelated question matches nothing');
        check(!/Tokyo/.test(hits.map(h => h.text).join(' ')), 'the passages for that question do not mention Tokyo');

    const srv = await serve(dist);
    const origin = 'http://127.0.0.1:' + srv.address().port;
    const browser = await chromium.launch();
    const errors = [];
    try {
        const desk = await browser.newContext({ viewport: { width: 1280, height: 800 } });
        const page = await desk.newPage();
        page.on('pageerror', e => errors.push(String(e)));
        await page.goto(origin + '/index.html', { waitUntil: 'load' });
        const guide = page.getByRole('button', { name: 'Ask Guide' });
        const stuart = page.getByRole('button', { name: 'Ask Stuart' });
        await guide.waitFor({ timeout: 10000 });
        await stuart.waitFor({ timeout: 10000 });
        const ga = await guide.boundingBox(), sa = await stuart.boundingBox();
        const overlap = ga && sa && ga.x < sa.x + sa.width && ga.x + ga.width > sa.x && ga.y < sa.y + sa.height && ga.y + ga.height > sa.y;
        check(!overlap, 'Ask Guide sits clear of Ask Stuart');
        await page.screenshot({ path: path.join(SHOTS, 'chat-buttons.png') });

        await guide.click();
        await page.getByText('Ask a question about this family.').waitFor();
        await ask(page, 'Where did Thomas Hartley live?', 'Leeds|Park Row');
        const answer = await page.locator('.sc-log').innerText();
        check(/from the site/i.test(answer), 'the answer names the passages it used');
        const bots = await page.locator('.sc-msg--bot').allInnerTexts();
        check(bots.every(t => !/Tokyo/.test(t)), 'no answer invents a place the site does not mention');
        await page.screenshot({ path: path.join(SHOTS, 'chat-answer.png') });
        await ask(page, 'What is the capital of Japan?', 'could not find anything');
        await page.screenshot({ path: path.join(SHOTS, 'chat-nothing.png') });
        const afterHome = await status(proxy.port);
        check(afterHome.requests === 1, 'only the question the site can cover called the service', JSON.stringify(afterHome));

        const askCtx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
        const askPage = await askCtx.newPage();
        askPage.on('pageerror', e => errors.push(String(e)));
        await askPage.goto(origin + '/ask.html', { waitUntil: 'load' });
        await askPage.getByRole('button', { name: 'Ask Guide' }).click();
        await ask(askPage, 'Where did Thomas Hartley live?', 'Leeds|Park Row');
        await askPage.screenshot({ path: path.join(SHOTS, 'chat-on-stuart.png') });
        const afterAsk = await status(proxy.port);
        check(afterAsk.requests === 2, 'Stuart\'s page allows the call', JSON.stringify(afterAsk));

        const phoneCtx = await browser.newContext({ viewport: { width: 390, height: 844 } });
        const phone = await phoneCtx.newPage();
        phone.on('pageerror', e => errors.push(String(e)));
        await phone.goto(origin + '/index.html', { waitUntil: 'load' });
        await phone.getByRole('button', { name: 'Ask Guide' }).click();
        await ask(phone, 'Where did Thomas Hartley live?', 'Leeds|Park Row');
        const box = await phone.locator('.sc-panel').boundingBox();
        check(box && box.x >= 0 && box.x + box.width <= 390 + 1, 'the window fits a phone', JSON.stringify(box));
        await phone.screenshot({ path: path.join(SHOTS, 'chat-phone.png') });
        check(errors.length === 0, 'no page errors', errors.join('; '));
    } finally {
        await browser.close();
        srv.close();
        proxy.proc.kill();
    }
    console.log(failures ? '\n' + failures + ' failed' : '\nall passed');
    process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
