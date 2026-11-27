"""The site chat's index: passages from a site's own pages and data.

Called by build_site.py when chat.enabled is true. The browser searches this
index when someone asks a question and sends only the passages it found to the
site's endpoint. Nothing here calls a model, and nothing is embedded.

People in a hidden region are left out, as on the tree, except a suspected
relative kept beside someone. A page the site publishes is read as it is written.
"""
import html, json, os, re
from fnmatch import fnmatch
from html.parser import HTMLParser
from urllib.parse import urlparse

DEFAULT_GREETING = 'Ask a question about this family. I answer only from the pages and records on this site.'
DEFAULT_PLACEHOLDER = 'Ask about this family'
SKIP_TAGS = {'nav', 'script', 'style', 'button', 'footer', 'noscript', 'svg', 'form', 'select', 'template', 'head', 'iframe'}
SKIP_CLASSES = {'nav-links', 'nav-inner', 'nav-toggle', 'lightbox-overlay', 'lightbox-main'}
VOID = {'img', 'br', 'hr', 'meta', 'link', 'input', 'source', 'area', 'col', 'embed', 'wbr', 'base'}
BLOCKS = {'p', 'li', 'figcaption', 'blockquote', 'dd', 'dt', 'caption'}
HEADINGS = {'h1', 'h2', 'h3', 'h4'}


def clean(t):
    return re.sub(r'\s+', ' ', html.unescape(t or '')).strip()


def strip_notes(t):
    return re.sub(r'\[\^[^\]]+\]', '', t or '')


def clip(text, n=1400):
    text = clean(text)
    if len(text) <= n:
        return text
    cut = text.rfind('. ', 0, n)
    if cut < n // 2:
        cut = n - 1
    return text[:cut + 1].strip()


def endpoint_ok(url):
    """An address we can publish. The key is not part of it."""
    if not isinstance(url, str) or not url.strip():
        return False
    u = urlparse(url.strip())
    if u.username or u.password or u.query or u.fragment:
        return False
    host = (u.hostname or '').lower()
    if u.scheme == 'https' and u.netloc:
        return True
    return u.scheme == 'http' and host in ('127.0.0.1', 'localhost') and bool(u.netloc)


def problem(site, cfg):
    """A reason to stop the build, or None. Checked before the output is touched."""
    chat = cfg.get('chat') or {}
    if not chat.get('enabled'):
        return None
    if not endpoint_ok(chat.get('endpoint')):
        return ('chat.endpoint must be an https address with no user, password or query '
                '(http://127.0.0.1 or http://localhost is allowed for a local check). The key stays on that service.')
    for name in chat.get('pages') or []:
        if not os.path.isfile(os.path.join(site, name)):
            return 'chat.pages: %s is not in the site' % name
    return None


class Reader(HTMLParser):
    """Headings and the paragraphs under them. Navigation, scripts and forms are left out."""

    def __init__(self, skip_classes):
        super().__init__(convert_charrefs=True)
        self.skip_classes = skip_classes
        self.stack = []
        self.parts = []
        self.heading = ''
        self.anchor = ''
        self.held = ''
        self.cur = []
        self.buf = []
        self.capture = None
        self.in_title = False
        self.title = ''

    def skipping(self):
        return bool(self.stack and self.stack[-1])

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, push=tag not in VOID)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, push=False)

    def _start(self, tag, attrs, push):
        d = {k: (v or '') for k, v in attrs}
        classes = set(d.get('class', '').split())
        skip = tag in SKIP_TAGS or bool(classes & self.skip_classes)
        if d.get('id') and not skip and not self.skipping():
            self.held = d['id']
        if tag in HEADINGS and not self.skipping() and not skip:
            self._flush()
            self.anchor = self.held
            self.capture = 'heading'
            self.buf = []
        elif tag in BLOCKS and not self.skipping() and not skip:
            self.capture = 'text'
            self.buf = []
        elif tag == 'br' and self.capture and not self.skipping():
            self.buf.append(' ')
        if tag == 'title':
            self.in_title = True
        if push:
            self.stack.append(skip or self.skipping())

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag in HEADINGS and self.capture == 'heading':
            self.heading = clean(''.join(self.buf))
            self.capture = None
            self.buf = []
        elif tag in BLOCKS and self.capture == 'text':
            line = clean(''.join(self.buf))
            if line:
                self.cur.append(line)
            self.capture = None
            self.buf = []
        if tag not in VOID and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.in_title:
            self.title += data
            return
        if self.capture and not self.skipping():
            self.buf.append(data)

    def _flush(self):
        text = clean(' '.join(self.cur))
        if len(text) >= 40:
            self.parts.append({'heading': self.heading, 'anchor': self.anchor, 'text': text})
        self.cur = []
        self.heading = ''

    def finish(self):
        self._flush()
        self.title = clean(self.title)
        return self.parts


