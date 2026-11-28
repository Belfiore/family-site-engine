"""A small, safe Markdown renderer for the Stories page, using only the standard library.

It reads the Markdown that stories need: headings, paragraphs, bold and italic, links, images, lists, quotes,
rules and code. Everything the author types is escaped, so raw HTML in a story is shown as text and never runs,
and a link can only go to http, https, mailto, another page of the site or a place on the same page.
"""
import html, re

INLINE = re.compile(r"""
    (?P<code>`+)(?P<codetext>.+?)(?P=code)
  | !\[(?P<ialt>[^\]]*)\]\((?P<isrc>[^)\s]+)(?:\s+"(?P<ititle>[^"]*)")?\)
  | \[(?P<ltext>[^\]]+)\]\((?P<lhref>[^)\s]+)(?:\s+"(?P<ltitle>[^"]*)")?\)
  | <(?P<auto>https?://[^>\s]+)>
  | (?P<b>\*\*|__)(?=\S)(?P<btext>.+?)(?<=\S)(?P=b)
  | \*(?=[^\s*])(?P<i1>.+?)(?<=[^\s*])\*
  | (?<![\w])_(?=[^\s_])(?P<i2>.+?)(?<=[^\s_])_(?![\w])
""", re.X | re.S)


def esc(s):
    return html.escape(s, quote=True)


def safe_href(u):
    """The link as written if it is safe to put in a page, else None."""
    u = (u or '').strip()
    if not u: return None
    if u.startswith('#'): return u
    if re.match(r'^(https?://|mailto:)', u, re.I): return u
    if u.startswith('//') or re.match(r'^[a-z][a-z0-9+.-]*:', u, re.I): return None
    if '..' in u.split('/'): return None
    return u


def inline(text, resolve=None):
    """Inline Markdown to HTML. resolve(path) may rewrite a relative link or image (for the story's own folder)."""
    out, pos = [], 0
    for m in INLINE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        pos = m.end()
        if m.group('code'):
            out.append('<code>%s</code>' % esc(m.group('codetext').strip()))
        elif m.group('isrc') is not None:
            src = safe_href(m.group('isrc'))
            if src and not src.startswith('#') and not src.lower().startswith('mailto:'):
                if resolve: src = resolve(src)
                out.append('<img src="%s" alt="%s" loading="lazy">' % (esc(src), esc(m.group('ialt'))))
            else:
                out.append(esc(m.group(0)))
        elif m.group('lhref') is not None:
            href = safe_href(m.group('lhref'))
            if href is None:
                out.append(inline(m.group('ltext'), resolve))
            else:
                ext = re.match(r'^https?://', href, re.I)
                title = ' title="%s"' % esc(m.group('ltitle')) if m.group('ltitle') else ''
                out.append('<a href="%s"%s%s>%s</a>' % (esc(href), title, ' rel="noopener"' if ext else '', inline(m.group('ltext'), resolve)))
        elif m.group('auto'):
            out.append('<a href="%s" rel="noopener">%s</a>' % (esc(m.group('auto')), esc(m.group('auto'))))
        elif m.group('b'):
            out.append('<strong>%s</strong>' % inline(m.group('btext'), resolve))
        else:
            out.append('<em>%s</em>' % inline(m.group('i1') if m.group('i1') is not None else m.group('i2'), resolve))
    out.append(esc(text[pos:]))
    return ''.join(out)


def line_breaks(lines, resolve):
    parts = []
    for i, ln in enumerate(lines):
        hard = ln.endswith('  ') or ln.endswith('\\')
        ln = ln.rstrip().rstrip('\\') if ln.endswith('\\') else ln.strip()
        parts.append(inline(ln, resolve) + ('<br>' if hard and i < len(lines) - 1 else ''))
    return '\n'.join(parts)


BULLET = re.compile(r'^\s{0,3}([-*+])\s+(.*)$')
NUMBER = re.compile(r'^\s{0,3}(\d{1,9})[.)]\s+(.*)$')
HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*#*\s*$')
RULE = re.compile(r'^\s{0,3}([-*_])(\s*\1){2,}\s*$')


def render(text, resolve=None, top_heading=2):
    """Markdown to HTML. A "#" heading in a story becomes an h2 (the story's title is the h1) unless top_heading says otherwise."""
    lines = (text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        fence = re.match(r'^\s{0,3}(```+|~~~+)', ln)
        if fence:
            mark, code = fence.group(1), []
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith(mark):
                code.append(lines[i])
                i += 1
            i += 1
            out.append('<pre><code>%s</code></pre>' % esc('\n'.join(code)))
            continue
        h = HEADING.match(ln)
        if h:
            level = min(6, len(h.group(1)) + top_heading - 1)
            out.append('<h%d>%s</h%d>' % (level, inline(h.group(2), resolve), level))
            i += 1
            continue
        if RULE.match(ln):
            out.append('<hr>')
            i += 1
            continue
        if ln.lstrip().startswith('>'):
            quote = []
            while i < len(lines) and lines[i].lstrip().startswith('>'):
                quote.append(re.sub(r'^\s*>\s?', '', lines[i]))
                i += 1
            out.append('<blockquote>\n%s\n</blockquote>' % render('\n'.join(quote), resolve, top_heading))
            continue
        b, n = BULLET.match(ln), NUMBER.match(ln)
        if b or n:
            pat, tag = (BULLET, 'ul') if b else (NUMBER, 'ol')
            items = []
            while i < len(lines):
                m = pat.match(lines[i])
                if m:
                    items.append([m.group(2)])
                    i += 1
                elif lines[i].strip() and re.match(r'^\s{2,}\S', lines[i]) and items:
                    items[-1].append(lines[i].strip())
                    i += 1
                else:
                    break
            start = ' start="%s"' % n.group(1) if n and n.group(1) != '1' else ''
            out.append('<%s%s>\n%s\n</%s>' % (tag, start, '\n'.join('<li>%s</li>' % line_breaks(it, resolve) for it in items), tag))
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not (HEADING.match(lines[i]) or RULE.match(lines[i]) or lines[i].lstrip().startswith(('>', '```', '~~~'))
                                                          or BULLET.match(lines[i]) or NUMBER.match(lines[i])):
            para.append(lines[i])
            i += 1
        if not para:                  # a line that matched nothing and is not a paragraph start: take it as text
            para.append(lines[i])
            i += 1
        out.append('<p>%s</p>' % line_breaks(para, resolve))
    return '\n'.join(out)


def plain(text):
    """The text of Markdown without its marks (for a summary taken from the first paragraph)."""
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text or '')
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)
    t = re.sub(r'[*_`>#]+', '', t)
    return re.sub(r'\s+', ' ', t).strip()
