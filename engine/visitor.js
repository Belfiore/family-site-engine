/* Who is visiting: "Who are you?", remembered on this device, and a small context other parts of the site can read.
   Loaded, with visitor-match.js and visitor.css, only on a site that turns visitor.enabled on (docs/visitor.md).

   Identity here is a preference, not a login. It holds one person's id in this browser's localStorage so the site
   can start from where that person sits in the family. It proves nothing, unlocks nothing and is never sent anywhere.
   Who may see the site at all is decided by the access gate (docs/access.md), and that is a separate thing.

   For other scripts (read after the page has loaded; all of this exists only when visitor.enabled is true):
     FamilyVisitor.status()     "identified", "skipped" (chose not to say) or "none" (not asked yet)
     FamilyVisitor.id()         the person's id in data/people.json, or null
     FamilyVisitor.ready        a promise that resolves to the person's record from data/people.json, or null
     FamilyVisitor.set(id)      remember this person
     FamilyVisitor.skip()       remember that the visitor chose not to say
     FamilyVisitor.clear()      forget, so the visitor is asked again next time
     FamilyVisitor.change()     open the picker
     FamilyVisitor.on(fn)       fn({ id, status, reason }) whenever any of the above changes things
   and the same news as a "familyvisitor:change" event on window. */
(function () {
    'use strict';
    var doc = document, html = doc.documentElement;
    var script = doc.currentScript;
    var ROOT = '/';
    try { if (script && script.src) ROOT = new URL('../../', script.src).pathname; } catch (_) {}
    var KEY = 'fs.visitor.v1:' + ROOT;
    var REDUCE = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
    var subs = [];

    // ------------------------------------------------------------------ what is remembered on this device
    function read() {
        try {
            var r = JSON.parse(localStorage.getItem(KEY) || 'null');
            if (r && r.v === 1 && (typeof r.id === 'string' || r.skipped === true)) return { id: typeof r.id === 'string' ? r.id : null, skipped: r.skipped === true };
        } catch (_) {}
        return null;
    }
    function write(rec) {
        try { if (rec) localStorage.setItem(KEY, JSON.stringify({ v: 1, id: rec.id || null, skipped: !!rec.skipped, at: new Date().toISOString().slice(0, 10) })); else localStorage.removeItem(KEY); } catch (_) {}
    }
    var rec = read();
    // no flash of the page before the question: hidden until it is answered, with a way out if anything goes wrong
    if (!rec) { html.classList.add('fv-pending'); setTimeout(function () { if (!doc.querySelector('.fv-root')) html.classList.remove('fv-pending'); }, 6000); }

    // ------------------------------------------------------------------ the people
    var peoplePromise = null, hidden = {}, keep = {};
    function loadPeople() {
        if (peoplePromise) return peoplePromise;
        peoplePromise = new Promise(function (ok) {
            function go() {
                var S = window.FamilySite || {}, url = S.data && S.data.people;
                var tree = S.tree || {};
                (tree.hiddenRegions || []).forEach(function (r) { hidden[r] = true; });
                keep = tree.suspectedRelatives || {};
                if (!url) return ok([]);
                fetch(new URL(url, location.origin + ROOT).href, { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : { people: [] }; })
                    .then(function (d) { ok((d && d.people) || []); }, function () { ok([]); });
            }
            if (window.FamilySite) go(); else doc.addEventListener('DOMContentLoaded', go);
        });
        return peoplePromise;
    }
    function scope() { return ((window.FamilySite || {}).visitor || {}).scope === 'all' ? 'all' : 'living'; }
    // who can be chosen: the people the tree shows, never a placeholder, and by default only people who may be alive
    function eligible(p) {
        if (!p || !p.id || p.placeholder || p.unidentified) return false;
        if (p.region && hidden[p.region] && !keep[p.id]) return false;
        return scope() === 'all' ? true : p.isLiving === true;
    }
    function find(people, id) { for (var i = 0; i < people.length; i++) if (people[i].id === id) return people[i]; return null; }
    function firstName(p) { return p.knownAs || String(p.givenNames || p.displayName || '').split(/\s+/)[0]; }
    function birthYear(p) { var m = /\d{4}/.exec((p.birth && (p.birth.date || p.birth.display)) || ''); return m ? m[0] : ''; }
    function context(p) {
        var bits = [];
        if (p.disambiguator) bits.push(p.disambiguator);
        var y = birthYear(p);
        if (y) bits.push('born ' + y);
        return bits.join(', ');
    }
    // a photo only where the site allows it: living people's pictures need visitor.livingPhotos
    function photoOf(p) {
        if (!p.photo) return '';
        if (p.isLiving && !((window.FamilySite || {}).visitor || {}).livingPhotos) return '';
        return new URL(p.photo, location.origin + ROOT).href;
    }

    // ------------------------------------------------------------------ the public side
    function status() { return rec ? (rec.id ? 'identified' : 'skipped') : 'none'; }
    function emit(reason) {
        var d = { id: rec && rec.id || null, status: status(), reason: reason };
        subs.slice().forEach(function (f) { try { f(d); } catch (_) {} });
        try { window.dispatchEvent(new CustomEvent('familyvisitor:change', { detail: d })); } catch (_) {}
        paintChip();
    }
    function set(id, quiet) { if (typeof id !== 'string' || !id) return; rec = { id: id, skipped: false }; write(rec); if (!quiet) emit('set'); }
    function skip() { rec = { id: null, skipped: true }; write(rec); emit('skip'); }
    function clear() { rec = null; write(null); emit('clear'); }
    var api = window.FamilyVisitor = {
        enabled: true, status: status, id: function () { return rec && rec.id || null; },
        set: function (id) { set(id); }, skip: skip, clear: clear, change: function () { open(false); },
        on: function (f) { if (typeof f === 'function') subs.push(f); },
        ready: null
    };
    api.ready = loadPeople().then(function (people) { return rec && rec.id ? find(people, rec.id) : null; });
    // a stored person who is no longer in the data is treated as not chosen yet
    loadPeople().then(function (people) {
        if (rec && rec.id && !find(people, rec.id)) { rec = null; write(null); emit('gone'); if (doc.readyState !== 'loading') open(true); }
    });

    // ------------------------------------------------------------------ small helpers
    function el(tag, attrs, kids) {
        var n = doc.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) { if (k === 'text') n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]); });
        (kids || []).forEach(function (c) { if (c) n.appendChild(c); });
        return n;
    }
    function treeMark() {   // the same small family tree the entrance draws, so the two feel like one place
        var ns = 'http://www.w3.org/2000/svg', s = doc.createElementNS(ns, 'svg');
        s.setAttribute('viewBox', '0 0 120 70'); s.setAttribute('class', 'fv-mark'); s.setAttribute('aria-hidden', 'true');
        [['M60 62 V38', 0], ['M60 38 H28 V22', 1], ['M60 38 H92 V22', 2], ['M28 22 V10', 3], ['M92 22 V10', 4]].forEach(function (d) {
            var p = doc.createElementNS(ns, 'path'); p.setAttribute('d', d[0]); p.setAttribute('pathLength', '1'); p.style.animationDelay = (0.12 * d[1]) + 's'; s.appendChild(p);
        });
        [[60, 62], [28, 10], [92, 10]].forEach(function (c, i) {
            var k = doc.createElementNS(ns, 'circle'); k.setAttribute('cx', c[0]); k.setAttribute('cy', c[1]); k.setAttribute('r', 3.2); k.style.animationDelay = (0.5 + 0.1 * i) + 's'; s.appendChild(k);
        });
        return s;
    }

    // ------------------------------------------------------------------ the question
    var root = null, lastFocus = null;
    function lockPage(on) {
        Array.prototype.forEach.call(doc.body.children, function (c) {
            if (c === root) return;
            try { if (on) c.setAttribute('inert', ''); else c.removeAttribute('inert'); } catch (_) {}
        });
    }
    function close(done) {
        if (!root) return;
        var r = root; root = null;
        html.classList.remove('fv-pending');
        lockPage(false);
        function gone() { if (r.parentNode) r.parentNode.removeChild(r); if (lastFocus && lastFocus.focus) try { lastFocus.focus({ preventScroll: true }); } catch (_) {} if (done) done(); }
        if (REDUCE) gone(); else { r.classList.add('is-leaving'); setTimeout(gone, 420); }
    }

    function open(first) {
        if (root) return;
        var S = window.FamilySite || {}, cfg = S.visitor || {};
        lastFocus = doc.activeElement;
        loadPeople().then(function (all) {
            if (root) return;
            var people = all.filter(eligible);
            var M = window.FamilyVisitorMatch;
            var chosen = null, active = 0, shown = [];

            root = el('div', { class: 'fv-root' + (first ? ' is-first' : ''), role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'fv-title' });
            if (!first) {      // a change can be given up; the first question has the quiet "continue" instead
                var esc = function (e) { if (e.key === 'Escape') { doc.removeEventListener('keydown', esc); close(); } };
                doc.addEventListener('keydown', esc);
            }
            var stage = el('div', { class: 'fv-stage' });
            root.appendChild(stage);
            doc.body.appendChild(root);
            lockPage(true);

            function pick() {
                stage.textContent = ''; stage.className = 'fv-stage fv-pick';
                var input = el('input', { type: 'text', id: 'fv-input', class: 'fv-input', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'fv-list', 'aria-autocomplete': 'list',
                    'aria-label': 'Your name', placeholder: 'Start typing your name', autocomplete: 'off', autocapitalize: 'words', spellcheck: 'false', enterkeyhint: 'search' });
                var list = el('ul', { class: 'fv-list', id: 'fv-list', role: 'listbox', 'aria-label': 'Matching family members' });
                var live = el('p', { class: 'fv-live', role: 'status', 'aria-live': 'polite' });
                stage.appendChild(el('h2', { id: 'fv-title', class: 'fv-title', text: cfg.question || 'Who are you?' }));
                stage.appendChild(el('p', { class: 'fv-lead', text: cfg.lead || '' }));
                stage.appendChild(input); stage.appendChild(list); stage.appendChild(live);
                var foot = el('div', { class: 'fv-foot' });
                var skipBtn = el('button', { type: 'button', class: 'fv-quiet', text: cfg.skipLabel || 'Continue without choosing' });
                skipBtn.addEventListener('click', function () { skip(); close(); });
                foot.appendChild(skipBtn);
                if (!first) { var cancel = el('button', { type: 'button', class: 'fv-quiet', text: 'Cancel' }); cancel.addEventListener('click', function () { close(); }); foot.appendChild(cancel); }
                stage.appendChild(foot);

                function draw() {
                    var q = input.value;
                    var rows = q.trim() ? M.search(people, q, 6) : [];
                    shown = rows;
                    if (active >= rows.length) active = Math.max(0, rows.length - 1);
                    list.textContent = '';
                    rows.forEach(function (r, i) {
                        var p = r.person, photo = photoOf(p);
                        var li = el('li', { id: 'fv-opt-' + i, role: 'option', class: 'fv-opt', 'aria-selected': String(i === active) });
                        li.appendChild(photo ? el('img', { class: 'fv-face', src: photo, alt: '', loading: 'lazy' }) : el('span', { class: 'fv-face fv-face--none', 'aria-hidden': 'true', text: (firstName(p) || '?').charAt(0).toUpperCase() }));
                        var t = el('span', { class: 'fv-opt-text' });
                        t.appendChild(el('span', { class: 'fv-opt-name', text: p.displayName }));
                        if (r.via) t.appendChild(el('span', { class: 'fv-opt-via', text: r.via.text + (r.via.note ? ' (' + r.via.note + ')' : '') }));
                        var c = context(p); if (c) t.appendChild(el('span', { class: 'fv-opt-ctx', text: c }));
                        li.appendChild(t);
                        li.addEventListener('mousedown', function (e) { e.preventDefault(); });
                        li.addEventListener('click', function () { confirm(p); });
                        list.appendChild(li);
                    });
                    if (rows[active]) input.setAttribute('aria-activedescendant', 'fv-opt-' + active); else input.removeAttribute('aria-activedescendant');
                    live.textContent = !q.trim() ? '' : rows.length ? rows.length + (rows.length === 1 ? ' match' : ' matches') : 'No one by that name. You can carry on without choosing.';
                    live.classList.toggle('is-none', !!q.trim() && !rows.length);
                }
                input.addEventListener('input', function () { active = 0; draw(); });
                input.addEventListener('keydown', function (e) {
                    if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(shown.length - 1, active + 1); draw(); }
                    else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(0, active - 1); draw(); }
                    else if (e.key === 'Enter') { e.preventDefault(); if (shown[active]) confirm(shown[active].person); }
                });
                setTimeout(function () { try { input.focus({ preventScroll: true }); } catch (_) {} }, REDUCE ? 0 : 250);
            }

            function confirm(p) {
                chosen = p;
                stage.textContent = ''; stage.className = 'fv-stage fv-confirm';
                var photo = photoOf(p);
                stage.appendChild(el('p', { class: 'fv-lead', text: 'Is this you?' }));
                stage.appendChild(photo ? el('img', { class: 'fv-face fv-face--big', src: photo, alt: '' }) : el('span', { class: 'fv-face fv-face--big fv-face--none', 'aria-hidden': 'true', text: (firstName(p) || '?').charAt(0).toUpperCase() }));
                stage.appendChild(el('h2', { id: 'fv-title', class: 'fv-title', text: p.displayName }));
                var c = context(p); if (c) stage.appendChild(el('p', { class: 'fv-ctx', text: c }));
                var yes = el('button', { type: 'button', class: 'fv-btn', text: 'Yes, that is me' });
                var no = el('button', { type: 'button', class: 'fv-quiet', text: 'No, go back' });
                yes.addEventListener('click', function () { choose(p); });
                no.addEventListener('click', pick);
                stage.appendChild(el('div', { class: 'fv-actions' }, [yes, no]));
                stage.appendChild(el('p', { class: 'fv-fine', text: 'This only decides where the family tree starts. It stays on this device and is not a login.' }));
                setTimeout(function () { try { yes.focus({ preventScroll: true }); } catch (_) {} }, 30);
            }

            function choose(p) {
                set(p.id, true);     // remembered now; everyone else hears about it as the welcome ends, so the tree moves as the page is revealed
                if (REDUCE || cfg.welcome === false) { emit('set'); close(); return; }
                stage.textContent = ''; stage.className = 'fv-stage fv-welcome';
                stage.appendChild(treeMark());
                stage.appendChild(el('p', { class: 'fv-lead', text: 'Welcome' }));
                stage.appendChild(el('h2', { id: 'fv-title', class: 'fv-title', text: firstName(p) }));
                var done = false;
                function end() { if (done) return; done = true; doc.removeEventListener('keydown', end); root && root.removeEventListener('click', end); emit('set'); close(); }
                setTimeout(end, 2200);
                // any key or tap skips it, but not the tap that got here
                setTimeout(function () { if (!done && root) { doc.addEventListener('keydown', end); root.addEventListener('click', end); } }, 500);
            }

            pick();
        });
    }

    // ------------------------------------------------------------------ the small control in the navigation bar
    var chip = null, menu = null;
    function who() { return loadPeople().then(function (people) { return rec && rec.id ? find(people, rec.id) : null; }); }
    function paintChip() {
        if (!chip) return;
        who().then(function (p) {
            var label = p ? firstName(p) : 'Who are you?';
            chip.querySelector('.fv-chip-text').textContent = label;
            chip.classList.toggle('is-quiet', !p);
            chip.setAttribute('aria-label', p ? 'You: ' + p.displayName + '. Change or forget.' : 'Say who you are');
            if (menu) {
                menu.querySelector('.fv-menu-line').textContent = p ? 'Viewing the family as ' + p.displayName + '.' : 'You have not said who you are.';
                menu.querySelector('[data-act=forget]').hidden = !rec;
                menu.querySelector('[data-act=change]').textContent = p ? 'Not you? Choose someone else' : 'Choose who you are';
            }
        });
    }
    function mountChip() {
        var host = doc.querySelector('.main-nav .nav-inner');
        if (!host || chip) return;
        var access = (window.FamilySite || {}).access;
        chip = el('button', { type: 'button', class: 'fv-chip', 'aria-haspopup': 'true', 'aria-expanded': 'false' }, [el('span', { class: 'fv-chip-dot', 'aria-hidden': 'true' }), el('span', { class: 'fv-chip-text' })]);
        menu = el('div', { class: 'fv-menu', role: 'group', 'aria-label': 'Who you are', hidden: '' });
        menu.appendChild(el('p', { class: 'fv-menu-line' }));
        menu.appendChild(el('button', { type: 'button', 'data-act': 'change', class: 'fv-menu-btn' }));
        menu.appendChild(el('button', { type: 'button', 'data-act': 'forget', class: 'fv-menu-btn', text: 'Forget me on this device' }));
        if (access && access.logout) menu.appendChild(el('button', { type: 'button', 'data-act': 'lock', class: 'fv-menu-btn', text: 'Lock this device' }));
        menu.appendChild(el('p', { class: 'fv-menu-fine', text: 'Only used to start the tree from your place in the family. Kept on this device, never sent anywhere, and not a login.' }));
        var wrap = el('div', { class: 'fv-wrap' }, [chip]);
        var toggle = host.querySelector('.nav-toggle');
        host.insertBefore(wrap, toggle || null);
        // the menu hangs off the body, not the bar, so no stacking rule of the page can put it behind the page's own controls
        doc.body.appendChild(menu);
        function place() { var r = chip.getBoundingClientRect(); menu.style.top = Math.round(r.bottom + 8) + 'px'; menu.style.right = Math.max(12, Math.round(innerWidth - r.right)) + 'px'; }
        function shut() { menu.hidden = true; chip.setAttribute('aria-expanded', 'false'); }
        chip.addEventListener('click', function (e) { e.stopPropagation(); var o = menu.hidden; if (o) place(); menu.hidden = !o; chip.setAttribute('aria-expanded', String(o)); if (o) { var b = menu.querySelector('button:not([hidden])'); if (b) b.focus({ preventScroll: true }); } });
        window.addEventListener('resize', function () { if (!menu.hidden) place(); });
        doc.addEventListener('click', function (e) { if (!menu.hidden && !wrap.contains(e.target) && !menu.contains(e.target)) shut(); });
        doc.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !menu.hidden) { shut(); chip.focus(); } });
        menu.addEventListener('click', function (e) {
            var b = e.target.closest && e.target.closest('[data-act]'); if (!b) return;
            shut();
            var act = b.getAttribute('data-act');
            if (act === 'change') open(false);
            else if (act === 'forget') clear();
            else if (act === 'lock') fetch(access.logout, { method: 'POST', credentials: 'same-origin' }).then(function () { location.reload(); }, function () { location.reload(); });
        });
        paintChip();
    }

    // ------------------------------------------------------------------ start
    function start() {
        mountChip();
        if (!rec) open(true);
    }
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start); else start();
})();
