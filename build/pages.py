"""Pages: the navigation bar, the engine's own pages (tree, map, Stuart) and the site's own pages.

The engine owns three things on every page: the navigation bar, the engine's stylesheets and scripts, and
Stuart's button. Everything else in a site's own pages is left exactly as the site wrote it.

On the site's own pages the build:
  * replaces the <nav class="main-nav"> block with the bar from site.config.json "nav", keeping which link
    is lit (from data-active on the nav, else the link the page marked active, else the page's own name);
  * removes references to engine files the page may still carry from before the engine (nav.css, stuart.js,
    tree-canvas.js ...) and points records.css and records.js at the engine's copies;
  * adds Stuart's stylesheet, the theme and nav.css (last, so nothing overrides the bar) to the head, and
    the site settings, the menu script and Stuart's button at the end of the body.
"""
import html, os, re
from urllib.parse import urlparse

import i18n

ENGINE_CSS_GONE = {'nav.css', 'stuart.css', 'tree-canvas.css', 'map.css', 'tokens.css', 'source-preview.css'}
ENGINE_JS_GONE = {'stuart.js', 'nav.js', 'config.js', 'tree-canvas.js', 'map-data.js', 'map-ui.js', 'map-timeline.js',
                  'map-player.js', 'map-steps.js', 'map-glyphs.js', 'archive-core.js', 'archive-kin.js',
                  'archive-dates.js', 'archive-search.js', 'site-config.js', 'kinship.js', 'map-viewpoint.js', 'source-preview.js'}
ENGINE_SHARED = {'records.css', 'records.js'}

# what each engine page loads, in order
PAGE_ASSETS = {
    'tree': {'css': ['tree-canvas.css'], 'js': ['kinship.js', 'tree-canvas.js'],
             'viewport': 'width=device-width, initial-scale=1.0, viewport-fit=cover',
             'widget': {'compact': True, 'avoid': '.tc-minimap, .tc-controls, .tc-legend, .dr-foot'}},
    'map': {'css': ['records.css', 'vendor/maplibre-gl-5.24.1/maplibre-gl.css', 'map.css', 'source-preview.css'],
            'js': ['vendor/maplibre-gl-5.24.1/maplibre-gl.js', 'records.js', 'kinship.js', 'map-glyphs.js', 'map-data.js', 'map-player.js',
                   'map-viewpoint.js', 'source-preview.js', 'map-ui.js', 'map-steps.js', 'map-timeline.js'],
            'preconnect': ['https://tiles.openfreemap.org'],
            'viewport': 'width=device-width, initial-scale=1.0, viewport-fit=cover',
            'widget': {'compact': True, 'avoid': '.maplibregl-ctrl-bottom-right, .fm-attrib, .fm-tl, .fm-chips, .fm-key, .fm-key-pill, .fm-note, .fm-edition, .fm-peek, .fm-panel, .fm-sheet, .fm-events, .sp-drawer, .sp-card'}},
    'ask': {'css': [], 'js': ['archive-kin.js', 'archive-dates.js', 'archive-search.js', 'archive-core.js', 'stuart.js'],
            'viewport': 'width=device-width, initial-scale=1.0', 'csp': True, 'widget': None},
    'timeline': {'css': ['timeline.css'], 'js': ['timeline.js'],
                 'viewport': 'width=device-width, initial-scale=1.0, viewport-fit=cover',
                 'widget': {'compact': True}},
    # Stories and Records and Research: pages made from the site's own files, with no script of their own
    'stories': {'css': ['content-pages.css'], 'js': [], 'viewport': 'width=device-width, initial-scale=1.0, viewport-fit=cover',
                'widget': {'compact': True}},
    'records': {'css': ['content-pages.css'], 'js': [], 'viewport': 'width=device-width, initial-scale=1.0, viewport-fit=cover',
                'widget': {'compact': True}},
}


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


# ------------------------------------------------------------------ the navigation bar
def nav_items(cfg):
    return [i for i in cfg.get('nav') or [] if isinstance(i, dict)]


