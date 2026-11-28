#!/usr/bin/env node
/* The settings page's editing logic (engine/admin.js), without a browser or GitHub.
 *
 *   node tests/check-admin-edit.js
 *
 * Checks that switching a page edits only the lines it has to, whatever the file's layout; that the page switches are read the
 * way the build reads them (the same cases tests/test_pages.py gives the build); and that an edit which would change something
 * else is refused.
 */
'use strict';
const fs = require('fs'), path = require('path'), assert = require('assert');
const A = require('../engine/admin.js');
const ROOT = path.join(__dirname, '..');
let n = 0;
function test(name, fn) { try { fn(); n++; } catch (e) { console.error('FAIL ' + name + '\n' + (e.stack || e)); process.exit(1); } }
const wantAll = (cfg, over) => { const pages = {}; A.PAGE_KEYS.forEach(k => { pages[k] = A.pageOn(k, cfg); }); Object.assign(pages, over); return { pages }; };

// the switches, read as the build reads them
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'pages-cases.json'), 'utf8'));
cases.forEach(c => test('switches: ' + c.name, () => {
    Object.keys(c.on).forEach(k => assert.strictEqual(A.pageOn(k, c.config), c.on[k], k));
    assert.strictEqual(A.pageOn('home', c.config), true);
}));

// the sample site's own settings file: a real layout (one space, objects written on one line)
const sample = fs.readFileSync(path.join(ROOT, 'sample', 'site.config.json'), 'utf8');
function diffLines(a, b) {
    const x = a.split('\n'), y = b.split('\n'), out = [];
    for (let i = 0; i < Math.max(x.length, y.length); i++) if (x[i] !== y[i]) out.push([x[i], y[i]]);
    return out;
}

test('sample: switching Stories off adds one line and changes nothing else', () => {
    const r = A.edit(sample, wantAll(JSON.parse(sample), { stories: false }));
    assert.deepStrictEqual(r.changes, [{ label: 'Stories', from: 'on', to: 'off' }]);
    assert.strictEqual(JSON.parse(r.text).pages.stories, false);
    assert.strictEqual(r.text.split('\n').length, sample.split('\n').length + 1);
    assert.ok(r.text.includes('\n  "stories": false'), r.text.slice(r.text.indexOf('"pages"'), r.text.indexOf('"pages"') + 600));
});

test('sample: an object value gets "enabled" inside it, keeping its other settings', () => {
    const r = A.edit(sample, wantAll(JSON.parse(sample), { tree: false }));
    const t = JSON.parse(r.text).pages.tree;
    assert.strictEqual(t.enabled, false);
    assert.strictEqual(t.file, 'family-tree.html');
    assert.strictEqual(diffLines(sample, r.text).length, 1, 'one line changed');
    assert.strictEqual(A.pageOn('tree', JSON.parse(r.text)), false);
});

test('sample: switching it back on, then off again, comes out the same', () => {
    const off = A.edit(sample, wantAll(JSON.parse(sample), { map: false })).text;
    const on = A.edit(off, wantAll(JSON.parse(off), { map: true })).text;
    assert.strictEqual(A.pageOn('map', JSON.parse(on)), true);
    assert.deepStrictEqual(JSON.parse(on).pages.map.file, 'map.html');
    assert.strictEqual(diffLines(sample, on).length, 1);
});

test('a file name value becomes an object so the file name is kept', () => {
    const src = '{\n  "schemaVersion": 1,\n  "pages": {\n    "home": "index.html",\n    "map": "map.html"\n  }\n}\n';
    const r = A.edit(src, wantAll(JSON.parse(src), { map: false }));
    assert.deepStrictEqual(JSON.parse(r.text).pages.map, { file: 'map.html', enabled: false });
    assert.strictEqual(JSON.parse(r.text).pages.home, 'index.html');
});

test('discoveries is a plain true or false, and wins over timeline.enabled', () => {
    const src = '{\n  "timeline": {"enabled": true},\n  "site": {"name": "A"}\n}\n';
    assert.strictEqual(A.pageOn('discoveries', JSON.parse(src)), true);
    const r = A.edit(src, wantAll(JSON.parse(src), { discoveries: false }));
    const cfg = JSON.parse(r.text);
    assert.strictEqual(cfg.pages.discoveries, false);
    assert.strictEqual(cfg.timeline.enabled, true, 'the older setting is left alone');
    assert.strictEqual(A.pageOn('discoveries', cfg), false);
});