def chunks(text, size=900):
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out = []
    while text:
        if len(text) <= size:
            out.append(text)
            break
        cut = text.rfind('. ', 0, size)
        if cut < size // 2:
            cut = size - 1
        else:
            cut += 1
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    return [c for c in out if c]


def published(name, cfg):
    for pattern in (cfg.get('publish') or {}).get('exclude') or []:
        if fnmatch(name, pattern):
            return False
    return True


def story_pages(site, cfg):
    listed = (cfg.get('chat') or {}).get('pages')
    if listed is not None:
        return [n for n in listed if published(n, cfg)]
    names = []
    for name in sorted(os.listdir(site)):
        if name.endswith('.html') and published(name, cfg):
            names.append(name)
    return names


def page_passages(site, name, skip_classes):
    path = os.path.join(site, name)
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    reader = Reader(skip_classes)
    reader.feed(raw)
    reader.close()
    out = []
    for part in reader.finish():
        title = part['heading'] or reader.title or name
        url = name + (('#' + part['anchor']) if part['anchor'] else '')
        base = 'page:%s' % url
        for i, text in enumerate(chunks(part['text'])):
            out.append({'id': base if i == 0 else '%s:%d' % (base, i + 1), 'title': title, 'url': url, 'text': text})
    return out


def load_json(site, cfg, name):
    path = os.path.join(site, (cfg.get('data') or {}).get('dir') or 'data', name)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def keep_person(p, hidden, suspected):
    region = p.get('region')
    if region and region in hidden and p.get('id') not in suspected:
        return False
    return True


def sentence(text):
    text = clean(strip_notes(text))
    if not text:
        return ''
    return text if text.endswith(('.', '?', '!')) else text + '.'


def person_text(p, by_id, keep):
    name = p.get('displayName') or p.get('id') or ''
    bits = []
    dis = clean(p.get('disambiguator'))
    bits.append(sentence(name + ((' (' + dis + ')') if dis else '')))
    known = clean(p.get('knownAs'))
    if known and known.lower() not in name.lower():
        bits.append(sentence('Known as ' + known))
    if p.get('isLiving'):
        bits.append('Is living.')
    birth = p.get('birth') or {}
    if isinstance(birth, dict):
        bits.append(sentence(when_where('Born', birth)))
    death = p.get('death') or {}
    if not p.get('isLiving') and isinstance(death, dict):
        bits.append(sentence(when_where('Died', death)))
    parents = []
    for pid in p.get('parents') or []:
        other = by_id.get(pid)
        if other and keep(other) and other.get('displayName'):
            parents.append(other['displayName'])
    if parents:
        bits.append(sentence('Parents: ' + ' and '.join(parents)))
    for sp in p.get('spouses') or []:
        if not isinstance(sp, dict):
            continue
        other = by_id.get(sp.get('id'))
        if not other or not keep(other) or not other.get('displayName'):
            continue
        extra = [clean(sp.get('marriageDisplay')), clean(sp.get('place'))]
        bits.append(sentence('Married ' + other['displayName'] + ''.join(', ' + x for x in extra if x)))
    bits.append(sentence(p.get('summary')))
    bits.append(sentence(p.get('story')))
    for r in p.get('residences') or []:
        if not isinstance(r, dict):
            continue
        where = clean(r.get('address') or r.get('place'))
        if not where:
            continue
        years = clean(r.get('years'))
        bits.append(sentence('Lived at ' + where + ((' (' + years + ')') if years else '')))
    for o in p.get('occupations') or []:
        if not isinstance(o, dict) or not o.get('title'):
            continue
        extra = [clean(o.get('place')), clean(o.get('years'))]
        bits.append(sentence('Occupation: ' + clean(o['title']) + ''.join(', ' + x for x in extra if x)))
    return clip(' '.join(b for b in bits if b))


