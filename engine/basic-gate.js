/* A basic family password, for a site on GitHub Pages that has not moved to a host that can check one.
 *
 * Read docs/basic-access.md before relying on this. It is NOT protection. The page and every file it uses are still
 * public and still sent to the browser; this script only keeps a page from being shown until the right password is
 * typed, and remembers the device. It stops casual visitors and nothing else. Real protection is the worker in
 * docs/access.md.
 *
 * The password is never in the site. The settings hold a salt and a PBKDF2-SHA256 hash of it, and this script hashes
 * what is typed the same way and compares. Settings are read from this script's own tag:
 *   data-salt, data-hash (base64), data-iter (iterations), data-days (how long a device is remembered), data-site (name)
 * A script tag without data-hash does nothing, but the functions below are still there for the settings page:
 *   FamilyBasicAccess.make(password) -> Promise of {salt, hash, iterations}
 *   FamilyBasicAccess.derive(password, saltBase64, iterations) -> Promise of the hash, base64
 *   FamilyBasicAccess.lock()   forget this device and reload
 */
(function (root) {
    'use strict';
    var KEY = 'fse-basic-access';
    var ITERATIONS = 210000;
    var TEXT = {
        title: 'Family password',
        lead: 'This page is for the family. Please enter the password.',
        label: 'Password',
        open: 'Open',
        checking: 'Checking',
        wrong: 'That is not the password.',
        noCrypto: 'This browser cannot check the password here. Open the site over https in a current browser.'
    };

    function utf8(s) { return new TextEncoder().encode(String(s).normalize('NFKC')); }
    function toB64(buf) {
        var a = new Uint8Array(buf), s = '', i;
        for (i = 0; i < a.length; i++) s += String.fromCharCode(a[i]);
        return btoa(s);
    }
    function fromB64(s) {
        var bin = atob(s), a = new Uint8Array(bin.length), i;
        for (i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
        return a;
    }
    function equal(a, b) {            // the same length of work whatever the strings are
        var x = String(a), y = String(b), d = x.length ^ y.length, i, n = Math.max(x.length, y.length);
        for (i = 0; i < n; i++) d |= (x.charCodeAt(i) || 0) ^ (y.charCodeAt(i) || 0);
        return d === 0;
    }
    function subtle() { return root.crypto && root.crypto.subtle ? root.crypto.subtle : null; }

    function derive(password, saltB64, iterations) {
        var s = subtle();
        if (!s) return Promise.reject(new Error('no crypto'));
        return s.importKey('raw', utf8(password), 'PBKDF2', false, ['deriveBits']).then(function (k) {
            return s.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: fromB64(saltB64), iterations: iterations || ITERATIONS }, k, 256);
        }).then(toB64);
    }
    function make(password, iterations) {
        var n = iterations || ITERATIONS, salt = toB64(root.crypto.getRandomValues(new Uint8Array(16)));
        return derive(password, salt, n).then(function (hash) { return { salt: salt, hash: hash, iterations: n }; });
    }

    function remembered(hash) {
        try {
            var v = JSON.parse(root.localStorage.getItem(KEY) || 'null');
            return !!v && typeof v.until === 'number' && v.until > Date.now() && equal(v.h, hash);
        } catch (e) { return false; }
    }
    function remember(hash, days) {
        try {
            root.localStorage.setItem(KEY, JSON.stringify({ h: hash, until: Date.now() + days * 86400000 }));
            return remembered(hash);
        } catch (e) { return false; }
    }
    function lock() {
        try { root.localStorage.removeItem(KEY); } catch (e) { /* nothing kept */ }
        root.location.reload();
    }

    root.FamilyBasicAccess = { make: make, derive: derive, equal: equal, lock: lock, text: TEXT };

    var me = root.document.currentScript;
    if (!me || !me.getAttribute('data-hash')) return;
    var hash = me.getAttribute('data-hash'), salt = me.getAttribute('data-salt') || '';
    var iter = parseInt(me.getAttribute('data-iter'), 10) || ITERATIONS;
    var days = parseInt(me.getAttribute('data-days'), 10) || 30;
    var siteName = me.getAttribute('data-site') || '';
    if (remembered(hash)) return;

    // hold the page back before it is drawn: everything in the body is hidden until the password is right
    var doc = root.document, html = doc.documentElement;
    html.classList.add('fse-locked');
    var style = doc.createElement('style');
    style.id = 'fse-gate-style';
    style.textContent =
        'html.fse-locked body>*:not(.fse-gate){display:none!important}' +
        'html.fse-locked body{margin:0}' +
        '.fse-gate{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;' +
        'background:var(--bg,#faf8f4);color:var(--ink,#222);font:16px/1.5 var(--font-body,Georgia,serif)}' +
        '.fse-gate form{width:100%;max-width:360px}' +
        '.fse-gate h1{font:600 1.6rem/1.2 var(--font-display,var(--font-body,Georgia,serif));margin:0 0 .5rem}' +
        '.fse-gate p{margin:0 0 1rem}' +
        '.fse-gate label{display:block;font-size:.9rem;margin-bottom:.25rem}' +
        '.fse-gate input{width:100%;box-sizing:border-box;font:inherit;padding:.6rem .7rem;border:1px solid #8a8478;border-radius:6px;background:#fff;color:#222}' +
        '.fse-gate input:focus-visible,.fse-gate button:focus-visible{outline:3px solid #1b5fa8;outline-offset:2px}' +
        '.fse-gate button{margin-top:.8rem;font:inherit;font-weight:600;padding:.6rem 1.2rem;border:0;border-radius:6px;background:#2b2b2b;color:#fff;cursor:pointer}' +
        '.fse-gate button[disabled]{opacity:.6;cursor:wait}' +
        '.fse-gate .fse-gate-msg{min-height:1.5em;margin:.8rem 0 0;color:#8a1c1c}';
    doc.head.appendChild(style);

    function unlock(box) {
        html.classList.remove('fse-locked');
        if (box && box.parentNode) box.parentNode.removeChild(box);
        var s = doc.getElementById('fse-gate-style');
        if (s && s.parentNode) s.parentNode.removeChild(s);
    }

    function draw() {
        var box = doc.createElement('main'), form = doc.createElement('form'), h1 = doc.createElement('h1'), lead = doc.createElement('p');
        var label = doc.createElement('label'), input = doc.createElement('input'), btn = doc.createElement('button'), msg = doc.createElement('p');
        box.className = 'fse-gate';
        form.setAttribute('novalidate', '');
        h1.textContent = siteName || TEXT.title;
        lead.textContent = TEXT.lead;
        label.setAttribute('for', 'fse-gate-password');
        label.textContent = TEXT.label;
        input.type = 'password'; input.id = 'fse-gate-password'; input.maxLength = 256;
        input.setAttribute('autocomplete', 'current-password');
        input.setAttribute('autocapitalize', 'off'); input.setAttribute('spellcheck', 'false');
        btn.type = 'submit'; btn.textContent = TEXT.open;
        msg.className = 'fse-gate-msg'; msg.setAttribute('role', 'alert');
        [h1, lead, label, input, btn, msg].forEach(function (n) { form.appendChild(n); });
        box.appendChild(form);
        doc.body.appendChild(box);
        input.focus();
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (!subtle()) { msg.textContent = TEXT.noCrypto; return; }
            var typed = input.value;
            btn.disabled = true; btn.textContent = TEXT.checking; msg.textContent = '';
            derive(typed, salt, iter).then(function (got) {
                if (equal(got, hash)) {
                    input.value = '';
                    if (remember(hash, days)) root.location.reload(); else unlock(box);
                    return;
                }
                return new Promise(function (r) { root.setTimeout(r, 700); }).then(function () {
                    msg.textContent = TEXT.wrong; input.value = ''; btn.disabled = false; btn.textContent = TEXT.open; input.focus();
                });
            }, function () { msg.textContent = TEXT.noCrypto; btn.disabled = false; btn.textContent = TEXT.open; });
        });
    }
    if (doc.body) draw(); else doc.addEventListener('DOMContentLoaded', draw);
})(window);