# the engine's own page names: a site that keeps one of these English names and gives no word of its own for a language
# gets the dictionary's
DEFAULT_NAMES = {'Home': 'nav.home', 'Family Tree': 'nav.tree', 'Family Map': 'nav.map', 'Ask Stuart': 'nav.ask', 'Discoveries': 'nav.discoveries'}


def other_word(obj, field, lang, base):
    """The site's word for a language, else the dictionary's word for one of the engine's own page names, else None."""
    v = obj.get(field + '_' + lang)
    if v: return v
    if lang == 'en': return base
    key = DEFAULT_NAMES.get(base) if field in ('label', 'title', 'heading') else None
    return i18n.raw(lang, key) if key else None


def words(cfg, obj, field):
    """A site's own words in its default language, and the attributes that give the other languages: ("text", ' data-label-en="..."').

    A site writes `label` and, where it wants, `label_de`. Without a language setting this is just the label."""
    st = i18n.settings(cfg)
    base = (obj or {}).get(field)
    if not st['active']:
        return base, ''
    shown = (other_word(obj, field, st['default'], base) if st['default'] != 'en' else base)
    shown = shown or base
    attrs = ''
    if st['switcher'] or st['default'] != 'en':
        for l in st['available']:
            if l == st['default']: continue
            v = other_word(obj, field, l, base)
            if v and v != shown: attrs += ' data-label-%s="%s"' % (l, esc(v))
    return shown, attrs


def html_words(cfg, obj, field):
    """Like words(), for a site's text that may hold HTML: (shown markup, attributes giving the other languages as markup)."""
    st = i18n.settings(cfg)
    base = (obj or {}).get(field)
    if not st['active']:
        return base, ''
    shown = (obj.get(field + '_' + st['default']) or base) if st['default'] != 'en' else base
    attrs = ''
    if st['switcher'] or st['default'] != 'en':
        for l in st['available']:
            if l == st['default']: continue
            v = obj.get(field + '_' + l) or (base if l == 'en' else None)
            if v and v != shown: attrs += ' data-html-%s="%s"' % (l, esc(v))
    return shown, attrs


def nav_html(cfg, active):
    lang = i18n.settings(cfg)['default']
    site = cfg.get('site') or {}
    name, name_attrs = words(cfg, site, 'name')
    name = name or ''
    home = cfg['_pages']['home']
    lines = ['<nav class="main-nav" aria-label="%s">' % esc(i18n.t(lang, 'nav.site')),
             '    <div class="nav-inner">',
             '        <a href="%s" class="nav-logo"%s>%s</a>' % (esc(home), name_attrs, esc(name)),
             '        <div class="nav-links" id="navLinks">']
    for it in nav_items(cfg):
        if 'comment' in it:
            lines.append('            <!-- %s -->' % str(it['comment']).replace('--', '-'))
            continue
        href = it.get('href') or ''
        on = href == active
        label, attrs = words(cfg, it, 'label')
        lines.append('            <a href="%s"%s%s>%s</a>' % (esc(href), ' class="active" aria-current="page"' if on else '', attrs, esc(label)))
    lines += ['        </div>',
              '        <button class="nav-toggle" id="navToggle" aria-label="%s" aria-expanded="false" aria-controls="navLinks">' % esc(i18n.t(lang, 'nav.openMenu')),
              '            <span></span><span></span><span></span>',
              '        </button>',
              '    </div>',
              '</nav>']
    return '\n'.join(lines)


def active_for(cfg, filename, nav_block=None):
    """Which nav link is lit on this page."""
    if nav_block:
        m = re.search(r'data-active="([^"]+)"', nav_block)
        if m: return m.group(1)
        m = re.search(r'<a\b[^>]*\bhref="([^"#]+)[^"]*"[^>]*\bclass="[^"]*\bactive\b', nav_block) or \
            re.search(r'<a\b[^>]*\bclass="[^"]*\bactive\b[^"]*"[^>]*\bhref="([^"#]+)', nav_block)
        if m: return m.group(1)
    for it in nav_items(cfg):
        if it.get('href') == filename or filename in (it.get('match') or []):
            return it.get('href')
    return None


# ------------------------------------------------------------------ head and body pieces
def stuart_on(cfg):
    return bool(cfg['_pages'].get('ask'))


