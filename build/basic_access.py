"""A basic family password for a site that is still on GitHub Pages (basicAccess in site.config.json).

This is a stopgap, not protection, and the settings, the page and the documentation all say so. GitHub Pages cannot check
a password before it serves a file, so every page and file stays public. The browser script (engine/basic-gate.js) only
keeps a page from being shown until the right password is typed. Real protection is private access (access.py).

The password is never a setting. The settings hold a random salt and the PBKDF2-SHA256 hash of the password, made by
tools/basic-password.py or by the settings page. A hash in a public file can be guessed against offline, so a long
passphrase matters more here than anywhere. See docs/basic-access.md.
"""
import base64, binascii, html, re

DEFAULTS = {'enabled': False, 'scope': 'home', 'salt': '', 'hash': '', 'iterations': 210000, 'days': 30}
SCOPES = ('home', 'all')
SECRETISH = re.compile(r'pass|secret|token|key|phrase', re.I)
DASHES = (chr(0x2014), chr(0x2013))


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def settings(raw):
    """The settings with defaults, or None when the site has not turned basicAccess on."""
    b = (raw or {}).get('basicAccess')
    if not isinstance(b, dict) or b.get('enabled') is not True:
        return None
    out = dict(DEFAULTS)
    out.update({k: v for k, v in b.items() if k in DEFAULTS})
    return out


def _b64_len(s):
    try:
        return len(base64.b64decode(s, validate=True))
    except (binascii.Error, ValueError, TypeError):
        return None


def check(cfg):
    """(errors, warnings) beyond what the schema says."""
    errors, warnings = [], []
    raw = (cfg.get('_raw') or {}).get('basicAccess')
    if raw is None:
        return errors, warnings
    if not isinstance(raw, dict):
        return ['basicAccess: must be an object (see docs/basic-access.md).'], warnings
    for k, v in raw.items():
        if SECRETISH.search(k):
            errors.append('basicAccess.%s: the password never goes in site.config.json (it is published). Make the salt and hash with '
                          'tools/basic-password.py or the settings page; see docs/basic-access.md.' % k)
        elif k not in DEFAULTS:
            errors.append('basicAccess.%s: not a setting (see docs/site-config.md). A misspelt "enabled" would leave the page open.' % k)
        if isinstance(v, str) and any(d in v for d in DASHES):
            errors.append('basicAccess.%s: no long dashes.' % k)
    if raw.get('enabled') is not True:
        if raw:
            warnings.append('basicAccess is in site.config.json but "enabled" is not true, so it is off and the site is NOT password protected.')
        return errors, warnings
    b = cfg.get('_basic')
    if not b:
        return errors, warnings
    if b['scope'] not in SCOPES:
        errors.append('basicAccess.scope: use "home" (the home page only) or "all" (every page).')
    n = b['iterations']
    if not (isinstance(n, int) and not isinstance(n, bool) and 100000 <= n <= 2000000):
        errors.append('basicAccess.iterations: use a whole number from 100000 to 2000000 (the tool sets 210000).')
    d = b['days']
    if not (isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= 365):
        errors.append('basicAccess.days: use a whole number of days from 1 to 365.')
    for k, lo, hi in (('salt', 16, 64), ('hash', 32, 32)):
        v = b[k]
        size = _b64_len(v) if isinstance(v, str) and v else None
        if size is None or not (lo <= size <= hi):
            errors.append('basicAccess.%s: missing or not valid. Make the salt and hash with tools/basic-password.py or the settings '
                          'page. With no hash the page would be left open.' % k)
    if cfg.get('_access'):
        errors.append('basicAccess and access: use one or the other. access is the real password (Cloudflare Pages) and basicAccess would only sit on top of it.')
    warnings.append('basicAccess: this keeps casual visitors from the page and nothing else. The pages, data and pictures are still public '
                    'and can be read by anyone with the address. Use a long passphrase. See docs/basic-access.md.')
    return errors, warnings


def head(cfg, ctx, filename):
    """The script tag for a page, in the head. Nothing for a site without basicAccess, or for a page the scope leaves out."""
    b = cfg.get('_basic')
    if not b:
        return []
    if b['scope'] == 'home' and filename != cfg['_pages'].get('home'):
        return []
    name = (cfg.get('site') or {}).get('name') or ''
    return ['<script src="%sbasic-gate.js" data-salt="%s" data-hash="%s" data-iter="%d" data-days="%d" data-site="%s"></script>' % (
        ctx['base'], esc(b['salt']), esc(b['hash']), b['iterations'], b['days'], esc(name))]
