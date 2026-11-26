"""The Discovery Timeline page: the HTML for what discoveries.py found.

The page is made whole at build time, so it reads without JavaScript. engine/timeline.js adds what needs a
browser: the "since your last visit" banner, the filters, and the "show all" buttons.
"""
import datetime, html, json, re

COLLAPSE_OVER = 6      # a day with more finds than this shows only the first few
COLLAPSE_SHOWN = 5
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
CONF_LABEL = {'confirmed': 'Confirmed', 'probable': 'Probable', 'family tradition': 'Family tradition', 'unverified': 'Unverified'}
TYPE_LABELS = {'person': 'New person', 'record': 'New record', 'photo': 'New photo', 'correction': 'Correction',
               'place': 'New place', 'connection': 'New connection'}
STATUS_TEXT = {'corrected': 'This find has since been corrected.', 'revised': 'Part of this find has since been withdrawn.',
               'withdrawn': 'This find has since been withdrawn.'}

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


def long_date(iso):
    d = datetime.date.fromisoformat(iso)
    return '%s, %d %s %d' % (WEEKDAYS[d.weekday()], d.day, MONTHS[d.month - 1], d.year)


def long_date_plain(iso):
    d = datetime.date.fromisoformat(iso)
    return '%d %s %d' % (d.day, MONTHS[d.month - 1], d.year)


def safe_url(u, allow_relative=True):
    u = (u or '').strip()
    if re.match(r'^https?://', u, re.I): return u
    if allow_relative and u and not re.match(r'^[a-z][a-z0-9+.-]*:', u, re.I) and not u.startswith('//'): return u
    return ''


def count_phrase(n):
    return '%d new find%s' % (n, '' if n == 1 else 's')


def join_and(xs):
    return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' and ' + xs[-1]


def day_summary(entries, line_labels, many_lines):
    """'4 new finds across The Hartleys and The Moreaus.' The same rule is in engine/timeline.js, which rewrites the
    sentence when a filter is on."""
    n = len(entries)
    used = [l['label'] for l in line_labels if any(l['id'] in (e.get('lines') or []) for e in entries)]
    if many_lines and len(used) >= 2: return '%s across %s.' % (count_phrase(n), join_and(used))
    if many_lines and len(used) == 1: return '%s in %s.' % (count_phrase(n), used[0])
    return '%s.' % count_phrase(n)


def action_for(e, pages):
    """One quiet link to the exact person or place, or none. Never a generic page."""
    tree, mp = pages.get('tree'), pages.get('map')
    pids, pls = e.get('personIds') or [], e.get('placeIds') or []
    focus = e.get('focus') if e.get('focus') in pids else (pids[0] if pids else None)
    if e.get('type') == 'place' and pls and mp:
        return {'label': 'Show on the map', 'href': '%s?place=%s' % (mp, pls[0])}
    if focus and tree:
        return {'label': 'See it in the tree', 'href': '%s#/person/%s' % (tree, focus)}
    if focus and mp:
        return {'label': 'Show on the map', 'href': '%s?person=%s' % (mp, focus)}
    if pls and mp:
        return {'label': 'Show on the map', 'href': '%s?place=%s' % (mp, pls[0])}
    return None


def card(e, pages):
    t = e.get('type') if e.get('type') in TYPE_LABELS else 'record'
    action = action_for(e, pages)
    src = e.get('source') or {}
    meta = []
    if src.get('text'):
        url = safe_url(src.get('url'), allow_relative=False)
        if url and not action:
            meta.append('<a class="tl-source" href="%s" rel="noopener">%s</a>' % (esc(url), esc(src['text'])))
        else:
            meta.append('<span class="tl-source">%s</span>' % esc(src['text']))
    if e.get('confidence') in CONF_LABEL:
        meta.append('<span class="tl-conf" data-conf="%s">%s</span>' % (esc(e['confidence']), CONF_LABEL[e['confidence']]))
    if e.get('foundBy'):
        meta.append('<span class="tl-by">Found by %s</span>' % esc(e['foundBy']))
    body = ['<p class="tl-type"><svg class="tl-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" '
            'stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">%s</svg><span>%s</span></p>' % (ICONS[t], TYPE_LABELS[t]),
            '<h3 class="tl-headline">%s</h3>' % esc(e.get('headline'))]
    if e.get('changeNote'):
        body.append('<p class="tl-context">%s</p>' % esc(e['changeNote']))
    head = (e.get('headline') or '')
    was = [c for c in (e.get('change') or []) if c.get('from') and c['from'] not in head][:2]
    if was:
        body.append('<p class="tl-was">Previously %s.</p>' % esc('; '.join('%s: %s' % (c['field'], c['from']) for c in was)))
    if e.get('status') in STATUS_TEXT:
        body.append('<p class="tl-status">%s</p>' % STATUS_TEXT[e['status']])
    if meta:
        body.append('<p class="tl-meta">%s</p>' % '<span class="tl-dot" aria-hidden="true"> &middot; </span>'.join(meta))
    if action:
        body.append('<p class="tl-act"><a class="tl-action" href="%s">%s</a></p>' % (esc(action['href']), esc(action['label'])))
    img = safe_url(e.get('image'))
    thumb = ('<img class="tl-thumb" src="%s" alt="%s" loading="lazy" decoding="async">' % (esc(img), esc(e.get('imageAlt') or ''))) if img else ''
    return ('<li class="tl-card%s" id="find-%s" data-type="%s" data-lines="%s" data-published="%s" data-status="%s">'
            '<div class="tl-card-text">%s</div>%s</li>') % (
        ' tl-has-thumb' if thumb else '', esc(e['id']), t, esc(' '.join(e.get('lines') or [])), esc(e.get('published') or ''),
        esc(e.get('status') or 'current'), '\n'.join(body), thumb)


