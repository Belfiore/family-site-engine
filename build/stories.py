"""The Stories page: stories, articles and essays written as Markdown files in the site's own repository.

    content/stories/the-crossing.md

    ---
    title: The Crossing
    date: 1923-04-02
    cover: images/crossing.jpg
    coverAlt: The ship at the dock
    people: [arthur-hartley, margot-moreau]
    summary: One sentence for the list of stories (optional; the first paragraph is used if it is left out).
    draft: true        (optional; a draft is not published)
    ---
    The story, in Markdown.

The build makes stories.html (the list, newest first) and one page per story, story-<name>.html. A person named in
"people" gets a tag that links to them on the family tree. People who are living, and people the tree does not show
(tree.hiddenRegions), get no tag, so a story never puts someone on a public page that the rest of the site leaves off.
See docs/stories.md.
"""
import datetime, html, json, os, re

import markdown, sitecfg

MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
DATE_RE = re.compile(r'^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$')
KEYS = {'title', 'date', 'cover', 'coverAlt', 'people', 'summary', 'draft'}
DASHES = (chr(0x2014), chr(0x2013))


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


# ------------------------------------------------------------------ reading a story file
def scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'': return v[1:-1]
    low = v.lower()
    if low in ('true', 'yes'): return True
    if low in ('false', 'no'): return False
    if low in ('null', '~', ''): return None
    return v


def front_matter(text):
    """(settings, body) from the start of a story file. The settings are a small subset of YAML: key: value, lists in
    square brackets or as "- item" lines, and # comments. Returns (None, text) if the file has no settings block."""
    t = text.replace('\r\n', '\n').replace('\r', '\n').lstrip(chr(0xFEFF))
    if not t.startswith('---\n'): return None, t
    end = re.search(r'^---[ \t]*$', t[4:], re.M)
    if not end: return None, t
    block, body = t[4:4 + end.start()], t[4 + end.end():].lstrip('\n')
    meta, key = {}, None
    for raw in block.split('\n'):
        if not raw.strip() or raw.lstrip().startswith('#'): continue
        item = re.match(r'^\s+-\s+(.*)$', raw)
        if item and key is not None:
            if not isinstance(meta.get(key), list): meta[key] = []
            meta[key].append(scalar(item.group(1)))
            continue
        m = re.match(r'^([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*)$', raw)
        if not m: raise ValueError('cannot read the line: %s' % raw.strip())
        key, v = m.group(1), m.group(2).strip()
        if v.startswith('['):
            if not v.endswith(']'): raise ValueError('the list for %s must end with ]' % key)
            meta[key] = [scalar(x) for x in v[1:-1].split(',') if x.strip()]
        else:
            meta[key] = scalar(v) if v else []
    return meta, body


def date_info(v):
    """(sort key, text, ISO-like value) for 1923, 1923-04 or 1923-04-02; None if it is not a date."""
    m = DATE_RE.match(str(v or '').strip())
    if not m: return None
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    if mo and not 1 <= int(mo) <= 12: return None
    if d:
        try: datetime.date(y, int(mo), int(d))
        except ValueError: return None
    key = '%04d-%02d-%02d' % (y, int(mo or 0), int(d or 0))
    text = '%d %s %d' % (int(d), MONTHS[int(mo) - 1], y) if d else ('%s %d' % (MONTHS[int(mo) - 1], y) if mo else str(y))
    return key, text, m.group(0)


def slugify(stem):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', stem.lower())).strip('-')


def people_by_id(site, cfg):
    p = os.path.join(site, (cfg.get('data') or {}).get('dir') or 'data', 'people.json')
    try:
        with open(p, encoding='utf-8') as f:
            return {x['id']: x for x in json.load(f).get('people') or [] if isinstance(x, dict) and 'id' in x}
    except (OSError, ValueError):
        return {}


def taggable(person, cfg):
    """Whether a story may name this person: not living, and shown on the tree."""
    tree = cfg.get('tree') or {}
    hidden, suspected = set(tree.get('hiddenRegions') or []), tree.get('suspectedRelatives') or {}
    if person.get('isLiving'): return False
    return person.get('region') not in hidden or person['id'] in suspected


