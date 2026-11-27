/* A stand-in for Cloudflare Pages, for tests: runs the built _worker.js in Node (Node 18 or later) and serves the built
 * site's files only through env.ASSETS, the way Pages does. The worker is the real one the build wrote.
 *
 *   const { startGate } = require('./gate-server');
 *   const g = await startGate({ dir: '/path/to/_site', password: 'secret' });   // g.url, g.close()
 *
 * Pages does not serve _worker.js or _routes.json as files, and neither does this.
 */
const fs = require('fs'), path = require('path'), http = require('http'), os = require('os'), { pathToFileURL } = require('url');

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.txt': 'text/plain', '.woff2': 'font/woff2' };

async function loadWorker(dir) {
    const copy = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'gate-worker-')), 'worker-' + process.hrtime.bigint() + '.mjs');
    fs.copyFileSync(path.join(dir, '_worker.js'), copy);
    return (await import(pathToFileURL(copy).href)).default;
}

function assets(dir) {
    const root = path.resolve(dir);
    return {
        async fetch(request) {
            let p = decodeURIComponent(new URL(request.url).pathname);
            if (p.endsWith('/')) p += 'index.html';
            const f = path.join(root, p);
            const hidden = ['/_worker.js', '/_routes.json'];
            if (!f.startsWith(root + path.sep) || hidden.indexOf(p) >= 0) return new Response('Not found', { status: 404 });
            const file = [f, f + '.html'].filter(x => fs.existsSync(x) && fs.statSync(x).isFile())[0];
            if (!file) return new Response('Not found', { status: 404 });
            return new Response(fs.readFileSync(file), { status: 200, headers: { 'content-type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream' } });
        },
    };
}

// env: what Cloudflare passes the worker. password: SITE_PASSWORD (leave out to see it refuse everything)
async function startGate({ dir, password, port = 0, env = {} }) {
    const worker = await loadWorker(dir);
    const full = Object.assign({}, password === undefined ? {} : { SITE_PASSWORD: password }, env, { ASSETS: assets(dir) });
    const srv = http.createServer(async (req, rsp) => {
        try {
            const chunks = [];
            for await (const c of req) chunks.push(c);
            const url = 'http://' + req.headers.host + req.url;
            const init = { method: req.method, headers: req.headers };
            if (chunks.length && req.method !== 'GET' && req.method !== 'HEAD') init.body = Buffer.concat(chunks);
            const res = await worker.fetch(new Request(url, init), full);
            const headers = {};
            res.headers.forEach((v, k) => { if (k !== 'set-cookie') headers[k] = v; });
            const cookies = res.headers.getSetCookie ? res.headers.getSetCookie() : [];
            if (cookies.length) headers['set-cookie'] = cookies;
            rsp.writeHead(res.status, headers);
            rsp.end(Buffer.from(await res.arrayBuffer()));
        } catch (e) {
            rsp.writeHead(500, { 'content-type': 'text/plain' });
            rsp.end('gate harness error: ' + e.message);
        }
    });
    await new Promise(r => srv.listen(port, '127.0.0.1', r));
    const url = 'http://127.0.0.1:' + srv.address().port;
    return { url, port: srv.address().port, close: () => new Promise(r => srv.close(r)) };
}

module.exports = { startGate };

if (require.main === module) {
    // node tests/gate-server.js DIST PASSWORD [PORT]   for looking at a protected build by hand
    const [dir, password, port] = process.argv.slice(2);
    if (!dir || !password) { console.error('usage: node tests/gate-server.js DIST PASSWORD [PORT]'); process.exit(2); }
    startGate({ dir, password, port: Number(port) || 8787 }).then(g => console.log('gate at ' + g.url));
}
