"""Loading a site's settings (site.config.json) and filling in what the site leaves out.

The settings are documented in docs/site-config.md and checked against schema/site-config.schema.json.
"""
import copy, json, os

import access, basic_access

DEFAULTS = {
    'schemaVersion': 1,
    'engine': {'channel': 'stable'},
    'site': {'name': '', 'familyName': 'this family', 'lang': 'en-GB', 'description': ''},
    'pages': {'home': 'index.html', 'tree': None, 'map': None, 'ask': None},
    'nav': [],
    'head': {'fonts': None, 'stylesheets': []},
    'theme': {},
    'data': {'dir': 'data'},
    'tree': {},
    'map': {},
    'stuart': {},
    'widget': {'enabled': True, 'exclude': []},
    'publish': {'exclude': []},
    'process': {'exclude': []},
}

# what each engine page needs if the site says nothing about it
PAGE_DEFAULTS = {
    'tree': {'file': 'family-tree.html', 'title': 'Family Tree', 'description': 'An interactive family tree.'},
    'map': {'file': 'map.html', 'title': 'Family Map', 'description': 'Where the family lived, married, worked and travelled, on a map and a timeline.'},
    'ask': {'file': 'ask.html', 'title': 'Ask Stuart', 'description': 'Stuart, the family archivist, answers questions from the records on this site.'},
}
# the Discovery Timeline is made only for a site that turns it on (timeline.enabled), so it is not in PAGE_DEFAULTS above
TIMELINE_PAGE = {'file': 'discoveries.html', 'title': 'Discovery Timeline',
                 'description': 'What the family has newly learned about its history, newest finds first.', 'label': 'Discoveries'}


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(site_dir):
    path = os.path.join(site_dir, 'site.config.json')
    if not os.path.exists(path):
        raise SystemExit('No site.config.json in %s. See docs/adding-a-site.md in the engine.' % site_dir)
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    cfg = merge(DEFAULTS, {k: v for k, v in raw.items() if not k.startswith('$')})
    # pages: a file name, an object with a file, or null when the site does not have that page
    pages = {'home': cfg['pages'].get('home') or 'index.html'}
    for k in ('tree', 'map', 'ask'):
        v = cfg['pages'].get(k)
        if not v:
            pages[k] = None
            continue
        if isinstance(v, str):
            v = {'file': v}
        pages[k] = merge(PAGE_DEFAULTS[k], v)
    cfg['pages'] = pages
    # the page names the engine scripts and Stuart's index use
    cfg['_pages'] = {'home': pages['home'], 'tree': pages['tree'] and pages['tree']['file'],
                     'map': pages['map'] and pages['map']['file'], 'ask': pages['ask'] and pages['ask']['file']}
    # the Discovery Timeline: only a site that turns it on gets the page, and a place in the navigation bar
    # (unless the site has put a link to the page there already)
    if (cfg.get('timeline') or {}).get('enabled'):
        tl = cfg['timeline']
        pages['timeline'] = merge({k: v for k, v in TIMELINE_PAGE.items() if k != 'label'}, {'file': tl['file']} if tl.get('file') else {})
        cfg['_pages']['timeline'] = pages['timeline']['file']
        if not any(isinstance(i, dict) and i.get('href') == pages['timeline']['file'] for i in cfg.get('nav') or []):
            cfg['nav'] = list(cfg.get('nav') or []) + [{'label': TIMELINE_PAGE['label'], 'href': pages['timeline']['file']}]
    # private access and visitor identity: both are off unless the site says enabled: true, and then nothing else changes
    cfg['_access'] = access.access_settings(raw)
    cfg['_visitor'] = access.visitor_settings(raw)
    cfg['_basic'] = basic_access.settings(raw)       # the stopgap password for a site not yet on Cloudflare (docs/basic-access.md)
    cfg['_raw'] = raw
    return cfg
