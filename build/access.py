"""Private access and the visitor's own place in the family: the settings, their checks, and the gate.

Two optional features, both off unless a site turns them on (docs/access.md, docs/visitor.md):

  access    a shared family password. The built site gets a Cloudflare Pages worker (_worker.js) that serves no
            page, picture or data file unless the request carries a cookie made by entering the password.
  visitor   "Who are you?": the visitor picks themselves from the people in the site's data, the site remembers
            it on that device, and the family tree opens from their place. This part is only a preference kept in
            the browser (engine/visitor.js); it grants nothing.

The password itself is never read here. It lives in the SITE_PASSWORD secret of the site's repository and of its
Cloudflare Pages project; this module only builds the code that checks it.
"""
import base64, hashlib, html, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(HERE)
DASHES = (chr(0x2014), chr(0x2013))

ACCESS_DEFAULTS = {
    'enabled': False,
    'project': '',
    'kicker': 'A private family archive',
    'wordmark': '',
    'prompt': 'Family password',
    'button': 'Enter',
    'hint': '',
    'cookieDays': 90,
    'entranceImage': '',
}
VISITOR_DEFAULTS = {
    'enabled': False,
    'question': 'Who are you?',
    'lead': 'Find yourself in the family, and the tree will open from where you sit in it.',
    'skipLabel': 'Continue without choosing',
    'welcome': True,
    'livingPhotos': False,
    'scope': 'living',
}
SECRETISH = re.compile(r'pass|secret|token|key', re.I)


def access_settings(raw):
    """The access settings with defaults, or None when the site has not turned access on."""
    a = (raw or {}).get('access')
    if not isinstance(a, dict) or a.get('enabled') is not True:
        return None
    out = dict(ACCESS_DEFAULTS)
    out.update({k: v for k, v in a.items() if k in ACCESS_DEFAULTS})
    return out


def visitor_settings(raw):
    """The visitor settings with defaults, or None when the site has not turned visitor identity on."""
    v = (raw or {}).get('visitor')
    if not isinstance(v, dict) or v.get('enabled') is not True:
        return None
    out = dict(VISITOR_DEFAULTS)
    out.update({k: v_ for k, v_ in v.items() if k in VISITOR_DEFAULTS})
    return out


def check(cfg, site):
    """(errors, warnings) for the access and visitor settings, beyond what the schema says."""
    errors, warnings = [], []
    raw = cfg.get('_raw') or {}
    days = (raw.get('access') or {}).get('cookieDays')
    if days is not None and not (isinstance(days, int) and not isinstance(days, bool) and 1 <= days <= 365):
        errors.append('access.cookieDays: use a whole number of days from 1 to 365.')
    known = {'access': ACCESS_DEFAULTS, 'visitor': VISITOR_DEFAULTS}
    for block in ('access', 'visitor'):
        b = raw.get(block)
        if not isinstance(b, dict):
            continue
        if b.get('enabled') is not True and b:
            warnings.append('%s is in site.config.json but "enabled" is not true, so it is off%s.' % (
                block, ' and the site is NOT password protected' if block == 'access' else ''))
        for k, v in b.items():
            # a misspelt setting must not quietly leave a site open or without its question, so these are errors, not warnings
            if k not in known[block] and not SECRETISH.search(k):
                errors.append('%s.%s: not a setting (see docs/site-config.md). A misspelt "enabled" would leave the feature off.' % (block, k))
            if SECRETISH.search(k) and k not in ('cookieDays',):
                errors.append('%s.%s: passwords and keys never go in site.config.json (it is published). Set the SITE_PASSWORD secret instead; see docs/access.md.' % (block, k))
            if isinstance(v, str) and any(d in v for d in DASHES):
                errors.append('%s.%s: no long dashes in text the visitor reads. Use a comma, a colon or a full stop.' % (block, k))
    a = cfg.get('_access')
    if a:
        if (raw.get('timeline') or {}).get('enabled'):
            errors.append('access and timeline: the Discovery Timeline reads its history from the live site, which a password keeps closed. They cannot be turned on together yet (docs/access.md).')
        if not a['project']:
            errors.append('access.project: name the Cloudflare Pages project the site is published to (docs/access.md).')
        elif not re.match(r'^[a-z0-9]([a-z0-9-]{0,56}[a-z0-9])?$', a['project']):
            errors.append('access.project: "%s" is not a Cloudflare Pages project name (lower case letters, digits and hyphens).' % a['project'])
        img = a['entranceImage']
        if img:
            if img.startswith('/') or '..' in img.split('/') or '\\' in img:
                errors.append('access.entranceImage: give a path inside the site, like images/entrance.jpg.')
            elif not os.path.isfile(os.path.join(site, img)):
                errors.append('access.entranceImage: %s is not in the site.' % img)
            else:
                warnings.append('access.entranceImage: %s is shown to everyone before the password. Use only a picture that is fine to make public.' % img)
        if not cfg['_pages'].get('tree') and cfg.get('_visitor'):
            warnings.append('visitor: the site has no family tree page, so the choice is only used by Stuart.')
        if os.path.isfile(os.path.join(site, 'robots.txt')):
            warnings.append('robots.txt: a private site publishes its own robots.txt that blocks every crawler. Yours is replaced.')
    return errors, warnings


