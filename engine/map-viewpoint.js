/* @i18n map kin */
/* Family map: "Relationships to".
 *
 * The same choice the family tree page has ("Relationships to" a person), kept in the same place
 * (FamilyKinship.viewpoint, localStorage "tc_viewpoint", and the visitor's own answer when visitor.enabled),
 * so what is chosen on one page is chosen on the other. Once someone is chosen, a person's name on the map is
 * followed by what they are to that person ("your great-grandaunt"). Nothing chosen: nothing is added and the
 * page is as it always was.
 *
 * The words come from FamilyKinship, the code the tree page uses. This file works out nothing itself: it asks.
 * A person the tree page does not draw (a hidden region, an associate) has no answer, so nothing is shown.
 *
 *   FM.rel.of(personId)        the words ("great-grandaunt") or null
 *   FM.rel.phrase(personId)    "your great-grandaunt" or ''
 *   FM.rel.chip(personId)      a <span class="chip-vp"> for a chip, or ''
 *   FM.rel.names(personIds)    "Name, your X; Name, your Y" for the people who have an answer, or ''
 *   window event "fm:viewpoint" when the choice changes
 */
(function () {
    'use strict';
    var FM = window.FM = window.FM || {};
    var I = window.FamilyI18n;
    var K = window.FamilyKinship;
    var VP = K && K.viewpoint;
    var data = null, chosen = null, cache = {}, sel = null;

    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    function by() { return data && data.treeById; }

    function current() {
        if (!by()) return null;
        return VP.visitor(by()) || VP.saved(by()) || null;
    }
    function of(id) {
        if (!chosen || !data || !data.kin || id === chosen || !by()[id]) return null;
        var key = I.lang + '|' + chosen + '|' + id;
        if (key in cache) return cache[key];
        var rel = null;
        try { rel = data.kin.relationship(chosen, id) || null; } catch (_) { rel = null; }
        return (cache[key] = rel);
    }
    function phrase(id) {
        var rel = of(id);
        return rel ? I.t('map.relYour', { rel: rel }) : '';
    }
    function chip(id) {
        var t = phrase(id);
        return t ? '<span class="chip-vp">' + esc(t) + '</span>' : '';
    }
    function names(ids, max) {
        if (!chosen) return '';
        var out = [], seen = {};
        (ids || []).forEach(function (id) {
            if (seen[id]) return; seen[id] = true;
            var t = phrase(id);
            if (t && data.people[id]) out.push(data.people[id].displayName + ', ' + t);
        });
        if (max && out.length > max) out = out.slice(0, max);
        return out.join('; ');
    }

    function changed() {
        cache = {};
        if (sel) sel.value = chosen || '';
        try { window.dispatchEvent(new CustomEvent('fm:viewpoint', { detail: { id: chosen } })); } catch (_) {}
    }
    function setup(d) {
        data = d;
        var box = document.getElementById('vpBox');
        sel = document.getElementById('vpSel');
        if (!box || !sel || !d.kin || !d.treePeople.length) return;
        var people = d.treePeople.slice().sort(function (a, b) {
            return ((a.generation || 0) - (b.generation || 0)) || String(a.displayName).localeCompare(String(b.displayName));
        });
        sel.insertAdjacentHTML('beforeend', people.map(function (p) { return '<option value="' + esc(p.id) + '">' + esc(p.displayName) + '</option>'; }).join(''));
        chosen = current();
        sel.value = chosen || '';
        box.hidden = false;
        sel.addEventListener('change', function () {
            chosen = sel.value || null;
            // a visitor who said who they are is not written over, as on the tree page
            if (!VP.visitor(by())) VP.save(chosen);
            changed();
        });
        // the visitor answered "Who are you?" (visitor.enabled), or the choice was changed in another tab
        window.addEventListener('familyvisitor:change', function () { chosen = current(); changed(); });
        window.addEventListener('storage', function (e) { if (e.key === VP.key) { chosen = current(); changed(); } });
        if (chosen) changed();
    }

    // chips already on the page (an open panel, the timeline card): bring their relationship text up to date without redrawing them
    function refreshChips(root) {
        Array.prototype.forEach.call((root || document).querySelectorAll('.chip[data-person]'), function (c) {
            var old = c.querySelector('.chip-vp'); if (old) old.parentNode.removeChild(old);
            var html = chip(c.dataset.person);
            if (!html) return;
            var after = c.querySelector('.chip-rel');
            (after ? after.parentNode : c).insertAdjacentHTML('beforeend', html);
        });
    }

    FM.rel = { of: of, phrase: phrase, chip: chip, names: names, setup: setup, refreshChips: refreshChips, get id() { return chosen; } };
})();