test('the pages block is made when the file has none, in the file\'s own style', () => {
    const two = '{\n  "schemaVersion": 1,\n  "site": {\n    "name": "A"\n  }\n}\n';
    const a = A.edit(two, wantAll(JSON.parse(two), { records: true })).text;
    assert.strictEqual(a, '{\n  "schemaVersion": 1,\n  "site": {\n    "name": "A"\n  },\n  "pages": {\n    "records": true\n  }\n}\n');
    const tab = '{\n\t"schemaVersion": 1\n}\n';
    const b = A.edit(tab, wantAll(JSON.parse(tab), { stories: false })).text;
    assert.strictEqual(b, '{\n\t"schemaVersion": 1,\n\t"pages": {\n\t\t"stories": false\n\t}\n}\n');
    const one = '{"schemaVersion": 1, "site": {"name": "A"}}';
    const c = A.edit(one, wantAll(JSON.parse(one), { map: true })).text;
    assert.strictEqual(c, '{"schemaVersion": 1, "site": {"name": "A"}, "pages": {"map": true}}');
    const mini = '{"schemaVersion":1}';
    assert.strictEqual(JSON.parse(A.edit(mini, wantAll(JSON.parse(mini), { tree: true })).text).pages.tree, true);
});

test('title, tagline and channel', () => {
    const src = fs.readFileSync(path.join(ROOT, 'sample', 'site.config.json'), 'utf8');
    const w = Object.assign(wantAll(JSON.parse(src), {}), { name: 'Hartley and Moreau: our story', description: 'A made-up family "for tests"', channel: 'canary' });
    const r = A.edit(src, w);
    const cfg = JSON.parse(r.text);
    assert.strictEqual(cfg.site.name, 'Hartley and Moreau: our story');
    assert.strictEqual(cfg.site.description, 'A made-up family "for tests"');
    assert.strictEqual(cfg.engine.channel, 'canary');
    assert.strictEqual(r.changes.length, 3);
    assert.strictEqual(diffLines(src, r.text).length, 3);
    const none = '{"schemaVersion": 1, "site": {"name": "A"}}';
    assert.strictEqual(JSON.parse(A.edit(none, { channel: 'beta' }).text).engine.channel, 'beta');
});

test('nothing changed means no edit', () => {
    const r = A.edit(sample, Object.assign(wantAll(JSON.parse(sample), {}), { name: JSON.parse(sample).site.name }));
    assert.strictEqual(r.text, sample);
    assert.deepStrictEqual(r.changes, []);
});

test('Home cannot be switched off, and nothing else in the file moves', () => {
    const r = A.edit(sample, wantAll(JSON.parse(sample), { home: false }));
    assert.strictEqual(r.text, sample);
    const w = wantAll(JSON.parse(sample), { stories: false, records: true, discoveries: true });
    const out = JSON.parse(A.edit(sample, w).text), before = JSON.parse(sample);
    ['theme', 'tree', 'map', 'nav', 'stuart', 'head', 'data'].forEach(k => assert.deepStrictEqual(out[k], before[k], k));
});

test('text that is awkward for JSON survives', () => {
    const src = '{\n "site": {"name": "A \\"quoted\\" { brace }", "description": "caf\\u00e9, tab\\t"},\n "pages": {"home": "index.html"}\n}\n';
    const r = A.edit(src, Object.assign(wantAll(JSON.parse(src), { tree: true }), { name: 'Café ☃' }));
    const cfg = JSON.parse(r.text);
    assert.strictEqual(cfg.site.name, 'Café ☃');
    assert.strictEqual(cfg.site.description, 'café, tab\t');
    assert.strictEqual(cfg.pages.tree, true);
});

test('a file that is not JSON, or not an object, is refused', () => {
    assert.throws(() => A.edit('{"a": 1,}', {}), /not valid JSON/);
    assert.throws(() => A.edit('[1]', { name: 'x' }), /one object/);
});

test('verify refuses an edit that changed something else', () => {
    const before = '{"a": 1, "pages": {"map": true}}';
    assert.throws(() => A.verify(before, '{"a": 2, "pages": {"map": false}}', { pages: { map: false } }), /would have changed "a"/);
    assert.throws(() => A.verify(before, '{"a": 1, "pages": {"map": true}}', { pages: { map: false } }), /did not come out as asked/);
    assert.throws(() => A.verify(before, '{"a": 1, "pages": {"map": false, "other": 1}}', { pages: { map: false } }), /other page settings/);
});

