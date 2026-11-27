(function () {
    var root = document.documentElement;
    var form = document.getElementById('gate'), pw = document.getElementById('pw'), go = document.getElementById('go');
    var msg = document.getElementById('msg'), show = document.getElementById('show');
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // a site with a language setting has its words in GATE_I18N (written by the build); without it every line below stays English
    var L = typeof GATE_I18N !== 'undefined' ? GATE_I18N : null;
    var lang = L ? L.default : 'en';
    if (L && L.available.length > 1) { try { var chosen = localStorage.getItem('fse-language'); if (chosen && L.available.indexOf(chosen) >= 0) lang = chosen; } catch (e) {} }
    var pageLang = root.getAttribute('lang') || 'en';
    function w(key, en) { var d = L && L.words[lang]; return d && d[key] !== undefined ? d[key] : en; }
    function paint() {
        if (!L) return;
        var all = document.querySelectorAll('[data-i18n]');
        for (var i = 0; i < all.length; i++) {
            var n = all[i];
            if (n.getAttribute('data-orig') === null) n.setAttribute('data-orig', n.textContent);
            n.textContent = w(n.getAttribute('data-i18n'), n.getAttribute('data-orig'));
        }
        var mine = document.querySelectorAll('[data-site-words]');
        for (var j = 0; j < mine.length; j++) {
            var m = mine[j], o = {};
            if (m.getAttribute('data-orig') === null) m.setAttribute('data-orig', m.textContent);
            try { o = JSON.parse(m.getAttribute('data-site-words')); } catch (e) {}
            m.textContent = o[lang] || m.getAttribute('data-orig');
        }
        root.setAttribute('lang', lang === 'en' && /^en\b/i.test(pageLang) ? pageLang : lang);
        show.textContent = pw.type === 'password' ? w('gate.show', 'Show') : w('gate.hide', 'Hide');
        var box = document.getElementById('glang');
        if (box) {
            box.textContent = '';
            L.available.forEach(function (code, k) {
                if (k) { var bar = document.createElement('span'); bar.setAttribute('aria-hidden', 'true'); bar.textContent = '|'; box.appendChild(bar); }
                var b = document.createElement('button');
                b.type = 'button'; b.setAttribute('lang', code); b.textContent = code.toUpperCase();
                b.title = w('lang.' + code, code); b.setAttribute('aria-label', w('lang.' + code, code));
                b.setAttribute('aria-pressed', code === lang ? 'true' : 'false');
                b.addEventListener('click', function () { lang = code; try { localStorage.setItem('fse-language', code); } catch (e) {} paint(); });
                box.appendChild(b);
            });
            box.setAttribute('aria-label', w('gate.language', 'Language'));
            box.hidden = false;
        }
    }
    var seen = false;
    try { seen = sessionStorage.getItem('fs.gate.seen') === '1'; } catch (e) {}
    if (seen || reduce) root.classList.add('g-skip');
    try { sessionStorage.setItem('fs.gate.seen', '1'); } catch (e) {}
    // any key or tap skips what is still moving
    function skip() { root.classList.add('g-skip'); }
    window.addEventListener('keydown', skip, { once: true });
    window.addEventListener('pointerdown', skip, { once: true });

    show.addEventListener('click', function () {
        var on = pw.type === 'password';
        pw.type = on ? 'text' : 'password';
        show.textContent = on ? w('gate.hide', 'Hide') : w('gate.show', 'Show');
        show.setAttribute('aria-pressed', on ? 'true' : 'false');
        pw.focus();
    });

    function say(text) { msg.textContent = text; }
    paint();
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (go.disabled || !pw.value.trim()) { pw.focus(); return; }
        go.disabled = true; say('');
        var label = go.textContent; go.textContent = w('gate.opening', 'Opening');
        fetch('/__gate/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify({ password: pw.value }) })
            .then(function (r) {
                if (r.ok) {
                    pw.value = '';
                    root.classList.add('g-open');
                    setTimeout(function () { location.reload(); }, reduce ? 0 : 420);
                    return;
                }
                go.disabled = false; go.textContent = label;
                say(r.status === 401 ? w('gate.wrong', 'That is not the family password. Please try again.') : w('gate.error', 'Something went wrong. Please try again in a moment.'));
                pw.focus();
            })
            .catch(function () { go.disabled = false; go.textContent = label; say(w('gate.offline', 'Could not reach the site. Check your connection and try again.')); });
    });
})();
