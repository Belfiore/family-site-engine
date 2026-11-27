/* Family site engine: language.
 *
 * This file is not shipped as it is. The build writes it, with the translations the script needs, in place of the
 * line `/* @i18n nav tree */` at the top of each engine script (the names are the groups of keys in engine/i18n/*.json).
 * So a script has its words before it runs, with no extra request and no extra tag in any page.
 *
 *   FamilyI18n.t('tree.born')                      one string
 *   FamilyI18n.t('tree.since', { year: 1891 })     with {year} filled in
 *   FamilyI18n.n('tree.people', 3)                 'tree.people_one' for 1, 'tree.people_other' for anything else, with {n}
 *   FamilyI18n.date('1891-03-12')                  12 March 1891, or 12. März 1891
 *   FamilyI18n.number(1234.5)                      1,234.5, or 1.234,5
 *   FamilyI18n.pick(obj, 'story')                  obj.story_de when German is chosen and there is one, else obj.story
 *   FamilyI18n.localize(data, {dates:false})       the same for every field of a whole data file, and its dates (unless dates is false)
 *   FamilyI18n.apply(root)                         fills data-i18n, data-i18n-html and data-i18n-<attribute> in the page
 *
 * A site that does not set "language" has English only and none of this is visible.
 */
function familyI18nRuntime(root) {
    'use strict';
    var KEY = 'fse-language';
    var dicts = {}, I = { version: 1 };
    // read when asked, not when this script runs: a script in the head can load before the site's settings do
    function site() { return (root.FamilySite && root.FamilySite.language) || null; }
    function stored() { try { return root.localStorage.getItem(KEY); } catch (e) { return null; } }
    var forced = null;
    Object.defineProperty(I, 'default', { get: function () { var s = site(); return (s && s.default) || 'en'; } });
    Object.defineProperty(I, 'available', { get: function () { var s = site(); return (s && s.available) || [I.default]; } });
    Object.defineProperty(I, 'switcher', { get: function () { return I.available.length > 1; } });
    Object.defineProperty(I, 'lang', { get: function () {
        if (forced) return forced;
        var s = I.switcher ? stored() : null;
        return s && I.available.indexOf(s) >= 0 ? s : I.default;
    } });

    I.add = function (more) { for (var l in more) { dicts[l] = dicts[l] || {}; for (var k in more[l]) dicts[l][k] = more[l][k]; } };
    I.has = function (key, lang) { return !!(dicts[lang || I.lang] && dicts[lang || I.lang][key] !== undefined); };
    function raw(key) {
        var d = dicts[I.lang];
        if (d && d[key] !== undefined) return d[key];
        d = dicts.en;                                   // a missing German string shows in English, never as a key
        return d && d[key] !== undefined ? d[key] : key;
    }
    function fill(s, vars) {
        if (!vars) return s;
        return s.replace(/\{([a-zA-Z0-9]+)\}/g, function (m, k) { return vars[k] === undefined ? m : vars[k]; });
    }
    I.t = function (key, vars) { return fill(raw(key), vars); };
    I.en = function (key) { return dicts.en && dicts.en[key] !== undefined ? dicts.en[key] : key; };
    I.n = function (key, count, vars) {
        var v = {}; for (var k in vars || {}) v[k] = vars[k];
        v.n = I.number(count);
        return fill(raw(key + (count === 1 ? '_one' : '_other')), v);
    };
    I.list = function (items) {
        var a = items.slice();
        if (a.length < 2) return a.join('');
        var last = a.pop();
        return a.join(I.t('list.sep')) + I.t('list.last') + last;
    };

    // ---------------------------------------------------------------- numbers and dates
    I.number = function (x) {
        if (typeof x !== 'number' || !isFinite(x)) return String(x);
        var parts = String(Math.abs(x)).split('.'), whole = parts[0], neg = x < 0 ? '-' : '';
        var g = I.t('fmt.group'), d = I.t('fmt.decimal');
        if (whole.length > 4) whole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, g);
        return neg + whole + (parts[1] ? d + parts[1] : '');
    };
    I.month = function (m, short) { return I.t((short ? 'date.monthShort.' : 'date.month.') + m); };
    I.weekday = function (w, short) { return I.t((short ? 'date.weekdayShort.' : 'date.weekday.') + w); };
    // y, m (1 to 12, or 0), d (1 to 31, or 0); long month names unless short
    I.dateParts = function (y, m, d, opts) {
        opts = opts || {};
        var mon = m ? I.month(m, opts.short) : '';
        if (m && d) {
            if (opts.weekday) {
                var wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
                return I.t('date.wdmy', { weekday: I.weekday(wd, opts.short), d: d, month: mon, y: y });
            }
            return I.t('date.dmy', { d: d, month: mon, y: y });
        }
        if (m) return I.t('date.my', { month: mon, y: y });
        return String(y);
    };
    I.date = function (iso, opts) {
        var m = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?/.exec(String(iso || ''));
        return m ? I.dateParts(+m[1], m[2] ? +m[2] : 0, m[3] ? +m[3] : 0, opts) : String(iso || '');
    };
    I.dayMonth = function (iso, opts) {
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
        return m ? I.t('date.dm', { d: +m[3], month: I.month(+m[2], opts && opts.short) }) : String(iso || '');
    };

    // Dates the site wrote as English words ("12 March 1891", "about 1853", "between 1850 and 1855") are read and written
    // again in the chosen language. Anything that is not clearly a date is left exactly as it was.
    var EN_MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];
    var QUAL = [['about', 'q.about'], ['probably', 'q.probably'], ['likely', 'q.likely'], ['circa', 'q.about'], ['c.', 'q.about'], ['abt.', 'q.about'], ['abt', 'q.about'], ['ca.', 'q.about'],
                ['before', 'q.before'], ['bef.', 'q.before'], ['after', 'q.after'], ['aft.', 'q.after'],
                ['between', 'q.between'], ['and', 'q.and'], ['or', 'q.or'], ['to', 'q.to'], ['from', 'q.from']];
    function monthNo(w) {
        var s = w.toLowerCase().replace(/\.$/, '');
        for (var i = 0; i < 12; i++) if (EN_MONTHS[i] === s || EN_MONTHS[i].slice(0, 3) === s || (s === 'sept' && i === 8)) return i + 1;
        return 0;
    }
    I.localizeDisplay = function (s) {
        if (I.lang === 'en' || typeof s !== 'string' || !s) return s;
        var out = s;
        out = out.replace(/\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b/g, function (all, d, mo, y) {
            var n = monthNo(mo); return n ? I.dateParts(+y, n, +d) : all;
        });
        out = out.replace(/\b([A-Za-z]{3,9})\.?\s+(\d{4})\b/g, function (all, mo, y) {
            var n = monthNo(mo); return n ? I.dateParts(+y, n, 0) : all;
        });
        // only the words that stand beside a year or another date, so a word inside a place or a name is never touched
        var yearish = '(?:\\d{4}|\\d{1,2}\\.? [^\\d\\s]+ \\d{4}|[^\\d\\s]+ \\d{4})';
        QUAL.forEach(function (q) {
            var w = q[0].replace(/\./g, '\\.');
            var re = new RegExp('(^|[\\s(~])' + w + '(?=\\s+' + yearish + ')', 'gi');
            out = out.replace(re, function (all, pre) { return pre + I.t(q[1]); });
        });
        out = out.replace(/(\d{4}|[^\d\s]+ \d{4}) (and|or|to) (?=\d|[^\d\s]+ \d{4}|\d{1,2}\.? [^\d\s]+ \d{4})/gi, function (all, a, w) { return a + ' ' + I.t('q.' + w.toLowerCase()) + ' '; });
        return out;
    };

    // ---------------------------------------------------------------- the site's own words in other languages
    I.pick = function (obj, field) {
        if (!obj) return undefined;
        var v = obj[field + '_' + I.lang];
        return (typeof v === 'string' ? v.trim() : v) ? v : obj[field];
    };
    // a copy-free pass over loaded data: field_xx replaces field, and dates are written in the chosen language
    I.localize = function (data, opts) {
        var suffix = '_' + I.lang, dates = !(opts && opts.dates === false);
        (function walk(o) {
            if (!o || typeof o !== 'object') return;
            if (Array.isArray(o)) { for (var i = 0; i < o.length; i++) walk(o[i]); return; }
            var keys = Object.keys(o);
            for (var j = 0; j < keys.length; j++) {
                var k = keys[j], v = o[k];
                if (k.length > suffix.length && k.slice(-suffix.length) === suffix && o[k.slice(0, -suffix.length)] !== undefined && v !== '' && v !== null) {
                    o[k.slice(0, -suffix.length)] = v;
                }
            }
            keys = Object.keys(o);
            for (var j2 = 0; j2 < keys.length; j2++) {
                var k2 = keys[j2], v2 = o[k2];
                if (typeof v2 === 'string') { if (dates && I.lang !== 'en' && (k2 === 'display' || k2 === 'marriageDisplay' || k2 === 'years')) o[k2] = I.localizeDisplay(v2); }
                else walk(v2);
            }
        })(data);
        return data;
    };

    // ---------------------------------------------------------------- the page
    I.apply = function (el) {
        I.syncHtml();
        var scope = el || root.document;
        if (!scope || !scope.querySelectorAll) return;
        var nodes = scope.querySelectorAll('[data-i18n],[data-i18n-html]');
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            if (n.hasAttribute('data-i18n-html')) n.innerHTML = I.t(n.getAttribute('data-i18n-html'));
            else n.textContent = I.t(n.getAttribute('data-i18n'));
        }
        var all = scope.querySelectorAll('*');
        for (var j = 0; j < all.length; j++) {
            var attrs = all[j].attributes;
            for (var a = attrs.length - 1; a >= 0; a--) {
                var nm = attrs[a].name;
                if (nm.indexOf('data-i18n-') === 0 && nm !== 'data-i18n-html') all[j].setAttribute(nm.slice(10), I.t(attrs[a].value));
            }
        }
    };
    I.set = function (lang) {
        if (I.available.indexOf(lang) < 0) return;
        try { root.localStorage.setItem(KEY, lang); } catch (e) { /* the choice lasts until the page is closed */ }
        forced = lang;
        if (root.location) root.location.reload();
    };
    I.htmlLang = function (original) {
        if (I.lang === 'en' && /^en\b/i.test(original || 'en')) return original || 'en';
        return I.lang;
    };
    // the language of the page, set as soon as the site's settings are known (every script that draws anything calls this first)
    I.syncHtml = function () {
        if (!I.switcher && I.default === 'en') return;
        var de = root.document && root.document.documentElement;
        if (de) de.setAttribute('lang', I.htmlLang(de.getAttribute('data-site-lang') || de.getAttribute('lang')));
        if (de && !de.getAttribute('data-site-lang')) de.setAttribute('data-site-lang', de.getAttribute('lang') || 'en');
    };
    return I;
}
