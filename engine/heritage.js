/* @i18n heritage */
/* Heritage styles at run time (docs/themes.md).
 *
 * A site that has applied a style already has its attribute and stylesheets in every page. This script exists for two
 * things: the settings page and the pages it previews (try a style on the real site without saving it), and the map
 * (its tiles and lines are drawn by script, so they read their colours from here).
 *
 *   FamilyHeritage.current()            the style on the page now ('classic' when none)
 *   FamilyHeritage.preview(id, opts)    show a style on this page without saving; remembered for this tab only
 *   FamilyHeritage.stopPreview()        back to what the site has saved
 *   FamilyHeritage.cv(name, fallback)   a colour from the style (a --h-* custom property), or the fallback
 *   document event 'heritage:change'    fired after the colours change (the map listens)
 */
(function (root) {
    'use strict';
    var doc = root.document, html = doc.documentElement;
    var KEY = 'family-style-preview';
    var me = doc.currentScript && doc.currentScript.src;
    var base = me ? me.replace(/heritage\.js(\?.*)?$/, 'themes/') : null;
    var saved = html.getAttribute('data-heritage') || 'classic';
    var savedTexture = html.getAttribute('data-h-texture');
    // a visitor who asked for less data gets no texture and no ornaments (only colours and fonts)
    try { var conn = root.navigator && root.navigator.connection; if (conn && conn.saveData) html.setAttribute('data-h-save', ''); } catch (e) { /* no connection information */ }
    var shown = saved, shownOff = savedTexture === 'off', registry = null;

    function words(key, vars) {
        var s = (root.FamilyI18n && root.FamilyI18n.t) ? root.FamilyI18n.t(key, vars) : null;
        return s || key;
    }
    function store(v) {
        try { if (v === null) root.sessionStorage.removeItem(KEY); else root.sessionStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* no storage: the preview lasts for this page only */ }
    }
    function stored() { try { return JSON.parse(root.sessionStorage.getItem(KEY) || 'null'); } catch (e) { return null; } }

    function loadRegistry() {
        if (registry) return Promise.resolve(registry);
        if (!base) return Promise.reject(new Error('no base'));
        return root.fetch(base + 'registry.json').then(function (r) { return r.json(); }).then(function (j) { registry = j; return j; });
    }
    function sheet(id, href) {
        var el = doc.getElementById(id);
        if (el) return Promise.resolve(el);
        return new Promise(function (ok, no) {
            el = doc.createElement('link'); el.rel = 'stylesheet'; el.id = id; el.href = href;
            el.onload = function () { ok(el); }; el.onerror = function () { no(new Error(href)); };
            doc.head.appendChild(el);
        });
    }
    function cv(name, fallback) {
        var v = root.getComputedStyle(html).getPropertyValue(name);
        v = v && v.trim();
        return v || fallback;
    }

    // Show a style: load its files, wait for its two fonts so nothing jumps, then change the attribute in one go.
    function show(id, opts) {
        opts = opts || {};
        if (id === shown && !opts.force && (opts.texture === false) === shownOff) return Promise.resolve(id);
        var done = function () {
            html.classList.add('h-fade');
            if (id === 'classic') { html.removeAttribute('data-heritage'); html.removeAttribute('data-h-texture'); }
            else {
                html.setAttribute('data-heritage', id);
                if (opts.texture === false) html.setAttribute('data-h-texture', 'off'); else html.removeAttribute('data-h-texture');
            }
            shown = id; shownOff = id !== 'classic' && opts.texture === false;
            root.setTimeout(function () { html.classList.remove('h-fade'); }, 260);
            doc.dispatchEvent(new root.CustomEvent('heritage:change', { detail: { id: id } }));
            return id;
        };
        if (id === 'classic') return Promise.resolve(done());
        return loadRegistry().then(function (reg) {
            var t = reg.themes.filter(function (x) { return x.id === id; })[0];
            if (!t || !t.file) throw new Error('unknown style ' + id);
            return sheet('h-base', base + 'base.css').then(function () { return sheet('h-theme-' + id, base + t.file); }).then(function () {
                var f = root.document.fonts;
                if (!f || !f.load) return null;
                return Promise.race([
                    Promise.all([f.load('1em "hf-' + slug(t.fonts.heading) + '"'), f.load('1em "hf-' + slug(t.fonts.body) + '"')]),
                    new Promise(function (ok) { root.setTimeout(ok, 1500); })
                ]);
            });
        }).then(done);
    }
    function slug(name) { return name.toLowerCase().replace(/ /g, '-'); }

    function banner(id) {
        if (doc.getElementById('ad-app')) return;      // the settings page has its own bar
        var b = doc.getElementById('h-preview');
        if (!id) { if (b) b.remove(); return; }
        loadRegistry().then(function (reg) {
            var t = reg.themes.filter(function (x) { return x.id === id; })[0];
            if (!t) return;
            if (!b) { b = doc.createElement('div'); b.id = 'h-preview'; b.setAttribute('role', 'status'); doc.body.appendChild(b); }
            b.innerHTML = '';
            var s = doc.createElement('span'); s.textContent = words('heritage.previewing', { name: t.name }); b.appendChild(s);
            var back = doc.createElement('a'); back.href = adminHref(); back.textContent = words('heritage.back'); b.appendChild(back);
            var stop = doc.createElement('button'); stop.type = 'button'; stop.textContent = words('heritage.stop');
            stop.addEventListener('click', function () { stopPreview(); }); b.appendChild(stop);
        });
    }
    function adminHref() {
        var p = stored(); return (p && p.admin) || '#';
    }
    function preview(id, opts) {
        opts = opts || {};
        var p = { id: id, texture: opts.texture, admin: opts.admin || (stored() || {}).admin };
        store(id === saved && opts.texture === undefined ? null : p);
        return show(id, opts).then(function () { banner(id === saved && opts.texture === undefined ? null : id); });
    }
    function stopPreview() {
        store(null); banner(null);
        return show(saved, { texture: savedTexture !== 'off', force: true });
    }

    // a preview started on the settings page carries over to every page of this tab
    var p0 = stored();
    if (p0 && p0.id && p0.id !== saved && doc.readyState !== 'loading') { show(p0.id, { texture: p0.texture }); }
    else if (p0 && p0.id && p0.id !== saved) {
        // before the first paint: use a style that is already loaded if there is one, otherwise load it
        doc.addEventListener('DOMContentLoaded', function () { show(p0.id, { texture: p0.texture }).then(function () { banner(p0.id); }); });
    }

    root.FamilyHeritage = { current: function () { return shown; }, saved: function () { return saved; }, savedTexture: function () { return savedTexture !== 'off'; },
        previewing: function () { var p = stored(); return p && p.id ? { id: p.id, texture: p.texture } : null; },
        preview: preview, stopPreview: stopPreview, cv: cv, registry: loadRegistry, show: show, themeSheet: function (t) { return t.file ? sheet('h-theme-' + t.id, base + t.file) : Promise.resolve(null); } };
})(window);
