"""Languages: the translation files, and what the build does with them.

The words of the engine's own interface live in engine/i18n/<language>.json (flat, dotted keys, {name} for a
value filled in, key_one and key_other for words that change with a number). English is the source: every other file
has to have every key English has (tests/test_i18n.py). A language is a file in that folder; adding one is adding a file.

A site chooses with "language": { "default": "en", "available": ["en"] }. Without that block, or with it saying English only,
the site is English only and nothing here changes a byte of its pages: the build only strips the data-i18n markers from the
engine's templates and puts the English words into the scripts that read them.

What the build does:
  * bundle(): writes engine/i18n.js and the words a script needs in place of its `/* @i18n group group */` line;
  * template(): fills the engine's page templates from the dictionary, in the site's default language, and keeps the
    data-i18n markers only on a site whose visitors can choose, so the browser can write the page again;
  * the same dates, numbers and plural rules as the browser (date_text(), number_text(), plural()), for the pages the
    build writes itself (the Discoveries page).
"""
import html, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(HERE)
I18N_DIR = os.path.join(ENGINE_ROOT, 'engine', 'i18n')
RUNTIME = os.path.join(ENGINE_ROOT, 'engine', 'i18n.js')
ALWAYS = ('date', 'fmt', 'list', 'q', 'lang')           # groups of keys every script gets: dates, numbers, lists, date qualifiers, language names
MARKER = re.compile(r'^/\*\s*@i18n\b([^*]*)\*/[ \t]*\n?')

_cache = {}


def languages():
    """The languages the engine has words for, by code."""
    return sorted(f[:-5] for f in os.listdir(I18N_DIR) if f.endswith('.json'))


def load(lang):
    if lang not in _cache:
        with open(os.path.join(I18N_DIR, lang + '.json'), encoding='utf-8') as f:
            _cache[lang] = json.load(f)
    return _cache[lang]


def settings(cfg):
    """The site's language choice: {'default', 'available', 'active', 'switcher'}.

    active is False for a site that does not set "language" (or sets English only), and then the site is built as it always was."""
    block = (cfg or {}).get('language') or {}
    default = block.get('default') or 'en'
    available = list(block.get('available') or [default])
    if default not in available: available.insert(0, default)
    active = default != 'en' or len(available) > 1
    return {'default': default, 'available': available, 'active': active, 'switcher': len(available) > 1}


def check(cfg):
    """Problems with the language settings, as (errors, warnings)."""
    errors, warnings = [], []
    block = (cfg or {}).get('language')
    if block is None: return errors, warnings
    have = languages()
    v = block.get('default')
    if v is not None and v not in have:
        errors.append('language.default is "%s", but the engine has no words for it (it has: %s).' % (v, ', '.join(have)))
    for v in block.get('available') or []:
        if v not in have:
            errors.append('language.available lists "%s", but the engine has no words for it (it has: %s).' % (v, ', '.join(have)))
    av = block.get('available')
    if av is not None and block.get('default') and block['default'] not in av:
        warnings.append('language.default "%s" is not in language.available, so it was added.' % block['default'])
    if av is not None and len(set(av)) != len(av):
        warnings.append('language.available lists a language more than once.')
    return errors, warnings


# ------------------------------------------------------------------ words
def raw(lang, key):
    d = load(lang)
    if key in d: return d[key]
    en = load('en')
    if key in en: return en[key]
    raise KeyError('no translation key %s' % key)


def fill(s, **vars):
    return re.sub(r'\{([a-zA-Z0-9]+)\}', lambda m: str(vars[m.group(1)]) if m.group(1) in vars else m.group(0), s)


def t(lang, key, **vars):
    return fill(raw(lang, key), **vars)


def plural(lang, key, count, **vars):
    vars = dict(vars, n=number_text(lang, count))
    return fill(raw(lang, key + ('_one' if count == 1 else '_other')), **vars)


def list_text(lang, items):
    items = list(items)
    if len(items) < 2: return ''.join(items)
    return t(lang, 'list.sep').join(items[:-1]) + t(lang, 'list.last') + items[-1]


def number_text(lang, x):
    if isinstance(x, float) and x != int(x):
        whole, frac = ('%s' % abs(x)).split('.')
    else:
        whole, frac = str(abs(int(x))), ''
    if len(whole) > 4: whole = re.sub(r'\B(?=(\d{3})+(?!\d))', t(lang, 'fmt.group'), whole)
    return ('-' if x < 0 else '') + whole + (t(lang, 'fmt.decimal') + frac if frac else '')


def date_text(lang, y, m=0, d=0, weekday=None, short=False):
    """12 March 1891 or 12. März 1891. weekday is 0 (Sunday) to 6, or None."""
    mon = t(lang, ('date.monthShort.%d' if short else 'date.month.%d') % m) if m else ''
    if m and d:
        if weekday is not None:
            return t(lang, 'date.wdmy', weekday=t(lang, ('date.weekdayShort.%d' if short else 'date.weekday.%d') % weekday), d=d, month=mon, y=y)
        return t(lang, 'date.dmy', d=d, month=mon, y=y)
    if m: return t(lang, 'date.my', month=mon, y=y)
    return str(y)