def load(site, cfg, by=None):
    """Every story in content/stories/. Returns (stories, errors, warnings); the stories are newest first."""
    errors, warnings, stories, seen = [], [], [], {}
    d = os.path.join(site, sitecfg.STORIES_DIR)
    if not os.path.isdir(d): return stories, errors, warnings
    by = people_by_id(site, cfg) if by is None else by
    for name in sorted(os.listdir(d)):
        if not name.lower().endswith('.md') or name.startswith(('.', '_')): continue
        rel = os.path.join(sitecfg.STORIES_DIR, name).replace(os.sep, '/')
        try:
            with open(os.path.join(d, name), encoding='utf-8') as f: text = f.read()
            meta, body = front_matter(text)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            errors.append('%s: %s' % (rel, e))
            continue
        if meta is None:
            errors.append('%s: the file must start with a block of settings between --- lines (title, date, cover, people)' % rel)
            continue
        for k in meta:
            if k not in KEYS: warnings.append('%s: unknown setting "%s"' % (rel, k))
        if meta.get('draft') is True: continue
        title = meta.get('title')
        if not isinstance(title, str) or not title.strip():
            errors.append('%s: a story needs a title' % rel)
            continue
        slug = slugify(name[:-3])
        if not slug:
            errors.append('%s: the file name has no letters or digits to make a page name from' % rel)
            continue
        if slug in seen:
            errors.append('%s: makes the same page as %s (story-%s.html). Rename one' % (rel, seen[slug], slug))
            continue
        seen[slug] = rel
        di = None
        if meta.get('date') not in (None, [], ''):
            di = date_info(meta['date'])
            if not di:
                errors.append('%s: the date %r must be like 1923, 1923-04 or 1923-04-02' % (rel, meta['date']))
                continue
        cover = meta.get('cover') if isinstance(meta.get('cover'), str) else None
        if cover:
            if not markdown.safe_href(cover) or cover.startswith('#') or cover.lower().startswith('mailto:'):
                errors.append('%s: the cover %r must be a picture in this site or an https address' % (rel, cover))
                cover = None
            elif not re.match(r'^https?://', cover, re.I) and not os.path.exists(os.path.join(site, cover)):
                warnings.append('%s: the cover %s is not in the site' % (rel, cover))
        tags, ids = [], meta.get('people') if isinstance(meta.get('people'), list) else []
        for pid in ids:
            p = by.get(pid)
            if p is None:
                errors.append('%s: people names %s, who is not in people.json' % (rel, pid))
            elif not taggable(p, cfg):
                warnings.append('%s: %s is not tagged, because the site does not show that person publicly (living, or in a hidden group)' % (rel, pid))
            elif pid not in tags:
                tags.append(pid)
        if any(c in text for c in DASHES):
            warnings.append('%s: has an em or en dash; the site style is commas, colons, brackets or full stops' % rel)
        for img in re.findall(r'!\[[^\]]*\]\(([^)\s]+)', body):
            if not re.match(r'^https?://', img, re.I) and markdown.safe_href(img) and not os.path.exists(os.path.join(site, img)):
                warnings.append('%s: the picture %s is not in the site' % (rel, img))
        summary = meta.get('summary') if isinstance(meta.get('summary'), str) else None
        first = next((p for p in re.split(r'\n\s*\n', body.strip()) if p.strip() and not p.lstrip().startswith(('#', '>', '-', '*', '!', '```'))), '')
        stories.append({'slug': slug, 'file': 'story-%s.html' % slug, 'source': rel, 'title': title.strip(),
                        'date': di, 'cover': cover, 'coverAlt': meta.get('coverAlt') if isinstance(meta.get('coverAlt'), str) else '',
                        'people': tags, 'summary': (summary or truncate(markdown.plain(first))), 'body': body})
    stories.sort(key=lambda s: s['title'].lower())
    stories.sort(key=lambda s: s['date'][0] if s['date'] else '', reverse=True)     # newest first; a story with no date goes last
    return stories, errors, warnings


def truncate(text, n=200):
    if len(text) <= n: return text
    cut = text[:n].rsplit(' ', 1)[0].rstrip(',;:')
    return cut + ' ...'


