"""Stuart's index: the knowledge base he answers from, built from a site's data and story pages.

Called by build_site.py:  build_archive(site_dir, cfg, out_dir) -> 'archive/kb-<hash>.json'

What goes in:
  * data/people.json, data/places.json and data/sources.json, the site's source of truth;
  * the text of the story pages listed in stuart.pages in site.config.json.

What is left out, on purpose:
  * people in a hidden region (tree.hiddenRegions), as on the tree and the map; a suspected relative kept
    beside someone (tree.suspectedRelatives) stays, with no parents and a note of who they are shown beside;
  * pages not listed in stuart.pages, and anything not linked from a page.

Nothing is inferred here. Dates are copied as the site writes them, with a machine-readable range next
to them so ages can be worked out without pretending to more precision than the record has.
"""
import hashlib, html, json, os, re, sys
from html.parser import HTMLParser

SCHEMA = 2
ROOT = None     # the site folder, set by build_archive
CFG = {}        # the site settings, set by build_archive

def load(name):
    with open(os.path.join(ROOT, CFG.get('data', {}).get('dir', 'data'), name), encoding='utf-8') as f:
        return json.load(f)


def clean(t):
    # " , " is what is left in some page text where a dash used to be
    return re.sub(r'\s+,', ',', re.sub(r'\s+', ' ', html.unescape(t or ''))).strip()


# ------------------------------------------------------------------ dates
MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                           'september', 'october', 'november', 'december'])}
# the site's words for a registration quarter
SEASON = {'early': (1, 3), 'spring': (4, 6), 'summer': (7, 9), 'late': (10, 12)}
QUARTER = {'march': (1, 3), 'june': (4, 6), 'september': (7, 9), 'december': (10, 12)}
DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def ymd(y, m=1, d=1):
    return '%04d-%02d-%02d' % (y, m, d)


def month_end(y, m):
    leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    return DAYS[m - 1] if m != 2 else (29 if leap else 28)


def norm_date(date, display):
    """A range for a date as the site gives it: {from, to, precision, qualifier}. None if there is no date."""
    disp = (display or '').lower()
    q = None
    if re.search(r'\bprobably\b', disp): q = 'probably'
    if re.search(r'\babout\b', disp): q = 'about'
    if re.search(r'^\s*(buried|baptised)\b', disp): q = 'on or before'
    if re.search(r'\bbefore\b', disp):
        m = re.search(r'before\s+(?:(\d{1,2})\s+)?([a-z]+)?\s*(\d{4})', disp)
        if m:
            y = int(m.group(3)); mo = MONTHS.get(m.group(2) or '', 1); d = int(m.group(1) or 1)
            return {'from': None, 'to': ymd(y, mo, d), 'precision': 'before', 'qualifier': 'before'}
    if date and re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        return {'from': date, 'to': date, 'precision': 'day', 'qualifier': q}
    if date and re.fullmatch(r'\d{4}-\d{2}', date):
        y, m = int(date[:4]), int(date[5:7])
        return {'from': ymd(y, m), 'to': ymd(y, m, month_end(y, m)), 'precision': 'month', 'qualifier': q}
    # a year, or nothing: read the display for a range, a quarter or a season
    rng = re.search(r'(\d{4})\s+(?:to|and)\s+(\d{4})', disp)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        return {'from': ymd(a), 'to': ymd(b, 12, 31), 'precision': 'range', 'qualifier': q or 'about'}
    m = re.search(r'\b(early|spring|summer|late)\s+(\d{4})', disp)
    if m:
        y = int(m.group(2)); a, b = SEASON[m.group(1)]
        return {'from': ymd(y, a), 'to': ymd(y, b, month_end(y, b)), 'precision': 'quarter', 'qualifier': q}
    m = re.search(r'\b(march|june|september|december)\s+quarter\s+(\d{4})', disp)
    if m:
        y = int(m.group(2)); a, b = QUARTER[m.group(1)]
        return {'from': ymd(y, a), 'to': ymd(y, b, month_end(y, b)), 'precision': 'quarter', 'qualifier': q}
    y = None
    if date and re.fullmatch(r'\d{4}', date): y = int(date)
    else:
        m = re.search(r'\b(1[5-9]\d\d|20\d\d)\b', disp)
        if m: y = int(m.group(1))
    if y is None: return None
    if q == 'about':
        return {'from': ymd(y - 2), 'to': ymd(y + 2, 12, 31), 'precision': 'about', 'qualifier': 'about'}
    return {'from': ymd(y), 'to': ymd(y, 12, 31), 'precision': 'year', 'qualifier': q}