def day_month_text(lang, m, d, short=False):
    return t(lang, 'date.dm', d=d, month=t(lang, ('date.monthShort.%d' if short else 'date.month.%d') % m))


# ------------------------------------------------------------------ scripts
def _slice(lang, groups):
    want = set(groups) | set(ALWAYS)
    return {k: v for k, v in load(lang).items() if k.split('.')[0] in want}


def bundle(engine_dir, cfg):
    """Replace the `/* @i18n group group */` line of each script in the built engine folder with the runtime and its words."""
    st = settings(cfg)
    langs = ['en'] + [l for l in dict.fromkeys([st['default']] + st['available']) if l != 'en']
    with open(RUNTIME, encoding='utf-8') as f:
        runtime = f.read()
    # the runtime opens with its own comment; the scripts get the code only
    runtime = runtime[runtime.index('function familyI18nRuntime'):]
    for root, _, files in os.walk(engine_dir):
        if os.sep + 'vendor' in root + os.sep or os.sep + 'fonts' in root + os.sep: continue
        for name in files:
            if not name.endswith('.js'): continue
            path = os.path.join(root, name)
            with open(path, encoding='utf-8') as f:
                src = f.read()
            m = MARKER.match(src)
            if not m: continue
            groups = m.group(1).split()
            words = {l: _slice(l, groups) for l in langs}
            pre = ('/* Family site engine: language (written by the build; the words are in engine/i18n/*.json). */\n'
                   '(function () {\n%s\n'
                   'var g = typeof window !== "undefined" ? window : globalThis;\n'
                   'var I = g.FamilyI18n || (g.FamilyI18n = familyI18nRuntime(g));\n'
                   'I.add(%s);\n})();\n') % (runtime.rstrip(), json.dumps(words, ensure_ascii=False, separators=(',', ':'), sort_keys=True))
            with open(path, 'w', encoding='utf-8') as f:
                f.write(pre + src[m.end():])


# ------------------------------------------------------------------ templates
ATTR = re.compile(r' data-i18n(?:-[a-z-]+)?="[^"]*"')
ELEM = re.compile(r'<(?P<tag>[a-zA-Z0-9]+)(?P<attrs>(?:\s[^<>]*?)?\sdata-i18n(?P<html>-html)?="(?P<key>[^"]+)"[^<>]*)>(?P<body>.*?)</(?P=tag)>', re.S)
WRAP = re.compile(r'<span data-i18w(?P<html>h)?="(?P<key>[^"]+)">(?P<body>.*?)</span>', re.S)
ATTRKEY = re.compile(r'\sdata-i18n-(?!html)(?P<attr>[a-z-]+)="(?P<key>[^"]+)"')


def template(src, cfg):
    """Fill a page template from the dictionary, in the site's default language.

    The English template already holds the English words, so an English-only site gets the template as written with the markers
    removed. A site with another default gets that language's words. A site whose visitors can choose keeps the markers, so the
    browser can write the page again in the language they pick."""
    st = settings(cfg)
    lang = st['default']

    def wrap(m):
        # a span that exists only to carry a translation: a site that never switches language gets the bare words, as before
        body = m.group('body')
        if lang != 'en':
            body = raw(lang, m.group('key'))
            body = body if m.group('html') else html.escape(body, quote=False)
        if not st['switcher']: return body
        return '<span data-i18n%s="%s">%s</span>' % ('-html' if m.group('html') else '', m.group('key'), body)
    src = WRAP.sub(wrap, src)
    if lang != 'en':
        def elem(m):
            body = raw(lang, m.group('key'))
            body = body if m.group('html') else html.escape(body, quote=False)
            return '<%s%s>%s</%s>' % (m.group('tag'), m.group('attrs'), body, m.group('tag'))
        src = ELEM.sub(elem, src)

        def tag(m):
            tg = m.group(0)
            for a in ATTRKEY.finditer(tg):
                val = html.escape(raw(lang, a.group('key')), quote=True)
                if re.search(r'\s%s="' % re.escape(a.group('attr')), tg):
                    tg = re.sub(r'(\s%s=")[^"]*(")' % re.escape(a.group('attr')), lambda mm: mm.group(1) + val + mm.group(2), tg, count=1)
                else:
                    tg = tg[:-1] + ' %s="%s">' % (a.group('attr'), val)
            return tg
        src = re.sub(r'<[a-zA-Z][^<>]*\sdata-i18n-(?!html)[a-z-]+="[^"]*"[^<>]*>', tag, src)
    if not st['switcher']:
        src = ATTR.sub('', src)
    return src


def span(cfg, key, **vars):
    """The words for a key in the site's default language, in a span the browser can rewrite when visitors can choose a language."""
    st = settings(cfg)
    text = html.escape(t(st['default'], key, **vars), quote=False)
    return '<span data-i18n="%s">%s</span>' % (key, text) if st['switcher'] else text
