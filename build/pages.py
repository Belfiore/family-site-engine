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

ENGINE_CSS_GONE = {'nav.css', 'stuart.css', 'tree-canvas.css', 'map.css', 'tokens.css'}
ENGINE_JS_GONE = {'stuart.js', 'nav.js', 'config.js', 'tree-canvas.js', 'map-data.js', 'map-ui.js', 'map-timeline.js',
                  'map-player.js', 'map-steps.js', 'map-glyphs.js', 'archive-core.js', 'archive-kin.js',
                  'archive-dates.js', 'archive-search.js', 'site-config.js'}
ENGINE_SHARED = {'records.css', 'records.js'}

# what each engine page loads, in order
PAGE_ASSETS = {
    'tree': {'css': ['tree-canvas.css'], 'js': ['tree-canvas.js'],
             'viewport': 'width=device-width, initial-scale=1.0, viewport-fit=cover',
             'widget': {'compact': True, 'avoid': '.tc-minimap, .tc-controls, .tc-legend, .dr-foot'}},
    'map': {'css': ['records.css', 'vendor/maplibre-gl-5.24.1/maplibre-gl.css', 'map.css'],
            'js': ['vendor/maplibre-gl-5.24.1/maplibre-gl.js', 'records.js', 'map-glyphs.js', 'map-data.js', 'map-player.js',
                   'map-ui.js', 'map-steps.js', 'map-timeline.js'],
            'preconnect': ['https://tiles.openfreemap.org'],
            'viewport': 'width=device-width, initial-scale=1.0, viewport-fit=cover',
            'widget': {'compact': True, 'avoid': '.maplibregl-ctrl-bottom-right, .fm-attrib, .fm-tl, .fm-chips, .fm-key, .fm-key-pill, .fm-note, .fm-edition, .fm-peek, .fm-panel, .fm-sheet, .fm-events'}},
    'ask': {'css': [], 'js': ['archive-kin.js', 'archive-dates.js', 'archive-search.js', 'archive-core.js', 'stuart.js'],
            'viewport': 'width=device-width, initial-scale=1.0', 'csp': True, 'widget': None},
}


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


# ------------------------------------------------------------------ the navigation bar
def nav_items(cfg):
    return [i for i in cfg.get('nav') or [] if isinstance(i, dict)]


def nav_html(cfg, active):
    name = (cfg.get('site') or {}).get('name') or ''
    home = cfg['_pages']['home']
    lines = ['<nav class="main-nav" aria-label="Site">',
             '    <div class="nav-inner">',
             '        <a href="%s" class="nav-logo">%s</a>' % (esc(home), esc(name)),
             '        <div class="nav-links" id="navLinks">']
    for it in nav_items(cfg):
        if 'comment' in it:
            lines.append('            <!-- %s -->' % str(it['comment']).replace('--', '-'))
            continue
        href = it.get('href') or ''
        on = href == active
        lines.append('            <a href="%s"%s>%s</a>' % (esc(href), ' class="active" aria-current="page"' if on else '', esc(it.get('label'))))
    lines += ['        </div>',
              '        <button class="nav-toggle" id="navToggle" aria-label="Open menu" aria-expanded="false" aria-controls="navLinks">',
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
def render_engine_page(kind, template, cfg, ctx):
    page = cfg['pages'][kind]
    assets = PAGE_ASSETS[kind]
    head = []
    head += fonts_links(cfg)
    for u in assets.get('preconnect', []):
        head.append('<link rel="preconnect" href="%s" crossorigin>' % u)
    head.append('<link rel="stylesheet" href="%stokens.css">' % ctx['base'])
    sheets = page.get('stylesheets') if page.get('stylesheets') is not None else (cfg.get('head') or {}).get('stylesheets') or []
    head += ['<link rel="stylesheet" href="%s">' % esc(s) for s in sheets]
    head += ['<link rel="stylesheet" href="%s%s">' % (ctx['base'], c) for c in assets['css']]
    head += tail_css(cfg, ctx)
    scripts = settings_scripts(ctx) + ['<script src="%s%s"></script>' % (ctx['base'], j) for j in assets['js']]
    if stuart_on(cfg) and cfg['widget'].get('enabled', True) and assets.get('widget'):
        scripts.append(widget_tag(ctx, assets['widget']))
    tree = cfg.get('tree') or {}
    mp = cfg.get('map') or {}
    home_region = (mp.get('home') or {}).get('name') or 'the home region'
    fams = ''.join('\n                        <option value="%s">%s</option>' % (esc(f.get('id')), esc(f.get('option') or f.get('label')))
                   for f in mp.get('families') or [])
    values = {
        'lang': esc((cfg.get('site') or {}).get('lang') or 'en-GB'),
        'viewport': assets['viewport'],
        'csp': ('    <meta http-equiv="Content-Security-Policy" content="%s">\n' % csp_for(cfg)) if assets.get('csp') else '',
        'title': esc(page.get('title')),
        'description': esc(page.get('description')),
        'head': ''.join('    %s\n' % h for h in head),
        'nav': nav_html(cfg, page['file']),
        'scripts': '\n'.join(scripts),
        'directLineLabel': esc(tree.get('directLineLabel') or 'Direct line'),
        'familyLabel': esc(tree.get('familyLabel') or (cfg.get('site') or {}).get('name') or 'The family tree'),
        'homePage': esc(cfg['_pages']['home']),
        'familyOptions': fams,
        'homeRegion': esc(home_region),
        'mapNoscriptExtra': mp.get('noscript') or '',   # the site's own words; HTML allowed
        'legendNote': (' ' + tree['legendNote']) if tree.get('legendNote') else '',   # the site's own words; HTML allowed
        'heading': esc(page.get('heading') or {'tree': 'The Family Tree', 'map': 'The Family Map', 'ask': 'Ask Stuart'}[kind]),
        'treeNoscript': tree.get('noscript') or ('The <a href="%s">home page</a> and the other pages work without it.' % esc(cfg['_pages']['home'])),
        # the key's row for framed groups, only on a tree that has them
        'legendRegions': '                <li><span class="lg-card lg-card--frame"></span>Group whose link to the family is unproven</li>\n' if tree.get('regions') else '',
    }
    out = template
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


def process_site_page(src, filename, cfg, ctx, widget_opts):
    changed = []
    m = NAV_RE.search(src)
    if m:
        active = active_for(cfg, filename, m.group(0))
        src = src[:m.start()] + nav_html(cfg, active) + src[m.end():]
        changed.append('nav')
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
        src = src[:i] + '\n'.join(tail_css(cfg, ctx)) + '\n' + src[i:]
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
