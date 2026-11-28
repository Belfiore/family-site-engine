"""Discoveries: finding out what a publication newly tells the family, and keeping the record of it.

Used by build_site.py (when a site has "timeline": {"enabled": true}) and by tools/backfill-discoveries.py.
See docs/discovery-timeline.md for the design; the short version:

  1. A site's data is reduced to "atoms": one small, normalised claim each (a person, a parent link, a birth,
     a residence, a photograph ...), keyed so that the same claim has the same key whatever file it sits in
     and however its fields are ordered or worded. Anyone withheld from the public timeline (living people
     and hidden regions) never becomes an atom.
  2. The atoms of this publication are compared with the atoms of the last publication. What is new, what
     was corrected and what gained evidence is grouped into findings, and each finding gets a headline.
  3. The findings are added to the history carried from the last publication. Researchers' own
     "discovery" notes in the data are laid over the generated findings, and always win.
  4. The atoms and the history travel inside the published site (discoveries/state.json), so "the last
     publication" is whatever is live. A failed build publishes nothing, so it cannot move the baseline.

Nothing here uses the network or a model: the same data always gives the same findings and headlines.
"""
import datetime, difflib, hashlib, json, os, re, unicodedata

ATOM_SCHEMA = 1     # bump when atoms are derived differently; sites then start a new baseline instead of a flood
STATE_SCHEMA = 1
TYPES = ('person', 'record', 'photo', 'correction', 'place', 'connection')
TYPE_LABELS = {'person': 'New person', 'record': 'New record', 'photo': 'New photo', 'correction': 'Correction',
               'place': 'New place', 'connection': 'New connection'}
CONF_RANK = {'confirmed': 3, 'probable': 2, 'family tradition': 1, 'unverified': 0}
PLACES_EACH = 3      # up to this many new places in one publication are a find each; more are one find
PAIRABLE = ('residence', 'event', 'placeevent')     # lists with no natural identity: a changed item looks like one removed and one added
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
URL_RE = re.compile(r'^(https?:)?//', re.I)