def render_body(entries, line_labels, cfg, pages, since=None):
    """The page's content: heading, banner, filters, and a section for each day with finds."""
    many_lines = len([l for l in line_labels if any(l['id'] in (e.get('lines') or []) for e in entries)]) >= 2
    days = {}
    for e in entries: days.setdefault(e['found'], []).append(e)
    parts = ['<div class="tl-root" data-collapse-over="%d" data-collapse-shown="%d" data-lines="%s">' % (
        COLLAPSE_OVER, COLLAPSE_SHOWN, esc(json.dumps({l['id']: l['label'] for l in line_labels}, ensure_ascii=False))),
        '<header class="tl-head"><h1>Discovery Timeline</h1>'
        '<p class="tl-lede">What the family has learned about its history, newest finds first.</p>%s</header>' % (
            ('<p class="tl-since">This timeline began on %s. What the family knew before then is not listed.</p>' % esc(long_date_plain(since))) if since else ''),
        '<div class="tl-banner" id="tlBanner" role="status" hidden><p class="tl-banner-text" id="tlBannerText"></p>'
        '<button type="button" class="tl-banner-go" id="tlJump">Jump to the first new find</button></div>']
    # filters (shown by the script; they do nothing without it)
    types = [t for t in TYPE_LABELS if any(e.get('type') == t for e in entries)]
    fl = []
    if many_lines:
        fl.append('<fieldset class="tl-fset"><legend>Family line</legend><div class="tl-chips" data-filter="line">'
                  '<button type="button" class="tl-chip" data-value="" aria-pressed="true">All lines</button>%s</div></fieldset>' % ''.join(
                      '<button type="button" class="tl-chip" data-value="%s" aria-pressed="false">%s</button>' % (esc(l['id']), esc(l['label']))
                      for l in line_labels if any(l['id'] in (e.get('lines') or []) for e in entries)))
    if len(types) > 1:
        fl.append('<fieldset class="tl-fset"><legend>Type of find</legend><div class="tl-chips" data-filter="type">'
                  '<button type="button" class="tl-chip" data-value="" aria-pressed="true">All types</button>%s</div></fieldset>' % ''.join(
                      '<button type="button" class="tl-chip" data-value="%s" aria-pressed="false">%s</button>' % (t, TYPE_LABELS[t]) for t in types))
    if fl:
        parts.append('<details class="tl-filters" id="tlFilters" hidden><summary>Filter finds</summary>%s</details>' % ''.join(fl))
    parts.append('<p class="tl-empty" id="tlEmpty" hidden>No finds match these filters.</p>')
    if not entries:
        parts.append('<p class="tl-none">Nothing has been found since the timeline began. New finds will appear here when they are published.</p>')
    parts.append('<ol class="tl-days" id="tlDays">')
    for day in sorted(days, reverse=True):
        es = days[day]
        extra = len(es) > COLLAPSE_OVER
        cards = []
        for i, e in enumerate(es):
            c = card(e, pages)
            if extra and i >= COLLAPSE_SHOWN: c = c.replace('<li class="tl-card', '<li class="tl-card tl-extra', 1)
            cards.append(c)
        parts.append('<li class="tl-day" data-date="%s" data-count="%d"><section aria-labelledby="day-%s">'
                     '<header class="tl-day-head"><h2 class="tl-date" id="day-%s"><time datetime="%s">%s</time></h2>'
                     '<p class="tl-summary">%s</p></header><ol class="tl-list">%s</ol>%s</section></li>' % (
                         day, len(es), day, day, day, esc(long_date(day)), esc(day_summary(es, line_labels, many_lines)), '\n'.join(cards),
                         ('<button type="button" class="tl-more" hidden>Show all %d finds</button>' % len(es)) if extra else ''))
    parts.append('</ol>')
    parts.append('<noscript><p class="tl-noscript">Filters and the “since your last visit” note need JavaScript. The finds above are all here without it.</p></noscript>')
    parts.append('</div>')
    return '\n'.join(parts)
