/* @i18n nav */
/* Family site engine: the menu button in the navigation bar, on every page.
 *
 * One handler for the whole site. It listens before any other click handler, so a page that still has an
 * older menu script of its own cannot open and close the menu in the same click.
 */
(function () {
    'use strict';
    var I = window.FamilyI18n;
    function parts(btn) {
        var id = btn.getAttribute('aria-controls') || 'navLinks';
        return { btn: btn, list: document.getElementById(id) || document.querySelector('.nav-links') };
    }
    function set(p, open) {
        if (!p.list) return;
        p.list.classList.toggle('open', open);
        p.btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        p.btn.setAttribute('aria-label', I.t(open ? 'nav.closeMenu' : 'nav.openMenu'));
    }
    document.addEventListener('click', function (e) {
        var btn = e.target && e.target.closest ? e.target.closest('.nav-toggle') : null;
        if (btn) {
            e.stopImmediatePropagation();
            e.preventDefault();
            var p = parts(btn);
            set(p, !(p.list && p.list.classList.contains('open')));
            return;
        }
        // a link chosen from the open menu closes it
        var link = e.target && e.target.closest ? e.target.closest('.nav-links.open a') : null;
        if (link) { var t = document.querySelector('.nav-toggle'); if (t) set(parts(t), false); }
    }, true);
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        var open = document.querySelector('.nav-links.open');
        var t = document.querySelector('.nav-toggle');
        if (open && t) { set(parts(t), false); t.focus(); }
    });

    // ---------------------------------------------------------------- a site with more than one language
    // The bar says which words to use for its links (data-label-de="Stammbaum"), and the visitor's choice is kept in this browser.
    function language() {
        I.syncHtml();
        if (!I.switcher && I.default === 'en') return;
        var bar = document.querySelector('.main-nav');
        if (!bar) return;
        // the site's own words in the language chosen: the logo, the links, a page's title and heading (data-label-xx, or data-html-xx for markup)
        var own = document.querySelectorAll('[data-label-' + I.lang + ']');
        for (var i = 0; i < own.length; i++) own[i].textContent = own[i].getAttribute('data-label-' + I.lang);
        var marked = document.querySelectorAll('[data-html-' + I.lang + ']');
        for (var m = 0; m < marked.length; m++) marked[m].innerHTML = marked[m].getAttribute('data-html-' + I.lang);
        var nav = bar.querySelector('.nav-inner');
        bar.setAttribute('aria-label', I.t('nav.site'));
        var tg = bar.querySelector('.nav-toggle');
        if (tg && tg.getAttribute('aria-expanded') !== 'true') tg.setAttribute('aria-label', I.t('nav.openMenu'));
        if (!I.switcher || !nav || nav.querySelector('.lang-switch')) return;
        var box = document.createElement('div');
        box.className = 'lang-switch';
        box.setAttribute('role', 'group');
        box.setAttribute('aria-label', I.t('nav.language'));
        I.available.forEach(function (code, n) {
            if (n) { var bar2 = document.createElement('span'); bar2.setAttribute('aria-hidden', 'true'); bar2.textContent = '|'; box.appendChild(bar2); }
            var b = document.createElement('button');
            b.type = 'button';
            b.setAttribute('lang', code);
            b.textContent = code.toUpperCase();
            b.title = I.t('lang.' + code);
            b.setAttribute('aria-label', I.t('lang.' + code));
            b.setAttribute('aria-pressed', code === I.lang ? 'true' : 'false');
            b.addEventListener('click', function () { if (code !== I.lang) I.set(code); });
            box.appendChild(b);
        });
        nav.insertBefore(box, tg || null);
    }
    language();
})();