# ------------------------------------------------------------------ the pages
def tags_html(story, by, cfg):
    tree = (cfg['pages'].get('tree') or {}).get('file')
    items = []
    for pid in story['people']:
        name = esc(by[pid].get('displayName') or pid)
        link = '<a href="%s#/person/%s">%s</a>' % (esc(tree), esc(pid), name) if tree else '<span>%s</span>' % name
        items.append('<li>%s</li>' % link)
    return '<ul class="cp-tags" aria-label="People in this story">%s</ul>' % ''.join(items) if items else ''


def date_html(story):
    if not story['date']: return ''
    return '<time datetime="%s">%s</time>' % (esc(story['date'][2]), esc(story['date'][1]))


def cover_html(story, size):
    if not story['cover']: return ''
    return '<img src="%s" alt="%s" loading="lazy">' % (esc(story['cover']), esc(story['coverAlt']))


def index_body(stories, by, cfg):
    page = cfg['pages']['stories']
    heading = esc(page.get('heading') or page.get('title') or 'Stories')
    out = ['<header class="cp-head"><h1>%s</h1></header>' % heading]
    if not stories:
        out.append('<p class="cp-empty">There are no stories here yet.</p>')
    else:
        out.append('<ul class="cp-cards">')
        for s in stories:
            out.append('<li class="cp-card">')
            if s['cover']:
                out.append('  <a class="cp-card-cover" href="%s" tabindex="-1" aria-hidden="true">%s</a>' % (esc(s['file']), cover_html(s, 'card')))
            out.append('  <div class="cp-card-text">')
            out.append('    <h2><a href="%s">%s</a></h2>' % (esc(s['file']), esc(s['title'])))
            if s['date']: out.append('    <p class="cp-meta">%s</p>' % date_html(s))
            if s['summary']: out.append('    <p class="cp-summary">%s</p>' % esc(s['summary']))
            t = tags_html(s, by, cfg)
            if t: out.append('    ' + t)
            out.append('  </div>')
            out.append('</li>')
        out.append('</ul>')
    return '\n'.join(out)


def story_body(story, newer, older, by, cfg):
    index = cfg['pages']['stories']['file']
    out = ['<article class="cp-story">', '<header class="cp-head">',
           '<p class="cp-kicker"><a href="%s">%s</a></p>' % (esc(index), esc(cfg['pages']['stories'].get('heading') or 'Stories')),
           '<h1>%s</h1>' % esc(story['title'])]
    if story['date']: out.append('<p class="cp-meta">%s</p>' % date_html(story))
    t = tags_html(story, by, cfg)
    if t: out.append(t)
    out.append('</header>')
    if story['cover']: out.append('<figure class="cp-cover">%s</figure>' % cover_html(story, 'full'))
    out.append('<div class="cp-text">\n%s\n</div>' % markdown.render(story['body']))
    out.append('</article>')
    nav = []
    if newer: nav.append('<a class="cp-newer" href="%s"><small>Newer</small>%s</a>' % (esc(newer['file']), esc(newer['title'])))
    if older: nav.append('<a class="cp-older" href="%s"><small>Older</small>%s</a>' % (esc(older['file']), esc(older['title'])))
    nav.append('<a class="cp-all" href="%s">All stories</a>' % esc(index))
    out.append('<nav class="cp-more" aria-label="More stories">%s</nav>' % ''.join(nav))
    return '\n'.join(out)


def build(site, out, cfg, ctx, template, render_page):
    """Write stories.html and every story's page. render_page(kind, template, cfg, ctx, extra) is pages.render_engine_page.
    Returns the names of the files written."""
    stories, _errors, _warnings = load(site, cfg)
    by = people_by_id(site, cfg)
    page = cfg['pages']['stories']
    made = []

    def write(name, text):
        with open(os.path.join(out, name), 'w', encoding='utf-8') as f: f.write(text)
        made.append(name)

    write(page['file'], render_page('stories', template, cfg, ctx, {'pageBody': index_body(stories, by, cfg)}))
    for i, s in enumerate(stories):
        view = dict(cfg, pages=dict(cfg['pages'], stories=dict(page, file=s['file'], title='%s | %s' % (s['title'], (cfg.get('site') or {}).get('name') or 'Stories'),
                                                              description=s['summary'] or page.get('description') or '')))
        write(s['file'], render_page('stories', template, view, ctx,
                                     {'pageBody': story_body(s, stories[i - 1] if i else None, stories[i + 1] if i + 1 < len(stories) else None, by, cfg),
                                      '_active': page['file']}))
    return made
