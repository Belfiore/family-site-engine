"""The settings page at /admin/: a static page that edits site.config.json in the site's GitHub repository.

The page is made at build time for a site that turns it on (admin.enabled). It carries what the build knows (the
site's name, the pages and which are on, the engine channel) as data, and engine/admin.js does the rest in the
browser: it signs in with a GitHub token the person pastes (kept only in that browser tab), checks that the person
can write to the repository, shows what will change, and commits the file through the GitHub API. The commit starts
the site's normal rebuild. Nothing about the token is ever written to the page, the repository or the console.
See docs/admin.md.
"""
import html, json, os

import sitecfg

CHANNELS = ('stable', 'beta', 'canary')


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def data_for(cfg, version):
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
            'pages': pages}


def render(template, cfg, ctx, version):
    # inside a <script> block: no "</" and no "<!--", whatever the site's own words are
    blob = json.dumps(data_for(cfg, version), ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    base = '../' + ctx['base']
    values = {'lang': esc((cfg.get('site') or {}).get('lang') or 'en-GB'),
              'siteName': esc((cfg.get('site') or {}).get('name') or 'this site'),
              'base': base, 'backHref': esc('../' + cfg['_pages']['home']),
              'theme': ('    <link rel="stylesheet" href="../%s">\n' % esc(ctx['theme'])) if ctx.get('theme') else '',
              'data': blob}
    out = template
    for k, v in values.items(): out = out.replace('{{%s}}' % k, v)
    return out
