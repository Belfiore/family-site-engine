"""The Discovery Timeline page: the HTML for what discoveries.py found.

The page is made whole at build time, so it reads without JavaScript. engine/timeline.js adds what needs a
browser: the "since your last visit" banner, the filters, and the "show all" buttons.
"""
import datetime, html, json, re

import i18n

COLLAPSE_OVER = 6      # a day with more finds than this shows only the first few
COLLAPSE_SHOWN = 5
TYPES = ('person', 'record', 'photo', 'correction', 'place', 'connection')
CONFS = ('confirmed', 'probable', 'family tradition', 'unverified')
STATUSES = ('corrected', 'revised', 'withdrawn')

ICONS = {
    'person': '<circle cx="8" cy="5.2" r="2.7"/><path d="M2.6 14c.5-2.9 2.6-4.4 5.4-4.4s4.9 1.5 5.4 4.4"/>',
    'record': '<path d="M4 1.8h5.3L12.2 4.7V14.2H4z"/><path d="M9.2 1.8v3h3M6 8h4M6 10.5h4"/>',
    'photo': '<rect x="1.8" y="4" width="12.4" height="9" rx="1.4"/><circle cx="8" cy="8.5" r="2.3"/><path d="M5.6 4l.8-1.7h3.2l.8 1.7"/>',
    'correction': '<path d="M2.5 13.5l.6-3L10.8 2.8a1.4 1.4 0 012 2L5.1 12.5z"/><path d="M9.6 4l2.4 2.4"/>',
    'place': '<path d="M8 14.3s4.6-4.3 4.6-8A4.6 4.6 0 003.4 6.3c0 3.7 4.6 8 4.6 8z"/><circle cx="8" cy="6.3" r="1.7"/>',
    'connection': '<path d="M6.8 9.2a2.7 2.7 0 003.8 0l2.2-2.2a2.7 2.7 0 00-3.8-3.8L8 4.2"/><path d="M9.2 6.8a2.7 2.7 0 00-3.8 0L3.2 9a2.7 2.7 0 003.8 3.8L8 11.8"/>',
}


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def long_date(iso, lang='en'):
    d = datetime.date.fromisoformat(iso)
    return i18n.date_text(lang, d.year, d.month, d.day, weekday=(d.weekday() + 1) % 7)


def long_date_plain(iso, lang='en'):
    d = datetime.date.fromisoformat(iso)
    return i18n.date_text(lang, d.year, d.month, d.day)


def say(e, lang, field):
    """A find's words in this language: the researcher's translation if there is one, else the words as written."""
    tr = ((e.get('tr') or {}).get(lang) or {}) if lang != 'en' else {}
    return tr.get(field) or e.get(field)


def safe_url(u, allow_relative=True):
    u = (u or '').strip()
    if re.match(r'^https?://', u, re.I): return u
    if allow_relative and u and not re.match(r'^[a-z][a-z0-9+.-]*:', u, re.I) and not u.startswith('//'): return u
    return ''


URL_IN_TEXT = re.compile(r'https?://[^\s<>"\']+', re.I)
NEW_TAB = ' target="_blank" rel="noopener"'


def trim_url(u):
    """A web address found inside a sentence, without the full stop or bracket that closes the sentence."""
    while u and (u[-1] in '.,;:!?' or (u[-1] in ')]' and u.count({')': '(', ']': '['}[u[-1]]) < u.count(u[-1]))):
        u = u[:-1]
    return u


def source_html(src, lang='en'):
    """The source of a find. A web address, whether the find names one (source.url) or the source's own words contain one, is
    a link that opens in a new tab. Anything else is plain text."""
    text = src.get('text') or ''
    url = safe_url(src.get('url'), allow_relative=False)
    if url:
        return '<a class="tl-source" href="%s"%s>%s</a>' % (esc(url), NEW_TAB, esc(text))
    out, pos = [], 0
    for m in URL_IN_TEXT.finditer(text):
        u = trim_url(m.group(0))
        if not safe_url(u, allow_relative=False): continue
        out.append(esc(text[pos:m.start()]))
        out.append('<a href="%s"%s>%s</a>' % (esc(u), NEW_TAB, esc(u)))
        pos = m.start() + len(u)
    out.append(esc(text[pos:]))
    return '<span class="tl-source">%s</span>' % ''.join(out)


def count_phrase(n, lang='en'):
    return i18n.plural(lang, 'timeline.newFinds', n)


def line_label(l, lang='en'):
    """A family line's name in this language: the site's `label_de` beside the `label` of the map branch."""
    return ((l.get('tr') or {}).get(lang) or l['label']) if lang != 'en' else l['label']


