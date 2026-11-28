"""The settings page at /admin/: a static page that edits site.config.json in the site's GitHub repository.

The page is made at build time for a site that turns it on (admin.enabled). It carries what the build knows (the
site's name, the pages and which are on, the engine channel) as data, and engine/admin.js does the rest in the
browser: it signs in with a GitHub token the person pastes (kept only in that browser tab), checks that the person
can write to the repository, shows what will change, and commits the file through the GitHub API. The commit starts
the site's normal rebuild. Nothing about the token is ever written to the page, the repository or the console.
See docs/admin.md.
"""
import html, json, os

import heritage, i18n, sitecfg

CHANNELS = ('stable', 'beta', 'canary')


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def style_data(cfg, site):
    """The heritage styles, the one the site has, and what the family's own data suggests (heritage.suggest). A suggestion
    is only ever shown: nothing here changes a setting."""
    reg = heritage.registry()
    names = {t['id']: t['name'] for t in reg['themes']}
    raw = cfg.get('_raw') or {}
    block = raw.get('style') if isinstance(raw.get('style'), dict) else {}
    saved = block.get('heritage') if block.get('heritage') in names else 'classic'
    opts = block.get('options') if isinstance(block.get('options'), dict) else {}
    suggestion = None
    if site:
        try:
            s = heritage.suggest(site, cfg)
            suggestion = {'suggested': s['suggested'], 'mixed': bool(s['mixed']), 'thin': bool(s['thin']), 'reason': s['reason'],
                          'ranked': [{'id': r['id'], 'name': names.get(r['id'], r['id']), 'percent': r['percent']} for r in s['ranked']]}
        except (OSError, ValueError, KeyError, TypeError):      # a site whose data cannot be read still gets the page; the build's own checks report the data
            suggestion = None
    themes = [{'id': t['id'], 'name': t['name'], 'blurb': t['blurb'], 'fonts': t['fonts'], 'swatches': t['swatches'],
               'options': t.get('options') or {}} for t in reg['themes']]
    return {'themes': themes, 'saved': saved, 'texture': opts.get('texture') is not False, 'suggestion': suggestion}


def language_data(cfg):
    """The languages the engine has words for, and the site's choice (the same reading the build makes)."""
    st = i18n.settings(cfg.get('_raw') or cfg)
    en = i18n.load('en')
    return {'have': [{'code': c, 'name': en.get('lang.' + c, c)} for c in i18n.languages()],
            'default': st['default'], 'available': st['available']}


def data_for(cfg, version, site_dir=None):
    """What the page is given, from the settings as built."""
    adm = cfg['_admin']
    site = cfg.get('site') or {}
    pages = []
    for key in sitecfg.STANDARD_PAGES:
        t = cfg['_toggles'][key]
        pages.append({'key': key, 'label': sitecfg.PAGE_LABELS[key], 'file': t['file'], 'on': bool(t['on']), 'made': bool(t['made']),
                      'locked': key == 'home'})
    return {'engine': version, 'repo': adm['repo'], 'branch': adm['branch'], 'configPath': adm['configPath'],
            'home': cfg['_pages']['home'], 'channels': list(CHANNELS),
            'site': {'name': site.get('name') or '', 'description': site.get('description') or ''},
            'engineSettings': {'channel': (cfg.get('engine') or {}).get('channel') or 'stable', 'version': (cfg.get('engine') or {}).get('version') or None},
            'pages': pages, 'language': language_data(cfg), 'style': style_data(cfg, site_dir)}


def render(template, cfg, ctx, version, site=None):
    # inside a <script> block: no "</" and no "<!--", whatever the site's own words are
    blob = json.dumps(data_for(cfg, version, site), ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    base = '../' + ctx['base']
    values = {'lang': esc((cfg.get('site') or {}).get('lang') or 'en-GB'),
              'siteName': esc((cfg.get('site') or {}).get('name') or 'this site'),
              'base': base, 'backHref': esc('../' + cfg['_pages']['home']),
              'theme': ('    <link rel="stylesheet" href="../%s">\n' % esc(ctx['theme'])) if ctx.get('theme') else '',
              'heritage': ''.join('    %s\n' % t for t in heritage.head_tags(cfg, {'base': base})),
              'data': blob}
    out = template
    for k, v in values.items(): out = out.replace('{{%s}}' % k, v)
    return heritage.mark_html(out, cfg)