def widget_tag(ctx, opts):
    if opts is None: return ''
    attrs = ' data-widget'
    if opts.get('compact'): attrs += ' data-compact'
    if opts.get('avoid'): attrs += ' data-avoid="%s"' % esc(opts['avoid'])
    return '<script src="%sstuart.js"%s defer></script>' % (ctx['base'], attrs)


def tail_css(cfg, ctx):
    """Stuart's stylesheet, the theme and the bar's stylesheet, in that order, at the end of the head."""
    out = []
    if stuart_on(cfg): out.append('<link rel="stylesheet" href="%sstuart.css">' % ctx['base'])
    if ctx.get('theme'): out.append('<link rel="stylesheet" href="%s">' % ctx['theme'])
    out.append('<link rel="stylesheet" href="%snav.css">' % ctx['base'])
    return out


def visitor_head(cfg, ctx):
    """The visitor files, in the head so the page can be held back until "Who are you?" is answered. Nothing for a site without visitor."""
    if not cfg.get('_visitor'): return []
    return ['<link rel="stylesheet" href="%svisitor.css">' % ctx['base'],
            '<script src="%svisitor-match.js"></script>' % ctx['base'],
            '<script src="%svisitor.js"></script>' % ctx['base']]


def settings_scripts(ctx):
    return ['<script src="%s"></script>' % ctx['config'], '<script src="%snav.js" defer></script>' % ctx['base']]


def fonts_links(cfg):
    fonts = (cfg.get('head') or {}).get('fonts')
    if not fonts: return []
    out = []
    if 'fonts.googleapis.com' in fonts:
        out += ['<link rel="preconnect" href="https://fonts.googleapis.com">',
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>']
    out.append('<link href="%s" rel="stylesheet">' % esc(fonts))
    return out


def csp_for(cfg):
    fonts = (cfg.get('head') or {}).get('fonts') or ''
    style_hosts, font_hosts = [], []
    if fonts:
        host = '%s://%s' % (urlparse(fonts).scheme or 'https', urlparse(fonts).netloc)
        style_hosts.append(host)
        font_hosts.append('https://fonts.gstatic.com' if 'fonts.googleapis.com' in host else host)
    return ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'%s; font-src 'self'%s; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'") % (
        ''.join(' ' + h for h in style_hosts), ''.join(' ' + h for h in font_hosts))


