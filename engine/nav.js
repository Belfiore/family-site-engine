/* Family site engine: the menu button in the navigation bar, on every page.
 *
 * One handler for the whole site. It listens before any other click handler, so a page that still has an
 * older menu script of its own cannot open and close the menu in the same click.
 */
(function () {
    'use strict';
    function parts(btn) {
        var id = btn.getAttribute('aria-controls') || 'navLinks';
        return { btn: btn, list: document.getElementById(id) || document.querySelector('.nav-links') };
    }
    function set(p, open) {
        if (!p.list) return;
        p.list.classList.toggle('open', open);
        p.btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        p.btn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
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
})();
