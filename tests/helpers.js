/* Small helpers shared by the browser checks (check-visitor.js, check-access.js). */
const fs = require('fs'), path = require('path'), http = require('http'), os = require('os'), cp = require('child_process');
const ROOT = path.dirname(__dirname);

const state = { failures: 0 };
const ok = m => console.log('  ok   ' + m);
const fail = m => { state.failures++; console.log('  FAIL ' + m); };
const check = (c, m, detail) => c ? ok(m) : fail(m + (detail !== undefined ? ': ' + detail : ''));
const section = t => console.log('\n' + t);

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.txt': 'text/plain' };
function serveStatic(dir) {
    dir = path.resolve(dir);
    return new Promise(res => {
        const srv = http.createServer((req, rsp) => {
            let p = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
            if (p.endsWith('/')) p += 'index.html';
            const f = path.join(dir, p);
            if (!f.startsWith(dir) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { rsp.writeHead(404); return rsp.end('not found'); }
            rsp.writeHead(200, { 'content-type': TYPES[path.extname(f).toLowerCase()] || 'application/octet-stream' });
            fs.createReadStream(f).pipe(rsp);
        });
        srv.listen(0, '127.0.0.1', () => res({ url: 'http://127.0.0.1:' + srv.address().port, close: () => new Promise(r => srv.close(r)) }));
    });
}

// a made-up site (tests/access_fixtures.py) built into a temporary folder; opts are access_fixtures.py's flags
function buildFixture(tmp, name, flags) {
    const site = path.join(tmp, name + '-src'), out = path.join(tmp, name);
    cp.execFileSync('python3', [path.join(ROOT, 'tests', 'access_fixtures.py'), site].concat(flags || []), { stdio: 'pipe' });
    cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', out], { stdio: 'pipe' });
    return out;
}
function buildSample(tmp) {
    const out = path.join(tmp, 'sample');
    cp.execFileSync('python3', [path.join(ROOT, 'build', 'build_site.py'), '--site', path.join(ROOT, 'sample'), '--out', out], { stdio: 'pipe' });
    return out;
}
const tmpdir = prefix => fs.mkdtempSync(path.join(os.tmpdir(), prefix));

// where a person's card is on screen, as a fraction of the tree's viewport (0.5, 0.5 is the middle)
async function cardAt(page, id) {
    return page.evaluate(id => {
        const c = document.querySelector('.card[data-id="' + id + '"]'), v = document.getElementById('viewport') || document.querySelector('.tc-viewport') || document.querySelector('.tc-canvas');
        if (!c || !v) return null;
        const a = c.getBoundingClientRect(), b = v.getBoundingClientRect();
        return { x: (a.left + a.width / 2 - b.left) / b.width, y: (a.top + a.height / 2 - b.top) / b.height, w: a.width / b.width };
    }, id);
}
async function treeView(page) { return page.evaluate(() => ({ tx: Math.round(__tree.S.tx), ty: Math.round(__tree.S.ty), s: +__tree.S.s.toFixed(3), viewpoint: __tree.S.viewpoint })); }

module.exports = { ROOT, state, ok, fail, check, section, serveStatic, buildFixture, buildSample, tmpdir, cardAt, treeView };
