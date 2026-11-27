/* Site chat: a button that answers from this site's own pages and records.
 *
 * The build writes chat/index.json (see build/chat_index.py). This script finds
 * the passages that share words with the question and sends only those, with the
 * question, to the address in the index. It does not send the rest of the site,
 * and it never holds a key. The answer is shown as text, never as HTML.
 *
 * The button is added only when a site sets chat.enabled. The script tag carries
 * data-chat="chat/index.json?v=...".
 */
(function (root) {
    'use strict';

    var STOP = { a: 1, an: 1, the: 1, of: 1, to: 1, in: 1, on: 1, for: 1, and: 1, or: 1, was: 1, were: 1, is: 1, are: 1, did: 1, do: 1, does: 1, who: 1, what: 1, where: 1, when: 1, how: 1, his: 1, her: 1, their: 1, from: 1, with: 1, that: 1, this: 1, about: 1, they: 1, them: 1, he: 1, she: 1, it: 1, at: 1, by: 1, as: 1, be: 1, been: 1, have: 1, has: 1, had: 1, not: 1, but: 1, if: 1, into: 1, over: 1, after: 1, before: 1, which: 1, there: 1, here: 1, you: 1, your: 1, we: 1, our: 1, me: 1, my: 1, can: 1, could: 1, would: 1, should: 1 };
    var NONE = 'I could not find anything about that in the pages and records on this site.';
    var DOWN = 'The answer service did not respond. The rest of the site still works, and you can try again in a moment.';
    var CLOSED = 'I could not open the pages on this site just now. The rest of the site still works.';
    var STORE = 'site.chat.turns';

    function terms(s) {
        var out = [];
        String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').split(' ').forEach(function (w) {
            if (w.length >= 3 && !STOP[w]) out.push(w);
        });
        return out;
    }

    function alike(a, b) {
        if (a === b) return true;
        var s = a.length <= b.length ? a : b, l = a.length <= b.length ? b : a;
        return s.length >= 4 && l.indexOf(s) === 0;
    }

    function rank(passages, question, limit) {
        var q = terms(question), n = (passages || []).length || 1, cap = limit || 5;
        if (!q.length) return [];
        var docs = (passages || []).map(function (p) { return { p: p, t: terms((p.title || '') + ' ' + (p.text || '')) }; });
        var df = {};
        q.forEach(function (w) {
            df[w] = 0;
            docs.forEach(function (d) { if (d.t.some(function (t) { return alike(w, t); })) df[w]++; });
        });
        var scored = [];
        docs.forEach(function (d) {
            var score = 0;
            q.forEach(function (w) {
                var tf = 0;
                d.t.forEach(function (t) { if (alike(w, t)) tf++; });
                if (!tf) return;
                var idf = Math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5));
                score += idf * (tf / (tf + 1.2));
            });
            if (score > 0) scored.push({ p: d.p, score: score });
        });
        scored.sort(function (a, b) { return b.score - a.score || String(a.p.id).localeCompare(String(b.p.id)); });
        var budget = 5500, used = 0, out = [];
        scored.forEach(function (x) {
            if (out.length >= cap) return;
            var text = String(x.p.text || '');
            if (text.length > 1200) text = text.slice(0, 1200);
            if (used && used + text.length > budget) return;
            used += text.length;
            out.push({ id: x.p.id, title: x.p.title || '', url: x.p.url || '', text: text });
        });
        return out;
    }

    function safeUrl(u) {
        u = String(u || '');
        if (!u || u.charAt(0) === '/' || u.indexOf('//') !== -1 || u.indexOf('\\') !== -1 || u.indexOf('..') !== -1) return '';
        if (!/^[A-Za-z0-9_./#?&=%-]+$/.test(u)) return '';
        return u;
    }

    function el(tag, attrs, kids) {
        var n = root.document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            var v = attrs[k];
            if (v == null || v === false) return;
            if (k === 'text') n.textContent = v;
            else n.setAttribute(k, v === true ? '' : v);
        });
        (kids || []).forEach(function (c) { if (c) n.appendChild(c); });
        return n;
    }

    function svg(d) {
        var n = root.document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        n.setAttribute('viewBox', '0 0 24 24');
        n.setAttribute('aria-hidden', 'true');
        n.setAttribute('class', 'sc-icon');
        var p = root.document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', d);
        p.setAttribute('fill', 'none');
        p.setAttribute('stroke', 'currentColor');
        p.setAttribute('stroke-width', '1.6');
        p.setAttribute('stroke-linejoin', 'round');
        n.appendChild(p);
        return n;
    }

    function boot() {
        var doc = root.document;
        var script = doc.querySelector('script[data-chat]');
        if (!script || script.getAttribute('data-chat-ready')) return;
        script.setAttribute('data-chat-ready', '1');
        var url = script.getAttribute('data-chat');
        if (!url) return;
        fetch(url, { credentials: 'same-origin' }).then(function (r) {
            if (!r.ok) throw new Error('index');
            return r.json();
        }).then(function (index) { mount(index); }).catch(function () {
            mount({ name: 'Guide', greeting: CLOSED, endpoint: '', passages: [] });
        });
    }

    function mount(index) {
        var doc = root.document;
        var name = String(index.name || 'Guide').slice(0, 40);
        var greeting = String(index.greeting || 'Ask a question about this family. I answer only from the pages and records on this site.');
        var busy = false;
        var launch = el('button', { type: 'button', class: 'sc-launch', 'aria-expanded': 'false', 'aria-controls': 'site-chat' });
        launch.appendChild(svg('M5 6h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H9l-4 3.2V16H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z'));
        launch.appendChild(el('span', { class: 'sc-launch-text', text: 'Ask ' + name }));
        var title = el('h2', { id: 'site-chat-title', text: name });
        var closer = el('button', { type: 'button', class: 'sc-close', 'aria-label': 'Close' });
        closer.appendChild(svg('M6 6l12 12M18 6L6 18'));
        var head = el('div', { class: 'sc-head' }, [title, closer]);
        var note = el('p', { class: 'sc-note', text: 'Answers from this site only.' });
        var log = el('div', { class: 'sc-log', role: 'log', 'aria-live': 'polite' });
        var input = el('input', { id: 'site-chat-q', class: 'sc-input', type: 'text', maxlength: '500', autocomplete: 'off', placeholder: String(index.placeholder || 'Ask about this family') });
        var send = el('button', { type: 'submit', class: 'sc-send', text: 'Send' });
        var form = el('form', { class: 'sc-form' }, [el('label', { class: 'sc-sr', for: 'site-chat-q', text: 'Question' }), input, send]);
        var panel = el('div', { id: 'site-chat', class: 'sc-panel', role: 'dialog', 'aria-labelledby': 'site-chat-title', hidden: true }, [head, note, log, form]);
        var host = el('div', { class: 'sc' }, [launch, panel]);
        doc.body.appendChild(host);
        if (!index.endpoint) { input.disabled = true; send.disabled = true; }

        function lift() {
            var onAsk = !!doc.getElementById('stuart-page');
            // on Stuart's own page his composer sits along the bottom, so the button takes the left and stays above it
            var gap = onAsk ? 128 : 22;
            if (!onAsk) {
                var s = doc.querySelector('.st-launch');
                if (s) {
                    var r = s.getBoundingClientRect();
                    if (r.height > 8) gap = Math.max(22, Math.round(root.innerHeight - r.top + 10));
                }
            }
            // the closed button sits on the left of Stuart's page, clear of his send button;
            // the open window sits on the right, clear of his seal
            launch.style.bottom = gap + 'px';
            panel.style.bottom = gap + 'px';
            launch.style.left = onAsk ? '22px' : 'auto';
            launch.style.right = onAsk ? 'auto' : '22px';
            panel.style.left = 'auto';
            panel.style.right = '22px';
            panel.style.maxHeight = 'calc(100vh - ' + (gap + 16) + 'px)';
        }
        lift();
        root.addEventListener('resize', lift);
        root.setTimeout(lift, 400);

        function scroll() { log.scrollTop = log.scrollHeight; }
        function add(who, text, passages) {
            var item = el('div', { class: 'sc-msg sc-msg--' + who });
            item.appendChild(el('p', { class: 'sc-who', text: who === 'me' ? 'You' : name }));
            var body = el('div', { class: 'sc-body' });
            String(text || '').split(/\n{2,}/).forEach(function (para) {
                para = para.trim();
                if (para) body.appendChild(el('p', { text: para }));
            });
            if (passages && passages.length) {
                var box = el('div', { class: 'sc-from' });
                box.appendChild(el('p', { text: 'From the site' }));
                var ul = el('ul');
                passages.forEach(function (p) {
                    var href = safeUrl(p.url), li = el('li');
                    if (href) li.appendChild(el('a', { href: href, text: p.title || href }));
                    else li.appendChild(el('span', { text: p.title || 'A page on this site' }));
                    ul.appendChild(li);
                });
                box.appendChild(ul);
                body.appendChild(box);
            }
            item.appendChild(body);
            log.appendChild(item);
            scroll();
            return item;
        }
        function remember(turns) {
            try { root.sessionStorage.setItem(STORE, JSON.stringify(turns.slice(-20))); } catch (e) { /* private mode */ }
        }
        var turns = [];
        try { turns = JSON.parse(root.sessionStorage.getItem(STORE) || '[]') || []; } catch (e) { turns = []; }
        if (!Array.isArray(turns)) turns = [];
        add('bot', greeting);
        turns.forEach(function (t) { if (t && t.q && t.a) { add('me', t.q); add('bot', t.a); } });

        function open() {
            panel.hidden = false;
            launch.hidden = true;
            launch.setAttribute('aria-expanded', 'true');
            if (!input.disabled) input.focus();
            scroll();
        }
        function close() {
            panel.hidden = true;
            launch.hidden = false;
            launch.setAttribute('aria-expanded', 'false');
            launch.focus();
        }
        launch.addEventListener('click', open);
        closer.addEventListener('click', close);
        panel.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); close(); } });

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var q = input.value.trim().slice(0, 500);
            if (!q || busy) return;
            input.value = '';
            add('me', q);
            if (!index.endpoint) { add('bot', CLOSED); return; }
            var picked = rank(index.passages || [], q, 5);
            if (!picked.length) { add('bot', NONE); return; }
            busy = true;
            send.disabled = true;
            var wait = add('bot', 'Looking through the site');
            wait.className += ' sc-msg--wait';
            fetch(index.endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: q,
                    passages: picked.map(function (p) { return { title: p.title, url: safeUrl(p.url), text: p.text }; })
                })
            }).then(function (r) {
                return r.json().then(function (j) { return { ok: r.ok, j: j }; }, function () { return { ok: false }; });
            }).then(function (x) {
                var a = x.ok && x.j && typeof x.j.answer === 'string' ? x.j.answer.trim().slice(0, 4000) : '';
                if (!a) throw new Error('empty');
                wait.remove();
                add('bot', a, picked);
                turns.push({ q: q, a: a });
                remember(turns);
            }).catch(function () {
                wait.remove();
                add('bot', DOWN);
            }).then(function () {
                busy = false;
                send.disabled = !index.endpoint;
                input.focus();
            });
        });
    }

    if (typeof module !== 'undefined' && module.exports) module.exports = { rank: rank, terms: terms };
    if (root.document) {
        if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', boot);
        else boot();
    }
})(typeof self !== 'undefined' ? self : this);