def stated_age(display):
    m = re.search(r'\baged\s+(\d{1,3})\b', display or '')
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------ names
# common short forms of given names; a site can add its own in stuart.nicknames
NICK = {'reginald': ['Reg'], 'robert': ['Bob', 'Bert'], 'herbert': ['Herb', 'Bert'], 'patricia': ['Pat'], 'ronald': ['Ron'],
        'sebastian': ['Seb'], 'william': ['Will', 'Bill'], 'frances': ['Frank'], 'francis': ['Frank'], 'henry': ['Harry'],
        'elizabeth': ['Liz', 'Lizzie'], 'edward': ['Ted', 'Eddie'], 'sidney': ['Sid'], 'frederick': ['Fred'], 'charles': ['Charlie'],
        'eileen': ['Babs'], 'alexander': ['Alex'], 'lilian': ['Lil'], 'rosina': ['Rose', 'Rosie'], 'horatio': ['Horace']}
KIN_TITLE = re.compile(r'^(?:called\s+)?((?:Grandma|Grandpa|Granny|Grandad|Nan|Auntie|Aunt|Uncle)\s+[A-Z][a-z]+)')


def aliases_for(p):
    """Names a visitor might use for this person: the site's own spellings and nicknames, nothing invented."""
    out = []
    def add(a, kind):
        a = clean(a).strip('"').strip()
        if a and len(a) > 1 and all(a.lower() != x['text'].lower() for x in out):
            out.append({'text': a, 'kind': kind})
    given = (p.get('givenNames') or '').split()
    sn = p.get('surname') or ''
    add(p.get('displayName'), 'display')
    if given and sn:
        add(' '.join(given) + ' ' + sn, 'full')
        add(given[0] + ' ' + sn, 'first')
    for v in p.get('nameVariants') or []:
        add(v.get('name'), 'variant')
    dis = clean(p.get('disambiguator'))
    for seg in [s.strip() for s in re.split(r'[,;(]', dis)]:
        m = KIN_TITLE.match(seg)
        if m: add(m.group(1), 'nickname')
        m = re.match(r'^called\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)$', seg)
        if m: add(m.group(1), 'nickname')
        # "Reg, Pat's father": a short form of one of the given names
        if re.fullmatch(r'[A-Z][a-z]{1,8}', seg) and any(seg in NICK.get(g.lower(), []) for g in given):
            add(seg, 'nickname')
    m = re.search(r'\b(?:nee|née)\s+([A-Z][A-Za-z\-]+)', dis)
    if m and given:
        add(given[0] + ' ' + m.group(1), 'maiden')
        add(' '.join(given) + ' ' + m.group(1), 'maiden')
    return out


# ------------------------------------------------------------------ html pages
SKIP_TAGS = {'nav', 'script', 'style', 'button', 'footer', 'noscript', 'svg', 'form', 'select', 'template', 'head'}
# page furniture that is not part of the story; a site adds its own in stuart.skipClasses
SKIP_CLASSES = {'whats-new', 'home-tour', 'gmap', 'lightbox-overlay', 'hero-actions', 'nav-links', 'nav-inner', 'lightbox-main',
                'tour', 'meet-pill', 'color-toggle-btn', 'page-link-arrow', 'hero-pair', 'home-ask'}
