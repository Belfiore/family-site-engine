"""Loading a site's settings (site.config.json) and filling in what the site leaves out.

The settings are documented in docs/site-config.md and checked against schema/site-config.schema.json.
"""
import copy, json, os

import access

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
# the Discovery Timeline is made only for a site that turns it on (pages.discoveries, or timeline.enabled), so it is not in PAGE_DEFAULTS above
TIMELINE_PAGE = {'file': 'discoveries.html', 'title': 'Discovery Timeline',
                 'description': 'What the family has newly learned about its history, newest finds first.', 'label': 'Discoveries'}
# Stories and Records and Research: pages of the site's own words and sources, made from files in the site's repository
STORIES_PAGE = {'file': 'stories.html', 'title': 'Stories', 'label': 'Stories',
                'description': 'Stories, articles and essays about the family.'}
RECORDS_PAGE = {'file': 'records.html', 'title': 'Records and Research', 'label': 'Records',
                'description': 'The records this site relies on, and where each one is kept.'}
STORIES_DIR = os.path.join('content', 'stories')

# the six standard pages, in the order the admin page shows them. Home cannot be turned off.
STANDARD_PAGES = ('home', 'stories', 'tree', 'map', 'records', 'discoveries')
PAGE_LABELS = {'home': 'Home', 'stories': 'Stories', 'tree': 'Family Tree', 'map': 'Family Map',
               'records': 'Records and Research', 'discoveries': 'Discoveries'}


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def page_state(v):
    """What the value of one key in "pages" says about that page:
    'on' (true, a file name, or an object that is not switched off), 'off' (false, or an object with enabled false),
    or 'none' (null, or the key is not there)."""
    if v is None or v == '' or v == {}: return 'none'      # an empty value has always meant "no such page"
    if v is False: return 'off'
    if isinstance(v, dict): return 'off' if v.get('enabled') is False else 'on'
    return 'on'


def page_object(v):
    """The settings object inside a pages value (empty for true or a file name), without the on/off switch."""
    if isinstance(v, str): return {'file': v}
    if isinstance(v, dict): return {k: x for k, x in v.items() if k != 'enabled'}
    return {}


def stories_present(site_dir):
    d = os.path.join(site_dir, STORIES_DIR)
    try:
        return any(n.lower().endswith('.md') and not n.startswith(('.', '_')) for n in os.listdir(d))
    except OSError:
        return False


def load(site_dir):
    path = os.path.join(site_dir, 'site.config.json')
    if not os.path.exists(path):
        raise SystemExit('No site.config.json in %s. See docs/adding-a-site.md in the engine.' % site_dir)
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    cfg = merge(DEFAULTS, {k: v for k, v in raw.items() if not k.startswith('$')})
    rp = raw.get('pages') if isinstance(raw.get('pages'), dict) else {}
    # pages: true, a file name, an object with a file, false, or null when the site does not have that page
    home = cfg['pages'].get('home')
    pages = {'home': home if isinstance(home, str) and home else 'index.html'}
    toggles = {'home': {'on': True, 'state': 'locked', 'made': True, 'file': pages['home']}}
    off_files = {}          # pages switched off with false: the navigation bar drops the link to each
    for k in ('tree', 'map', 'ask'):
        v = rp.get(k)
        st = page_state(v)
        page = merge(PAGE_DEFAULTS[k], page_object(v))
        if st == 'off': off_files[page['file']] = k
        pages[k] = page if st == 'on' else None
        toggles[k] = {'on': st == 'on', 'state': st, 'made': st == 'on', 'file': page['file']}
    cfg['pages'] = pages
    # the page names the engine scripts and Stuart's index use
    cfg['_pages'] = {'home': pages['home'], 'tree': pages['tree'] and pages['tree']['file'],
                     'map': pages['map'] and pages['map']['file'], 'ask': pages['ask'] and pages['ask']['file']}
    added = []              # pages the build adds to the navigation bar itself (unless the site has put a link there already)

    # Stories and Records and Research: not mentioned means "not switched off". Stories then appears as soon as the
    # site has a story in content/stories/; Records and Research appears only when the site turns it on, because
    # every site has sources and some already have a page of their own for them.
    for k, default, kind in (('stories', STORIES_PAGE, 'stories'), ('records', RECORDS_PAGE, 'records')):
        v = rp.get(k)
        st = page_state(v)
        if st == 'none': st = 'unset'
        page = merge({x: y for x, y in default.items() if x != 'label'}, page_object(v))
        if st == 'off': off_files[page['file']] = k
        made = st == 'on' or (st == 'unset' and k == 'stories' and stories_present(site_dir))
        toggles[k] = {'on': st == 'on' or (st == 'unset' and k == 'stories'), 'state': st, 'made': made, 'file': page['file']}
        if made:
            pages[kind] = page
            cfg['_pages'][kind] = page['file']
            added.append((page['file'], default['label']))

    # the Discovery Timeline: pages.discoveries decides; if the site does not say, timeline.enabled does (as before).
    tl = cfg.get('timeline') or {}
    dv = rp.get('discoveries')
    dstate = 'on' if dv is True else 'off' if dv is False else 'unset'
    legacy = tl.get('enabled') is True
    on = dv if isinstance(dv, bool) else legacy
    dfile = tl.get('file') or TIMELINE_PAGE['file']
    toggles['discoveries'] = {'on': bool(on), 'state': dstate if dstate != 'unset' else ('legacy' if legacy else 'unset'),
                              'made': bool(on), 'file': dfile}
    if dv is False: off_files[dfile] = 'discoveries'
    if on:
        pages['timeline'] = merge({k: v for k, v in TIMELINE_PAGE.items() if k != 'label'}, {'file': tl['file']} if tl.get('file') else {})
        cfg['_pages']['timeline'] = pages['timeline']['file']
        added.append((pages['timeline']['file'], TIMELINE_PAGE['label']))
        cfg['timeline'] = dict(tl, enabled=True)
    elif 'timeline' in cfg:
        cfg['timeline'] = dict(tl, enabled=False)

    # the navigation bar: no link to a page that is switched off, and an entry for each page the build adds
    nav = [i for i in cfg.get('nav') or [] if not (isinstance(i, dict) and i.get('href') in off_files)]
    for href, label in added:
        if not any(isinstance(i, dict) and i.get('href') == href for i in nav):
            nav.append({'label': label, 'href': href})
    cfg['nav'] = nav
    cfg['_toggles'] = toggles
    # private access and visitor identity: both are off unless the site says enabled: true, and then nothing else changes
    cfg['_access'] = access.access_settings(raw)
    cfg['_visitor'] = access.visitor_settings(raw)
    # the settings page: only a site that turns it on gets /admin/
    ad = cfg.get('admin') or {}
    if ad.get('enabled') is True:
        cfg['_admin'] = {'repo': ad.get('repo') or os.environ.get('GITHUB_REPOSITORY') or None, 'branch': ad.get('branch') or None,
                         'configPath': ad.get('configPath') or 'site.config.json'}
    cfg['_off_files'] = off_files
    cfg['_raw'] = raw
    return cfg