# ------------------------------------------------------------------ the engine's own pages
def render_engine_page(kind, template, cfg, ctx, extra=None):
    page = cfg['pages'][kind]
    assets = PAGE_ASSETS[kind]
    head = []
    head += fonts_links(cfg)
    for u in assets.get('preconnect', []):
        head.append('<link rel="preconnect" href="%s" crossorigin>' % u)
    head.append('<link rel="stylesheet" href="%stokens.css">' % ctx['base'])
    sheets = page.get('stylesheets') if page.get('stylesheets') is not None else (cfg.get('head') or {}).get('stylesheets') or []
    head += ['<link rel="stylesheet" href="%s">' % esc(s) for s in sheets]
    css, js = assets['css'], assets['js']
    if kind == 'timeline' and 'tl-thumb-link' in ((extra or {}).get('timelineBody') or ''):
        css, js = ['records.css'] + css, ['records.js'] + js       # a find with a picture: it opens large in the engine's lightbox
    head += ['<link rel="stylesheet" href="%s%s">' % (ctx['base'], c) for c in css]
    head += tail_css(cfg, ctx)
    head += visitor_head(cfg, ctx)
    scripts = settings_scripts(ctx) + ['<script src="%s%s"></script>' % (ctx['base'], j) for j in js]
    if stuart_on(cfg) and cfg['widget'].get('enabled', True) and assets.get('widget'):
        scripts.append(widget_tag(ctx, assets['widget']))
    tree = cfg.get('tree') or {}
    mp = cfg.get('map') or {}
    home_name = (mp.get('home') or {}).get('name')
    fams = ''.join('\n                        <option value="%s">%s</option>' % (esc(f.get('id')), esc(f.get('option') or f.get('label')))
                   for f in mp.get('families') or [])
    st = i18n.settings(cfg)
    title_text, title_attrs = words(cfg, page, 'title')
    if page.get('heading'):
        head_text, head_attrs = words(cfg, page, 'heading')
    elif kind in ('tree', 'map', 'ask'):
        head_text = i18n.t(st['default'], kind + '.heading')
        head_attrs = ' data-i18n="%s.heading"' % kind if st['switcher'] else ''
    else:
        head_text, head_attrs = title_text, title_attrs
    if tree.get('directLineLabel'):
        dl_text, dl_attrs = words(cfg, tree, 'directLineLabel')
        direct_line = '<span%s>%s</span>' % (dl_attrs, esc(dl_text)) if dl_attrs else esc(dl_text)
    else:
        direct_line = i18n.span(cfg, 'tree.directLine')
    legend_note = ''
    if tree.get('legendNote'):
        note_text, note_attrs = html_words(cfg, tree, 'legendNote')
        legend_note = ' <span%s>%s</span>' % (note_attrs, note_text) if note_attrs else ' ' + note_text    # the site's own words; HTML allowed
    home_url = esc(cfg['_pages']['home'])
    values = {
        'lang': esc((cfg.get('site') or {}).get('lang') or 'en-GB') if i18n.settings(cfg)['default'] == 'en' else i18n.settings(cfg)['default'],
        'viewport': assets['viewport'],
        'csp': ('    <meta http-equiv="Content-Security-Policy" content="%s">\n' % csp_for(cfg)) if assets.get('csp') else '',
        'title': esc(title_text),
        'titleAttr': title_attrs,
        'headingAttr': head_attrs,
        'description': esc(page.get('description')),
        'head': ''.join('    %s\n' % h for h in head),
        'nav': nav_html(cfg, (extra or {}).get('_active') or page['file']),
        'scripts': '\n'.join(scripts),
        'directLineLabel': direct_line,
        'homePage': esc(cfg['_pages']['home']),
        'familyOptions': fams,
        'backHome': esc(i18n.t(st['default'], 'map.backTo', place=(((mp.get('home') or {}).get('name_' + st['default']) if st['default'] != 'en' else None) or home_name)) if home_name else i18n.t(st['default'], 'map.backHome')),
        'mapNoscriptExtra': (html_words(cfg, mp, 'noscript')[0] if mp.get('noscript') else ''),   # the site's own words; HTML allowed
        'legendNote': legend_note,
        'heading': esc(head_text),
        'timelineBody': '',
        'pageBody': '',
        'treeNoscript': (html_words(cfg, tree, 'noscript')[0] if tree.get('noscript') else i18n.t(st['default'], 'tree.noscriptHome', home=home_url)),
        # the key's row for framed groups, only on a tree that has them
        'legendRegions': '                <li><span class="lg-card lg-card--frame"></span>%s</li>\n' % i18n.span(cfg, 'tree.legendRegions') if tree.get('regions') else '',
    }
    values.update({k: v for k, v in (extra or {}).items() if not k.startswith('_')})   # what only one page has: the timeline's content, made by timeline.py
    out = i18n.template(template, cfg)
    for k, v in values.items():
        out = out.replace('{{%s}}' % k, v)
    left = re.findall(r'\{\{[a-zA-Z]+\}\}', out)
    if left: raise SystemExit('template %s: no value for %s' % (kind, ', '.join(sorted(set(left)))))
    return out


# ------------------------------------------------------------------ the site's own pages
NAV_RE = re.compile(r'<nav\b[^>]*\bclass="[^"]*\bmain-nav\b[^"]*"[^>]*>.*?</nav>', re.S)
LINK_RE = re.compile(r'[ \t]*<link\b[^>]*\bhref="([^"]+)"[^>]*>[ \t]*\n?', re.I)
SCRIPT_RE = re.compile(r'[ \t]*<script\b([^>]*)\bsrc="([^"]+)"([^>]*)>\s*</script>[ \t]*\n?', re.I)


def bare(url):
    u = url.split('?')[0].split('#')[0]
    return u if '/' not in u else None


