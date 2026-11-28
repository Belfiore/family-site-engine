/* The settings page (/admin/): switch pages on and off, change the site's title, tagline and engine channel, and
 * save site.config.json to the site's GitHub repository.
 *
 * There is no server. The page talks to the GitHub API from the browser with a token the person pastes. The token is
 * kept in this browser tab only (sessionStorage), is sent only to api.github.com, and is never written to the page,
 * the repository, the address bar or the console. Only people with write access to the repository can save; everyone
 * else sees the settings read only.
 *
 * The file is changed by editing the few lines that need it, not by writing it out again, so the commit shows only
 * what the person changed and the file keeps the way its owner laid it out. Before anything is sent, the result is
 * read back and checked: every setting this page does not own must be exactly as it was.
 *
 * The functions at the top (reading the settings, planning and applying the edits) have no page in them, so
 * tests/check-admin-edit.js runs them in Node.
 */
(function (root, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else { root.FamilyAdmin = api; if (root.document) api.start(root); }
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    var PAGE_KEYS = ['home', 'stories', 'tree', 'map', 'records', 'discoveries'];
    var DASHES = new RegExp('[' + String.fromCharCode(0x2013, 0x2014) + ']');
    var REPO_RE = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/;

    /* ------------------------------------------------------------------ the settings, read the way the build reads them */
    function isObject(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }

    // 'none' (null, empty or not there), 'off' (false, or an object with enabled false) or 'on': the same as build/sitecfg.py page_state
    function pageState(v) {
        if (v === undefined || v === null || v === '' || (isObject(v) && !Object.keys(v).length)) return 'none';
        if (v === false) return 'off';
        if (isObject(v)) return v.enabled === false ? 'off' : 'on';
        return 'on';
    }

    // whether a page is on, from the settings object: the same as the "on" in sitecfg.load's toggles
    function pageOn(key, cfg) {
        var pages = isObject(cfg.pages) ? cfg.pages : {};
        var v = pages[key], s = pageState(v);
        if (key === 'home') return true;
        if (key === 'stories') return s === 'on' || s === 'none';
        if (key === 'discoveries') return typeof v === 'boolean' ? v : !!(isObject(cfg.timeline) && cfg.timeline.enabled === true);
        return s === 'on';
    }

    /* ------------------------------------------------------------------ editing JSON text in place */
    function parse(text) {
        var i = 0, n = text.length;
        function fail(why) { throw new Error('The settings file is not valid JSON (' + why + ' at character ' + i + ').'); }
        function ws() { while (i < n && ' \t\r\n'.indexOf(text.charAt(i)) >= 0) i++; }
        function str() {
            var s = i;
            i++;
            while (i < n && text.charAt(i) !== '"') { if (text.charAt(i) === '\\') i++; i++; }
            if (i >= n) fail('a string is not closed');
            i++;
            return JSON.parse(text.slice(s, i));
        }
        function value() {
            ws();
            var start = i, c = text.charAt(i), members, items;
            if (c === '{') {
                i++; members = []; ws();
                if (text.charAt(i) === '}') { i++; return { type: 'object', start: start, end: i, members: members }; }
                for (;;) {
                    ws();
                    if (text.charAt(i) !== '"') fail('a name was expected');
                    var ks = i, key = str();
                    ws();
                    if (text.charAt(i) !== ':') fail('a : was expected');
                    i++;
                    members.push({ key: key, keyStart: ks, value: value() });
                    ws();
                    if (text.charAt(i) === ',') { i++; continue; }
                    if (text.charAt(i) === '}') { i++; break; }
                    fail('a , or } was expected');
                }
                return { type: 'object', start: start, end: i, members: members };
            }
            if (c === '[') {
                i++; items = []; ws();
                if (text.charAt(i) === ']') { i++; return { type: 'array', start: start, end: i, items: items }; }
                for (;;) {
                    items.push(value()); ws();
                    if (text.charAt(i) === ',') { i++; continue; }
                    if (text.charAt(i) === ']') { i++; break; }
                    fail('a , or ] was expected');
                }
                return { type: 'array', start: start, end: i, items: items };
            }
            if (c === '"') { str(); return { type: 'string', start: start, end: i }; }
            var re = /-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null/y;
            re.lastIndex = i;
            var m = re.exec(text);
            if (!m) fail('a value was expected');
            i += m[0].length;
            return { type: 'literal', start: start, end: i };
        }
        var root = value();
        ws();
        if (i < n) fail('something follows the end');
        return root;
    }

    function lineIndent(text, pos) {
        var s = text.lastIndexOf('\n', pos - 1) + 1, e = s;
        while (e < pos && (text.charAt(e) === ' ' || text.charAt(e) === '\t')) e++;
        return text.slice(s, e);
    }

    function isMultiLine(text, node) {
        return node.members.length > 0 && text.slice(node.start, node.members[0].keyStart).indexOf('\n') >= 0;
    }

    // the text of a new object holding one value at a path, laid out like the object it goes into
    function nested(path, valueText, multi, indent, unit) {
        if (!path.length) return valueText;
        var inner = nested(path.slice(1), valueText, multi, indent + unit, unit);
        if (!multi) return '{' + JSON.stringify(path[0]) + ': ' + inner + '}';
        return '{\n' + indent + unit + JSON.stringify(path[0]) + ': ' + inner + '\n' + indent + '}';
    }

    // text with the value at path (a list of names) set to valueText, changing nothing else in the file
    function setValue(text, path, valueText) {
        var rootNode = parse(text);
        if (rootNode.type !== 'object') throw new Error('The settings file must hold one object.');
        var unit = isMultiLine(text, rootNode) ? lineIndent(text, rootNode.members[0].keyStart) : '';
        function at(node, rest, depthIndent) {
            var member = null, k;
            for (k = 0; k < node.members.length; k++) if (node.members[k].key === rest[0]) member = node.members[k];
            var multi = isMultiLine(text, node);
            if (member) {
                if (rest.length === 1) return text.slice(0, member.value.start) + valueText + text.slice(member.value.end);
                if (member.value.type === 'object') return at(member.value, rest.slice(1), multi ? lineIndent(text, member.keyStart) : depthIndent);
                var indentHere = multi ? lineIndent(text, member.keyStart) : depthIndent;
                return text.slice(0, member.value.start) + nested(rest.slice(1), valueText, multi, indentHere, unit) + text.slice(member.value.end);
            }
            var memberIndent = multi ? lineIndent(text, node.members[0].keyStart) : depthIndent;
            var add = JSON.stringify(rest[0]) + ': ' + nested(rest.slice(1), valueText, multi, memberIndent, unit);
            if (!node.members.length) return text.slice(0, node.start) + '{' + add + '}' + text.slice(node.end);
            var last = node.members[node.members.length - 1].value.end;
            return text.slice(0, last) + (multi ? ',\n' + memberIndent : ', ') + add + text.slice(last);
        }
        return at(rootNode, path, '');
    }

    /* ------------------------------------------------------------------ planning the edits */
    function pageOps(key, want, cfg) {
        var v = (isObject(cfg.pages) ? cfg.pages : {})[key];
        var yes = want ? 'true' : 'false';
        if (key === 'discoveries') return [{ path: ['pages', key], text: yes }];
        if (isObject(v) && Object.keys(v).length) return [{ path: ['pages', key, 'enabled'], text: yes }];
        if (typeof v === 'string' && v && !want) return [{ path: ['pages', key], text: '{"file": ' + JSON.stringify(v) + ', "enabled": false}' }];
        return [{ path: ['pages', key], text: yes }];
    }

    /* languages: read the way build/i18n.py settings() reads them */
    function langSettings(cfg) {
        var b = isObject(cfg.language) ? cfg.language : {};
        var def = typeof b.default === 'string' && b.default ? b.default : 'en';
        var av = Array.isArray(b.available) && b.available.length ? b.available.slice() : [def];
        if (av.indexOf(def) < 0) av.unshift(def);
        return { default: def, available: av };
    }
    function sameSet(a, b) { return a.length === b.length && a.every(function (x) { return b.indexOf(x) >= 0; }); }
    function langName(code, names) { return (names && names[code]) || code; }

    // the style the settings name: an id, or 'classic' when none (the Classic Archive is the same as having no style)
    function styleId(cfg) { return isObject(cfg.style) && typeof cfg.style.heritage === 'string' && cfg.style.heritage ? cfg.style.heritage : 'classic'; }
    function styleTexture(cfg) { return !(isObject(cfg.style) && isObject(cfg.style.options) && cfg.style.options.texture === false); }

    // wanted: { pages: {key: bool}, name, description, channel, language: {default, available}, style: {id, texture, names, hasTexture} }.
    // Returns { ops, changes }: only what differs from cfg.
    function plan(cfg, wanted) {
        var ops = [], changes = [];
        if (wanted.language && typeof wanted.language.default === 'string' && Array.isArray(wanted.language.available)) {
            var L = langSettings(cfg), W = wanted.language, names = W.names || {};
            var wantAv = W.available.indexOf(W.default) < 0 ? [W.default].concat(W.available) : W.available.slice();
            if (W.default !== L.default) {
                ops.push({ path: ['language', 'default'], text: JSON.stringify(W.default) });
                changes.push({ label: 'Default language', from: langName(L.default, names), to: langName(W.default, names), plain: true });
            }
            var after = langSettings({ language: { default: W.default, available: isObject(cfg.language) ? cfg.language.available : undefined } });
            if (!sameSet(after.available, wantAv)) {
                ops.push({ path: ['language', 'available'], text: JSON.stringify(wantAv) });
                changes.push({ label: 'Languages visitors can choose', from: L.available.map(function (c) { return langName(c, names); }).join(', '),
                               to: wantAv.map(function (c) { return langName(c, names); }).join(', '), plain: true });
            }
        }
        if (wanted.style && typeof wanted.style.id === 'string') {
            var X = wanted.style, names2 = X.names || {}, was = styleId(cfg);
            if (X.id !== was) {
                ops.push({ path: ['style', 'heritage'], text: JSON.stringify(X.id) });
                changes.push({ label: 'Site style', from: names2[was] || was, to: names2[X.id] || X.id, plain: true });
            }
            if (X.id !== 'classic' && X.hasTexture && typeof X.texture === 'boolean' && X.texture !== styleTexture(cfg)) {
                ops.push({ path: ['style', 'options', 'texture'], text: X.texture ? 'true' : 'false' });
                changes.push({ label: 'Paper texture', from: styleTexture(cfg) ? 'on' : 'off', to: X.texture ? 'on' : 'off' });
            }
        }
        PAGE_KEYS.forEach(function (key) {
            if (key === 'home' || !wanted.pages || typeof wanted.pages[key] !== 'boolean') return;
            var was = pageOn(key, cfg);
            if (was === wanted.pages[key]) return;
            ops = ops.concat(pageOps(key, wanted.pages[key], cfg));
            changes.push({ label: pageLabel(key), from: was ? 'on' : 'off', to: wanted.pages[key] ? 'on' : 'off' });
        });
        var site = isObject(cfg.site) ? cfg.site : {}, engine = isObject(cfg.engine) ? cfg.engine : {};
        if (typeof wanted.name === 'string' && wanted.name !== (site.name || '')) {
            ops.push({ path: ['site', 'name'], text: JSON.stringify(wanted.name) });
            changes.push({ label: 'Site title', from: site.name || '', to: wanted.name });
        }
        if (typeof wanted.description === 'string' && wanted.description !== (site.description || '')) {
            ops.push({ path: ['site', 'description'], text: JSON.stringify(wanted.description) });
            changes.push({ label: 'Tagline', from: site.description || '', to: wanted.description });
        }
        if (typeof wanted.channel === 'string' && wanted.channel !== (engine.channel || 'stable')) {
            ops.push({ path: ['engine', 'channel'], text: JSON.stringify(wanted.channel) });
            changes.push({ label: 'Engine channel', from: engine.channel || 'stable', to: wanted.channel, plain: true });
        }
        return { ops: ops, changes: changes };
    }

    function pageLabel(key) {
        return { home: 'Home', stories: 'Stories', tree: 'Family Tree', map: 'Family Map', records: 'Records and Research', discoveries: 'Discoveries' }[key];
    }

    function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

    // Read the edited text back and make sure it says what was asked and nothing else changed. Throws if not.
    function verify(before, after, wanted) {
        var b, a;
        try { b = JSON.parse(before); a = JSON.parse(after); } catch (e) { throw new Error('The edited settings could not be read back, so nothing was saved.'); }
        Object.keys(b).concat(Object.keys(a)).forEach(function (k) {
            if (k === 'pages' || k === 'site' || k === 'engine' || k === 'language' || k === 'style') return;
            if (!same(b[k], a[k])) throw new Error('Editing would have changed "' + k + '", so nothing was saved.');
        });
        function rest(o, drop) {
            var c = {}; Object.keys(isObject(o) ? o : {}).forEach(function (k) { if (drop.indexOf(k) < 0) c[k] = o[k]; }); return c;
        }
        if (!same(rest(b.site, ['name', 'description']), rest(a.site, ['name', 'description']))) throw new Error('Editing would have changed other site settings, so nothing was saved.');
        if (!same(rest(b.engine, ['channel']), rest(a.engine, ['channel']))) throw new Error('Editing would have changed other engine settings, so nothing was saved.');
        if (!same(rest(b.language, ['default', 'available']), rest(a.language, ['default', 'available']))) throw new Error('Editing would have changed other language settings, so nothing was saved.');
        if (!same(rest(b.style, ['heritage', 'options']), rest(a.style, ['heritage', 'options']))) throw new Error('Editing would have changed other style settings, so nothing was saved.');
        if (!same(rest(isObject(b.style) ? b.style.options : null, ['texture']), rest(isObject(a.style) ? a.style.options : null, ['texture']))) throw new Error('Editing would have changed other style options, so nothing was saved.');
        if (!same(rest(b.pages, PAGE_KEYS), rest(a.pages, PAGE_KEYS))) throw new Error('Editing would have changed other page settings, so nothing was saved.');
        if (!same(isObject(b.pages) ? b.pages.home : undefined, isObject(a.pages) ? a.pages.home : undefined)) throw new Error('The home page setting must not change.');
        PAGE_KEYS.forEach(function (key) {
            if (key === 'home' || !wanted.pages || typeof wanted.pages[key] !== 'boolean') return;
            if (pageOn(key, a) !== wanted.pages[key]) throw new Error('The ' + pageLabel(key) + ' switch did not come out as asked, so nothing was saved.');
            if (isObject(b.pages) && isObject(b.pages[key]) && isObject(a.pages[key])) {
                if (!same(rest(b.pages[key], ['enabled']), rest(a.pages[key], ['enabled']))) throw new Error('Editing would have changed the ' + pageLabel(key) + ' settings, so nothing was saved.');
            }
            if (typeof (isObject(b.pages) ? b.pages[key] : undefined) === 'string' && pageOn(key, b) !== pageOn(key, a) && isObject(a.pages[key]) && a.pages[key].file !== b.pages[key]) throw new Error('The ' + pageLabel(key) + ' file name was lost, so nothing was saved.');
        });
        ['name', 'description'].forEach(function (k) {
            if (typeof wanted[k] === 'string' && (isObject(a.site) ? a.site[k] || '' : '') !== wanted[k]) throw new Error('The ' + k + ' did not come out as asked, so nothing was saved.');
        });
        if (wanted.language && typeof wanted.language.default === 'string' && Array.isArray(wanted.language.available)) {
            var got = langSettings(a), W2 = wanted.language;
            var wantAv2 = W2.available.indexOf(W2.default) < 0 ? [W2.default].concat(W2.available) : W2.available;
            if (got.default !== W2.default || !sameSet(got.available, wantAv2)) throw new Error('The language settings did not come out as asked, so nothing was saved.');
        }
        if (wanted.style && typeof wanted.style.id === 'string') {
            if (styleId(a) !== wanted.style.id) throw new Error('The style did not come out as asked, so nothing was saved.');
            if (wanted.style.id !== 'classic' && wanted.style.hasTexture && typeof wanted.style.texture === 'boolean' && styleTexture(a) !== wanted.style.texture) throw new Error('The paper texture did not come out as asked, so nothing was saved.');
        }
        if (typeof wanted.channel === 'string' && ((isObject(a.engine) ? a.engine.channel : null) || 'stable') !== wanted.channel) throw new Error('The channel did not come out as asked, so nothing was saved.');
        return a;
    }

    function apply(text, ops) {
        var out = text;
        ops.forEach(function (op) { out = setValue(out, op.path, op.text); });
        return out;
    }

    // the whole edit: the new text and the changes to show. Throws with a plain message when it cannot be done safely.
    function edit(text, wanted) {
        var cfg;
        try { cfg = JSON.parse(text); } catch (e) { throw new Error('The settings file on GitHub is not valid JSON, so it cannot be edited here.'); }
        if (!isObject(cfg)) throw new Error('The settings file must hold one object.');
        var p = plan(cfg, wanted);
        if (!p.ops.length) return { text: text, changes: [] };
        var next = apply(text, p.ops);
        verify(text, next, wanted);
        return { text: next, changes: p.changes };
    }

    function checkWords(name, description) {
        var problems = [];
        if (!name.trim()) problems.push('The site needs a title.');
        if (DASHES.test(name)) problems.push('The title has a long dash. Use a comma, a colon or brackets instead.');
        if (DASHES.test(description)) problems.push('The tagline has a long dash. Use a comma, a colon or brackets instead.');
        return problems;
    }

    /* ------------------------------------------------------------------ GitHub */
    var TOKEN_KEY = 'family-site-admin-token';

    function b64decode(s) {
        var bin = atob(s.replace(/\s/g, '')), bytes = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        return new TextDecoder('utf-8').decode(bytes);
    }
    function b64encode(s) {
        var bytes = new TextEncoder().encode(s), bin = '';
        for (var i = 0; i < bytes.length; i += 8192) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
        return btoa(bin);
    }
    function pathPart(p) { return p.split('/').map(encodeURIComponent).join('/'); }

    function client(token) {
        // The token goes in the Authorization header of a request to api.github.com and nowhere else.
        function call(method, path, body) {
            var headers = { 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
            if (token) headers['Authorization'] = 'Bearer ' + token;
            if (body) headers['Content-Type'] = 'application/json';
            return fetch('https://api.github.com' + path, { method: method, headers: headers, body: body ? JSON.stringify(body) : undefined, cache: 'no-store' })
                .then(function (r) { return r.text().then(function (t) { var j = null; try { j = t ? JSON.parse(t) : null; } catch (e) { j = null; } return { status: r.status, body: j }; }); });
        }
        return { call: call };
    }

    function explain(res, doing) {
        var why = res.body && res.body.message ? ' GitHub says: ' + res.body.message : '';
        if (res.status === 401) return 'GitHub did not accept the token. Check it has not expired, then sign in again.';
        if (res.status === 403 || res.status === 404) return 'GitHub would not let this token ' + doing + '. The token needs access to this repository with Contents set to read and write.' + why;
        if (res.status === 409 || res.status === 422) return 'The settings changed on GitHub (or the branch is protected) while this page was open. Reload the page, make the changes again and save.' + why;
        return 'GitHub answered ' + res.status + ' when this page tried to ' + doing + '.' + why;
    }

    /* ------------------------------------------------------------------ the page */
    function h(tag, attrs, kids) {
        var el = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            if (k === 'text') el.textContent = attrs[k];
            else if (k === 'class') el.className = attrs[k];
            else if (attrs[k] === true) el.setAttribute(k, '');
            else if (attrs[k] !== false && attrs[k] != null) el.setAttribute(k, attrs[k]);
        });
        (kids || []).forEach(function (c) { if (c) el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
        return el;
    }

    function guessRepo(loc) {
        var m = /^([a-z0-9-]+)\.github\.io$/i.exec(loc.hostname || '');
        if (!m) return null;
        var seg = (loc.pathname || '').split('/').filter(Boolean)[0];
        return seg && seg !== 'admin' ? m[1] + '/' + seg : null;
    }

    function start(win) {
        var node = win.document.getElementById('ad-data'), app = win.document.getElementById('ad-app');
        if (!node || !app) return;
        var data = JSON.parse(node.textContent);
        var S = { token: null, repo: data.repo || guessRepo(win.location), branch: data.branch, canWrite: false, user: null,
                  text: null, sha: null, cfg: null, live: false, busy: false, status: null, saved: null };
        try { S.token = win.sessionStorage.getItem(TOKEN_KEY); } catch (e) { S.token = null; }

        var ui = {};
        function build() {
            app.textContent = '';
            // account
            ui.account = h('section', { class: 'ad-card', 'aria-labelledby': 'ad-h-account' });
            // settings
            ui.form = h('form', { class: 'ad-card', novalidate: true, 'aria-labelledby': 'ad-h-settings' });
            ui.form.addEventListener('submit', function (e) { e.preventDefault(); review(); });
            ui.review = h('section', { class: 'ad-card ad-review', hidden: true, 'aria-labelledby': 'ad-h-review', tabindex: '-1' });
            ui.out = h('div', { class: 'ad-out', role: 'status', 'aria-live': 'polite' });
            [ui.account, ui.form, ui.review, ui.out].forEach(function (x) { app.appendChild(x); });
            app.hidden = false;
        }

        function wanted() {
            var pages = {};
            (ui.switches || []).forEach(function (s) { pages[s.key] = s.input.checked; });
            var w = { pages: pages, name: ui.name ? ui.name.value : '', description: ui.tagline ? ui.tagline.value : '', channel: ui.channel ? ui.channel.value : '' };
            if (ui.langDefault) {
                var names = {};
                data.language.have.forEach(function (c) { names[c.code] = c.name; });
                w.language = { default: ui.langDefault.value, names: names, available: (ui.langBoxes || []).filter(function (b) { return b.input.checked; }).map(function (b) { return b.code; }) };
            }
            if (S.styleSel) {
                var tn = {}, t = themeOf(S.styleSel);
                data.style.themes.forEach(function (x) { tn[x.id] = x.name; });
                w.style = { id: S.styleSel, names: tn, hasTexture: !!(t && t.options && t.options.texture), texture: S.styleTexture };
            }
            return w;
        }

        function themeOf(id) { return data.style.themes.filter(function (t) { return t.id === id; })[0] || null; }
        function slug(name) { return String(name).toLowerCase().replace(/ /g, '-'); }
        function fam(name) { return '"hf-' + slug(name) + '", "' + name + '", Georgia, serif'; }

        function drawAccount() {
            var a = ui.account;
            a.textContent = '';
            a.appendChild(h('h2', { id: 'ad-h-account', text: 'GitHub' }));
            if (!S.repo) {
                var rin = h('input', { type: 'text', id: 'ad-repo', autocomplete: 'off', spellcheck: 'false', placeholder: 'owner/name' });
                a.appendChild(h('p', { text: 'Which GitHub repository holds this site?' }));
                a.appendChild(h('label', { for: 'ad-repo', text: 'Repository' }));
                a.appendChild(rin);
                a.appendChild(h('button', { type: 'button', class: 'ad-btn', text: 'Use this repository', onclick: null }));
                a.lastChild.addEventListener('click', function () {
                    if (!REPO_RE.test(rin.value.trim())) { setOut('Write the repository as owner/name, like Belfiore/kohlmann-heritage.', 'error'); return; }
                    S.repo = rin.value.trim(); load();
                });
                return;
            }
            a.appendChild(h('p', { class: 'ad-repo' }, ['Repository: ', h('a', { href: 'https://github.com/' + S.repo, rel: 'noopener', text: S.repo })]));
            if (S.canWrite) {
                a.appendChild(h('p', { class: 'ad-ok', text: 'Signed in' + (S.user ? ' as ' + S.user : '') + '. You can save changes.' }));
                var out = h('button', { type: 'button', class: 'ad-btn ad-btn-quiet', text: 'Sign out' });
                out.addEventListener('click', signOut);
                a.appendChild(out);
                return;
            }
            a.appendChild(h('p', { class: 'ad-ro' }, [h('strong', { text: 'Read only. ' }), S.token && S.user ? 'This token does not have write access to the repository, so changes cannot be saved.' : 'Only people with write access to the repository can save changes.']));
            var field = h('input', { type: 'password', id: 'ad-token', autocomplete: 'off', spellcheck: 'false', 'aria-describedby': 'ad-token-help' });
            var go = h('button', { type: 'button', class: 'ad-btn', text: 'Sign in with a token' });
            go.addEventListener('click', function () { signIn(field.value.trim()); field.value = ''; });
            field.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); go.click(); } });
            a.appendChild(h('label', { for: 'ad-token', text: 'GitHub fine-grained token' }));
            a.appendChild(field);
            a.appendChild(go);
            a.appendChild(h('p', { id: 'ad-token-help', class: 'ad-help' }, [
                'Create one at ', h('a', { href: 'https://github.com/settings/personal-access-tokens/new', rel: 'noopener', text: 'GitHub, Settings, Developer settings, Fine-grained tokens' }),
                '. Choose only this repository and give it one permission: Contents, read and write. The token stays in this browser tab until you sign out or close it. It is never saved to the repository or the site.']));
        }

        function drawForm() {
            var f = ui.form, cfg = S.cfg, ro = !S.canWrite;
            f.textContent = '';
            f.appendChild(h('h2', { id: 'ad-h-settings', text: 'Settings' }));
            if (ro) f.appendChild(h('p', { class: 'ad-ro-note', text: S.live ? 'Read only. These are the settings on GitHub now.' : 'Read only. These are the settings the site was built with.' }));
            // pages
            var fs = h('fieldset', { class: 'ad-set' }, [h('legend', { text: 'Pages' })]);
            ui.switches = [];
            data.pages.forEach(function (p) {
                var on = S.cfg ? pageOn(p.key, cfg) : p.on;
                var id = 'ad-page-' + p.key;
                var input = h('input', { type: 'checkbox', id: id, role: 'switch', checked: on, disabled: ro || p.locked });
                input.checked = on;
                var note = '';
                if (p.locked) note = 'Always on';
                else if (on && !p.made && p.key === 'stories') note = 'Appears once the site has a story in content/stories';
                else if (p.key === 'discoveries') note = 'Needs the site\'s build workflow from engine 1.2.0 or newer';
                var row = h('div', { class: 'ad-row' }, [input, h('label', { for: id }, [h('span', { class: 'ad-name', text: p.label }), note ? h('span', { class: 'ad-note', text: note }) : null])]);
                input.addEventListener('change', onInput);
                ui.switches.push({ key: p.key, input: input });
                fs.appendChild(row);
            });
            f.appendChild(fs);
            // words
            var site = (cfg && isObject(cfg.site)) ? cfg.site : data.site, eng = (cfg && isObject(cfg.engine)) ? cfg.engine : { channel: data.engineSettings.channel, version: data.engineSettings.version };
            ui.name = h('input', { type: 'text', id: 'ad-name', value: site.name || '', disabled: ro, maxlength: '120' });
            ui.tagline = h('input', { type: 'text', id: 'ad-tagline', value: site.description || '', disabled: ro, maxlength: '300' });
            ui.name.value = site.name || ''; ui.tagline.value = site.description || '';
            f.appendChild(h('div', { class: 'ad-field' }, [h('label', { for: 'ad-name', text: 'Site title' }), ui.name]));
            f.appendChild(h('div', { class: 'ad-field' }, [h('label', { for: 'ad-tagline', text: 'Tagline' }), ui.tagline,
                h('span', { class: 'ad-note', text: 'Saved as site.description. Pages show it only if the site\'s own pages or theme use it.' })]));
            drawLanguage(f, ro);
            drawStyle(f, ro);
            ui.channel = h('select', { id: 'ad-channel', disabled: ro }, data.channels.map(function (c) { return h('option', { value: c, text: c }); }));
            ui.channel.value = eng.channel || 'stable';
            var chNote = eng.version ? 'This site is pinned to engine ' + eng.version + ', which overrides the channel. Remove engine.version in site.config.json to follow the channel.' : 'stable is the default. beta and canary get new engine versions first.';
            f.appendChild(h('div', { class: 'ad-field' }, [h('label', { for: 'ad-channel', text: 'Engine channel' }), ui.channel, h('span', { class: 'ad-note', text: chNote })]));
            [ui.name, ui.tagline, ui.channel].forEach(function (x) { x.addEventListener('input', onInput); x.addEventListener('change', onInput); });
            ui.problems = h('p', { class: 'ad-error', role: 'alert', hidden: true });
            ui.save = h('button', { type: 'submit', class: 'ad-btn ad-btn-main', text: 'Review changes', disabled: true });
            f.appendChild(ui.problems);
            if (!ro) f.appendChild(h('div', { class: 'ad-actions' }, [ui.save]));
            onInput();
        }


        /* ---------------------------------------------------------- language */
        function syncLang() {
            var d = ui.langDefault.value;
            (ui.langBoxes || []).forEach(function (b) {
                if (b.code === d) b.input.checked = true;
                b.input.disabled = !S.canWrite || b.code === d;
            });
        }
        function drawLanguage(f, ro) {
            var cur = langSettings(S.cfg || { language: { default: data.language.default, available: data.language.available } });
            var fs = h('fieldset', { class: 'ad-set ad-lang' }, [h('legend', { text: 'Language' })]);
            ui.langDefault = h('select', { id: 'ad-lang-default', disabled: ro }, data.language.have.map(function (c) { return h('option', { value: c.code, text: c.name }); }));
            ui.langDefault.value = cur.default;
            fs.appendChild(h('div', { class: 'ad-field' }, [h('label', { for: 'ad-lang-default', text: 'Default language' }), ui.langDefault,
                h('span', { class: 'ad-note', text: 'The language of the engine\'s own words (menus, buttons, dates) until a visitor chooses another. The site\'s own text stays as written.' })]));
            ui.langBoxes = [];
            fs.appendChild(h('p', { class: 'ad-sublabel', id: 'ad-lang-av', text: 'Languages visitors can choose' }));
            var group = h('div', { class: 'ad-langs', role: 'group', 'aria-labelledby': 'ad-lang-av' });
            data.language.have.forEach(function (c) {
                var input = h('input', { type: 'checkbox', id: 'ad-lang-' + c.code, value: c.code });
                input.checked = cur.available.indexOf(c.code) >= 0;
                input.addEventListener('change', onInput);
                ui.langBoxes.push({ code: c.code, input: input });
                group.appendChild(h('label', { class: 'ad-check', for: 'ad-lang-' + c.code }, [input, ' ' + c.name]));
            });
            fs.appendChild(group);
            fs.appendChild(h('span', { class: 'ad-note', text: 'With more than one, the navigation bar shows a switcher and the visitor\'s choice is kept in their browser. The style below does not depend on the language.' }));
            ui.langDefault.addEventListener('change', function () { syncLang(); onInput(); });
            f.appendChild(fs);
            syncLang();
        }

        /* ---------------------------------------------------------- site style */
        function savedStyle() { return S.cfg ? styleId(S.cfg) : data.style.saved; }
        function savedTexture() { return S.cfg ? styleTexture(S.cfg) : data.style.texture; }

        function previewNow() {
            var H = win.FamilyHeritage;
            if (!H) return;
            var t = themeOf(S.styleSel), hasTex = !!(t && t.options && t.options.texture);
            var tex = hasTex ? S.styleTexture : undefined;
            if (S.styleSel === savedStyle() && tex === savedTexture()) tex = undefined;
            H.preview(S.styleSel, { texture: tex, admin: win.location.href });
        }

        function syncStyle() {
            var changed = S.styleSel !== savedStyle() || (!!(themeOf(S.styleSel) && themeOf(S.styleSel).options.texture) && S.styleTexture !== savedTexture());
            (ui.styleCards || []).forEach(function (c) {
                c.input.checked = c.id === S.styleSel;
                c.card.classList.toggle('is-picked', c.id === S.styleSel);
                c.card.classList.toggle('is-saved', c.id === savedStyle());
            });
            var t = themeOf(S.styleSel), hasTex = !!(t && t.options && t.options.texture);
            ui.texRow.hidden = !hasTex;
            ui.tex.checked = S.styleTexture;
            ui.styleBar.hidden = !changed;
            ui.styleApply.disabled = !S.canWrite || !S.cfg;
            ui.styleSay.textContent = changed
                ? 'Trying the ' + (t ? t.name : S.styleSel) + ' style on every page of this site, in this browser tab only. Nothing is saved yet.' + (S.canWrite ? '' : ' Saving needs a token with write access (sign in above).')
                : '';
        }

        function drawStyle(f, ro) {
            var st = data.style, sg = st.suggestion, H = win.FamilyHeritage;
            var prev = H && H.previewing ? H.previewing() : null;
            if (!S.styleTouched) {
                S.styleSel = prev ? prev.id : savedStyle();
                S.styleTexture = prev && typeof prev.texture === 'boolean' ? prev.texture : savedTexture();
            }
            if (!themeOf(S.styleSel)) S.styleSel = 'classic';
            var fs = h('fieldset', { class: 'ad-set ad-style' }, [h('legend', { id: 'ad-style-h', text: 'Site style' })]);
            fs.appendChild(h('p', { class: 'ad-note ad-style-lede', text: 'A heritage style changes the fonts, colours, ornaments and the map\'s colours on every page. Choose one to try it on the real site. Nothing changes for visitors until you apply it.' }));
            if (sg) {
                var line = sg.reason;
                if (sg.mixed && sg.ranked && sg.ranked.length > 1) line += ' Closest matches: ' + sg.ranked.map(function (r) { return r.name + ' ' + r.percent + '%'; }).join(', ') + '.';
                fs.appendChild(h('p', { class: 'ad-suggest', text: line }));
            }
            var grid = h('div', { class: 'ad-styles', role: 'radiogroup', 'aria-labelledby': 'ad-style-h' });
            ui.styleCards = [];
            st.themes.forEach(function (t) {
                var input = h('input', { type: 'radio', name: 'ad-style', id: 'ad-style-' + t.id, value: t.id, class: 'ad-style-in' });
                var mock = h('span', { class: 'ad-mock', 'aria-hidden': 'true' }, [
                    h('span', { class: 'ad-mock-bar' }, [h('span', { class: 'ad-mock-title', text: 'Family name' })]),
                    h('span', { class: 'ad-mock-body' }, [h('span', { class: 'ad-mock-rule' }), h('span', { class: 'ad-mock-pin' }), h('span', { class: 'ad-mock-chip' })])]);
                ['paper', 'ink', 'accent', 'gold', 'line'].forEach(function (k) { mock.style.setProperty('--sw-' + k, t.swatches[k]); });
                mock.firstChild.firstChild.style.fontFamily = fam(t.fonts.heading);
                var sw = h('span', { class: 'ad-swatches', 'aria-hidden': 'true' }, ['paper', 'ink', 'accent', 'gold', 'line'].map(function (k) {
                    var d = h('span', { class: 'ad-sw' }); d.style.setProperty('background', t.swatches[k]); return d; }));
                var name = h('span', { class: 'ad-style-name', text: t.name });
                name.style.fontFamily = fam(t.fonts.heading);
                var badge = null;
                if (sg && sg.suggested === t.id) badge = h('span', { class: 'ad-badge' }, ['Suggested for this family' + (sg.mixed && sg.ranked[0] ? ', ' + sg.ranked[0].percent + '%' : '')]);
                else if (sg && sg.mixed) { var r = sg.ranked.filter(function (x) { return x.id === t.id; })[0]; if (r) badge = h('span', { class: 'ad-badge ad-badge-soft' }, ['Also fits, ' + r.percent + '%']); }
                var card = h('label', { class: 'ad-style-card', for: input.id }, [input, mock, name, badge, h('span', { class: 'ad-style-blurb', text: t.blurb }), h('span', { class: 'ad-style-fonts', text: t.fonts.heading === t.fonts.body ? t.fonts.heading : t.fonts.heading + ' and ' + t.fonts.body }), sw]);
                input.addEventListener('change', function () {
                    S.styleTouched = true; S.styleSel = t.id; S.styleTexture = savedTexture() === false && t.id !== savedStyle() ? true : S.styleTexture;
                    syncStyle(); previewNow(); onInput();
                });
                ui.styleCards.push({ id: t.id, input: input, card: card });
                grid.appendChild(card);
            });
            fs.appendChild(grid);
            ui.tex = h('input', { type: 'checkbox', id: 'ad-style-texture' });
            ui.texRow = h('div', { class: 'ad-opt' }, [h('label', { class: 'ad-check', for: 'ad-style-texture' }, [ui.tex, ' Paper texture']),
                h('span', { class: 'ad-note', text: 'A light paper grain behind the pages. It is off for visitors who ask their device for less motion or to save data.' })]);
            ui.tex.addEventListener('change', function () { S.styleTouched = true; S.styleTexture = ui.tex.checked; syncStyle(); previewNow(); onInput(); });
            fs.appendChild(ui.texRow);
            ui.styleSay = h('p', { class: 'ad-say', role: 'status' });
            ui.styleApply = h('button', { type: 'button', class: 'ad-btn ad-btn-main', text: 'Apply this style' });
            ui.styleCancel = h('button', { type: 'button', class: 'ad-btn ad-btn-quiet', text: 'Cancel' });
            ui.styleApply.addEventListener('click', function () { review(); });
            ui.styleCancel.addEventListener('click', function () {
                S.styleTouched = false; S.styleSel = savedStyle(); S.styleTexture = savedTexture();
                if (H) H.stopPreview();
                syncStyle(); onInput();
            });
            ui.styleBar = h('div', { class: 'ad-stylebar', hidden: true }, [ui.styleSay, h('div', { class: 'ad-actions' }, [ui.styleApply, ui.styleCancel])]);
            fs.appendChild(ui.styleBar);
            f.appendChild(fs);
            syncStyle();
            // every style's fonts are on hand so the cards show their own heading face
            if (H && H.registry) H.registry().then(function (reg) { reg.themes.forEach(function (t) { H.themeSheet(t).catch(function () { /* the card falls back to a serif */ }); }); }, function () { /* no styles to preview */ });
        }

        function currentCfg() { return S.cfg || {}; }

        function onInput() {
            if (!ui.save) return;
            var w = wanted(), problems = checkWords(w.name, w.description), p = plan(currentCfg(), w);
            ui.problems.hidden = !problems.length;
            ui.problems.textContent = problems.join(' ');
            ui.save.disabled = !S.canWrite || !S.cfg || !p.ops.length || !!problems.length || S.busy;
            ui.review.hidden = true;
        }

        function setOut(text, kind, links) {
            ui.out.textContent = '';
            ui.out.className = 'ad-out' + (kind ? ' ad-' + kind : '');
            if (text) ui.out.appendChild(document.createTextNode(text));
            (links || []).forEach(function (l) { if (l) { ui.out.appendChild(document.createTextNode(' ')); ui.out.appendChild(l); } });
        }
        // what to say once the settings have been read again (a token that was refused, for one)
        function settled() { var n = S.notice; S.notice = null; setOut(n || '', n ? 'error' : ''); }

        function ghLink(url, text) {
            if (!/^https:\/\/github\.com\//.test(url)) return null;
            return h('a', { href: url, rel: 'noopener', text: text });
        }

        // fetch the repository and the settings file; work out whether this person can save
        function load() {
            drawAccount();
            if (!S.repo) { drawForm(); return; }
            var gh = client(S.token);
            setOut('Reading the settings from GitHub...');
            gh.call('GET', '/repos/' + S.repo).then(function (repo) {
                if (repo.status === 401 && S.token) { forget(); S.notice = 'GitHub did not accept the token, so it was cleared. Sign in again.'; return load(); }
                if (repo.status !== 200) { S.cfg = null; S.live = false; S.canWrite = false; drawAccount(); drawForm(); setOut(repo.status === 404 ? 'This repository could not be read without signing in. The settings below are the ones the site was built with.' : explain(repo, 'read the repository'), repo.status === 404 ? '' : 'error'); return; }
                S.canWrite = !!(S.token && repo.body && repo.body.permissions && repo.body.permissions.push);
                S.branch = data.branch || (repo.body && repo.body.default_branch) || 'main';
                return Promise.all([S.token ? gh.call('GET', '/user') : { status: 0 }, gh.call('GET', '/repos/' + S.repo + '/contents/' + pathPart(data.configPath) + '?ref=' + encodeURIComponent(S.branch))]).then(function (rs) {
                    S.user = rs[0].status === 200 && rs[0].body ? rs[0].body.login : null;
                    var file = rs[1];
                    if (file.status !== 200 || !file.body || !file.body.content) { S.cfg = null; S.canWrite = false; drawAccount(); drawForm(); setOut(explain(file, 'read ' + data.configPath), 'error'); return; }
                    try { S.text = b64decode(file.body.content); S.cfg = JSON.parse(S.text); S.sha = file.body.sha; S.live = true; }
                    catch (e) { S.cfg = null; S.canWrite = false; drawAccount(); drawForm(); setOut('The settings file on GitHub could not be read: ' + e.message, 'error'); return; }
                    drawAccount(); drawForm(); settled();
                });
            }, function () { setOut('GitHub could not be reached. Check the connection and reload the page.', 'error'); S.cfg = null; drawForm(); });
        }

        function signIn(token) {
            if (!token) { setOut('Paste a token first.', 'error'); return; }
            S.token = token;
            try { win.sessionStorage.setItem(TOKEN_KEY, token); } catch (e) { /* the token then lasts until the page is closed */ }
            load();
        }
        function forget() { S.token = null; S.canWrite = false; S.user = null; try { win.sessionStorage.removeItem(TOKEN_KEY); } catch (e) { /* nothing to remove */ } }
        function signOut() { forget(); load(); }

        function review() {
            var w = wanted(), problems = checkWords(w.name, w.description);
            if (problems.length || !S.canWrite) return;
            var result;
            try { result = edit(S.text, w); } catch (e) { setOut(e.message, 'error'); return; }
            if (!result.changes.length) { setOut('Nothing has changed.'); return; }
            S.pending = result;
            var r = ui.review;
            r.textContent = '';
            r.appendChild(h('h2', { id: 'ad-h-review', text: 'Check before saving' }));
            r.appendChild(h('p', { text: 'Saving commits site.config.json to ' + S.repo + ' on the ' + S.branch + ' branch. The site then rebuilds by itself.' }));
            var ul = h('ul', { class: 'ad-changes' });
            result.changes.forEach(function (c) {
                var onoff = c.plain || c.to === 'on' || c.to === 'off';
                ul.appendChild(h('li', {}, [h('strong', { text: c.label + ': ' }), onoff ? c.from + ' to ' + c.to : '"' + c.from + '" to "' + c.to + '"']));
            });
            r.appendChild(ul);
            var back = h('button', { type: 'button', class: 'ad-btn ad-btn-quiet', text: 'Go back' });
            var go = h('button', { type: 'button', class: 'ad-btn ad-btn-main', text: 'Save and rebuild' });
            back.addEventListener('click', function () { r.hidden = true; ui.save.focus(); });
            go.addEventListener('click', save);
            r.appendChild(h('div', { class: 'ad-actions' }, [go, back]));
            r.hidden = false;
            r.focus();
        }

        function save() {
            if (S.busy || !S.pending) return;
            S.busy = true; ui.review.hidden = true; ui.save.disabled = true;
            var gh = client(S.token), msg = 'Update site settings: ' + S.pending.changes.map(function (c) { return c.label; }).join(', ');
            setOut('Saving...');
            gh.call('PUT', '/repos/' + S.repo + '/contents/' + pathPart(data.configPath), { message: msg + ' (from /admin)', content: b64encode(S.pending.text), sha: S.sha, branch: S.branch }).then(function (res) {
                S.busy = false;
                if (res.status !== 200 && res.status !== 201) { setOut(explain(res, 'save the settings'), 'error'); onInput(); return; }
                S.text = S.pending.text; S.cfg = JSON.parse(S.text); S.pending = null; S.styleTouched = false;
                S.sha = res.body && res.body.content ? res.body.content.sha : S.sha;
                var commit = res.body && res.body.commit ? res.body.commit : {};
                drawForm();
                S.changeLink = commit.html_url ? ghLink(commit.html_url, 'See the change') : null;
                setOut('Saved. The site is rebuilding.', 'ok', [S.changeLink]);
                if (commit.sha) findRun(gh, commit.sha, 0);
            }, function () { S.busy = false; setOut('GitHub could not be reached, so nothing was saved.', 'error'); onInput(); });
        }

        // the build starts a few seconds after the commit: look for its run, then link to it
        function findRun(gh, sha, tries) {
            gh.call('GET', '/repos/' + S.repo + '/actions/runs?head_sha=' + encodeURIComponent(sha) + '&per_page=10').then(function (res) {
                var runs = res.status === 200 && res.body && res.body.workflow_runs ? res.body.workflow_runs : [];
                if (runs.length) { setOut('Saved. The site is rebuilding.', 'ok', [S.changeLink, ghLink(runs[0].html_url, 'Watch the build')]); return; }
                if (tries < 8) { win.setTimeout(function () { findRun(gh, sha, tries + 1); }, 3000); return; }
                setOut('Saved. The build has not shown up yet.', 'ok', [S.changeLink, ghLink('https://github.com/' + S.repo + '/actions', 'See the builds')]);
            });
        }

        build();
        drawAccount();
        drawForm();
        load();
    }

    return { pageState: pageState, pageOn: pageOn, setValue: setValue, plan: plan, apply: apply, verify: verify, edit: edit,
             checkWords: checkWords, guessRepo: guessRepo, start: start, PAGE_KEYS: PAGE_KEYS, langSettings: langSettings, styleId: styleId, styleTexture: styleTexture };
});
