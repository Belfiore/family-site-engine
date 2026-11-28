/* @i18n sp */
/* =====================================================================
   FAMILY SITE ENGINE: SOURCE PREVIEW
   ---------------------------------------------------------------------
   One component for "here is a source": a clear title that links to the
   document, a preview card on hover or keyboard focus, and a drawer that
   shows the document without leaving the page (a bottom sheet on a phone).

   A source is an entry of data/sources.json: { id, title, type, repository,
   date, url, file, note }. Only what the entry holds is shown. A source with
   neither `file` nor `url` is plain text: no link, no card, no drawer. The
   engine never makes up a link, a thumbnail or a summary.

     FamilySourcePreview.resolver(function (id) { return source or null; })   once, so a link can name its source by id
     FamilySourcePreview.titleHTML(source, { className })    the title as <a class="sp-link" data-sp="id" href="...">, or plain text
     FamilySourcePreview.describe(source)                    { title, publisher, date, summary, href, kind } or null
     FamilySourcePreview.open(source, opener)                the drawer
     FamilySourcePreview.close()

   Without this script a title link is an ordinary link that opens the
   document in a new tab. Pages that load it get the card and the drawer on
   every .sp-link in the page, whenever it was drawn.
   No dependencies.
   ===================================================================== */
(function () {
    'use strict';
    var I = window.FamilyI18n;
    var SP = window.FamilySourcePreview = {};
    var lookup = function () { return null; };
    var SHOW_AFTER = 300, HIDE_AFTER = 160, FADE = 150, SLIDE = 220;
    var IMG = /\.(jpe?g|png|gif|webp|avif|bmp)(?:[?#].*)?$/i, PDF = /\.pdf(?:[?#].*)?$/i;

    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    function reduced() { return !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches); }
    function clean(v) { v = typeof v === 'string' ? v.trim() : ''; return v && !/^\s*(javascript|data|vbscript):/i.test(v) ? v : ''; }

    // ---- what a source offers
    function describe(src) {
        if (!src) return null;
        var file = clean(src.file), url = clean(src.url);
        if (url && !/^https?:\/\//i.test(url)) url = '';
        var target = file || url;
        if (!target) return null;
        var kind = IMG.test(target) ? 'image' : PDF.test(target) ? 'pdf' : file ? 'file' : 'web';
        var href = file ? encodeURI(file) : url;
        var origin = '';
        if (kind === 'web') { try { origin = new URL(url).origin; } catch (_) { origin = ''; } }
        return {
            id: src.id, title: src.title || target, publisher: src.repository || '', date: src.date || '', summary: src.note || '',
            href: href, kind: kind, origin: origin, host: origin ? origin.replace(/^https?:\/\//, '') : ''
        };
    }
    SP.describe = describe;
    SP.resolver = function (fn) { lookup = fn; };
    SP.frameTimeout = 9000;           // ms before a page that has not loaded gets the fallback card (a test shortens it)
    SP.titleHTML = function (src, opts) {
        opts = opts || {};
        var d = describe(src);
        var cls = opts.className ? ' ' + esc(opts.className) : '';
        if (!d) return '<strong class="sp-plain' + cls + '">' + esc((src && src.title) || '') + '</strong>';
        return '<a class="sp-link' + cls + '" href="' + esc(d.href) + '" target="_blank" rel="noopener" data-sp="' + esc(src.id) + '" aria-haspopup="dialog">' + esc(d.title) + '</a>';
    };

    var ICON = {
        doc: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 2h8l5 5v15H6zM14 2v5h5M9 12h7M9 16h7"/></svg>',
        globe: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/></svg>'
    };
    function kindWord(d) { return I.t(d.kind === 'image' ? 'sp.kindImage' : d.kind === 'pdf' ? 'sp.kindPdf' : d.kind === 'web' ? 'sp.kindWeb' : 'sp.kindFile'); }
    function thumb(d) {
        if (d.kind === 'image') return '<span class="sp-thumb"><img src="' + esc(d.href) + '" alt="" loading="lazy"></span>';
        if (d.kind === 'web' && d.origin) return '<span class="sp-thumb sp-thumb--icon"><img class="sp-fav" src="' + esc(d.origin + '/favicon.ico') + '" alt="" width="32" height="32" referrerpolicy="no-referrer"><span class="sp-fallback" hidden>' + ICON.globe + '</span></span>';
        return '<span class="sp-thumb sp-thumb--icon">' + (d.kind === 'web' ? ICON.globe : ICON.doc) + (d.kind === 'pdf' ? '<b>PDF</b>' : '') + '</span>';
    }
    function pubLine(d) { return [d.publisher, d.date].filter(Boolean).join(' · '); }

    // ---- the preview card
    var card = null, cardFor = null, showTimer = null, hideTimer = null, fadeTimer = null;
    function makeCard() {
        if (card) return card;
        card = document.createElement('div');
        card.className = 'sp-card'; card.id = 'sp-card'; card.setAttribute('role', 'tooltip'); card.hidden = true;
        card.addEventListener('pointerenter', function () { clearTimeout(hideTimer); });
        card.addEventListener('pointerleave', function (e) { if (e.pointerType === 'mouse') scheduleHide(); });
        card.addEventListener('click', function () { var l = cardFor; if (l) { hideCard(true); openFor(l); } });
        card.addEventListener('error', function (e) {          // a favicon that does not load: a plain globe
            var t = e.target;
            if (t && t.classList && t.classList.contains('sp-fav')) { t.hidden = true; var f = t.parentNode.querySelector('.sp-fallback'); if (f) f.hidden = false; }
        }, true);
        document.body.appendChild(card);
        return card;
    }
    function sourceOf(link) { return lookup(link.getAttribute('data-sp')); }
    function showCard(link) {
        var src = sourceOf(link), d = describe(src);
        if (!d) return;
        clearTimeout(hideTimer); clearTimeout(fadeTimer);
        var c = makeCard();
        if (cardFor && cardFor !== link) cardFor.removeAttribute('aria-describedby');
        cardFor = link;
        link.setAttribute('aria-describedby', 'sp-card');
        var pub = pubLine(d);
        c.innerHTML = thumb(d) + '<span class="sp-meta"><span class="sp-kind">' + esc(kindWord(d)) + (d.host ? ' · ' + esc(d.host) : '') + '</span>' +
            '<span class="sp-t">' + esc(d.title) + '</span>' + (pub ? '<span class="sp-pub">' + esc(pub) + '</span>' : '') +
            (d.summary ? '<span class="sp-sum">' + esc(d.summary) + '</span>' : '') + '</span>';
        c.hidden = false;
        place(c, link);
        void c.offsetWidth;
        c.classList.add('is-in');
    }
    function place(c, link) {
        var r = link.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
        var w = c.offsetWidth, h = c.offsetHeight;
        var left = Math.max(8, Math.min(vw - w - 8, r.left));
        var below = r.bottom + 8, top = below + h <= vh - 8 ? below : Math.max(8, r.top - h - 8);
        c.style.left = left + 'px'; c.style.top = top + 'px';
    }
    function hideCard(now) {
        clearTimeout(showTimer); clearTimeout(hideTimer);
        if (!card || card.hidden) { cardFor = null; return; }
        if (cardFor) cardFor.removeAttribute('aria-describedby');
        cardFor = null;
        card.classList.remove('is-in');
        clearTimeout(fadeTimer);
        if (now || reduced()) { card.hidden = true; return; }
        fadeTimer = setTimeout(function () { if (!card.classList.contains('is-in')) card.hidden = true; }, FADE);
    }
    function scheduleHide() { clearTimeout(hideTimer); hideTimer = setTimeout(function () { hideCard(); }, HIDE_AFTER); }
    function linkOf(t) { return t && t.closest ? t.closest('a.sp-link[data-sp]') : null; }

    // ---- the drawer
    var drawer = null, scrim = null, openToken = 0, drawerOpener = null, frameTimer = null;
    function makeDrawer() {
        if (drawer) return;
        scrim = document.createElement('div'); scrim.className = 'sp-scrim'; scrim.hidden = true;
        drawer = document.createElement('aside');
        drawer.className = 'sp-drawer'; drawer.hidden = true; drawer.tabIndex = -1;
        drawer.setAttribute('role', 'dialog'); drawer.setAttribute('aria-modal', 'true'); drawer.setAttribute('aria-labelledby', 'sp-d-title');
        drawer.innerHTML =
            '<header class="sp-d-head"><div class="sp-d-id"><p class="sp-d-kind" id="sp-d-kind"></p><h2 class="sp-d-title" id="sp-d-title"></h2><p class="sp-d-sub" id="sp-d-sub"></p></div>' +
            '<div class="sp-d-actions"><a class="sp-btn" id="sp-d-open" target="_blank" rel="noopener">' + esc(I.t('sp.openNewTab')) + '</a>' +
            '<button type="button" class="sp-x" id="sp-d-close" aria-label="' + esc(I.t('sp.close')) + '"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div></header>' +
            '<div class="sp-d-body" id="sp-d-body"></div>';
        document.body.appendChild(scrim); document.body.appendChild(drawer);
        scrim.addEventListener('click', function () { SP.close(); });
        drawer.querySelector('#sp-d-close').addEventListener('click', function () { SP.close(); });
        drawer.addEventListener('keydown', trap);
    }
    function focusables() {
        return Array.prototype.filter.call(drawer.querySelectorAll('a[href], button:not([disabled]), iframe, [tabindex="0"]'), function (n) { return !n.hidden && n.offsetParent !== null; });
    }
    function trap(e) {
        if (e.key !== 'Tab') return;
        var f = focusables();
        if (!f.length) { e.preventDefault(); drawer.focus(); return; }
        var first = f[0], last = f[f.length - 1], a = document.activeElement;
        if (e.shiftKey && (a === first || a === drawer)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && a === last) { e.preventDefault(); first.focus(); }
    }
    function fallbackCard(d) {
        return '<div class="sp-fb"><div class="sp-fb-ic">' + (d.kind === 'web' ? ICON.globe : ICON.doc) + '</div><p class="sp-fb-t">' + esc(d.title) + '</p>' +
            '<p class="sp-fb-m">' + esc(d.kind === 'web' ? I.t('sp.noEmbed') : I.t('sp.noShow')) + '</p>' +
            '<a class="sp-btn sp-btn--solid" href="' + esc(d.href) + '" target="_blank" rel="noopener">' + esc(I.t('sp.openNewTab')) + '</a></div>';
    }
    function body(d) {
        if (d.kind === 'image') return '<div class="sp-d-img"><img src="' + esc(d.href) + '" alt="' + esc(d.title) + '"></div>';
        if (d.kind === 'pdf') return '<iframe class="sp-frame" src="' + esc(d.href) + '" title="' + esc(d.title) + '"></iframe>';
        if (d.kind === 'web') {
            // a page on http cannot be framed by an https page: say so at once rather than show a blank frame
            if (location.protocol === 'https:' && /^http:/i.test(d.href)) return fallbackCard(d);
            return '<iframe class="sp-frame" src="' + esc(d.href) + '" title="' + esc(d.title) + '" referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox" data-web="1"></iframe>' +
                '<p class="sp-hint">' + esc(I.t('sp.hint')) + ' <a href="' + esc(d.href) + '" target="_blank" rel="noopener">' + esc(I.t('sp.openNewTab')) + '</a></p>';
        }
        return fallbackCard(d);
    }
    function openFor(link) { SP.open(sourceOf(link), link); }
    SP.open = function (src, opener) {
        var d = describe(src);
        if (!d) return;
        makeDrawer(); hideCard(true);
        var token = ++openToken;
        if (drawer.hidden) drawerOpener = opener || document.activeElement;
        document.getElementById('sp-d-kind').textContent = kindWord(d);
        document.getElementById('sp-d-title').textContent = d.title;
        document.getElementById('sp-d-sub').textContent = pubLine(d);
        document.getElementById('sp-d-open').href = d.href;
        var bodyEl = document.getElementById('sp-d-body');
        bodyEl.innerHTML = body(d);
        drawer.setAttribute('aria-label', I.t('sp.drawerLabel', { title: d.title }));
        clearTimeout(frameTimer);
        var web = bodyEl.querySelector('iframe[data-web]');
        if (web) {
            // a page that never loads (or refuses to be framed and reports an error) gets the same card as a page that cannot be shown
            var done = false;
            web.addEventListener('load', function () { done = true; clearTimeout(frameTimer); });
            web.addEventListener('error', function () { bodyEl.innerHTML = fallbackCard(d); });
            frameTimer = setTimeout(function () { if (!done && token === openToken) bodyEl.innerHTML = fallbackCard(d); }, SP.frameTimeout);
        }
        scrim.hidden = false; drawer.hidden = false;
        void drawer.offsetWidth;
        scrim.classList.add('is-open'); drawer.classList.add('is-open');
        document.documentElement.classList.add('sp-lock');
        drawer.querySelector('#sp-d-close').focus({ preventScroll: true });
    };
    SP.close = function () {
        if (!drawer || drawer.hidden) return;
        var token = ++openToken;
        clearTimeout(frameTimer);
        scrim.classList.remove('is-open'); drawer.classList.remove('is-open');
        document.documentElement.classList.remove('sp-lock');
        var opener = drawerOpener; drawerOpener = null;
        function finish() {
            if (token !== openToken) return;
            drawer.hidden = true; scrim.hidden = true;
            document.getElementById('sp-d-body').innerHTML = '';     // stop a page or a PDF still loading behind the scenes
        }
        if (reduced()) finish(); else setTimeout(finish, SLIDE);
        if (opener && document.contains(opener) && opener.focus) opener.focus({ preventScroll: true });
    };
    SP.isOpen = function () { return !!drawer && !drawer.hidden && drawer.classList.contains('is-open'); };

    // ---- listening, once, for every .sp-link there is or will be
    var canHover = !window.matchMedia || matchMedia('(hover: hover)').matches;
    document.addEventListener('pointerover', function (e) {
        if (e.pointerType !== 'mouse' || !canHover) return;
        var l = linkOf(e.target); if (!l) return;
        clearTimeout(hideTimer);
        if (cardFor === l && card && !card.hidden) return;
        clearTimeout(showTimer);
        showTimer = setTimeout(function () { showCard(l); }, SHOW_AFTER);
    });
    document.addEventListener('pointerout', function (e) {
        if (e.pointerType !== 'mouse') return;
        var l = linkOf(e.target); if (!l) return;
        var to = e.relatedTarget;
        if (to && (l.contains(to) || (card && card.contains(to)))) return;
        clearTimeout(showTimer); scheduleHide();
    });
    document.addEventListener('focusin', function (e) {
        var l = linkOf(e.target); if (!l || SP.isOpen()) return;
        try { if (!l.matches(':focus-visible')) return; } catch (_) {}
        showCard(l);
    });
    document.addEventListener('focusout', function (e) { if (linkOf(e.target)) hideCard(); });
    document.addEventListener('click', function (e) {
        var l = linkOf(e.target); if (!l) return;
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;   // "open in a new tab" the usual ways still work
        if (!describe(sourceOf(l))) return;
        e.preventDefault();
        openFor(l);
    });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        if (SP.isOpen()) { e.preventDefault(); e.stopPropagation(); SP.close(); return; }
        if (card && !card.hidden) { e.stopPropagation(); hideCard(); }
    }, true);
    window.addEventListener('scroll', function () { if (card && !card.hidden) hideCard(true); }, true);
    window.addEventListener('resize', function () { if (card && !card.hidden && cardFor) place(card, cardFor); });
})();