def _fonts(cfg):
    fonts = (cfg.get('head') or {}).get('fonts')
    if not fonts:
        return '', '', ''
    host = 'https://%s' % re.sub(r'^https?://', '', fonts).split('/')[0]
    style_host = host
    font_host = 'https://fonts.gstatic.com' if 'fonts.googleapis.com' in host else host
    pre = ''
    if 'fonts.googleapis.com' in host:
        pre = '    <link rel="preconnect" href="https://fonts.googleapis.com">\n    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    return pre + '    <link href="%s" rel="stylesheet">\n' % html.escape(fonts, quote=True), style_host, font_host


def entrance_page(cfg, a):
    """The password page, one self-contained HTML string, and the content security policy that goes with it."""
    with open(os.path.join(ENGINE_ROOT, 'templates', 'gate.html'), encoding='utf-8') as f:
        tpl = f.read()
    with open(os.path.join(ENGINE_ROOT, 'templates', 'gate.js'), encoding='utf-8') as f:
        script = f.read().strip()
    site = cfg.get('site') or {}
    name = a['wordmark'] or site.get('name') or 'Family archive'
    fonts_html, style_host, font_host = _fonts(cfg)
    theme = cfg.get('theme') or {}
    vars_css = '        :root {\n%s        }' % ''.join(
        '            %s: %s;\n' % (k if k.startswith('--') else '--' + k, str(v).replace('<', '\\3c ')) for k, v in theme.items()) if theme else ''
    image = ('    <img class="g-img" src="/%s" alt="">\n' % html.escape(a['entranceImage'], quote=True)) if a['entranceImage'] else ''
    hint = ('    <p class="g-hint">%s</p>\n' % html.escape(a['hint'])) if a['hint'] else ''
    values = {
        'lang': html.escape(site.get('lang') or 'en-GB'),
        'title': html.escape(name),
        'fonts': fonts_html,
        'vars': vars_css,
        'kicker': html.escape(a['kicker']),
        'wordmark': html.escape(name),
        'image': image,
        'prompt': html.escape(a['prompt']),
        'button': html.escape(a['button']),
        'hint': hint,
        'script': script,
    }
    out = tpl
    for k, v in values.items():
        out = out.replace('{{%s}}' % k, v)
    left = re.findall(r'\{\{[a-zA-Z]+\}\}', out)
    if left:
        raise SystemExit('gate.html: no value for %s' % ', '.join(sorted(set(left))))
    digest = base64.b64encode(hashlib.sha256(('\n%s\n' % script).encode('utf-8')).digest()).decode('ascii')
    csp = ("default-src 'none'; script-src 'sha256-%s'; style-src 'unsafe-inline'%s; font-src%s; img-src 'self'; connect-src 'self'; "
           "form-action 'self'; base-uri 'none'; frame-ancestors 'none'") % (digest, (' ' + style_host) if style_host else '', (' ' + font_host) if font_host else " 'none'")
    return out, csp


def worker_source(cfg, a):
    page, csp = entrance_page(cfg, a)
    open_paths = ['/robots.txt'] + (['/' + a['entranceImage']] if a['entranceImage'] else [])
    config = ('const CONFIG = %s;\nconst GATE_HTML = %s;\nconst GATE_CSP = %s;\n') % (
        json.dumps({'days': int(a['cookieDays']), 'open': open_paths, 'failDelayMs': 700}),
        json.dumps(page, ensure_ascii=True), json.dumps(csp))
    with open(os.path.join(ENGINE_ROOT, 'templates', 'gate-worker.js'), encoding='utf-8') as f:
        tpl = f.read()
    assert '/*__CONFIG__*/' in tpl
    return tpl.replace('/*__CONFIG__*/', config)


def build(out, cfg):
    """Write _worker.js and robots.txt into the built site. Returns what was made, for engine-build.json."""
    a = cfg['_access']
    src = worker_source(cfg, a)
    with open(os.path.join(out, '_worker.js'), 'w', encoding='utf-8') as f:
        f.write(src)
    with open(os.path.join(out, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write('# A private family archive. Nothing here is for search engines.\nUser-agent: *\nDisallow: /\n')
    return {'project': a['project'], 'cookieDays': int(a['cookieDays']), 'entranceImage': bool(a['entranceImage'])}


def browser_visitor(v):
    """What engine/visitor.js reads (window.FamilySite.visitor)."""
    return {k: v[k] for k in ('question', 'lead', 'skipLabel', 'welcome', 'livingPhotos', 'scope')}