def when_where(label, obj):
    disp, place = clean(obj.get('display')), clean(obj.get('place'))
    if disp and place:
        return '%s %s in %s' % (label, disp, place)
    if disp:
        return '%s %s' % (label, disp)
    if place:
        return '%s in %s' % (label, place)
    return ''


def person_passages(site, cfg):
    hidden = set((cfg.get('tree') or {}).get('hiddenRegions') or [])
    suspected = set(((cfg.get('tree') or {}).get('suspectedRelatives') or {}))
    people = load_json(site, cfg, 'people.json').get('people') or []
    by_id = {p.get('id'): p for p in people if isinstance(p, dict)}

    def keep(p):
        return keep_person(p, hidden, suspected)

    tree = (cfg.get('_pages') or {}).get('tree') or ''
    out = []
    for p in people:
        if not isinstance(p, dict) or not keep(p):
            continue
        text = person_text(p, by_id, keep)
        if len(text) < 20:
            continue
        out.append({'id': 'person:%s' % p.get('id'), 'title': p.get('displayName') or p.get('id'), 'url': tree, 'text': text})
    return out


def place_passages(site, cfg):
    places = load_json(site, cfg, 'places.json').get('places') or []
    url = (cfg.get('_pages') or {}).get('map') or ''
    out = []
    for pl in places:
        if not isinstance(pl, dict):
            continue
        if pl.get('status') not in (None, '', 'published'):
            continue
        bits = [sentence(pl.get('name'))]
        historic = clean(pl.get('historicName'))
        if historic and historic != clean(pl.get('name')):
            bits.append(sentence(historic))
        address = clean(pl.get('address'))
        if address and address not in (clean(pl.get('name')), historic):
            bits.append(sentence(address))
        if isinstance(pl.get('blurb'), str):
            bits.append(sentence(pl.get('blurb')))
        text = clip(' '.join(b for b in bits if b))
        if len(text) < 8:
            continue
        out.append({'id': 'place:%s' % pl.get('id'), 'title': pl.get('name') or pl.get('id'), 'url': url, 'text': text})
    return out


def source_passages(site, cfg):
    out = []
    for s in load_json(site, cfg, 'sources.json').get('sources') or []:
        if not isinstance(s, dict) or not s.get('title'):
            continue
        kind = clean(s.get('type'))
        if kind:
            kind = kind[:1].upper() + kind[1:]
        tail = ', '.join(x for x in (kind, clean(s.get('repository')), clean(s.get('date'))) if x)
        text = sentence(s['title'])
        if tail:
            text = text + ' ' + sentence(tail)
        out.append({'id': 'source:%s' % s.get('id'), 'title': s['title'], 'url': '', 'text': text})
    return out


def passages_for(site, cfg):
    chat = cfg.get('chat') or {}
    skip = set(SKIP_CLASSES)
    skip.update(chat.get('skipClasses') or [])
    out = []
    for name in story_pages(site, cfg):
        out.extend(page_passages(site, name, skip))
    out.extend(person_passages(site, cfg))
    out.extend(place_passages(site, cfg))
    out.extend(source_passages(site, cfg))
    return out


def build(site, cfg, out):
    chat = cfg.get('chat') or {}
    name = clean(chat.get('name'))[:40] or 'Guide'
    greeting = clean(chat.get('greeting'))[:500] or DEFAULT_GREETING
    placeholder = clean(chat.get('placeholder'))[:80] or DEFAULT_PLACEHOLDER
    doc = {
        'name': name,
        'greeting': greeting,
        'placeholder': placeholder,
        'endpoint': chat.get('endpoint').strip(),
        'passages': passages_for(site, cfg),
    }
    dest = os.path.join(out, 'chat')
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, 'index.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write('\n')
    return {'passages': len(doc['passages'])}
