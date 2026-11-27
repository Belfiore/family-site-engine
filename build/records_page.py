"""The Records and Research page: the records the site relies on, and the questions its researchers still have.

Made from data/sources.json (every record, grouped by kind, with where it is kept) and from the open questions on
people who are not living and are shown on the tree. Nothing is invented: a site with no sources gets a page that
says so. See docs/site-config.md (pages.records).
"""
import html, json, os, re

import stories as st


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def read_sources(site, cfg):
    p = os.path.join(site, (cfg.get('data') or {}).get('dir') or 'data', 'sources.json')
    try:
        with open(p, encoding='utf-8') as f: return [s for s in json.load(f).get('sources') or [] if isinstance(s, dict) and s.get('title')]
    except (OSError, ValueError):
        return []


def target(src, site):
    """Where a record's title links to: its web address, or a file in the site."""
    u = (src.get('url') or '').strip()
    if re.match(r'^https?://', u, re.I): return u
    f = (src.get('file') or '').strip()
    if f and not re.match(r'^[a-z][a-z0-9+.-]*:|^//', f, re.I) and '..' not in f.split('/') and os.path.exists(os.path.join(site, f)): return f
    return None


def body(site, cfg):
    page = cfg['pages']['records']
    sources = read_sources(site, cfg)
    by = st.people_by_id(site, cfg)
    tree = (cfg['pages'].get('tree') or {}).get('file')
    out = ['<header class="cp-head"><h1>%s</h1></header>' % esc(page.get('heading') or page.get('title') or 'Records and Research')]
    kinds = {}
    for s in sources: kinds.setdefault((s.get('type') or 'other').strip().lower() or 'other', []).append(s)
    if not sources:
        out.append('<p class="cp-empty">No records have been added to this site yet.</p>')
    else:
        out.append('<p class="cp-intro">%d record%s, in %d kind%s of source.</p>' % (
            len(sources), '' if len(sources) == 1 else 's', len(kinds), '' if len(kinds) == 1 else 's'))
        for kind in sorted(kinds):
            out.append('<section class="cp-group" aria-labelledby="rec-%s">' % esc(re.sub(r'[^a-z0-9]+', '-', kind)))
            out.append('<h2 id="rec-%s">%s <span class="cp-count">%d</span></h2>' % (esc(re.sub(r'[^a-z0-9]+', '-', kind)), esc(kind[:1].upper() + kind[1:]), len(kinds[kind])))
            out.append('<ul class="cp-records">')
            for s in sorted(kinds[kind], key=lambda x: (x['title'].lower(), x.get('id') or '')):
                t = target(s, site)
                title = '<a href="%s"%s>%s</a>' % (esc(t), ' rel="noopener"' if t.startswith('http') else '', esc(s['title'])) if t else esc(s['title'])
                bits = [esc(b) for b in (s.get('repository'), s.get('date')) if b]
                out.append('<li id="%s"><span class="cp-rec-title">%s</span>%s%s</li>' % (
                    esc(s.get('id') or ''), title, ('<span class="cp-rec-where">%s</span>' % ', '.join(bits)) if bits else '',
                    ('<span class="cp-rec-note">%s</span>' % esc(s['note'])) if s.get('note') else ''))
            out.append('</ul></section>')
    # what the researchers still want to find, for people the site shows
    rows = []
    for pid, p in sorted(by.items(), key=lambda kv: (kv[1].get('displayName') or kv[0]).lower()):
        if not p.get('openQuestions') or not st.taggable(p, cfg): continue
        name = esc(p.get('displayName') or pid)
        who = '<a href="%s#/person/%s">%s</a>' % (esc(tree), esc(pid), name) if tree else name
        for q in p['openQuestions']:
            if not isinstance(q, dict) or not q.get('question'): continue
            rows.append('<li><span class="cp-q-who">%s</span> <span class="cp-q">%s</span>%s</li>' % (
                who, esc(q['question']), ('<span class="cp-rec-note">A record that could answer it: %s</span>' % esc(q['record'])) if q.get('record') else ''))
    if rows:
        out.append('<section class="cp-group" aria-labelledby="rec-questions"><h2 id="rec-questions">Open questions <span class="cp-count">%d</span></h2>' % len(rows))
        out.append('<ul class="cp-records">\n%s\n</ul></section>' % '\n'.join(rows))
    return '\n'.join(out)