BLOCKS = {'p', 'li', 'figcaption', 'td', 'th', 'blockquote', 'dd', 'dt', 'h1', 'h2', 'h3', 'h4', 'h5', 'caption'}
VOID = {'img', 'br', 'hr', 'meta', 'link', 'input', 'source', 'area', 'col', 'embed', 'wbr'}


# Places outside the home region carry no country in places.json, so work it out from the coordinates (boxes are
# rough but a family's places abroad are few and far apart). "Who went to South Africa?" then finds Cape Town,
# Bellville and Port Elizabeth as well as places whose names happen to say South Africa. A place can also say
# its country itself ("country" in places.json), which wins.
COUNTRY_BOXES = [
    ('South Africa', -35.5, -21.5, 16.0, 33.5), ('Egypt', 21.5, 32.0, 24.5, 37.5), ('Canada', 41.5, 84.0, -141.5, -52.0),
    ('Korea', 33.0, 43.5, 124.0, 131.5), ('Ireland', 51.3, 55.5, -10.7, -5.9), ('France', 42.3, 51.2, -5.2, 8.3),
    ('Sri Lanka', 5.8, 9.9, 79.5, 81.9), ('India', 6.5, 35.7, 68.0, 97.5), ('Australia', -44.0, -10.0, 112.0, 154.0),
    ('New Zealand', -47.5, -34.0, 166.0, 179.0), ('United States', 24.5, 49.5, -125.0, -66.9),
    ('Italy', 36.6, 47.1, 6.6, 18.6), ('Germany', 47.3, 55.1, 5.9, 15.0),
]


def in_home(pl):
    v = pl.get('inHomeRegion')
    return pl.get('inEngland') if v is None else v


def country_of(pl):
    if pl.get('country'): return pl['country']
    if in_home(pl): return CFG.get('stuart', {}).get('homeCountry') or None
    lat, lng = pl.get('lat'), pl.get('lng')
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        for name, s, n, w, e in COUNTRY_BOXES:
            if s <= lat <= n and w <= lng <= e: return name
    text = ' '.join(str(pl.get(k) or '') for k in ('name', 'address', 'historicName'))
    for name, *_ in COUNTRY_BOXES:
        if name.lower() in text.lower(): return name
    return None


