/* Finding a person by the name a visitor types: first names, surnames, full names, maiden names, other names.
   Forgiving about case, accents, hyphens, a missing letter or two letters swapped, and a name only half typed.
   No dependencies. Used by engine/visitor.js in the browser and by tests/test_visitor_match.js in Node. */
(function (root) {
    'use strict';

    function fold(s) {
        return String(s == null ? '' : s).toLowerCase()
            .replace(/ß/g, 'ss').replace(/æ/g, 'ae').replace(/œ/g, 'oe').replace(/ø/g, 'o').replace(/ł/g, 'l').replace(/đ/g, 'd')
            .normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/[’'`]/g, '')
            .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    }

    // edit distance with swapped neighbours counted as one change, giving up above max
    function distance(a, b, max) {
        if (a === b) return 0;
        if (Math.abs(a.length - b.length) > max) return max + 1;
        var prev2 = null, prev = [], cur, i, j;
        for (j = 0; j <= b.length; j++) prev[j] = j;
        for (i = 1; i <= a.length; i++) {
            cur = [i];
            var rowMin = i;
            for (j = 1; j <= b.length; j++) {
                var cost = a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1;
                var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
                if (prev2 && i > 1 && j > 1 && a.charAt(i - 1) === b.charAt(j - 2) && a.charAt(i - 2) === b.charAt(j - 1)) v = Math.min(v, prev2[j - 2] + 1);
                cur[j] = v;
                if (v < rowMin) rowMin = v;
            }
            if (rowMin > max) return max + 1;
            prev2 = prev; prev = cur;
        }
        return prev[b.length];
    }

    function allowed(len) { return len >= 8 ? 2 : len >= 4 ? 1 : 0; }

    // how well one typed word fits one word of a name: 0 for not at all, up to 1 for the same word
    function wordScore(q, w, isLast) {
        if (q === w) return 1;
        if (w.indexOf(q) === 0) return isLast ? 0.9 : 0.75;       // a half typed word only counts for the word being typed
        var d = distance(q, w, allowed(Math.max(q.length, w.length)));
        if (d <= allowed(Math.max(q.length, w.length)) && d > 0) return 0.7 - 0.1 * d;
        if (isLast && q.length >= 4) {                             // half typed and a letter wrong
            var head = w.slice(0, q.length), dh = distance(q, head, allowed(q.length));
            if (dh <= allowed(q.length)) return 0.6 - 0.1 * dh;
        }
        return 0;
    }

    // every name a person is known by, with where it came from
    function namesOf(p) {
        var out = [], seen = {};
        function add(text, kind, note) {
            var f = fold(text);
            if (!f || seen[f]) return;
            seen[f] = true;
            out.push({ text: String(text).trim(), fold: f, words: f.split(' '), kind: kind, note: note || '' });
        }
        add(p.displayName, 'name');
        var given = String(p.givenNames || '').trim(), first = given.split(/\s+/)[0] || '';
        if (given && p.surname) add(given + ' ' + p.surname, 'birth', 'name at birth');
        if (p.knownAs) {
            add(p.knownAs, 'known');
            if (p.surname) add(p.knownAs + ' ' + p.surname, 'known');
            if (p.displayName) add(p.displayName.split(/\s+/).length > 1 ? p.knownAs + ' ' + p.displayName.split(/\s+/).slice(-1)[0] : p.knownAs, 'known');
        }
        (p.nameVariants || []).forEach(function (v) { if (v && v.name) add(v.name, 'variant', v.note); });
        if (first) add(first, 'first');
        return out;
    }

    function scoreName(qWords, n) {
        if (!qWords.length) return 0;
        var used = {}, total = 0;
        for (var i = 0; i < qWords.length; i++) {
            var best = 0, at = -1;
            for (var j = 0; j < n.words.length; j++) {
                if (used[j]) continue;
                var s = wordScore(qWords[i], n.words[j], i === qWords.length - 1);
                if (s > best) { best = s; at = j; }
            }
            if (!best) return 0;
            used[at] = true; total += best;
        }
        var s = total / qWords.length;
        if (qWords.length === n.words.length) s += 0.15;           // the whole name
        if (n.fold.indexOf(qWords.join(' ')) === 0) s += 0.1;      // the name starts as typed
        if (n.kind === 'first') s -= 0.1;                          // a first name alone matches many people
        return s;
    }

    // people: the list to search. Returns up to limit of { person, score, via } best first, via being the name that matched when it is not the usual one.
    function search(people, query, limit) {
        var q = fold(query), qWords = q ? q.split(' ') : [];
        var rows = [];
        (people || []).forEach(function (p) {
            var best = 0, via = null, names = namesOf(p);
            if (!qWords.length) { rows.push({ person: p, score: 0, via: null }); return; }
            names.forEach(function (n) {
                var s = scoreName(qWords, n);
                if (s > best) { best = s; via = n; }
            });
            if (best >= 0.5) rows.push({ person: p, score: best, via: via && via.kind !== 'name' && via.kind !== 'first' && via.fold !== fold(p.displayName) ? via : null });
        });
        rows.sort(function (a, b) {
            return b.score - a.score || String(a.person.displayName).localeCompare(String(b.person.displayName)) || String(a.person.id).localeCompare(String(b.person.id));
        });
        return rows.slice(0, limit || 8);
    }

    var api = { fold: fold, distance: distance, namesOf: namesOf, search: search };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.FamilyVisitorMatch = api;
}(typeof window !== 'undefined' ? window : this));
