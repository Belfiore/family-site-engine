/* @i18n kin tree */
/* =====================================================================
   FAMILY SITE ENGINE: KINSHIP
   ---------------------------------------------------------------------
   The one place that works out how two people on the tree are related
   ("great-grandaunt", "Urgroßvater", "wife's brother-in-law"), and why.
   The family tree and the family map both use it, so the same pair of
   people gets the same words on both pages. Nothing else on the engine
   works out a relationship.

     var K = FamilyKinship.create(D);   // D = { people, byId }, as the canvas builds it
     K.relationship(fromId, toId)       // the words, or null (the same person, or no known link)
     K.relInfo(a, b), K.relPath(a, b), K.relNotes(path, info)   // the reasoning, for the canvas

   FamilyKinship.pruneHidden(people, meta) is the canvas's own rule for who is on the tree
   (tree.hiddenRegions, tree.suspectedRelatives). A page that wants the canvas's answer must
   work on the same people, so the map builds its tree with it.
   No dependencies.
   ===================================================================== */
(function () {
    'use strict';
    var I = window.FamilyI18n;

        // People in a hidden region (tree.hiddenRegions) stay in data/people.json untouched but are not drawn.
        // A person listed in tree.suspectedRelatives ({ personId: besideId }) is kept from a hidden region and
        // drawn beside that person as a suspected relative, joined by a dashed line, with no proven link.
        function pruneHidden(people, meta) {
            meta = meta || {};
            var hidden = {}; (meta.hiddenRegions || []).forEach(function (r) { hidden[r] = true; });
            var keep = meta.suspectedRelatives || {};
            if (!Object.keys(hidden).length) return people;
            var drop = {};
            people.forEach(function (p) { if (p.region && hidden[p.region] && !keep[p.id]) drop[p.id] = true; });
            var idOf = function (r) { return typeof r === 'string' ? r : r && r.id; };
            var host = {};
            people.forEach(function (p) { host[p.id] = p; });
            return people.filter(function (p) { return !drop[p.id]; }).map(function (p) {
                var q = Object.assign({}, p);
                q.parents = (p.parents || []).filter(function (r) { return !drop[idOf(r)]; });
                q.children = (p.children || []).filter(function (r) { return !drop[idOf(r)]; });
                q.spouses = (p.spouses || []).filter(function (r) { return !drop[idOf(r)]; });
                if (q.uncertainBeside && drop[q.uncertainBeside]) delete q.uncertainBeside;
                if (keep[p.id] && host[keep[p.id]]) {
                    var beside = host[keep[p.id]];
                    q.region = null; q.parents = []; q.spouses = [];
                    q.uncertainBeside = beside.id; q.generation = beside.generation;
                    q.suspectedRelative = true;
                }
                return q;
            });
        }

    function create(D) {
            function ancestors(id) {
                var map = {}; map[id] = 0; var q = [[id, 0]];
                while (q.length) { var c = q.shift(); (D.byId[c[0]].parents || []).forEach(function (p) { if (!(p in map)) { map[p] = c[1] + 1; q.push([p, c[1] + 1]); } }); }
                return map;
            }
            // nearest shared ancestors of a and b: m = generations up from a, n = from b
            function blood(a, b) {
                var A = ancestors(a), B = ancestors(b), best = null;
                Object.keys(A).forEach(function (k) {
                    if (!(k in B)) return;
                    var s = A[k] + B[k];
                    if (!best || s < best.s || (s === best.s && Math.abs(A[k] - B[k]) < Math.abs(best.m - best.n))) best = { m: A[k], n: B[k], s: s };
                });
                if (!best) return null;
                best.commons = Object.keys(A).filter(function (k) { return k in B && A[k] === best.m && B[k] === best.n; })
                    .sort(function (x, y) { return (D.byId[x].sex === 'M' ? 0 : 1) - (D.byId[y].sex === 'M' ? 0 : 1); });
                // half relations: one shared ancestor who had children by more than one partner
                best.half = best.m > 0 && best.n > 0 && best.commons.length === 1 && (D.byId[best.commons[0]].spouses || []).length > 1;
                return best;
            }
            // ---- the words for a relationship. The pieces (father, stepmother, son-in-law) come from the dictionary; how they are put
            // together (great-grandfather, Urgroßvater, 2nd cousin once removed, Cousin 2. Grades) is each language's own rule, below.
            function ordinal(n) { var s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
            function kw(p, m, f, n) { return I.t('kin.' + (p.sex === 'M' ? m : p.sex === 'F' ? f : n)); }
            function lowerFirst(w) { return w.charAt(0).toLowerCase() + w.slice(1); }
            var KIN = {
                en: {
                    greats: function (k) { return k <= 0 ? '' : k === 1 ? 'great-' : k === 2 ? 'great-great-' : k + '× great-'; },
                    blood: function (m, n, sex) {
                        var g = function (mw, fw, nw) { return I.t('kin.' + (sex === 'M' ? mw : sex === 'F' ? fw : nw)); }, greats = KIN.en.greats;
                        if (m === 0 && n === 0) return I.t('kin.same');
                        if (m === 0) return n === 1 ? g('son', 'daughter', 'child') : greats(n - 2) + g('grandson', 'granddaughter', 'grandchild');
                        if (n === 0) return m === 1 ? g('father', 'mother', 'parent') : greats(m - 2) + g('grandfather', 'grandmother', 'grandparent');
                        if (m === 1 && n === 1) return g('brother', 'sister', 'sibling');
                        if (n === 1) return greats(m - 2) + g('uncle', 'aunt', 'auntOrUncle');
                        if (m === 1) return (n === 2 ? '' : n === 3 ? 'grand-' : greats(n - 3) + 'grand-') + g('nephew', 'niece', 'nieceOrNephew');
                        var deg = Math.min(m, n) - 1, rem = Math.abs(m - n);
                        return ordinal(deg) + ' ' + I.t('kin.cousin') + (rem === 1 ? I.t('kin.removed1') : rem === 2 ? I.t('kin.removed2') : rem > 2 ? I.t('kin.removedN', { n: rem }) : '');
                    },
                    half: function (lbl, b) {
                        if (!b.half) return lbl;
                        if (/cousin/.test(lbl)) return 'half ' + lbl;
                        return lbl.replace(/(aunt or uncle|niece or nephew|brother|sister|sibling|uncle|aunt|nephew|niece)$/, 'half-$1');
                    },
                    partnerOf: function (lbl) { return lbl + "'s " + I.t('kin.partner'); },
                    spouseOf: function (lbl, B) { return lbl + "'s " + kw(B, 'husband', 'wife', 'spouse'); },
                    ofPartner: function (lbl) { return "partner's " + lbl; },
                    byMarriage: function (lbl) { return lbl + ' by marriage'; }
                },
                de: {
                    join: function (k, w) {      // Enkel, Urenkel, Ururenkel; Großvater, Urgroßvater
                        return k <= 0 ? w : (k <= 3 ? 'Ur' + new Array(k).join('ur') : k + '× Ur') + lowerFirst(w);
                    },
                    blood: function (m, n, sex) {
                        var g = function (mw, fw, nw) { return I.t('kin.' + (sex === 'M' ? mw : sex === 'F' ? fw : nw)); }, join = KIN.de.join;
                        if (m === 0 && n === 0) return I.t('kin.same');
                        if (m === 0) return n === 1 ? g('son', 'daughter', 'child') : join(n - 2, g('grandson', 'granddaughter', 'grandchild'));
                        if (n === 0) return m === 1 ? g('father', 'mother', 'parent') : join(m - 2, g('grandfather', 'grandmother', 'grandparent'));
                        if (m === 1 && n === 1) return g('brother', 'sister', 'sibling');
                        if (n === 1) return m === 2 ? g('uncle', 'aunt', 'auntOrUncle') : join(m - 3, 'Groß' + lowerFirst(g('uncle', 'aunt', 'auntOrUncle')));
                        if (m === 1) return n === 2 ? g('nephew', 'niece', 'nieceOrNephew') : join(n - 3, 'Groß' + lowerFirst(g('nephew', 'niece', 'nieceOrNephew')));
                        var deg = Math.min(m, n) - 1, rem = Math.abs(m - n);
                        return g('cousinM', 'cousinF', 'cousinN') + ' ' + deg + '. Grades' + (rem === 1 ? I.t('kin.removed1') : rem === 2 ? I.t('kin.removed2') : rem > 2 ? I.t('kin.removedN', { n: rem }) : '');
                    },
                    half: function (lbl, b) { return b.half ? 'Halb' + lowerFirst(lbl) : lbl; },
                    partnerOf: function (lbl) { return I.t('kin.partner') + ' von ' + lbl; },
                    spouseOf: function (lbl, B) { return kw(B, 'husband', 'wife', 'spouse') + ' von ' + lbl; },
                    ofPartner: function (lbl) { return lbl + ' des Partners'; },
                    byMarriage: function (lbl) { return lbl + ' (angeheiratet)'; }
                }
            };
            function kin() { return KIN[I.lang] || KIN.en; }
            function label(m, n, sex) { return kin().blood(m, n, sex); }
            function halfify(lbl, b) { return kin().half(lbl, b); }
            // What b is to a, with the reasoning behind it.
            function relInfo(a, b) {
                var A = D.byId[a], B = D.byId[b], r = { a: a, b: b, kind: 'none', label: null, commons: [], m: 0, n: 0, half: false, via: null };
                if (a === b) { r.kind = 'self'; r.label = I.t('kin.same'); return r; }
                var sp = (A.spouses || []).filter(function (s) { return s.id === b; })[0];
                if (sp) { r.kind = 'spouse'; r.label = sp.relation === 'partner' ? partnerWord(B) : ((A.spouses.length > 1) ? kw(B, sp.order === 1 ? 'firstHusband' : 'secondHusband', sp.order === 1 ? 'firstWife' : 'secondWife', sp.order === 1 ? 'firstSpouse' : 'secondSpouse') : kw(B, 'husband', 'wife', 'spouse')); return r; }
                var x = blood(a, b);
                if (x) { r.kind = 'blood'; r.m = x.m; r.n = x.n; r.commons = x.commons; r.half = x.half; r.label = halfify(label(x.m, x.n, B.sex), x); return r; }
                // b married one of a's blood relatives
                var hit = null;
                (B.spouses || []).some(function (s) { var y = blood(a, s.id); if (y) { hit = { y: y, s: s.id }; return true; } return false; });
                if (hit) {
                    var y = hit.y, S2 = D.byId[hit.s];
                    r.kind = 'inlaw'; r.via = hit.s; r.commons = y.commons;
                    if (isPartner(hit.s, b)) r.label = kin().partnerOf(halfify(label(y.m, y.n, S2.sex), y), B);
                    else if (y.m === 0 && y.n === 1) r.label = kw(B, 'sonInLaw', 'daughterInLaw', 'childInLaw');
                    else if (y.m === 1 && y.n === 1) r.label = kw(B, 'brotherInLaw', 'sisterInLaw', 'siblingInLaw');
                    else if (y.m === 1 && y.n === 0) { r.label = kw(B, 'stepfather', 'stepmother', 'stepParent'); r.kind = 'step'; }
                    else if (y.m === 2 && y.n === 0) { r.label = kw(B, 'stepGrandfather', 'stepGrandmother', 'stepGrandparent'); r.kind = 'step'; }
                    else r.label = kin().spouseOf(halfify(label(y.m, y.n, S2.sex), y), B);
                    return r;
                }
                // b is a blood relative of a's husband or wife
                (A.spouses || []).some(function (s) { var y = blood(s.id, b); if (y) { hit = { y: y, s: s.id }; return true; } return false; });
                if (hit) {
                    var z = hit.y;
                    r.kind = 'inlaw'; r.via = hit.s; r.commons = z.commons;
                    if (isPartner(a, hit.s)) r.label = kin().ofPartner(halfify(label(z.m, z.n, B.sex), z));
                    else if (z.m === 1 && z.n === 0) r.label = kw(B, 'fatherInLaw', 'motherInLaw', 'parentInLaw');
                    else if (z.m === 1 && z.n === 1) r.label = kw(B, 'brotherInLaw', 'sisterInLaw', 'siblingInLaw');
                    else if (z.m === 0 && z.n === 1) { r.label = kw(B, 'stepson', 'stepdaughter', 'stepchild'); r.kind = 'step'; }
                    else if (z.m === 0 && z.n === 2) { r.label = kw(B, 'stepGrandson', 'stepGranddaughter', 'stepGrandchild'); r.kind = 'step'; }
                    else r.label = kin().byMarriage(halfify(label(z.m, z.n, B.sex), z));
                    return r;
                }
                r.kind = relPath(a, b) ? 'marriage' : 'none';
                r.label = r.kind === 'marriage' ? I.t('kin.relatedByMarriage') : null;
                return r;
            }
            function isPartner(a, b) { return ((D.byId[a] || {}).spouses || []).some(function (s) { return s.id === b && s.relation === 'partner'; }); }
            function partnerWord(p) { return I.t(p.sex === 'F' ? 'kin.partnerF' : 'kin.partner'); }
            function spouseWord(a, p) { return isPartner(a, p.id) ? partnerWord(p) : kw(p, 'husband', 'wife', 'spouse'); }
            function relationship(from, to) {
                if (!from || from === to) return null;
                return relInfo(from, to).label;
            }
            // Shortest chain through parents, children and marriages; confirmed links are preferred over uncertain ones.
            function relPath(a, b) {
                var dist = {}, prev = {}, done = {};
                D.people.forEach(function (p) { dist[p.id] = Infinity; });
                dist[a] = 0;
                function pen(id) { var p = D.byId[id]; return (p.confidence === 'confirmed' ? 0 : 0.05) + (p.parentLinkConfidence && p.parentLinkConfidence !== 'confirmed' ? 0.05 : 0) + (p.isDirectLine ? 0 : 0.001); }
                for (;;) {
                    var u = null, best = Infinity;
                    Object.keys(dist).forEach(function (k) { if (!done[k] && dist[k] < best) { best = dist[k]; u = k; } });
                    if (u === null || u === b) break;
                    done[u] = true;
                    var P = D.byId[u], nb = [];
                    (P.parents || []).forEach(function (x) { nb.push([x, 1, 'parent']); });
                    (P.children || []).forEach(function (x) { nb.push([x, 1, 'child']); });
                    (P.spouses || []).forEach(function (s) { nb.push([s.id, 1.25, 'spouse']); });
                    nb.forEach(function (e) {
                        if (!D.byId[e[0]]) return;
                        var d = dist[u] + e[1] + pen(e[0]);
                        if (d < dist[e[0]]) { dist[e[0]] = d; prev[e[0]] = { from: u, type: e[2] }; }
                    });
                }
                if (dist[b] === Infinity) return null;
                var out = [{ id: b, type: prev[b] ? prev[b].type : null }], c = b;
                while (prev[c]) { c = prev[c].from; out.unshift({ id: c, type: prev[c] ? prev[c].type : null }); }
                out[0].type = null;
                return out;
            }
            function relNotes(path, info) {
                var notes = [];
                if (!path) return notes;
                for (var i = 1; i < path.length; i++) {
                    var u = D.byId[path[i - 1].id], v = D.byId[path[i].id], t = path[i].type;
                    var child = t === 'parent' ? u : t === 'child' ? v : null;
                    if (child && child.parentLinkConfidence && child.parentLinkConfidence !== 'confirmed') notes.push(I.t('tree.noteLink', { name: child.displayName, other: (child === u ? v : u).displayName, status: confWord(child.parentLinkConfidence) }));
                }
                path.slice(1, -1).forEach(function (s) {
                    var p = D.byId[s.id];
                    if (p.placeholder) notes.push(I.t('tree.noteIndirect', { name: p.displayName }));
                    else if (p.confidence === 'unverified') notes.push(I.t('tree.noteUnverified', { name: p.displayName }));
                });
                if (info && info.kind === 'blood' && info.commons.length === 1 && !info.half && info.m > 0 && info.n > 0) notes.push(I.t('tree.noteOneAncestor'));
                return notes.filter(function (n, i, all) { return all.indexOf(n) === i; });
            }
            function firstName(p) {
                if (p.shortName) return p.shortName;
                var q = p.displayName.match(/"([^"]+)"/);
                return (q ? q[1] : p.displayName.split(' ')[0]).replace(/[,.;:]+$/, '');
            }
            function shortName(p, other) {
                // people known only by a title and initials ("Mr H. G. Andrews") keep their full name
                if (p.placeholder || /^(Mr|Mrs|Miss|Ms)\b/.test(p.displayName)) return p.displayName;
                var s = firstName(p);
                if (other && !other.placeholder && firstName(other) === s) return p.displayName;
                return s;
            }
            function poss(s) { return new RegExp(I.t('kin.possEnd'), 'i').test(s) ? I.t('kin.possS', { name: s }) : I.t('kin.poss', { name: s }); }

        return {
            relInfo: relInfo, relationship: relationship, relPath: relPath, relNotes: relNotes, blood: blood,
            kw: kw, isPartner: isPartner, partnerWord: partnerWord, spouseWord: spouseWord,
            firstName: firstName, shortName: shortName, poss: poss
        };
    }

    // ---- "Relationships to": who the page works out relationships from, shared by the tree and the map.
    // One stored person id (localStorage "tc_viewpoint"), kept when the visitor chooses one in either page. A visitor who has said
    // who they are (visitor.enabled) overrides it and is never written to this key.
    var KEY = 'tc_viewpoint';
    var viewpoint = {
        key: KEY,
        saved: function (byId) { var v = null; try { v = localStorage.getItem(KEY); } catch (_) {} return v && byId[v] ? v : null; },
        save: function (id) { try { if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY); } catch (_) {} },
        visitor: function (byId) { var v = window.FamilyVisitor, id = v && v.id && v.id(); return id && byId[id] ? id : null; }
    };

    window.FamilyKinship = { create: create, pruneHidden: pruneHidden, viewpoint: viewpoint };
})();