# ------------------------------------------------------------------ small helpers
def norm(s):
    s = unicodedata.normalize('NFKD', str(s if s is not None else '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def slug(s):
    return norm(s).replace(' ', '-')


def sha(s, n=10):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:n]


def hid(pid):
    """A one-way mark for a withheld person's id, so a later publication can tell 'was withheld' from 'is new'
    without the file naming anyone who is withheld."""
    return hashlib.sha256(('family-site-engine:' + str(pid)).encode('utf-8')).hexdigest()[:12]


def idof(r):
    return r if isinstance(r, str) else (r or {}).get('id')


def is_living(p):
    """The engine's one definition of a living person: isLiving (the older "living" flag is folded into it by
    migrate.py, and is read here too so an unmigrated file is not treated as public)."""
    return bool(p.get('isLiving') or p.get('living'))


def a_an(word):
    return ('an ' if re.match(r'^[aeiou]', norm(word) or 'x') else 'a ') + word


def count_word(n):
    words = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
    return words[n] if 0 <= n < len(words) else str(n)


def human_list(items):
    items = [i for i in items if i]
    if len(items) <= 1: return ''.join(items)
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def pick(seed, options):
    return options[int(sha(seed, 6), 16) % len(options)]


def today(now):
    return now[:10]


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


def date_text(d, display=None):
    """1876, June 1876, 10 June 1875; anything else as the site wrote it."""
    d = (d or '').strip()
    m = re.match(r'^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$', d)
    if m:
        y, mo, da = m.groups()
        if mo and 1 <= int(mo) <= 12:
            if da: return '%d %s %s' % (int(da), MONTHS[int(mo) - 1], y)
            return '%s %s' % (MONTHS[int(mo) - 1], y)
        return y
    return (display or d or '').strip()


def differs(a, b):
    """Do two canonical values (fields joined with '|') differ in a way that matters? Case, punctuation,
    accents and a one-letter spelling slip do not matter; a different number, name or place does."""
    if a == b: return False
    pa, pb = (a or '').split('|'), (b or '').split('|')
    if len(pa) != len(pb): return True
    return any(seg_differs(x, y) for x, y in zip(pa, pb))


def seg_differs(x, y):
    nx, ny = norm(x), norm(y)
    if nx == ny: return False
    if re.findall(r'\d+', nx) != re.findall(r'\d+', ny): return True
    return difflib.SequenceMatcher(None, nx, ny).ratio() < 0.88


def refines(kind, c1, c2):
    """The new value is the old date with more detail (1874 became 1874-04-02) and nothing else moved."""
    if kind not in ('birth', 'death', 'burial', 'spouse'): return False
    p1, p2 = c1.split('|'), c2.split('|')
    if len(p1) != 2 or len(p2) != 2: return False
    return bool(p1[0]) and p2[0] != p1[0] and p2[0].startswith(p1[0]) and not seg_differs(p1[1], p2[1])


def weakest(confs):
    confs = [c for c in confs if c in CONF_RANK]
    return min(confs, key=lambda c: CONF_RANK[c]) if confs else None


# ------------------------------------------------------------------ the snapshot: a site's data as atoms
class Snapshot:
    """What one publication says, with everyone withheld left out."""
    def __init__(self):
        self.atoms = {}
        self.names = {}          # id -> display name, everyone in the data
        self.sex = {}
        self.persons = set()     # ids of people who may appear in the timeline
        self.withheld = set()    # ids of people who may not
        self.withheld_names = []
        self.sources = {}
        self.places = {}
        self.lines = {}          # person id -> branch id
        self.line_labels = []    # [{id, label}]
        self.manual = []         # researcher-written discoveries: {covers, d, origin}
        self.refs = {'place_public': set(), 'place_private': set(), 'src_public': set(), 'src_private': set()}
        self.off_tree = set()    # people in a hidden region that timeline.showRegions lets the page name; the tree still leaves them off
        self.off_places = set()  # places only those people have anything to do with: the map does not draw them either
        self.full_of = {}        # a picture's thumbnail path -> the full-size file, from the media of people the page may show
        self.warnings = []


def collect_refs(o, places, sources):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ('placeId', 'fromPlaceId', 'toPlaceId') and isinstance(v, str): places.add(v)
            elif k in ('sourceIds', 'coordinateSourceIds') and isinstance(v, list): sources.update(s for s in v if isinstance(s, str))
            elif k == 'sourceId' and isinstance(v, str): sources.add(v)
            else: collect_refs(v, places, sources)
    elif isinstance(o, list):
        for v in o: collect_refs(v, places, sources)


def file_sha(site, rel):
    if not rel or URL_RE.match(rel): return None
    p = os.path.join(site, rel)
    if not os.path.isfile(p): return None
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()[:10]


def branch_lines(cfg, people):
    branches = (cfg.get('map') or {}).get('branches') or [{'id': 'family', 'label': 'The family', 'default': True}]
    default = next((b for b in branches if b.get('default')), branches[0])
    out = {}
    for p in people:
        pick_ = None
        if p.get('region'):
            pick_ = next((b for b in branches if p['region'] in (b.get('regions') or [])), None)
        if not pick_:
            pick_ = next((b for b in branches if p['id'] in (b.get('people') or [])), None)
        if not pick_:       # then by a story page they appear on, as the map does (engine/map-data.js: branchOf)
            pages = [(r if isinstance(r, str) else (r.get('url') or r.get('href') or '') if isinstance(r, dict) else '').split('#')[0]
                     for r in p.get('relatedPages') or []]
            pick_ = next((b for b in branches if b is not default and not (b.get('regions') or []) and any(pg in (b.get('pages') or []) for pg in pages)), None)
        out[p['id']] = (pick_ or default)['id']
    return out, [{'id': b['id'], 'label': b.get('label') or b['id']} for b in branches], default['id']


def build_snapshot(site, cfg, people_doc, sources_doc, places_doc, curated_doc, file_id=None):
    """file_id(path) says which picture a path is (a hash of its contents); the default reads the file from the site folder.
    The backfill script gives it a way to ask git instead, for the site as it was at an earlier commit."""
    snap = Snapshot()
    meta = (people_doc or {}).get('meta') or {}
    tree = cfg.get('tree') or {}
    hidden = set(tree.get('hiddenRegions') or meta.get('hiddenRegions') or [])
    people = [p for p in (people_doc or {}).get('people') or [] if isinstance(p, dict) and p.get('id')]
    by = {p['id']: p for p in people}
    # timeline.showRegions lets named hidden regions onto the timeline (leads, associates). A living person is withheld whatever
    # region they are in, and a region that is not hidden has nothing to show. Left out, this is exactly as it was.
    shown = set((cfg.get('timeline') or {}).get('showRegions') or []) & hidden
    snap.withheld = {p['id'] for p in people if is_living(p) or (p.get('region') and p['region'] in hidden and p['region'] not in shown)}
    snap.off_tree = {p['id'] for p in people if not is_living(p) and p.get('region') and p['region'] in shown}
    snap.persons = set(by) - snap.withheld
    snap.names = {p['id']: p.get('displayName') or p['id'] for p in people}
    snap.sex = {p['id']: p.get('sex') for p in people}
    snap.withheld_names = [norm(snap.names[i]) for i in snap.withheld if len(norm(snap.names[i])) >= 4]
    snap.sources = {s['id']: s for s in (sources_doc or {}).get('sources') or [] if isinstance(s, dict) and s.get('id')}
    plist = [p for p in (places_doc or {}).get('places') or [] if isinstance(p, dict) and p.get('id')]
    snap.places = {p['id']: p for p in plist}
    snap.lines, snap.line_labels, snap.default_line = None, None, None
    lines, labels, default = branch_lines(cfg, people)
    snap.lines, snap.line_labels, snap.default_line = lines, labels, default

    atoms = snap.atoms

    def add(kind, key, pids, v=None, c='', src=None, conf=None, pl=None, anchor='', d=None):
        key = '%s:%s' % (kind, key)
        n = 2
        while key in atoms:
            if atoms[key]['c'] == c and atoms[key]['p'] == sorted(pids):
                return key                      # the same claim stated twice
            key = '%s~%d' % (key.split('~')[0], n)
            n += 1
        atoms[key] = {'kind': kind, 'p': sorted(pids), 'pl': sorted(pl or []), 'v': v or {}, 'c': c,
                      'src': [s for s in (src or []) if isinstance(s, str)], 'conf': conf if conf in CONF_RANK else None, 'a': anchor}
        if isinstance(d, dict) and d:
            snap.manual.append({'covers': [key], 'd': d, 'origin': 'data'})
        return key

    # places, and who is in them: a place only withheld people have anything to do with is withheld too
    off_pl, on_pl = set(), set()
    for p in people:
        pl, so = set(), set()
        collect_refs(p, pl, so)
        tgt = 'private' if p['id'] in snap.withheld else 'public'
        snap.refs['place_' + tgt] |= pl
        snap.refs['src_' + tgt] |= so
        if p['id'] in snap.off_tree: off_pl |= pl
        elif tgt == 'public': on_pl |= pl
    for pl in plist:
        # what a place says about itself (where its coordinates came from, its blurb) is public, and counts as citing a source
        own = {k: v for k, v in pl.items() if k != 'events'}
        collect_refs(own, set(), snap.refs['src_public'])
        for e in pl.get('events') or []:
            hid_ = any(o in snap.withheld for o in e.get('personIds') or [])
            tgt = 'private' if hid_ else 'public'
            snap.refs['place_' + tgt].add(pl['id'])
            if not hid_: (off_pl if any(o in snap.off_tree for o in e.get('personIds') or []) else on_pl).add(pl['id'])
            so = set()
            collect_refs(e, set(), so)
            snap.refs['src_' + tgt] |= so

    snap.off_places = off_pl - on_pl

    def place_name(pid_):
        return (snap.places.get(pid_) or {}).get('name') or ''

    def event_atom(kind, p, e):
        if not isinstance(e, dict): return
        date = (e.get('date') or '').strip()
        place = e.get('place') or place_name(e.get('placeId')) or ''
        pk = slug(e.get('placeId') or place)
        if not (date or pk): return
        add(kind, p['id'], [p['id']], v={'date': date, 'display': e.get('display') or '', 'place': place, 'placeId': e.get('placeId') or ''},
            c='%s|%s' % (date, pk), src=e.get('sourceIds'), conf=e.get('confidence'), pl=[e['placeId']] if e.get('placeId') else [],
            d=e.get('discovery'))

    for p in people:
        pid = p['id']
        if pid in snap.withheld:
            continue
        add('person', pid, [pid], v={'name': snap.names[pid], 'placeholder': bool(p.get('placeholder'))}, c='', d=p.get('discovery'))
        for kind in ('birth', 'death', 'burial'):
            event_atom(kind, p, p.get(kind))
        for r in p.get('parents') or []:
            o = idof(r)
            if o in snap.persons:
                add('parent', '%s:%s' % (pid, o), [pid, o], v={'child': pid, 'parent': o}, c='', conf=p.get('parentLinkConfidence'))
        for r in p.get('children') or []:
            o = idof(r)
            if o in snap.persons and ('parent:%s:%s' % (o, pid)) not in atoms:
                add('parent', '%s:%s' % (o, pid), [o, pid], v={'child': o, 'parent': pid}, c='', conf=by[o].get('parentLinkConfidence'))
        for s in p.get('spouses') or []:
            o = idof(s)
            if o not in snap.persons or not isinstance(s, dict): continue
            a, b = sorted([pid, o])
            place = s.get('place') or place_name(s.get('placeId')) or ''
            mdate = (s.get('marriageDate') or '').strip()
            add('spouse', '%s:%s' % (a, b), [a, b], v={'date': mdate, 'display': s.get('marriageDisplay') or '', 'place': place,
                                                     'rel': s.get('relation') or 'marriage', 'order': s.get('order'), 'of': pid},
                c='%s|%s' % (mdate, slug(s.get('placeId') or place)), src=s.get('sourceIds'), conf=s.get('confidence'),
                pl=[s['placeId']] if s.get('placeId') else [], d=s.get('discovery'))
        for r in p.get('residences') or []:
            if not isinstance(r, dict): continue
            where = r.get('placeId') or r.get('place') or r.get('address') or ''
            if not where: continue
            add('residence', '%s:%s:%s' % (pid, slug(where), slug(r.get('years'))), [pid],
                v={'place': r.get('place') or place_name(r.get('placeId')), 'address': r.get('address') or '', 'years': r.get('years') or ''},
                c=slug(r.get('address')), src=r.get('sourceIds'), conf=r.get('confidence'), pl=[r['placeId']] if r.get('placeId') else [],
                anchor=slug(where), d=r.get('discovery'))
        for o in p.get('occupations') or []:
            if not isinstance(o, dict) or not o.get('title'): continue
            add('occupation', '%s:%s:%s' % (pid, slug(o['title']), slug(o.get('employer'))), [pid],
                v={'title': o['title'], 'employer': o.get('employer') or '', 'years': o.get('years') or '', 'place': o.get('place') or ''},
                c='%s|%s' % (o.get('years') or '', slug(o.get('placeId') or o.get('place'))), src=o.get('sourceIds'), conf=o.get('confidence'),
                pl=[o['placeId']] if o.get('placeId') else [], d=o.get('discovery'))
        im = p.get('immigration')
        if isinstance(im, dict) and (im.get('date') or im.get('port') or im.get('ship')):
            add('immigration', pid, [pid], v={'date': im.get('date') or '', 'port': im.get('port') or '', 'ship': im.get('ship') or ''},
                c='%s|%s|%s' % (im.get('date') or '', slug(im.get('port')), slug(im.get('ship'))), src=im.get('sourceIds'), conf=im.get('confidence'),
                d=im.get('discovery'))
        for vy in p.get('voyages') or []:
            if not isinstance(vy, dict): continue
            ident = vy.get('id') or '%s-%s' % (slug(vy.get('ship')), slug(vy.get('departureDate')))
            add('voyage', '%s:%s' % (pid, ident), [pid], v={'ship': vy.get('ship') or '', 'from': vy.get('from') or '', 'to': vy.get('to') or ''},
                c='%s|%s|%s|%s' % (vy.get('departureDate') or '', vy.get('arrivalDate') or '', slug(vy.get('from')), slug(vy.get('to'))),
                src=vy.get('sourceIds'), conf=vy.get('confidence'), d=vy.get('discovery'))
        for f in p.get('facts') or []:
            if not isinstance(f, dict) or not f.get('label'): continue
            add('fact', '%s:%s' % (pid, slug(f['label'])), [pid], v={'label': f['label'], 'value': f.get('value') or ''},
                c=str(f.get('value') or ''), src=f.get('sourceIds'), conf=f.get('confidence'), d=f.get('discovery'))
        for t in p.get('timeline') or []:
            if not isinstance(t, dict) or t.get('kind') == 'context' or not t.get('label'): continue
            add('event', '%s:%s:%s' % (pid, slug(t['label']), slug(t.get('date'))), [pid],
                v={'date': t.get('date') or '', 'label': t['label'], 'event': t.get('event') or ''}, c='', src=t.get('sourceIds'),
                conf=t.get('confidence'), pl=[t['placeId']] if t.get('placeId') else [], anchor=slug(t['label']), d=t.get('discovery'))
        for m in p.get('media') or []:
            if not isinstance(m, dict): continue
            rel = m.get('file') or m.get('thumb')
            if not rel: continue
            if m.get('thumb') and m.get('file') and m['thumb'] != m['file']: snap.full_of.setdefault(m['thumb'], m['file'])
            ident = (file_id(rel) if file_id else file_sha(site, rel)) or slug(rel)
            kind = 'photo' if (m.get('type') or 'photo') in ('photo', 'portrait', 'gravestone') else 'document'
            add(kind, '%s:%s' % (pid, ident), [pid], v={'type': m.get('type') or 'photo', 'caption': m.get('caption') or '', 'alt': m.get('alt') or '',
                                                       'file': rel, 'thumb': m.get('thumb') or rel}, c='', src=[m['sourceId']] if m.get('sourceId') else [],
                d=m.get('discovery'))

    for pl in plist:
        pub = snap.refs['place_public']
        if pl['id'] in snap.refs['place_private'] and pl['id'] not in pub:
            continue
        add('place', pl['id'], [], v={'name': pl.get('name') or pl['id'], 'country': pl.get('country') or '', 'kind': pl.get('kind') or ''},
            c='', pl=[pl['id']], d=pl.get('discovery'))
        for e in pl.get('events') or []:
            if not isinstance(e, dict) or e.get('factRef') or not e.get('id'): continue
            pids = [o for o in e.get('personIds') or [] if o in by]
            if any(o in snap.withheld for o in pids): continue
            add('placeevent', '%s:%s' % (pl['id'], e['id']), pids, v={'type': e.get('type') or '', 'date': e.get('dateStart') or e.get('date') or '',
                                                                      'place': pl.get('name') or ''},
                c='%s|%s' % (e.get('dateStart') or e.get('date') or '', e.get('type') or ''), src=e.get('sourceIds'), conf=e.get('confidence'),
                pl=[pl['id']], anchor=slug(e.get('type')), d=e.get('discovery'))

    for d in (curated_doc or {}).get('discoveries') or []:
        if isinstance(d, dict):
            snap.manual.append({'covers': [k for k in d.get('covers') or [] if isinstance(k, str)], 'd': d, 'origin': 'file',
                                'people': [o for o in d.get('personIds') or [] if isinstance(o, str)],
                                'places': [o for o in d.get('placeIds') or [] if isinstance(o, str)]})
    return snap


# ------------------------------------------------------------------ comparing two snapshots
def diff(prev_atoms, cur_atoms, absorbed, masked, absorbed_places=frozenset()):
    """What changed in meaning. absorbed: people who were withheld last time and are not now (their existing record
    is the new baseline, not news). masked: people withheld now (nothing about them is reported or retired).
    absorbed_places: places that are public now only because such a person is (a region newly shown by
    timeline.showRegions); a place that was already in the data is not a new place."""
    changes = []
    added, removed = {}, {}
    for k, b in cur_atoms.items():
        if set(b['p']) & absorbed: continue
        a = prev_atoms.get(k)
        if a is None:
            if b['kind'] == 'place' and set(b['pl']) & absorbed_places: continue
            added[k] = b
        elif differs(a.get('c', ''), b.get('c', '')):
            op = 'refine' if refines(b['kind'], a.get('c', ''), b.get('c', '')) else 'modify'
            changes.append({'op': op, 'key': k, 'new': b, 'old': a})
        elif a.get('conf') != b.get('conf') and CONF_RANK.get(a.get('conf'), -1) != CONF_RANK.get(b.get('conf'), -1):
            changes.append({'op': 'conf', 'key': k, 'new': b, 'old': a})
        else:
            fresh = [s for s in b['src'] if s not in a['src']]
            if fresh and CONF_RANK.get(b.get('conf'), -1) > CONF_RANK.get(a.get('conf'), -1):
                changes.append({'op': 'conf', 'key': k, 'new': b, 'old': a})
            elif fresh:
                changes.append({'op': 'evidence', 'key': k, 'new': b, 'old': a, 'fresh': fresh})
    for k, a in prev_atoms.items():
        if k not in cur_atoms and not (set(a['p']) & masked) and not (set(a['p']) & absorbed):
            removed[k] = a
    # a changed list item looks like one removed and one added: pair them up
    buckets = {}
    for k, b in added.items():
        if b['kind'] in PAIRABLE: buckets.setdefault((b['kind'], tuple(b['p']), b['a']), [[], []])[0].append(k)
    for k, a in removed.items():
        if a['kind'] in PAIRABLE: buckets.setdefault((a['kind'], tuple(a['p']), a['a']), [[], []])[1].append(k)
    for (kind, pids, anchor), (adds, rems) in buckets.items():
        if adds and len(adds) == len(rems):
            for ka, kr in zip(sorted(adds), sorted(rems)):
                changes.append({'op': 'modify', 'key': ka, 'new': added.pop(ka), 'old': removed.pop(kr), 'replaces': kr})
    for k, b in added.items():
        changes.append({'op': 'add', 'key': k, 'new': b})
    for k, a in removed.items():
        changes.append({'op': 'remove', 'key': k, 'old': a})
    return sorted(changes, key=lambda c: (c['op'], c['key']))


# ------------------------------------------------------------------ wording
def lcfirst(t):
    t = str(t or '')
    return t[:1].lower() + t[1:] if t[1:2].islower() else t


class Words:
    """Headlines from data. Names and values come straight from the data; the engine adds only connecting words."""
    def __init__(self, snap):
        self.s = snap

    def name(self, pid):
        return self.s.names.get(pid) or pid

    def poss(self, pid):
        n = self.name(pid)
        return n + ("'" if n.endswith('s') else "'s")

    def pron(self, pid):
        return {'M': ('he', 'his'), 'F': ('she', 'her')}.get(self.s.sex.get(pid), ('they', 'their'))

    def kin(self, pid, male, female, neutral):
        return {'M': male, 'F': female}.get(self.s.sex.get(pid), neutral)

    def part(self, a):
        """A noun phrase for what an atom says: 'birth in Cork (1876)', 'an occupation (wool merchant)'."""
        k, v = a['kind'], a['v']
        if k in ('birth', 'death', 'burial'):
            when = date_text(v.get('date'), v.get('display'))
            bits = ' '.join(x for x in [('in ' + v['place']) if v.get('place') else '', ('(%s)' % when) if when else ''] if x)
            return ('%s %s' % (k, bits)).strip()
        if k == 'residence': return 'a home at %s' % (v.get('address') or v.get('place'))
        if k == 'occupation': return 'an occupation (%s)' % lcfirst(v['title'])
        if k == 'fact': return ('%s: %s' % (v['label'], v['value'])) if v.get('value') else v['label']
        if k == 'voyage': return 'a voyage%s' % ((' on the %s' % v['ship']) if v.get('ship') else '')
        if k == 'immigration': return 'an immigration record'
        if k == 'event': return v['label']
        if k == 'placeevent': return 'an event at %s' % v.get('place')
        if k == 'spouse': return 'a marriage'
        return k

    def fixes(self, old, new):
        """[(possessive or None, label, from, to)] for a corrected atom."""
        k, ov, nv = new['kind'], old['v'], new['v']
        who = new['p'][0] if new['p'] else None
        out = []
        if k in ('birth', 'death', 'burial', 'spouse'):
            od, nd = (old['c'].split('|') + ['', ''])[:2], (new['c'].split('|') + ['', ''])[:2]
            poss = self.poss(who) if k != 'spouse' else None
            tail = ' of the marriage of %s and %s' % (self.name(new['p'][0]), self.name(new['p'][1])) if k == 'spouse' else ''
            if seg_differs(od[0], nd[0]):
                full = len(od[0]) == 10 and len(nd[0]) == 10
                years = od[0][:4] != nd[0][:4] and not full
                noun = {'birth': 'birth', 'death': 'death', 'burial': 'burial', 'spouse': ''}[k]
                lab = ('%s %s' % (noun, 'year' if years else 'date')).strip() if k != 'spouse' else ('year' if years else 'date')
                fro = (od[0][:4] if years else date_text(ov.get('date'), ov.get('display'))) or 'no date'
                to = nd[0][:4] if years else date_text(nv.get('date'), nv.get('display'))
                out.append((poss, lab + tail, fro, to))
            if seg_differs(od[1], nd[1]):
                lab = {'birth': 'birthplace', 'death': 'place of death', 'burial': 'place of burial', 'spouse': 'place'}[k]
                out.append((poss, lab + tail, ov.get('place') or 'no place', nv.get('place') or 'no place'))
        else:
            poss = self.poss(who)
            if k == 'residence':
                out.append((poss, 'dates at %s' % (nv.get('address') or nv.get('place')), ov.get('years') or 'unrecorded', nv.get('years') or 'unrecorded'))
            elif k == 'occupation':
                out.append((poss, 'dates as %s' % a_an(lcfirst(nv['title'])), ov.get('years') or 'unrecorded', nv.get('years') or 'unrecorded'))
            elif k == 'fact':
                out.append((poss, lcfirst(nv['label']), ov.get('value') or 'nothing', nv.get('value') or 'nothing'))
            elif k == 'immigration':
                out.append((poss, 'immigration details', ' '.join(x for x in [ov.get('date'), ov.get('port')] if x) or 'unrecorded',
                            ' '.join(x for x in [nv.get('date'), nv.get('port')] if x) or 'unrecorded'))
            elif k == 'voyage':
                out.append((poss, 'voyage details', ' '.join(x for x in [ov.get('ship'), ov.get('from'), ov.get('to')] if x),
                            ' '.join(x for x in [nv.get('ship'), nv.get('from'), nv.get('to')] if x)))
            else:
                out.append((poss, k, old['c'], new['c']))
        return out or [(None, k, '', '')]


def hedge_word(conf):
    return {'probable': 'probably', 'unverified': 'possibly'}.get(conf, '')


# ------------------------------------------------------------------ grouping changes into findings
def entry_id(type_, changes):
    basis = '|'.join(sorted('%s:%s:%s' % (c['op'], c['key'], (c.get('new') or c.get('old') or {}).get('c', '')) for c in changes))
    return 'd-' + sha(type_ + '|' + basis, 10)


def bucket(items, keyfn):
    out = {}
    for c in items: out.setdefault(keyfn(c), []).append(c)
    return sorted(out.items(), key=lambda kv: str(kv[0]))


def person_components(people_adds, rest):
    """Sets of new people, joined when a new parent or spouse link runs between them."""
    ids = sorted({c['new']['p'][0] for c in people_adds})
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for c in rest:
        n = c['new']
        if n['kind'] in ('parent', 'spouse') and len(n['p']) == 2 and all(p in parent for p in n['p']):
            parent[find(n['p'][0])] = find(n['p'][1])
    comps = {}
    for i in ids: comps.setdefault(find(i), set()).add(i)
    return [comps[k] for k in sorted(comps, key=lambda k: sorted(comps[k])[0])]


def a_record(s, who=''):
    """'Found a probate record for George Turner: Probate calendar, 1919' for a source, naming whom it is about."""
    title, typ = s.get('title') or s.get('id'), (s.get('type') or '').strip().lower()
    for_ = (' for ' + who) if who else ''
    if 'photo' in typ: return 'Added a photograph%s: %s' % (for_, title)
    if 'newspaper' in typ: return 'Found a newspaper article%s: %s' % (for_, title)
    if typ:
        return 'Found %s %s %s%s: %s' % ('an' if typ[0] in 'aeiou' else 'a', typ, 'entry' if 'register' in typ else 'record', for_, title)
    return 'Found a record%s: %s' % (for_, title)


def group(changes, snap, new_sources, cfg):
    """Findings from changes: one per research find, not one per field. Returns entries without dates."""
    W = Words(snap)
    pages = cfg.get('_pages') or {}
    entries, used = [], set()

    def take(pred):
        got = [c for c in changes if id(c) not in used and pred(c)]
        used.update(id(c) for c in got)
        return got

    def new_source_of(c):
        for s in list((c.get('new') or {}).get('src') or []) + list(c.get('fresh') or []):
            if s in new_sources: return s
        return None

    new_persons = {c['new']['p'][0] for c in changes if c['op'] == 'add' and c['new']['kind'] == 'person'}

    def finish(type_, cs, headline, persons=None, places=None, source=None, change=None, image=None, image_alt=None, focus=None):
        base = [c.get('new') or c.get('old') for c in cs]
        pids = sorted({p for a in base for p in a['p']} if persons is None else persons)
        pls = sorted({p for a in base for p in a['pl']} if places is None else places)
        src_ids = []
        for c in cs:
            for s in (c.get('new') or {}).get('src') or []:
                if s not in src_ids: src_ids.append(s)
        source = source or (src_ids[0] if src_ids else None)
        sdoc = snap.sources.get(source) or {}
        entries.append({
            'id': entry_id(type_, cs), 'type': type_, 'headline': headline,
            'atoms': sorted({c['key'] for c in cs} | {c['replaces'] for c in cs if c.get('replaces')}),
            'personIds': pids, 'placeIds': pls, 'focus': focus or (pids[0] if pids else None),
            'source': ({'text': sdoc.get('title') or source, 'url': sdoc.get('url') or None} if source else None),
            'confidence': weakest([(c.get('new') or {}).get('conf') for c in cs]), 'change': change or [],
            'image': image, 'imageAlt': image_alt or '',
            'lines': sorted({snap.lines.get(p) for p in pids if snap.lines.get(p)} or {snap.default_line}),
        })

    def media_of(cs):
        for c in cs:
            n = c.get('new')
            if n and n['kind'] in ('photo', 'document'):
                return n['v'].get('thumb') or n['v'].get('file'), n['v'].get('alt') or n['v'].get('caption') or ''
        return None, ''

    # 1. whatever cites a source that is new to the archive is one find about that source
    by_source = {}
    for c in changes:
        s = new_source_of(c) if c['op'] != 'remove' else None
        if s: by_source.setdefault(s, []).append(c)
    def absorb(cs):
        """The new people a source brought, and the links that tie them in, are part of the same find."""
        gp = {p for c in cs for p in c['new']['p']}
        grew = True
        while grew:
            grew = False
            for c in changes:
                if id(c) in used or c['op'] != 'add': continue
                n = c['new']
                if (n['kind'] == 'person' and n['p'][0] in gp) or (n['kind'] in ('parent', 'spouse') and any(p in gp and p in new_persons for p in n['p'])):
                    cs.append(c)
                    used.add(id(c))
                    gp |= set(n['p'])
                    grew = True

    for sid in sorted(by_source):
        cs = by_source[sid]
        used.update(id(c) for c in cs)
        absorb(cs)
        source_finding(W, snap, sid, cs, new_persons, finish, media_of)

    # 2. corrections, grouped by person
    for _, cs in bucket(take(lambda c: c['op'] == 'modify'), lambda c: tuple(c['new']['p'])):
        correction_finding(W, snap, cs, None, finish)

    # 3. new evidence for something already known
    for c in take(lambda c: c['op'] in ('conf', 'evidence')):
        confidence_finding(W, snap, c, finish)

    # 4. new people (joined by new links they are one find), then what is left
    rest = take(lambda c: c['op'] in ('add', 'refine'))
    claimed = set()
    for comp in person_components([c for c in rest if c['new']['kind'] == 'person'], rest):
        cs = [c for c in rest if set(c['new']['p']) & comp and c['new']['kind'] != 'place']
        person_finding(W, snap, comp, cs, finish, media_of)
        claimed.update(id(c) for c in cs)
    rest = [c for c in rest if id(c) not in claimed]
    for c in [c for c in rest if c['new']['kind'] in ('parent', 'spouse')]:
        link_finding(W, snap, c, finish)
        claimed.add(id(c))
    rest = [c for c in rest if id(c) not in claimed]
    for (_, kind), cs in bucket([c for c in rest if c['new']['kind'] in ('photo', 'document')], lambda c: (tuple(c['new']['p']), c['new']['kind'])):
        photo_finding(W, snap, cs, kind, finish)
        claimed.update(id(c) for c in cs)
    rest = [c for c in rest if id(c) not in claimed]
    # a new place that another find already mentions is part of that find (and gives its map link something to point at)
    lone = []
    for c in [c for c in rest if c['new']['kind'] == 'place']:
        pid_ = c['new']['pl'][0]
        elsewhere = {p for e in entries for p in e['placeIds']} | {p for c2 in rest if c2 is not c and c2['new']['kind'] != 'place' for p in c2['new']['pl']}
        if pid_ not in elsewhere: lone.append(c)
        claimed.add(id(c))
    if len(lone) <= PLACES_EACH:
        for c in lone: place_finding(W, snap, c, finish, pages)
    else:       # a pass that adds many places to the map at once is one find, not a page of them
        names = [c['new']['v']['name'] for c in lone]
        shown = human_list(sorted(names)[:3])
        finish('place', lone, 'Added %d places to the family map, including %s.' % (len(lone), shown) if pages.get('map') else
               'Added %d places the family is known to have been, including %s.' % (len(lone), shown),
               persons=[], places=[c['new']['pl'][0] for c in lone], focus=None)
    rest = [c for c in rest if id(c) not in claimed]
    for cs in households(bucket(rest, lambda c: tuple(c['new']['p']))):
        record_finding(W, snap, cs, finish)

    # 5. a source added to the archive that nothing cites
    for sid in sorted(new_sources):
        if sid in by_source or sid not in snap.sources: continue
        if sid in snap.refs['src_public'] or sid in snap.refs['src_private']: continue
        cs = [{'op': 'add', 'key': 'source:' + sid, 'new': {'kind': 'source', 'p': [], 'pl': [], 'v': {}, 'c': '', 'src': [sid], 'conf': None, 'a': ''}}]
        finish('record', cs, 'Added %s to the sources.' % (snap.sources[sid].get('title') or sid), persons=[], places=[], source=sid)
    return entries


def source_finding(W, snap, sid, cs, new_persons, finish, media_of):
    s = snap.sources.get(sid) or {'id': sid, 'title': sid}
    typ = (s.get('type') or '').lower()
    mods = [c for c in cs if c['op'] == 'modify']
    if mods:
        return correction_finding(W, snap, mods, sid, finish, extra=[c for c in cs if c['op'] != 'modify'])
    weight = {}
    for c in cs:
        for p in c['new']['p']:
            weight[p] = weight.get(p, 0) + (2 if c['new']['kind'] in ('birth', 'death', 'residence', 'occupation', 'person') else 1)
    subjects = sorted(weight, key=lambda p: (-weight[p], p))
    img, alt = media_of(cs)
    only_media = all(c['new']['kind'] in ('photo', 'document') for c in cs)
    if only_media:
        who = human_list([W.name(p) for p in subjects[:3]])
        if all(c['new']['kind'] == 'document' for c in cs):
            cap = cs[0]['new']['v'].get('caption') or s.get('title')
            return finish('record', cs, 'Added a document: %s.' % cap, image=img, image_alt=alt, source=sid, focus=subjects[0] if subjects else None)
        return finish('photo', cs, ('Added a photograph of %s.' % who) if who else 'Added a photograph.', image=img, image_alt=alt, source=sid,
                      focus=subjects[0] if subjects else None)
    heads = [p for p in subjects if any(c['new']['kind'] in ('residence', 'occupation') and p in c['new']['p'] for c in cs)] or subjects
    top = heads[:2]
    if len(top) == 2 and snap.sex.get(top[0]) == 'F' and snap.sex.get(top[1]) == 'M': top = top[::-1]     # a couple reads husband first
    lead = top[0] if top else None
    details = []
    occ = next((c['new'] for c in cs if c['new']['kind'] == 'occupation' and c['new']['p'][0] in top), None)
    res = next((c['new'] for c in cs if c['new']['kind'] == 'residence' and c['new']['p'][0] in top), None)
    if occ: details.append('recorded as ' + a_an(lcfirst(occ['v']['title'])))
    if res:
        where = res['v'].get('address') or res['v'].get('place')
        words = [w for w in norm(where).split() if not w.isdigit()]
        if where and not all(w in norm(s.get('title') or '').split() for w in words):
            details.append('living %s %s' % ('at' if res['v'].get('address') else 'in', where))
    kids = sorted({c['new']['v']['child'] for c in cs if c['new']['kind'] == 'parent' and c['new']['v']['parent'] in top and c['new']['v']['child'] in new_persons})
    spouses = [c['new'] for c in cs if c['new']['kind'] == 'spouse' and lead in c['new']['p']]
    house = []
    their = W.pron(lead)[1] if len(top) == 1 and lead else 'their'
    if spouses and [p for p in spouses[0]['p'] if p != lead][0] not in top:
        other = [p for p in spouses[0]['p'] if p != lead][0]
        house.append('%s %s %s' % (their, W.kin(other, 'husband', 'wife', 'partner'), W.name(other)))
    if len(kids) == 1:
        house.append('%s %s %s' % (their, W.kin(kids[0], 'son', 'daughter', 'child'), W.name(kids[0])))
    elif kids:
        house.append('%s children' % count_word(len(kids)))
    if house: details.append('with ' + human_list(house))
    who = human_list([W.name(p) for p in top]) or 'the family'
    if 'census' in typ:
        headline = 'Found %s in the %s%s.' % (who, s.get('title') or sid, (', ' + ', '.join(details)) if details else '')
    else:
        learned = [W.part(c['new']) for c in cs if c['new']['kind'] not in ('person', 'parent', 'spouse', 'photo', 'document', 'place', 'residence', 'occupation')
                   and not (c['new']['kind'] in ('birth', 'death', 'burial') and c['new']['p'][0] in new_persons)]
        newp = [p for p in subjects if p in new_persons]
        extra = []
        if newp and not top_is_new(top, new_persons): extra.append('introduces %s' % human_list([W.name(p) for p in newp[:3]]))
        if learned: extra.append('adds %s' % human_list(learned[:3]))
        headline = a_record(s, who) + ((', ' + ', '.join(details)) if details else '') + (', which %s' % human_list(extra) if extra else '') + '.'
    return finish('person' if top_is_new(top, new_persons) else 'record', cs, headline, source=sid, image=img, image_alt=alt, focus=lead)


def top_is_new(top, new_persons):
    return bool(top) and all(p in new_persons for p in top)


def correction_finding(W, snap, cs, sid, finish, extra=None):
    cs = sorted(cs, key=lambda c: c['key'])
    fixes = [f for c in cs for f in W.fixes(c['old'], c['new'])]
    pids = sorted({p for c in cs for p in c['new']['p']})
    after = (' after finding %s' % ((snap.sources.get(sid) or {}).get('title') or sid)) if sid else ''

    def one(f):
        poss, lab, a, b = f
        return 'Corrected %s%s from %s to %s' % ((poss + ' ') if poss else 'the ', lab, a, b) if not poss else 'Corrected %s %s from %s to %s' % (poss, lab, a, b)
    if len(fixes) == 1:
        poss, lab, a, b = fixes[0]
        headline = ('Corrected %s %s from %s to %s%s.' % (poss, lab, a, b, after)) if poss else ('Corrected the %s from %s to %s%s.' % (lab, a, b, after))
    elif len(pids) == 1:
        parts = ['%s from %s to %s' % (lab, a, b) for _, lab, a, b in fixes[:3]]
        headline = 'Corrected %s details about %s: %s%s.' % (count_word(len(fixes)), W.name(pids[0]), human_list(parts), after)
    else:
        headline = 'Corrected %s details about %s%s.' % (count_word(len(fixes)), human_list([W.name(p) for p in pids[:3]]), after)
    return finish('correction', cs + (extra or []), headline, source=sid,
                  change=[{'field': lab, 'from': a, 'to': b} for _, lab, a, b in fixes], focus=pids[0] if pids else None)


def confidence_finding(W, snap, c, finish):
    n, o = c['new'], c['old']
    now, was = n.get('conf'), o.get('conf')
    better = CONF_RANK.get(now, -1) >= CONF_RANK.get(was, -1)
    if n['kind'] == 'parent':
        child, par = n['v']['child'], n['v']['parent']
        if better:
            h = ('New evidence confirms %s as the %s of %s.' % (W.name(child), W.kin(child, 'son', 'daughter', 'child'), W.name(par))) if now == 'confirmed' \
                else 'New evidence supports the connection between %s and %s.' % (W.name(child), W.name(par))
        else:
            h = 'The link between %s and %s is now treated as %s.' % (W.name(child), W.name(par), now or 'unverified')
        return finish('connection' if better else 'correction', [c], h, focus=child)
    if n['kind'] == 'spouse':
        a, b = n['p']
        h = ('New evidence supports the connection between %s and %s.' % (W.name(a), W.name(b))) if better \
            else 'The marriage of %s and %s is now treated as %s.' % (W.name(a), W.name(b), now or 'unverified')
        return finish('connection' if better else 'correction', [c], h, focus=a)
    p = n['p'][0] if n['p'] else None
    what = W.part(n)
    if better:
        return finish('record', [c], 'New evidence %s %s %s.' % ('confirms' if now == 'confirmed' else 'supports', W.poss(p), what) if p else 'New evidence supports %s.' % what, focus=p)
    return finish('correction', [c], '%s %s is now treated as %s.' % (W.poss(p), what, now or 'unverified'), focus=p)


def person_finding(W, snap, comp, cs, finish, media_of):
    ids = sorted(comp)
    anchors = []
    for c in cs:
        n = c['new']
        if n['kind'] in ('parent', 'spouse'):
            for p in n['p']:
                if p not in comp and p not in anchors: anchors.append(p)
    img, alt = media_of(cs)
    hedge = hedge_word(weakest([c['new'].get('conf') for c in cs if c['new']['kind'] in ('parent', 'spouse')]))
    seed = '|'.join(ids)
    everyone = sorted(set(ids) | set(anchors))
    if len(ids) == 1:
        n = ids[0]
        pre = (hedge + ' ') if hedge else ''
        parents_ = sorted(c['new']['v']['parent'] for c in cs if c['new']['kind'] == 'parent' and c['new']['v']['child'] == n and c['new']['v']['parent'] not in comp)
        kids_ = sorted(c['new']['v']['child'] for c in cs if c['new']['kind'] == 'parent' and c['new']['v']['parent'] == n and c['new']['v']['child'] not in comp)
        sp = [c['new'] for c in cs if c['new']['kind'] == 'spouse' and n in c['new']['p'] and (set(c['new']['p']) - {n}) & set(anchors)]
        rel = ''
        if parents_:
            rel = '%s%s of %s' % (pre, a_an(W.kin(n, 'son', 'daughter', 'child')), human_list([W.name(p) for p in parents_]))
        elif sp:
            o = [p for p in sp[0]['p'] if p != n][0]
            ordinal = {2: 'second ', 3: 'third '}.get(sp[0]['v'].get('order')) if sp[0]['v'].get('of') == o else ''
            rel = '%s%s of %s' % (pre, a_an((ordinal or '') + W.kin(n, 'husband', 'wife', 'partner')), W.name(o))
        elif kids_:
            rel = '%s%s of %s' % (pre, a_an(W.kin(n, 'father', 'mother', 'parent')), human_list([W.name(p) for p in kids_]))
        birth = next((c['new'] for c in cs if c['new']['kind'] == 'birth' and c['new']['p'][0] == n), None)
        tail = ''
        if birth:
            when = date_text(birth['v'].get('date'), birth['v'].get('display'))
            bits = ([('born ' + when)] if when else []) + ([('in ' + birth['v']['place'])] if birth['v'].get('place') else [])
            tail = (', ' + ' '.join(bits)) if bits else ''
        h = '%s %s%s%s.' % (pick(seed, ['Identified', 'Added', 'Found']), W.name(n), (', ' + rel) if rel else '', tail)
        return finish('person', cs, h, persons=everyone, image=img, image_alt=alt, focus=n)
    names = [W.name(p) for p in ids]
    shown = human_list(names) if len(names) <= 4 else ', '.join(names[:4]) + ' and %d more' % (len(names) - 4)
    kids_of = {}
    for c in cs:
        n = c['new']
        if n['kind'] == 'parent' and n['v']['child'] in comp and n['v']['parent'] not in comp:
            kids_of.setdefault(n['v']['parent'], set()).add(n['v']['child'])
    if kids_of and set().union(*kids_of.values()) == set(ids):
        h = '%s %s children of %s: %s.' % (pick(seed, ['Identified', 'Found']), count_word(len(ids)), human_list([W.name(p) for p in sorted(kids_of)]), shown)
    else:
        link = (' linked to %s' % human_list([W.name(p) for p in anchors[:2]])) if anchors else ''
        h = '%s %s %s%s: %s.' % (pick(seed, ['Identified', 'Added']), count_word(len(ids)), 'new relatives' if anchors else 'new people', link, shown)
    return finish('person', cs, h, persons=everyone, image=img, image_alt=alt, focus=ids[0])


def link_finding(W, snap, c, finish):
    n = c['new']
    hedge = hedge_word(n.get('conf'))
    adj = {'probably': 'probable', 'possibly': 'possible'}.get(hedge)
    if n['kind'] == 'parent':
        child, par = n['v']['child'], n['v']['parent']
        rel = '%s %s' % (W.kin(par, 'father', 'mother', 'parent'), W.name(par))
        h = ('Found a %s link between %s and %s %s.' % (adj, W.name(child), W.pron(child)[1], rel)) if adj \
            else '%s %s to %s %s.' % (pick(c['key'], ['Linked', 'Connected']), W.name(child), W.pron(child)[1], rel)
        return finish('connection', [c], h, focus=child)
    a, b = n['p']
    v = n['v']
    what = 'partnership' if v.get('rel') == 'partner' else 'marriage'
    when = date_text(v.get('date'), v.get('display'))
    h = ('Found a %s %s between %s and %s.' % (adj, what, W.name(a), W.name(b))) if adj \
        else 'Established the %s of %s and %s%s.' % (what, W.name(a), W.name(b), (', ' + when) if when else '')
    return finish('connection', [c], h, focus=a)


def photo_finding(W, snap, cs, kind, finish):
    p = cs[0]['new']['p'][0]
    n, first, nm = len(cs), cs[0]['new']['v'], W.name(p)
    img, alt = first.get('thumb') or first.get('file'), first.get('alt') or first.get('caption') or ''
    cap = (first.get('caption') or '').strip()
    if kind == 'document':
        h = 'Added a document about %s%s.' % (nm, (': ' + cap) if cap and n == 1 else '') if n == 1 else 'Added %s documents about %s.' % (count_word(n), nm)
        return finish('record', cs, h, image=img, image_alt=alt, focus=p)
    if cap.lower().startswith(nm.lower()): cap = cap[len(nm):].lstrip(' ,;:.-')
    if n > 1:
        h = 'Added %s photographs of %s.' % (count_word(n), nm)
    elif first.get('type') == 'gravestone':
        h = 'Added a photograph of the gravestone of %s%s.' % (nm, (', ' + cap) if cap else '')
    else:
        h = 'Added %s of %s%s.' % ('a portrait' if first.get('type') == 'portrait' else 'a photograph', nm, (', ' + cap) if cap else '')
    return finish('photo', cs, h, image=img, image_alt=alt, focus=p)


def place_finding(W, snap, c, finish, pages):
    v = c['new']['v']
    where = (' in %s' % v['country']) if v.get('country') else ''
    h = 'Added %s%s %s.' % (v['name'], where, 'to the family map' if pages.get('map') else 'to the places the family is known to have been')
    return finish('place', [c], h, persons=[], places=c['new']['pl'], focus=None)


HOUSEHOLD_MAX = 4      # people who were each given exactly the same new details in one publication are one find, up to this many


def households(buckets):
    """[[change]] from [(people, [change])]: people who were each given the very same details (the couple at one address,
    a family on one census page) share one find instead of one each."""
    out, shared = [], {}
    for people, cs in buckets:
        shape = tuple(sorted((c['new']['kind'], json.dumps(c['new']['v'], sort_keys=True)) for c in cs))
        if len(people) == 1 and all(c['op'] == 'add' for c in cs): shared.setdefault(shape, []).append(cs)
        else: out.append(cs)
    for group in shared.values():
        for i in range(0, len(group), HOUSEHOLD_MAX):
            out.append([c for cs in group[i:i + HOUSEHOLD_MAX] for c in cs])
    return out


def record_finding(W, snap, cs, finish):
    cs = sorted(cs, key=lambda c: c['key'])
    parts = []
    for c in cs:
        part = W.part(c['new'])
        if part not in parts: parts.append(part)       # two people with the same new home give one phrase, not two
    p = cs[0]['new']['p'][0] if cs[0]['new']['p'] else None
    if not p:
        return finish('record', cs, 'Added %s.' % human_list(parts), focus=None)
    pids = sorted({q for c in cs for q in c['new']['p']})
    # the people in the order the data lists them first: the one with most to say leads
    pids = sorted(pids, key=lambda q: (-sum(1 for c in cs if q in c['new']['p']), 0 if snap.sex.get(q) == 'M' else 1, q))      # a couple reads husband first
    names = human_list([W.name(q) for q in pids[:3]]) + ((' and %d more' % (len(pids) - 3)) if len(pids) > 3 else '')
    if len(parts) > 1 or (len(cs) > 1 and len(pids) == 1):
        shown = human_list(parts) if len(parts) <= 4 else ', '.join(parts[:4]) + ' and %d more' % (len(parts) - 4)
        return finish('record', cs, 'Added details about %s: %s.' % (human_list([W.name(q) for q in pids[:2]]), shown), focus=p)
    n, v, k = cs[0]['new'], cs[0]['new']['v'], cs[0]['new']['kind']
    if len(pids) > 1:       # several people, one new detail between them
        if k == 'residence':
            h = 'Found where %s lived: %s%s.' % (names, v.get('address') or v.get('place'), (' (%s)' % v['years']) if v.get('years') else '')
        else:
            h = 'Added %s for %s.' % (parts[0], names)
        return finish('record', cs, h, focus=p)
    if k in ('birth', 'death', 'burial'):
        when, where = date_text(v.get('date'), v.get('display')), v.get('place')
        if cs[0]['op'] == 'refine':
            h = 'Found the exact date of %s %s: %s.' % (W.poss(p), k, when)
        else:
            h = 'Added %s %s: %s.' % (W.poss(p), k, ' in '.join(x for x in [when, where] if x))
    elif k == 'residence':
        h = 'Found where %s lived: %s%s.' % (W.name(p), v.get('address') or v.get('place'), (' (%s)' % v['years']) if v.get('years') else '')
    elif k == 'occupation':
        h = 'Found %s occupation: %s%s%s.' % (W.poss(p), lcfirst(v['title']), (' with ' + v['employer']) if v.get('employer') else '', (', %s' % v['years']) if v.get('years') else '')
    elif k == 'voyage':
        h = 'Traced %s voyage%s%s.' % (W.poss(p), (' on the ' + v['ship']) if v.get('ship') else '', (' from %s to %s' % (v['from'], v['to'])) if v.get('from') and v.get('to') else '')
    elif k == 'immigration':
        h = 'Added %s immigration record%s.' % (W.poss(p), (' via ' + v['port']) if v.get('port') else '')
    elif k == 'fact':
        h = 'Added to %s record: %s%s.' % (W.poss(p), v['label'], (', ' + v['value']) if v.get('value') else '')
    elif k == 'event':
        h = 'Added to %s story: %s.' % (W.poss(p), v['label'])
    else:
        h = 'Added %s for %s.' % (W.part(n), W.name(p))
    return finish('record', cs, h, focus=p)


# ------------------------------------------------------------------ the history: keeping findings between publications
def apply_status(entries, changes, new_entries, day):
    """A published finding whose claim was later corrected or removed is marked, never left standing as plain fact."""
    by_key = {}
    for e in entries:
        for k in e.get('atoms') or []: by_key.setdefault(k, []).append(e)
    mine = {e['id'] for e in new_entries}
    for c in changes:
        if c['op'] not in ('modify', 'remove'): continue
        old_key = c.get('replaces') or c['key']
        for e in by_key.get(old_key, []):
            if e['id'] in mine: continue
            if c['op'] == 'modify':
                e['status'], e['statusDate'] = 'corrected', day
                later = next((n for n in new_entries if c['key'] in n['atoms']), None)
                if later: e['correctedBy'] = later['id']
            else:
                gone = set(e.get('gone') or []) | {old_key}
                e['gone'] = sorted(gone)
                e['status'] = 'withdrawn' if gone >= set(e['atoms']) else 'revised'
                e['statusDate'] = day


def text_fields(e):
    out = [e.get('headline'), e.get('changeNote'), (e.get('source') or {}).get('text'), e.get('foundBy')]
    out += [x for ch in e.get('change') or [] for x in (ch.get('field'), ch.get('from'), ch.get('to'))]
    return ' '.join(str(x) for x in out if x)


def public_ok(e, snap):
    """Is this finding allowed on a public page now? Re-asked on every build, so a person marked living later
    takes their old findings with them."""
    for p in e.get('personIds') or []:
        if p in snap.withheld or p not in snap.names: return False
    text = ' ' + norm(text_fields(e)) + ' '
    if any((' %s ' % n) in text for n in snap.withheld_names): return False
    return True


def overlay(entries, snap, now):
    """Researchers' notes laid over the generated findings. Called on every build with the current data, so a
    changed note takes effect and a removed one lets the generated wording back."""
    day = today(now)
    # take last build's overlay off first (it kept what it replaced under "auto")
    for e in entries:
        base = e.pop('auto', None)
        if base: e.update(base)
    by_atom = {}
    for e in sorted(entries, key=lambda e: (e.get('found') or '', e['id'])):
        if e.get('origin') == 'manual': continue
        for k in e.get('atoms') or []: by_atom.setdefault(k, e)
    live_manual = set()
    for m in snap.manual:
        d = m['d']
        covers = [k for k in m['covers'] if k in snap.atoms or k in by_atom]
        pids = sorted({p for k in covers for p in (snap.atoms.get(k) or {}).get('p', [])} | set(m.get('people') or []))
        pls = sorted({p for k in covers for p in (snap.atoms.get(k) or {}).get('pl', [])} | set(m.get('places') or []))
        if any(p in snap.withheld or p not in snap.names for p in pids): continue
        target = next((by_atom[k] for k in covers if k in by_atom), None)
        if target is None:
            if not covers and not pids and not pls: continue     # nothing to hang a find on
            mid = 'm-' + sha('|'.join(sorted(covers)) or d.get('id') or json.dumps(d, sort_keys=True))
            target = next((e for e in entries if e['id'] == mid), None)
            if target is None:
                target = {'id': mid, 'origin': 'manual', 'type': infer_type(covers, snap), 'headline': '', 'atoms': sorted(covers), 'personIds': pids,
                          'placeIds': pls, 'focus': pids[0] if pids else None, 'source': None, 'confidence': None, 'change': [], 'image': None,
                          'imageAlt': '', 'found': day, 'foundIs': 'published', 'published': now, 'status': 'current',
                          'lines': sorted({snap.lines.get(p) for p in pids if snap.lines.get(p)} or {snap.default_line})}
                cs = [{'op': 'add', 'key': k, 'new': snap.atoms[k]} for k in covers if k in snap.atoms]
                gen = group(cs, snap, set(), {'_pages': {}}) if cs else []
                if gen:
                    for f in ('headline', 'type', 'source', 'confidence', 'image', 'imageAlt'): target[f] = gen[0][f]
                entries.append(target)
        live_manual.add(target['id'])
        fields = {}
        if (d.get('headline') or '').strip(): fields['headline'] = d['headline'].strip()
        if d.get('findType') in TYPES: fields['type'] = d['findType']
        if d.get('found'): fields['found'], fields['foundIs'] = d['found'], 'researcher'
        if (d.get('foundBy') or '').strip(): fields['foundBy'] = d['foundBy'].strip()
        src = d.get('source')
        if isinstance(src, str) and src.strip(): fields['source'] = {'text': src.strip(), 'url': None}
        elif isinstance(src, dict) and src.get('text'): fields['source'] = {'text': src['text'], 'url': src.get('url') or None}
        if d.get('confidence') in CONF_RANK: fields['confidence'] = d['confidence']
        if d.get('image'): fields['image'] = d['image']
        if d.get('imageAlt'): fields['imageAlt'] = d['imageAlt']
        if (d.get('changeNote') or '').strip(): fields['changeNote'] = d['changeNote'].strip()
        if fields:
            target['auto'] = {**target.get('auto', {}), **{k: target.get(k) for k in fields if k not in target.get('auto', {})}}
            target.update(fields)
    entries[:] = [e for e in entries if e.get('origin') != 'manual' or e['id'] in live_manual]
    return entries


def infer_type(covers, snap):
    kinds = {(snap.atoms.get(k) or {}).get('kind') or k.split(':')[0] for k in covers}
    for kind, t in (('person', 'person'), ('photo', 'photo'), ('place', 'place'), ('parent', 'connection'), ('spouse', 'connection')):
        if kind in kinds: return t
    return 'record'


def update(prev, snap, now, engine_version, cfg):
    """One publication. prev: the state published last time, or None. Returns (state, report)."""
    report = {'mode': 'initial', 'new': 0, 'notes': []}
    day = today(now)
    atoms = snap.atoms
    withheld_now = {hid(p) for p in snap.withheld}
    ok = isinstance(prev, dict) and prev.get('schema') == STATE_SCHEMA
    if prev and not ok:
        raise ValueError('The previous discovery history (discoveries/state.json) is in a format this engine does not read (schema %r). '
                         'Use a newer engine, or remove the file to start a new baseline.' % (prev.get('schema') if isinstance(prev, dict) else prev))
    entries = []
    if ok:
        entries = json.loads(json.dumps(prev.get('entries') or []))
        if prev.get('atomSchema') != ATOM_SCHEMA:
            report.update(mode='rebaselined')
            report['notes'].append('The way claims are read changed since the last publication, so this one starts a new baseline; findings so far are kept.')
        else:
            prev_atoms = prev.get('atoms') or {}
            was_withheld = set(prev.get('withheld') or [])
            absorbed = {p for p in snap.persons if hid(p) in was_withheld}
            masked = set(snap.withheld)
            shown_now = absorbed & snap.off_tree
            absorbed_places = {pl for b in atoms.values() if set(b['p']) & shown_now for pl in b['pl']} if shown_now else frozenset()
            changes = diff(prev_atoms, atoms, absorbed, masked, absorbed_places)
            new_sources = set(snap.sources) - set(prev.get('sources') or [])
            new_entries = group(changes, snap, new_sources, cfg) if changes or new_sources else []
            have = {e['id']: e for e in entries}
            fresh = []
            for e in new_entries:
                old = have.get(e['id'])
                if old:
                    if old.get('status') and old.get('status') != 'current':
                        for f in ('status', 'statusDate', 'correctedBy', 'gone'): old.pop(f, None)
                    continue
                e['found'], e['foundIs'], e['published'], e['status'] = day, 'published', now, 'current'
                fresh.append(e)
            apply_status(entries, changes, fresh, day)
            entries += fresh
            report.update(mode='unchanged' if not changes and not new_sources else 'updated', new=len(fresh))
    entries = [e for e in entries if public_ok(e, snap)]
    entries = overlay(entries, snap, now)
    entries = [e for e in entries if public_ok(e, snap)]
    before = {e['id'] for e in (prev.get('entries') or [])} if ok else set()
    report['new'] = sum(1 for e in entries if e['id'] not in before)       # includes researchers' own notes that stand alone
    for e in entries:
        e.setdefault('status', 'current')
    rank = {'person': 0, 'connection': 1, 'record': 2, 'correction': 3, 'place': 4, 'photo': 5}
    entries.sort(key=lambda e: (rank.get(e.get('type'), 9), e.get('headline') or '', e['id']))      # within a day: people first, then by wording
    entries.sort(key=lambda e: e.get('found') or '', reverse=True)     # newest day first (the sort is stable, so the order above holds)
    since = (prev.get('since') if ok else None) or day
    state = {'schema': STATE_SCHEMA, 'atomSchema': ATOM_SCHEMA, 'engine': engine_version, 'site': (cfg.get('site') or {}).get('name'),
             'since': since, 'published': now, 'sources': sorted(snap.sources), 'withheld': sorted(withheld_now),
             'atoms': {k: atoms[k] for k in sorted(atoms)}, 'entries': entries}
    return state, report


def off_tree(e, snap):
    """Is this find about someone the tree leaves out (a hidden region shown by timeline.showRegions), or a place only they
    have to do with? Such a find is shown with no link to the tree or the map, because there is nothing there to open."""
    pids, pls = e.get('personIds') or [], e.get('placeIds') or []
    focus = e.get('focus') if e.get('focus') in pids else (pids[0] if pids else None)
    if focus: return focus in snap.off_tree
    return bool(pls) and all(p in snap.off_places for p in pls)


PUBLIC_FIELDS = ('id', 'found', 'foundIs', 'published', 'type', 'headline', 'foundBy', 'source', 'confidence', 'image', 'imageAlt',
                 'changeNote', 'status', 'statusDate', 'change', 'lines', 'personIds', 'placeIds', 'focus')


def public_history(state, snap):
    """The slim, public view of the history: what the page shows and nothing that only the engine needs."""
    out = []
    for e in state['entries']:
        if not public_ok(e, snap): continue
        item = {k: e[k] for k in PUBLIC_FIELDS if k in e and e[k] not in (None, '', [])} | {'id': e['id']}
        if (snap.off_tree or snap.off_places) and off_tree(e, snap): item['offTree'] = True      # only on a site that shows such a region
        out.append(item)
    return {'schema': 1, 'site': state.get('site'), 'since': state.get('since'), 'lines': snap.line_labels, 'entries': out}