def unlink_off_pages(src, off_files):
    """A link in the page's own words to a page that is switched off is shown as plain text, so nothing leads to a page
    that is not there. Only links to those pages are touched, and only on a site that has turned a page off."""
    if not off_files: return src
    names = '|'.join(re.escape(f) for f in sorted(off_files))
    anchor = re.compile(r'<a\b[^>]*?\bhref\s*=\s*(?:"(?:%s)(?:[#?][^"]*)?"|\'(?:%s)(?:[#?][^\']*)?\')[^>]*>(.*?)</a>' % (names, names), re.S | re.I)
    return anchor.sub(lambda m: m.group(1), src)


def process_site_page(src, filename, cfg, ctx, widget_opts):
    changed = []
    m = NAV_RE.search(src)
    if m:
        active = active_for(cfg, filename, m.group(0))
        src = src[:m.start()] + nav_html(cfg, active) + src[m.end():]
        changed.append('nav')
    src = unlink_off_pages(src, cfg.get('_off_files'))
    widget_attrs = None

    def fix_link(mm):
        name = bare(mm.group(1))
        if name in ENGINE_CSS_GONE: return ''
        if name in ENGINE_SHARED: return mm.group(0).replace(mm.group(1), ctx['base'] + name)
        return mm.group(0)

    def fix_script(mm):
        nonlocal widget_attrs
        name = bare(mm.group(2))
        if name == 'stuart.js':
            widget_attrs = mm.group(1) + mm.group(3)
            return ''
        if name in ENGINE_JS_GONE: return ''
        if name in ENGINE_SHARED: return mm.group(0).replace(mm.group(2), ctx['base'] + name)
        return mm.group(0)

    src = LINK_RE.sub(fix_link, src)
    src = SCRIPT_RE.sub(fix_script, src)
    # the head ends with Stuart's stylesheet, the theme and nav.css
    i = src.lower().rfind('</head>')
    if i >= 0:
        src = src[:i] + '\n'.join(tail_css(cfg, ctx) + visitor_head(cfg, ctx)) + '\n' + src[i:]
    # the body ends with the settings, the menu script and Stuart's button
    tail = settings_scripts(ctx)
    if widget_opts is not None:
        opts = dict(widget_opts)
        if widget_attrs:
            if 'data-compact' in widget_attrs: opts['compact'] = True
            a = re.search(r'data-avoid="([^"]*)"', widget_attrs)
            if a: opts.setdefault('avoid', html.unescape(a.group(1)))
        tail.append(widget_tag(ctx, opts))
    j = src.lower().rfind('</body>')
    if j >= 0:
        src = src[:j] + '\n'.join(tail) + '\n' + src[j:]
    return src


# ------------------------------------------------------------------ the sitemap
def clean_sitemap(out, off_files, admin_on, stories_off):
    """Take every entry for a page that is turned off (and for /admin/) out of a sitemap.xml the site keeps itself.
    A site without a sitemap, or with no page off and no /admin/, is left exactly as it was. Returns what was removed."""
    path = os.path.join(out, 'sitemap.xml')
    if not os.path.exists(path) or not (off_files or admin_on or stories_off): return []
    with open(path, encoding='utf-8') as f:
        text = f.read()
    removed = []

    def gone(loc):
        p = urlparse(loc.strip()).path.rstrip('/') if '://' in loc else loc.strip().split('#')[0].split('?')[0].rstrip('/')
        name = p.rsplit('/', 1)[-1]
        if admin_on and (p.endswith('/admin') or p.endswith('/admin/index.html')): return True
        if name in off_files and not os.path.exists(os.path.join(out, name)): return True
        if stories_off and re.match(r'^story-[a-z0-9-]+\.html$', name) and not os.path.exists(os.path.join(out, name)): return True
        return False

    def keep(m):
        loc = re.search(r'<loc>\s*([^<]+?)\s*</loc>', m.group(0))
        if loc and gone(html.unescape(loc.group(1))):
            removed.append(html.unescape(loc.group(1)))
            return ''
        return m.group(0)

    new = re.sub(r'[ \t]*<url>.*?</url>[ \t]*\n?', keep, text, flags=re.S)
    if new != text:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new)
    return removed
