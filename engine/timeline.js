/* The Discovery Timeline page in the browser. The page arrives complete (the build wrote every find and every
 * day); this script adds what needs a visitor:
 *   - "N new finds since your last visit on 12 Nov", with the new finds marked, and a button to the first one;
 *   - filters for family line and type of find, with each day's summary rewritten to match;
 *   - "Show all N finds" on days with many.
 *
 * The visit date is kept in this browser only (localStorage). Nothing is sent anywhere. "New" means published
 * after the visit before this one, not found after it: a find dated last year but first published yesterday is new.
 */
(function () {
    'use strict';
    var root = document.querySelector('.tl-root');
    if (!root) return;
    document.documentElement.classList.add('tl-js');

    // the date headers stick just under the navigation bar, whatever height the site's bar has
    function bar() { var n = document.querySelector('.main-nav'); if (n) root.style.setProperty('--tl-nav', n.getBoundingClientRect().height + 'px'); }
    bar(); window.addEventListener('resize', bar); window.addEventListener('load', bar);

    var LINES = {}; try { LINES = JSON.parse(root.getAttribute('data-lines') || '{}'); } catch (e) {}
    var LINE_IDS = Object.keys(LINES);
    var OVER = +root.getAttribute('data-collapse-over') || 6, SHOWN = +root.getAttribute('data-collapse-shown') || 5;
    var lang = document.documentElement.lang || undefined;
    var days = [].slice.call(root.querySelectorAll('.tl-day'));
    var cards = [].slice.call(root.querySelectorAll('.tl-card'));
    var filters = { line: '', type: '' };
    var expanded = {};

    function store(kind) { try { var s = window[kind]; var k = '__tl'; s.setItem(k, '1'); s.removeItem(k); return s; } catch (e) { return null; } }
    var local = store('localStorage'), session = store('sessionStorage');
    var path = location.pathname;
    var VISIT = 'fse-timeline-visit:' + path, PREV = 'fse-timeline-prev:' + path;

    // ---------------------------------------------------------------- the visit before this one
    // It is read once per browser session and remembered for the session, so a reload does not turn "7 new finds"
    // into none. A first visit has nothing to compare with and shows no banner.
    function previousVisit() {
        var prev = null;
        if (session) prev = session.getItem(PREV);
        if (prev === null) {
            prev = local ? local.getItem(VISIT) : null;
            if (session) session.setItem(PREV, prev || '');
        }
        if (local) local.setItem(VISIT, new Date().toISOString());
        var t = prev ? Date.parse(prev) : NaN;
        return isNaN(t) ? null : t;
    }
    var prevVisit = previousVisit();

    function shortDate(t) {
        var d = new Date(t), now = new Date();
        var o = { day: 'numeric', month: 'short' };
        if (d.getFullYear() !== now.getFullYear()) o.year = 'numeric';
        try { return d.toLocaleDateString(lang, o); } catch (e) { return d.toDateString(); }
    }
    var fresh = [];
    if (prevVisit !== null) {
        cards.forEach(function (c) {
            var t = Date.parse(c.getAttribute('data-published') || '');
            if (!isNaN(t) && t > prevVisit) {
                c.classList.add('is-new');
                var tag = document.createElement('span');
                tag.className = 'tl-new-tag';
                tag.textContent = 'New';
                var type = c.querySelector('.tl-type');
                if (type) type.appendChild(tag);
                fresh.push(c);
            }
        });
    }
    var banner = document.getElementById('tlBanner');
    function showBanner() {
        if (!banner || !fresh.length) return;
        document.getElementById('tlBannerText').textContent = fresh.length + ' new find' + (fresh.length === 1 ? '' : 's') + ' since your last visit on ' + shortDate(prevVisit) + '.';
        banner.hidden = false;
    }

    // ---------------------------------------------------------------- filters and collapsed days
    function join(xs) { return xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]; }
    function summary(visible) {
        var n = visible.length, base = n + ' new find' + (n === 1 ? '' : 's');
        var used = LINE_IDS.filter(function (id) { return visible.some(function (c) { return (c.getAttribute('data-lines') || '').split(' ').indexOf(id) >= 0; }); });
        var many = LINE_IDS.length > 1 && document.querySelector('.tl-chips[data-filter="line"]');
        if (many && used.length >= 2) return base + ' across ' + join(used.map(function (id) { return LINES[id]; })) + '.';
        if (many && used.length === 1) return base + ' in ' + LINES[used[0]] + '.';
        return base + '.';
    }
    function matches(c) {
        if (filters.type && c.getAttribute('data-type') !== filters.type) return false;
        if (filters.line && (c.getAttribute('data-lines') || '').split(' ').indexOf(filters.line) < 0) return false;
        return true;
    }
    function apply() {
        var any = false;
        days.forEach(function (day) {
            var dc = [].slice.call(day.querySelectorAll('.tl-card'));
            var vis = dc.filter(matches);
            dc.forEach(function (c) { c.hidden = vis.indexOf(c) < 0; });
            day.hidden = !vis.length;
            if (vis.length) any = true;
            day.querySelector('.tl-summary').textContent = summary(vis);
            var more = day.querySelector('.tl-more');
            var date = day.getAttribute('data-date');
            var fold = vis.length > OVER && !expanded[date];
            vis.forEach(function (c, i) { c.classList.toggle('tl-extra', vis.length > OVER && i >= SHOWN); c.classList.toggle('is-folded', fold && i >= SHOWN); });
            if (more) {
                more.hidden = vis.length <= OVER;
                more.textContent = expanded[date] ? 'Show fewer' : 'Show all ' + vis.length + ' finds';
                more.setAttribute('aria-expanded', expanded[date] ? 'true' : 'false');
            }
        });
        document.getElementById('tlEmpty').hidden = any;
        var box = document.getElementById('tlFilters');
        if (box) { if (filters.line || filters.type) box.setAttribute('data-active', ''); else box.removeAttribute('data-active'); }
    }
    days.forEach(function (day) {
        var more = day.querySelector('.tl-more');
        if (more) more.addEventListener('click', function () {
            var date = day.getAttribute('data-date');
            expanded[date] = !expanded[date];
            apply();
            if (!expanded[date]) day.querySelector('.tl-day-head').scrollIntoView({ block: 'start' });
        });
    });
    var box = document.getElementById('tlFilters');
    if (box) {
        box.hidden = false;
        [].forEach.call(box.querySelectorAll('.tl-chips'), function (group) {
            group.addEventListener('click', function (ev) {
                var b = ev.target.closest('.tl-chip');
                if (!b) return;
                filters[group.getAttribute('data-filter')] = b.getAttribute('data-value');
                [].forEach.call(group.querySelectorAll('.tl-chip'), function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
                apply();
            });
        });
    }

    // ---------------------------------------------------------------- going to a find, even one in a folded day
    function reveal(card, flash) {
        var day = card.closest('.tl-day');
        if (card.hidden) { filters.line = filters.type = ''; resetChips(); apply(); }
        if (card.classList.contains('is-folded')) { expanded[day.getAttribute('data-date')] = true; apply(); }
        var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
        card.setAttribute('tabindex', '-1');
        card.scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
        card.focus({ preventScroll: true });
        if (flash) { card.classList.add('is-flash'); setTimeout(function () { card.classList.remove('is-flash'); }, 1800); }
    }
    function resetChips() {
        [].forEach.call(root.querySelectorAll('.tl-chips'), function (g) {
            [].forEach.call(g.querySelectorAll('.tl-chip'), function (x, i) { x.setAttribute('aria-pressed', i === 0 ? 'true' : 'false'); });
        });
    }
    var jump = document.getElementById('tlJump');
    if (jump) jump.addEventListener('click', function () {
        var first = cards.filter(function (c) { return c.classList.contains('is-new'); })[0];
        if (first) reveal(first, true);
    });

    function toHash() {
        if (!/^#find-/.test(location.hash)) return;
        var target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
        if (target) reveal(target, true);
    }
    window.addEventListener('hashchange', toHash);
    apply();
    showBanner();
    toHash();
    window.__timeline = { fresh: fresh.length, prev: prevVisit };
})();