def day_summary(entries, line_labels, many_lines, lang='en'):
    """'4 new finds across The Hartleys and The Moreaus.' The same rule is in engine/timeline.js, which rewrites the
    sentence when a filter is on."""
    n = len(entries)
    used = [line_label(l, lang) for l in line_labels if any(l['id'] in (e.get('lines') or []) for e in entries)]
    count = count_phrase(n, lang)
    if many_lines and len(used) >= 2: return i18n.t(lang, 'timeline.summaryAcross', count=count, lines=i18n.list_text(lang, used))
    if many_lines and len(used) == 1: return i18n.t(lang, 'timeline.summaryIn', count=count, line=used[0])
    return i18n.t(lang, 'timeline.summaryPlain', count=count)


def action_for(e, pages, lang='en'):
    """One quiet link to the exact person or place, or none. Never a generic page."""
    if e.get('offTree'): return None        # about someone (or a place) the tree and the map leave out: nothing there to open
    tree, mp = pages.get('tree'), pages.get('map')
    pids, pls = e.get('personIds') or [], e.get('placeIds') or []
    focus = e.get('focus') if e.get('focus') in pids else (pids[0] if pids else None)
    if e.get('type') == 'place' and pls and mp:
        return {'label': i18n.t(lang, 'timeline.showOnMap'), 'href': '%s?place=%s' % (mp, pls[0])}
    if focus and tree:
        return {'label': i18n.t(lang, 'timeline.seeInTree'), 'href': '%s#/person/%s' % (tree, focus)}
    if focus and mp:
        return {'label': i18n.t(lang, 'timeline.showOnMap'), 'href': '%s?person=%s' % (mp, focus)}
    if pls and mp:
        return {'label': i18n.t(lang, 'timeline.showOnMap'), 'href': '%s?place=%s' % (mp, pls[0])}
    return None


def card(e, pages, show_conf=False, full_of=None, lang='en'):
    """show_conf: timeline.showConfidence. full_of: a thumbnail's path -> the full-size file, so the picture can open large."""
    t = e.get('type') if e.get('type') in TYPES else 'record'
    action = action_for(e, pages, lang)
    src = dict(e.get('source') or {})
    if src.get('text') and lang != 'en':
        src['text'] = say(e, lang, 'sourceText') or src['text']
    meta = []
    if src.get('text'):
        meta.append(source_html(src))
    if show_conf and e.get('confidence') in CONFS:
        meta.append('<span class="tl-conf" data-conf="%s">%s</span>' % (esc(e['confidence']), esc(i18n.t(lang, 'timeline.conf.' + e['confidence']))))
    if say(e, lang, 'foundBy'):
        meta.append('<span class="tl-by">%s</span>' % esc(i18n.t(lang, 'timeline.foundBy', name=say(e, lang, 'foundBy'))))
    headline = say(e, lang, 'headline')
    body = ['<p class="tl-type"><svg class="tl-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" '
            'stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">%s</svg><span>%s</span></p>' % (ICONS[t], esc(i18n.t(lang, 'timeline.type.' + t))),
            '<h3 class="tl-headline">%s</h3>' % esc(headline)]
    if say(e, lang, 'changeNote'):
        body.append('<p class="tl-context">%s</p>' % esc(say(e, lang, 'changeNote')))
    head = (e.get('headline') or '') + ' ' + (headline or '')
    was = [c for c in (e.get('change') or []) if c.get('from') and c['from'] not in head][:2]
    if was:
        body.append('<p class="tl-was">%s</p>' % esc(i18n.t(lang, 'timeline.previously', changes='; '.join('%s: %s' % (c['field'], c['from']) for c in was))))
    if e.get('status') in STATUSES:
        body.append('<p class="tl-status">%s</p>' % esc(i18n.t(lang, 'timeline.status.' + e['status'])))
    if meta:
        body.append('<p class="tl-meta">%s</p>' % '<span class="tl-dot" aria-hidden="true"> &middot; </span>'.join(meta))
    if action:
        body.append('<p class="tl-act"><a class="tl-action" href="%s">%s</a></p>' % (esc(action['href']), esc(action['label'])))
    img = safe_url(e.get('image'))
    thumb = ''
    if img:
        full = safe_url((full_of or {}).get(e.get('image'))) or img
        alt = say(e, lang, 'imageAlt') or ''
        # the engine's own lightbox (records.js) opens it on a click; with no script, or a middle click, it opens in a new tab
        thumb = ('<a class="record-link tl-thumb-link" href="%s"%s aria-label="%s"><img class="tl-thumb" src="%s" alt="%s" loading="lazy" decoding="async"></a>' % (
            esc(full), NEW_TAB, esc(i18n.t(lang, 'timeline.viewFull', alt=alt) if alt else i18n.t(lang, 'timeline.viewFullNoAlt')), esc(img), esc(alt)))
    return ('<li class="tl-card%s" id="find-%s" data-type="%s" data-lines="%s" data-published="%s" data-status="%s">'
            '<div class="tl-card-text">%s</div>%s</li>') % (
        ' tl-has-thumb' if thumb else '', esc(e['id']), t, esc(' '.join(e.get('lines') or [])), esc(e.get('published') or ''),
        esc(e.get('status') or 'current'), '\n'.join(body), thumb)