test('language: reads the way the build reads it, and edits only what changed', () => {
    assert.deepStrictEqual(A.langSettings({}), { default: 'en', available: ['en'] });
    assert.deepStrictEqual(A.langSettings({ language: { default: 'de' } }), { default: 'de', available: ['de'] });
    assert.deepStrictEqual(A.langSettings({ language: { default: 'de', available: ['en'] } }), { default: 'de', available: ['de', 'en'] });
    const file = '{\n  "site": {"name": "X"},\n  "nav": []\n}\n';
    // nothing wanted that differs: no edit
    assert.strictEqual(A.edit(file, { language: { default: 'en', available: ['en'] } }).changes.length, 0);
    // default de, both choosable
    const r = A.edit(file, { language: { default: 'de', available: ['de', 'en'], names: { de: 'Deutsch', en: 'English' } } });
    const cfg = JSON.parse(r.text);
    assert.deepStrictEqual(cfg.language, { default: 'de', available: ['de', 'en'] });
    assert.strictEqual(r.changes.length, 2);
    assert.deepStrictEqual(JSON.parse(r.text).nav, []);
    // a site that already lists both and only changes the default writes only the default
    const f2 = '{"site": {"name": "X"}, "language": {"default": "en", "available": ["en", "de"]}}';
    const r2 = A.edit(f2, { language: { default: 'de', available: ['en', 'de'] } });
    assert.strictEqual(r2.changes.length, 1);
    assert.deepStrictEqual(JSON.parse(r2.text).language, { default: 'de', available: ['en', 'de'] });
    // other members of the block are never touched
    assert.throws(() => A.verify('{"language": {"default": "en"}}', '{"language": {"default": "en", "x": 1}}', {}), /other language settings/);
});

test('style: the Classic Archive is the same as none, and options are separate', () => {
    assert.strictEqual(A.styleId({}), 'classic');
    assert.strictEqual(A.styleId({ style: { heritage: 'german' } }), 'german');
    assert.strictEqual(A.styleTexture({ style: { heritage: 'english', options: { texture: false } } }), false);
    const file = '{\n  "site": {"name": "X"}\n}\n';
    assert.strictEqual(A.edit(file, { style: { id: 'classic', hasTexture: false } }).changes.length, 0);
    const names = { classic: 'Classic Archive', english: 'English' };
    const r = A.edit(file, { style: { id: 'english', names: names, hasTexture: true, texture: true } });
    assert.deepStrictEqual(JSON.parse(r.text).style, { heritage: 'english' });
    assert.deepStrictEqual(r.changes.map(c => c.label), ['Site style']);
    const r2 = A.edit(r.text, { style: { id: 'english', names: names, hasTexture: true, texture: false } });
    assert.deepStrictEqual(JSON.parse(r2.text).style, { heritage: 'english', options: { texture: false } });
    assert.deepStrictEqual(r2.changes.map(c => c.label), ['Paper texture']);
    // moving to a style with no texture option writes no texture
    const r3 = A.edit(r2.text, { style: { id: 'german', names: names, hasTexture: false, texture: false } });
    assert.strictEqual(JSON.parse(r3.text).style.heritage, 'german');
    assert.throws(() => A.verify('{"style": {"heritage": "english"}}', '{"style": {"heritage": "english", "other": 1}}', {}), /other style settings/);
    assert.throws(() => A.verify('{"style": {"options": {"texture": true, "x": 1}}}', '{"style": {"options": {"texture": false}}}', {}), /other style options/);
    assert.throws(() => A.verify('{"style": {"heritage": "english"}}', '{"style": {"heritage": "german"}}', { style: { id: 'english' } }), /did not come out as asked/);
    // style and language are two settings: changing one never writes the other
    const both = A.edit(file, { style: { id: 'english', names: names, hasTexture: true, texture: true }, language: { default: 'en', available: ['en'] } });
    assert.strictEqual(JSON.parse(both.text).language, undefined);
});

test('words: a long dash or an empty title is a problem', () => {
    const dash = String.fromCharCode(0x2014);
    assert.deepStrictEqual(A.checkWords('Fine title', 'Fine tagline'), []);
    assert.strictEqual(A.checkWords('', 'x').length, 1);
    assert.strictEqual(A.checkWords('A ' + dash + ' B', 'x').length, 1);
    assert.strictEqual(A.checkWords('A', 'a ' + String.fromCharCode(0x2013) + ' b').length, 1);
});

test('the repository can be read from a GitHub Pages address', () => {
    assert.strictEqual(A.guessRepo({ hostname: 'belfiore.github.io', pathname: '/kohlmann-heritage/admin/' }), 'belfiore/kohlmann-heritage');
    assert.strictEqual(A.guessRepo({ hostname: 'example.org', pathname: '/admin/' }), null);
    assert.strictEqual(A.guessRepo({ hostname: 'belfiore.github.io', pathname: '/admin/' }), null);
});

console.log('admin edit checks passed (' + n + ')');