class PageText(HTMLParser):
    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.stack = []          # (tag, skip, id, classes)
        self.blocks = []         # {kind, text, heading, anchor, level}
        self.media = []          # photographs and record images with their captions
        self.buf = None
        self.heading = ''
        self.anchor = ''
        self.title = ''
        self.in_title = False
        self.description = ''
        self.last_id = ''
        self.figure = None
        self.links = []
        self.in_a = 0
        self.link_text = []      # text inside links in the current block, to spot link-only list items

    def skipping(self):
        return any(s[1] for s in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag == 'meta' and a.get('name') == 'description': self.description = clean(a.get('content'))
        classes = set((a.get('class') or '').split())
        skip = tag in SKIP_TAGS or bool(classes & SKIP_CLASSES) or a.get('aria-hidden') == 'true' or 'hidden' in a
        if a.get('id') and not skip and not self.skipping(): self.last_id = a['id']
        if tag == 'img' and not self.skipping() and not skip:
            src = a.get('src') or ''
            cap = clean(a.get('data-caption') or '')
            alt = clean(a.get('alt') or '')
            if src and not src.startswith('data:') and (cap or alt):
                rec = {'file': src, 'caption': cap, 'alt': alt, 'heading': self.heading, 'anchor': self.anchor or self.last_id,
                       'kind': 'record' if '/records/' in src else 'photo'}
                if self.figure is not None: self.figure['imgs'].append(rec)
                else: self.media.append(rec)
        if tag == 'a' and self.buf is not None and a.get('href'):
            self.links.append(a['href'])
        if tag == 'a' and self.buf is not None: self.in_a += 1
        if tag == 'br' and self.buf is not None: self.buf.append(' ')
        if tag in VOID: return
        if tag == 'figure' and not skip and not self.skipping():
            self.figure = {'imgs': [], 'caption': '', 'href': None, 'record': 'record' in classes}
        self.stack.append((tag, skip, a.get('id'), classes))
        if tag in BLOCKS and not self.skipping():
            self.buf = []
            self.links = []
            self.link_text = []

    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag == 'a' and self.in_a: self.in_a -= 1
        if tag in VOID: return
        # pop to the matching tag (tolerates small markup slips)
        idx = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag: idx = i; break
        if idx is None: return
        was_skipping = self.skipping()
        el = self.stack[idx]
        del self.stack[idx:]
        if tag in BLOCKS and self.buf is not None and not was_skipping:
            text = clean(''.join(self.buf))
            self.buf = None
            if not text: return
            if tag in ('h1', 'h2', 'h3', 'h4', 'h5'):
                self.heading = text
                self.anchor = el[2] or self.anchor
                self.blocks.append({'kind': 'heading', 'level': int(tag[1]), 'text': text, 'anchor': self.anchor})
            elif tag == 'li' and clean(''.join(self.link_text)) == text:
                pass  # a list item that is only a link ("Andrews, Stacey and Walter") is a signpost to another page
            elif tag == 'figcaption' and self.figure is not None:
                self.figure['caption'] = re.sub(r'\s*View the original\.?$', '', text)
                self.figure['href'] = next((h for h in self.links if h.startswith('http')), None)
            else:
                self.blocks.append({'kind': 'text', 'text': text, 'heading': self.heading, 'anchor': self.anchor,
                                    'links': [h for h in self.links if h.startswith('http')]})
        if tag == 'figure' and self.figure is not None:
            for img in self.figure['imgs']:
                img['caption'] = img['caption'] or self.figure['caption']
                img['original'] = self.figure['href']
                if self.figure['record']: img['kind'] = 'record'
                self.media.append(img)
            self.figure = None

    def handle_data(self, data):
        if self.in_title: self.title += data
        if self.buf is not None and not self.skipping():
            self.buf.append(data)
            if self.in_a: self.link_text.append(data)


def read_page(page):
    with open(os.path.join(ROOT, page), encoding='utf-8') as f:
        src = f.read()
    p = PageText(page)
    p.feed(src)
    title = clean(p.title).split('|')[0].split(' , ')[0].strip()
    h1 = next((b['text'] for b in p.blocks if b['kind'] == 'heading' and b['level'] == 1), title)
    return title or h1, h1, p.blocks, p.media, p.description


def chunk_page(page, title, blocks, limit=900):
    """Paragraphs grouped under their heading, in pieces of about `limit` characters, never splitting a paragraph."""
    chunks, cur = [], None
    def flush():
        if cur and cur['parts']:
            # a short label paragraph ("FitzMaurice, Falcke, Spencer and Bennett") gets a full stop, so that it does
            # not run into the next paragraph as one sentence
            text = ' '.join(x if re.search(r'[.!?:;)\]"\u201d\u2019]$', x) else x + '.' for x in cur['parts'])
            n = sum(1 for c in chunks if c['anchor'] == cur['anchor']) + 1
            chunks.append({'id': 'pg:%s#%s%s' % (page[:-5], cur['anchor'] or 'top', '' if n == 1 else '-' + str(n)), 'type': 'section',
                           'page': page, 'pageTitle': title, 'heading': cur['heading'], 'anchor': cur['anchor'],
                           'url': page + ('#' + cur['anchor'] if cur['anchor'] else ''), 'text': text, 'links': cur['links']})
    for b in blocks:
        if b['kind'] == 'heading':
            flush(); cur = None; continue
        if cur is None or len(' '.join(cur['parts'])) + len(b['text']) > limit:
            flush(); cur = {'heading': b['heading'] or title, 'anchor': b['anchor'], 'parts': [], 'links': []}
        cur['parts'].append(b['text']); cur['links'] += b.get('links') or []
    flush()
    return chunks


# ------------------------------------------------------------------ build
def strip_footnotes(t):
    """The stories cite sources as [^id]; keep the ids and give back plain text."""
    ids = re.findall(r'\[\^([a-z0-9-]+)\]', t or '')
    return re.sub(r'\[\^[a-z0-9-]+\]', '', t or '').replace(' .', '.').strip(), ids


def build():
    st = CFG.get('stuart', {}) or {}
    tree = CFG.get('tree', {}) or {}
    pages_cfg = CFG.get('_pages', {})
    TREEP, MAPP, HOMEP = pages_cfg.get('tree') or 'family-tree.html', pages_cfg.get('map') or 'map.html', pages_cfg.get('home') or 'index.html'
    PAGES = [p for p in st.get('pages') or [HOMEP] if os.path.exists(os.path.join(ROOT, p))]
    hidden = set(tree.get('hiddenRegions') or [])
    suspected = tree.get('suspectedRelatives') or {}
    for k, v in (st.get('nicknames') or {}).items():
        NICK[k.lower()] = sorted(set(NICK.get(k.lower(), []) + list(v)))
    SKIP_CLASSES.update(st.get('skipClasses') or [])
    pdoc, pldoc, sdoc = load('people.json'), load('places.json') if os.path.exists(os.path.join(ROOT, CFG.get('data', {}).get('dir', 'data'), 'places.json')) else {'places': []}, load('sources.json')
    raw = {p['id']: p for p in pdoc['people']}
    keep = {i for i, p in raw.items() if p.get('region') not in hidden or i in suspected}
    sources = {s['id']: s for s in sdoc['sources']}
    places = {p['id']: p for p in pldoc['places']}
    used_sources, used_places = set(), set()

    def src(ids):
        ids = [i for i in (ids or []) if i in sources]
        used_sources.update(ids)
        return ids

    def place(pid):
        if pid and pid in places: used_places.add(pid); return pid
        return None

    def fact(o, extra=None):
        if not o: return None
        r = {'display': clean(o.get('display')), 'date': o.get('date'), 'range': norm_date(o.get('date'), o.get('display')),
             'place': clean(o.get('place')) or None, 'placeId': place(o.get('placeId')), 'sources': src(o.get('sourceIds')),
             'confidence': o.get('confidence'), 'note': clean(o.get('note')) or None}
        age = stated_age(o.get('display')) or stated_age(o.get('note'))
        if age is not None: r['statedAge'] = age
        if extra: r.update(extra)
        return r

    people = []
    for pid in [p['id'] for p in pdoc['people'] if p['id'] in keep]:
        p = raw[pid]
        rel = {
            'parents': [x for x in p.get('parents') or [] if x in keep],
            'children': [x for x in p.get('children') or [] if x in keep],
            'spouses': [{'id': s['id'], 'order': s.get('order'), 'relation': s.get('relation') or 'spouse',
                         'display': clean(s.get('marriageDisplay')) or None, 'date': s.get('marriageDate'),
                         'range': norm_date(s.get('marriageDate'), s.get('marriageDisplay')), 'place': clean(s.get('place')) or None,
                         'placeId': place(s.get('placeId')), 'sources': src(s.get('sourceIds')), 'confidence': s.get('confidence'),
                         'note': clean(s.get('note')) or None}
                        for s in p.get('spouses') or [] if s['id'] in keep],
        }
        base = {'id': pid, 'name': p['displayName'], 'given': p.get('givenNames') or '', 'surname': p.get('surname') or '',
                'sex': p.get('sex'), 'generation': p.get('generation'), 'about': clean(p.get('disambiguator')),
                'aliases': aliases_for(p), 'url': TREEP + '#/person/' + pid, **rel,
                'parentLink': p.get('parentLinkConfidence')}
        # living people are marked so answers use the present tense; what they show is what the data holds
        if p.get('isLiving'): base['living'] = True
        if p.get('kin') or p.get('placeholder'): base['unidentified'] = True
        if pid in suspected:
            base['parents'] = []; base['suspectedRelativeOf'] = suspected[pid]
        story_plain, story_src = strip_footnotes(p.get('story'))
        src(story_src)
        story = clean(p.get('story'))
        base.update({
            'summary': clean(p.get('summary')), 'story': story, 'storySources': story_src, 'confidence': p.get('confidence'),
            'directLine': bool(p.get('isDirectLine')),
            'birth': fact(p.get('birth')), 'death': fact(p.get('death')), 'burial': fact(p.get('burial')),
            'residences': [{'place': clean(r.get('place')), 'address': clean(r.get('address')) or None, 'years': clean(str(r.get('years') or '')) or None,
                            'placeId': place(r.get('placeId')), 'sources': src(r.get('sourceIds')), 'confidence': r.get('confidence')}
                           for r in p.get('residences') or []],
            'occupations': [{'title': clean(o.get('title')), 'employer': clean(o.get('employer')) or None, 'place': clean(o.get('place')) or None,
                             'years': clean(str(o.get('years') or '')) or None, 'placeId': place(o.get('placeId')),
                             'sources': src(o.get('sourceIds')), 'confidence': o.get('confidence')} for o in p.get('occupations') or []],
            'facts': [{'label': clean(f.get('label')), 'value': clean(f.get('value')), 'sources': src(f.get('sourceIds')),
                       'confidence': f.get('confidence')} for f in p.get('facts') or []],
            'timeline': [{'date': t.get('date'), 'range': norm_date(t.get('date'), t.get('label')), 'label': clean(t.get('label')),
                          'text': clean(t.get('event')), 'kind': t.get('kind'), 'placeId': place(t.get('placeId')),
                          'sources': src(t.get('sourceIds')), 'confidence': t.get('confidence')} for t in p.get('timeline') or []],
            'voyages': [{'ship': v.get('ship'), 'from': v.get('from'), 'to': v.get('to'), 'display': clean(v.get('display')),
                         'date': v.get('departureDate') or v.get('arrivalDate'), 'fromPlaceId': place(v.get('fromPlaceId')),
                         'toPlaceId': place(v.get('toPlaceId')), 'sources': src(v.get('sourceIds')), 'confidence': v.get('confidence'),
                         'records': ['images/records/' + c for c in v.get('recordCrops') or []]} for v in p.get('voyages') or []],
            'immigration': p.get('immigration'),
            'media': [{'file': m.get('file'), 'thumb': m.get('thumb') or m.get('file'), 'caption': clean(m.get('caption')),
                       'alt': clean(m.get('alt')), 'type': m.get('type'), 'summary': clean(m.get('summary')) or None,
                       'source': (src([m.get('sourceId')]) or [None])[0], 'original': m.get('original') or m.get('pdf')}
                      for m in p.get('media') or []],
            'openQuestions': [{'question': clean(q.get('question')), 'record': clean(q.get('record')) or None} for q in p.get('openQuestions') or []],
            'relatedPages': [{'title': clean(r.get('title')), 'url': r.get('url')} for r in p.get('relatedPages') or []],
        })
        people.append(base)

    ids = {p['id'] for p in people}
    # which side of the family each person is on, as on the tree: the first anchor's relatives, the second's,
    # or the couple's descendants ("both")
    anchors = [a for a in st.get('anchors') or [] if a.get('id') in ids][:2]
    SIDES = {a.get('key') or ('a', 'b')[i]: a['id'] for i, a in enumerate(anchors)}
    side = {}
    for name, root in (SIDES.items() if len(SIDES) == 2 else []):
        other = [v for k, v in SIDES.items() if k != name][0]
        seen, queue = {other}, [root]
        down = set()
        q2 = list(raw[root].get('children') or [])
        while q2:
            c = q2.pop()
            if c in down or c not in ids: continue
            down.add(c); q2 += raw[c].get('children') or []
        seen |= down
        while queue:
            x = queue.pop(0)
            if x in side and x != root: continue
            side.setdefault(x, name)
            pr = next(p for p in people if p['id'] == x)
            for n in pr['parents'] + pr['children'] + [s['id'] for s in pr['spouses']]:
                if n in ids and n not in seen and n not in side: queue.append(n)
        for c in down: side[c] = 'both'
    for p in people: p['side'] = side.get(p['id'])

    # pages
    sections, page_media, pages = [], [], []
    for page in PAGES:
        title, h1, blocks, media, desc = read_page(page)
        lede = desc or next((b['text'] for b in blocks if b['kind'] == 'text'), '')
        pages.append({'url': page, 'title': h1 if page != HOMEP else 'Home', 'about': lede[:300]})
        sections += chunk_page(page, h1 if page != HOMEP else 'Home', blocks)
        for m in media:
            m['page'] = page; m['url'] = page + ('#' + m['anchor'] if m['anchor'] else '')
            page_media.append(m)
    # the engine's own pages, for "where can I read about ..." questions
    if pages_cfg.get('tree'): pages.append({'url': TREEP, 'title': 'The family tree', 'about': "Everyone on the tree, with each person's story, records and how they are related."})
    if pages_cfg.get('map'): pages.append({'url': MAPP, 'title': 'The family map', 'about': 'The places where the family were born, lived, married, worked and were buried, with a timeline and old maps.'})

    # people named in each section, for retrieval (full names and the unambiguous short names only)
    name_index = {}
    for p in people:
        for a in p['aliases']:
            if a['kind'] in ('display', 'full', 'first', 'variant', 'nickname', 'maiden') and len(a['text']) > 2:
                name_index.setdefault(a['text'].lower(), set()).add(p['id'])
    names = sorted(name_index, key=len, reverse=True)
    pat = re.compile(r'\b(' + '|'.join(re.escape(n) for n in names) + r')\b', re.I)
    def mentions(text):
        hit = set()
        for m in pat.finditer(text or ''):
            ids_ = name_index.get(m.group(1).lower(), set())
            if len(ids_) == 1: hit |= ids_
        return sorted(hit)
    living_ids = {p['id'] for p in people if p.get('living')}
    # a page about one person (Ron in Egypt) is about them all the way down, even where it says "he";
    # pages about many people (stuart.generalPages, the home page by default) are not
    general = set(st.get('generalPages') or [HOMEP])
    page_people = {}
    for page in PAGES:
        title, h1, blocks, media, desc = read_page(page)
        if page not in general:
            page_people[page] = mentions(h1 + ' ' + (desc or ''))
    for s in sections:
        s['people'] = mentions(s['text'])
        s['pagePeople'] = [i for i in page_people.get(s['page'], []) if i not in s['people']]
    seen_files = set()
    photos = []
    for m in page_media:
        key = (m['file'], m['caption'])
        if key in seen_files: continue
        seen_files.add(key)
        photos.append({'id': 'ph:%d' % len(photos), 'file': m['file'], 'caption': m['caption'] or m['alt'], 'alt': m['alt'],
                       'kind': m['kind'], 'page': m['page'], 'url': m['url'], 'heading': m['heading'], 'original': m.get('original'),
                       'people': mentions((m['caption'] or '') + ' ' + (m['alt'] or ''))})

    places_out = [{'id': i, 'name': clean(pl['name']), 'historicName': clean(pl.get('historicName')), 'variants': pl.get('variants') or [],
                   'kind': pl.get('kind'), 'address': clean(pl.get('address')) or None, 'inHomeRegion': in_home(pl), 'country': country_of(pl),
                   'blurb': clean(pl.get('blurb')) or None, 'title': clean(pl.get('title')) or None, 'url': (MAPP + '?place=' + i) if pages_cfg.get('map') else None}
                  for i, pl in places.items() if i in used_places]
    srcs_out = [{'id': i, 'title': clean(s['title']), 'type': s.get('type'), 'repository': clean(s.get('repository')) or None,
                 'date': s.get('date'), 'url': s.get('url'), 'file': s.get('file'), 'note': clean(s.get('note')) or None}
                for i, s in sources.items() if i in used_sources]

    site = {
        'familyName': (CFG.get('site') or {}).get('familyName') or 'this family',
        'anchors': [{'key': a.get('key') or ('a', 'b')[i], 'id': a['id'], 'title': a.get('title') or raw[a['id']]['displayName'],
                     'short': a.get('short') or (raw[a['id']].get('givenNames') or raw[a['id']]['displayName']).split()[0]} for i, a in enumerate(anchors)],
        'homeCountry': st.get('homeCountry') or '',
        'pages': {'home': HOMEP, 'tree': pages_cfg.get('tree'), 'map': pages_cfg.get('map'), 'ask': pages_cfg.get('ask')},
    }
    for k in ('overviewSections', 'overviewFallback', 'overviewFollowups', 'warFollowups', 'stories', 'helpExample', 'photos',
              'wordlikeNames', 'familyNames'):
        if st.get(k) is not None: site[k] = st[k]
    kb = {'schema': SCHEMA, 'title': ((CFG.get('site') or {}).get('name') or 'Family') + ' family archive', 'site': site,
          'counts': {'people': len(people), 'living': len(living_ids), 'sections': len(sections), 'photos': len(photos),
                     'places': len(places_out), 'sources': len(srcs_out)},
          'people': people, 'places': places_out, 'sources': srcs_out, 'sections': sections, 'photos': photos, 'pages': pages,
          'examples': examples(people, st.get('examples'))}
    return kb


def examples(people, configured=None):
    """Starter questions. A site lists its own in stuart.examples ([{ kind, q, needs: [person ids] }]); a question
    whose people are not all on the tree is dropped, so none of them asks about something that is not there.
    Without a list, a few are made from what the records hold."""
    by = {p['id']: p for p in people}
    if configured:
        return [{'kind': e.get('kind') or 'question', 'q': e['q']} for e in configured
                if all(i in by and not by[i].get('unidentified') for i in e.get('needs') or [])]
    out = []
    rich = sorted([p for p in people if not p.get('living') and not p.get('unidentified') and p.get('parents')],
                  key=lambda p: -(len(p.get('residences') or []) + len(p.get('occupations') or []) + len(p.get('media') or [])))
    if rich: out.append(('genealogy', "Who were %s's parents?" % rich[0]['name']))
    if len(rich) > 1 and rich[1].get('residences'): out.append(('places', 'Where did %s live?' % rich[1]['name']))
    out.append(('analysis', 'What jobs did the family have?'))
    out.append(('overview', 'Who is the earliest documented member of the family?'))
    return [{'kind': k, 'q': q} for k, q in out]


def build_archive(site_dir, cfg, out_dir):
    """Write archive/kb-<hash>.json (and archive/manifest.json, for older pages) into out_dir; return the path."""
    global ROOT, CFG
    ROOT, CFG = site_dir, cfg
    kb = build()
    body = json.dumps(kb, ensure_ascii=False, separators=(',', ':'), sort_keys=False)
    digest = hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]
    name = 'kb-%s.json' % digest
    out = os.path.join(out_dir, 'archive')
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.startswith('kb-') and f.endswith('.json'): os.remove(os.path.join(out, f))
    with open(os.path.join(out, name), 'w', encoding='utf-8') as f: f.write(body)
    with open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump({'schema': SCHEMA, 'kb': name, 'hash': digest, 'counts': kb['counts']}, f, indent=1)
    return 'archive/' + name, kb['counts'], len(body)