def render_body(entries, line_labels, cfg, pages, since=None, full_of=None, lang='en'):
    """The page's content: heading, banner, filters, and a section for each day with finds, in one language."""
    T = lambda key, **kw: esc(i18n.t(lang, key, **kw))
    show_conf = bool((cfg.get('timeline') or {}).get('showConfidence'))
    many_lines = len([l for l in line_labels if any(l['id'] in (e.get('lines') or []) for e in entries)]) >= 2
    days = {}
    for e in entries: days.setdefault(e['found'], []).append(e)
    names = {l['id']: line_label(l, lang) for l in line_labels}
    parts = ['<div class="tl-root" data-collapse-over="%d" data-collapse-shown="%d" data-lines="%s">' % (
        COLLAPSE_OVER, COLLAPSE_SHOWN, esc(json.dumps(names, ensure_ascii=False))),
        '<header class="tl-head"><h1>%s</h1>'
        '<p class="tl-lede">%s</p>%s</header>' % (
            T('timeline.heading'), T('timeline.lede'),
            ('<p class="tl-since">%s</p>' % T('timeline.since', date=long_date_plain(since, lang))) if since else ''),
        '<div class="tl-banner" id="tlBanner" role="status" hidden><p class="tl-banner-text" id="tlBannerText"></p>'
        '<button type="button" class="tl-banner-go" id="tlJump">%s</button></div>' % T('timeline.jump')]
    # filters (shown by the script; they do nothing without it)
    types = [t for t in TYPES if any(e.get('type') == t for e in entries)]
    fl = []
    if many_lines:
        fl.append('<fieldset class="tl-fset"><legend>%s</legend><div class="tl-chips" data-filter="line">'
                  '<button type="button" class="tl-chip" data-value="" aria-pressed="true">%s</button>%s</div></fieldset>' % (T('timeline.familyLine'), T('timeline.allLines'), ''.join(
                      '<button type="button" class="tl-chip" data-value="%s" aria-pressed="false">%s</button>' % (esc(l['id']), esc(names[l['id']]))
                      for l in line_labels if any(l['id'] in (e.get('lines') or []) for e in entries))))
    if len(types) > 1:
        fl.append('<fieldset class="tl-fset"><legend>%s</legend><div class="tl-chips" data-filter="type">'
                  '<button type="button" class="tl-chip" data-value="" aria-pressed="true">%s</button>%s</div></fieldset>' % (T('timeline.typeOfFind'), T('timeline.allTypes'), ''.join(
                      '<button type="button" class="tl-chip" data-value="%s" aria-pressed="false">%s</button>' % (t, T('timeline.type.' + t)) for t in types)))
    if fl:
        parts.append('<details class="tl-filters" id="tlFilters" hidden><summary>%s</summary>%s</details>' % (T('timeline.filter'), ''.join(fl)))
    parts.append('<p class="tl-empty" id="tlEmpty" hidden>%s</p>' % T('timeline.noMatch'))
    if not entries:
        parts.append('<p class="tl-none">%s</p>' % T('timeline.none'))
    parts.append('<ol class="tl-days" id="tlDays">')
    for day in sorted(days, reverse=True):
        es = days[day]
        extra = len(es) > COLLAPSE_OVER
        cards = []
        for i, e in enumerate(es):
            c = card(e, pages, show_conf, full_of, lang)
            if extra and i >= COLLAPSE_SHOWN: c = c.replace('<li class="tl-card', '<li class="tl-card tl-extra', 1)
            cards.append(c)
        parts.append('<li class="tl-day" data-date="%s" data-count="%d"><section aria-labelledby="day-%s">'
                     '<header class="tl-day-head"><h2 class="tl-date" id="day-%s"><time datetime="%s">%s</time></h2>'
                     '<p class="tl-summary">%s</p></header><ol class="tl-list">%s</ol>%s</section></li>' % (
                         day, len(es), day, day, day, esc(long_date(day, lang)), esc(day_summary(es, line_labels, many_lines, lang)), '\n'.join(cards),
                         ('<button type="button" class="tl-more" hidden>%s</button>' % esc(i18n.plural(lang, 'timeline.showAll', len(es)))) if extra else ''))
    parts.append('</ol>')
    parts.append('<noscript><p class="tl-noscript">%s</p></noscript>' % T('timeline.noscript'))
    parts.append('</div>')
    return '\n'.join(parts)
