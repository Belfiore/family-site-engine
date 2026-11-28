#!/usr/bin/env python3
"""Checks for languages: the translation files, the words in the engine's templates and scripts, and that a site which
has not asked for another language is built exactly as before.

    python3 tests/test_i18n.py          (needs only Python 3.9 or later)

The browser side (the switcher, the saved choice, German dates, translated fields) is in check-i18n.js.
"""
import html, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'build'))
import i18n, validate  # noqa: E402

VERSION = open(os.path.join(ROOT, 'VERSION')).read().strip()
EM_DASH = chr(0x2014)
EN = i18n.load('en')


def read(path, mode='r'):
    with open(path, mode, **({} if 'b' in mode else {'encoding': 'utf-8'})) as f:
        return f.read()


def files(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = read(p, 'rb')
    return out


def normal(s):
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()


def placeholders(s):
    return sorted(re.findall(r'\{([a-zA-Z0-9]+)\}', s))


# ------------------------------------------------------------------ the dictionaries
# values a translation may take differently from English (the German greeting does not name the relationship)
# (and the German headline puts the name after the noun, so it takes the plain name where English takes the possessive)
EXPECTED = {('de', 'stuart.meet'): ['name'], ('de', 'map.headline'): ['noun', 'who']}


class TestDictionaries(unittest.TestCase):
    def test_the_engine_has_english_and_german(self):
        self.assertIn('en', i18n.languages())
        self.assertIn('de', i18n.languages())

    def test_every_language_has_exactly_the_keys_english_has(self):
        for lang in i18n.languages():
            have = set(i18n.load(lang))
            self.assertEqual(sorted(set(EN) - have), [], '%s.json is missing keys English has' % lang)
            self.assertEqual(sorted(have - set(EN)), [], '%s.json has keys English does not' % lang)

    def test_no_string_is_missing_from_de_json(self):
        """Fails when any interface string in en.json has no German words, or has an empty one."""
        de = i18n.load('de')
        missing = [k for k in EN if k not in de]
        empty = [k for k, v in de.items() if not str(v).strip() and str(EN.get(k, '')).strip()]
        self.assertEqual(missing, [], 'missing from de.json: %s' % ', '.join(missing[:20]))
        self.assertEqual(empty, [], 'empty in de.json: %s' % ', '.join(empty[:20]))

    def test_the_values_to_fill_in_match(self):
        for lang in i18n.languages():
            d = i18n.load(lang)
            for k, v in EN.items():
                have, want = placeholders(d.get(k, '')), placeholders(v)
                if (lang, k) in EXPECTED: want = EXPECTED[(lang, k)]
                self.assertEqual(have, want, '%s: {values} differ in %s' % (lang, k))

    def test_every_plural_has_both_forms(self):
        for lang in i18n.languages():
            d = i18n.load(lang)
            for k in d:
                if k.endswith('_one'): self.assertIn(k[:-4] + '_other', d, '%s: %s has no _other' % (lang, k))
                if k.endswith('_other'): self.assertIn(k[:-6] + '_one', d, '%s: %s has no _one' % (lang, k))

    def test_no_long_dashes_in_any_dictionary(self):
        for lang in i18n.languages():
            bad = [k for k, v in i18n.load(lang).items() if EM_DASH in v or EM_DASH in k]
            self.assertEqual(bad, [], '%s.json: %s' % (lang, bad))

    def test_the_german_is_not_just_the_english(self):
        de = i18n.load('de')
        same = [k for k in EN if de[k] == EN[k] and re.search(r'[A-Za-z]{4,}', EN[k])]
        self.assertLess(len(same), len(EN) * 0.08, 'too many German strings equal the English: %s' % same[:30])

    def test_german_dates_and_numbers(self):
        self.assertEqual(i18n.date_text('de', 1891, 3, 12), '12. März 1891')
        self.assertEqual(i18n.date_text('en', 1891, 3, 12), '12 March 1891')
        self.assertEqual(i18n.date_text('de', 1891, 3), 'März 1891')
        self.assertEqual(i18n.date_text('de', 1891), '1891')
        self.assertEqual(i18n.number_text('de', 12345), '12.345')
        self.assertEqual(i18n.number_text('en', 12345), '12,345')
        self.assertEqual(i18n.number_text('de', 1234), '1234')
        self.assertEqual(i18n.plural('de', 'map.nPlaces', 1), '1 Ort')
        self.assertEqual(i18n.plural('de', 'map.nPlaces', 3), '3 Orte')
        self.assertEqual(i18n.list_text('de', ['a', 'b', 'c']), 'a, b und c')
        self.assertEqual(i18n.list_text('en', ['a', 'b', 'c']), 'a, b and c')


# ------------------------------------------------------------------ the words in code and templates
GROUPS = sorted({k.split('.')[0] for k in EN})
# things that look like keys but are not: storage names, folders of settings, and families built from a name (checked below)
NOT_KEYS = {'stuart.me', 'stuart.chat', 'stuart.mode', 'stuart.open', 'stuart.flash', 'stuart.seen', 'stuart.look', 'tree.anc', 'tree.ancN'}
KEYLIKE = re.compile(r"""(?<![\w.$-])(['"])((?:%s)\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)\1""" % '|'.join(GROUPS))
FILE_WORDS = ('.html', '.js', '.css', '.json', '.png', '.svg', '.pbf')
# keys that code builds from a name: the families it asks for, listed here so that each one is checked
DYNAMIC = (
    ['map.type.' + t for t in ('born', 'baptised', 'lived', 'married', 'worked', 'served', 'sailed', 'civilcase', 'photographed', 'celebrated', 'died', 'buried')]
    + ['map.h.' + t for t in ('born', 'baptised', 'lived', 'married', 'worked', 'served', 'sailed', 'died', 'buried', 'civilcase', 'photographed', 'celebrated',
                              'place', 'birth', 'deathReg', 'births', 'baptisms', 'deaths', 'graves', 'sailing', 'arrival')]
    + ['map.gen.%d' % n for n in range(6)] + ['map.genChip.%d' % n for n in range(6)]
    + ['map.scope.' + s for s in ('self', 'spouse', 'family', 'ancestors', 'descendants')]
    + ['map.kind.' + k for k in ('home', 'church', 'cemetery', 'studio', 'workplace', 'hospital', 'militarysite', 'port', 'venue', 'parish',
                                 'registrationdistrict', 'district', 'town', 'county', 'country', 'farm', 'other')]
    + ['map.pair.' + k for k in ('parents', 'grandparents', 'greatgrandparents', 'children')]
    + ['tree.anc%d%s' % (n, pl) for n in (1, 2, 3) for pl in ('', 's')] + ['tree.ancN', 'tree.ancNs']
    + ['date.month.%d' % n for n in range(1, 13)] + ['date.monthShort.%d' % n for n in range(1, 13)]
    + ['date.weekday.%d' % n for n in range(7)] + ['date.weekdayShort.%d' % n for n in range(7)]
    + ['kin.' + k for k in ('father', 'mother', 'parent', 'grandfather', 'grandmother', 'grandparent', 'son', 'daughter', 'child', 'grandson', 'granddaughter',
                            'grandchild', 'brother', 'sister', 'sibling', 'uncle', 'aunt', 'auntOrUncle', 'nephew', 'niece', 'husband', 'wife', 'spouse',
                            'fatherInLaw', 'motherInLaw', 'parentInLaw', 'sonInLaw', 'daughterInLaw', 'childInLaw', 'stepfather', 'stepmother', 'stepParent',
                            'brotherInLaw', 'sisterInLaw', 'siblingInLaw')]
)


def has_key(key):
    return key in EN or (key + '_one') in EN


def sources():
    for sub in ('engine', 'templates', 'build'):
        for d, dirs, fs in os.walk(os.path.join(ROOT, sub)):
            dirs[:] = [x for x in dirs if x not in ('vendor', 'fonts', 'i18n', 'map-styles', '__pycache__')]
            for f in fs:
                if f.endswith(('.js', '.html', '.py')) and f not in ('i18n.py', 'validate.py') and not (sub == 'engine' and f == 'i18n.js'):
                    yield os.path.join(d, f)


class TestKeysInCode(unittest.TestCase):
    def test_every_key_the_code_asks_for_is_in_the_dictionary(self):
        bad = []
        for p in sources():
            for m in KEYLIKE.finditer(read(p)):
                key = m.group(2)
                if key.endswith(FILE_WORDS) or key.endswith('_') or key in NOT_KEYS or has_key(key): continue
                bad.append('%s: %s' % (os.path.relpath(p, ROOT), key))
        self.assertEqual(bad, [], '\n'.join(bad[:30]))

    def test_the_keys_code_builds_from_a_name_exist(self):
        for lang in i18n.languages():
            d = i18n.load(lang)
            self.assertEqual([k for k in DYNAMIC if k not in d], [], lang)

    def test_every_script_that_reads_the_words_asks_for_them(self):
        """A script with I.t(...) in it has the /* @i18n */ line, or comes after one that has (they share the runtime)."""
        asks = {'stuart.js', 'tree-canvas.js', 'timeline.js', 'visitor.js', 'map-data.js', 'nav.js'}
        for name in sorted(asks):
            first = read(os.path.join(ROOT, 'engine', name)).split('\n', 1)[0]
            self.assertTrue(first.startswith('/* @i18n') or name == 'nav.js', '%s has no /* @i18n */ line' % name)


class TestTemplates(unittest.TestCase):
    """The English template holds the English words, so a site that stays in English gets its pages unchanged.
    These checks keep the template and en.json from drifting apart."""

    def templates(self):
        d = os.path.join(ROOT, 'templates')
        return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith('.html')]

    def test_marked_words_in_the_templates_equal_en_json(self):
        bad = []
        for p in self.templates():
            src = read(p)
            for m in i18n.ELEM.finditer(src):
                key = m.group('key')
                if '{' in EN.get(key, '') or '{{' in m.group('body'): continue
                if key not in EN: bad.append('%s: no key %s' % (os.path.basename(p), key)); continue
                if normal(m.group('body')) != normal(EN[key]):
                    bad.append('%s: %s\n   template: %s\n   en.json:  %s' % (os.path.basename(p), key, normal(m.group('body'))[:90], normal(EN[key])[:90]))
            for m in i18n.WRAP.finditer(src):
                key = m.group('key')
                if key not in EN: bad.append('%s: no key %s' % (os.path.basename(p), key)); continue
                if normal(m.group('body')) != normal(EN[key]):
                    bad.append('%s: %s\n   template: %s\n   en.json:  %s' % (os.path.basename(p), key, normal(m.group('body'))[:90], normal(EN[key])[:90]))
            for tag in re.finditer(r'<[a-zA-Z][^<>]*>', src):
                for a in i18n.ATTRKEY.finditer(tag.group(0)):
                    key, attr = a.group('key'), a.group('attr')
                    if key not in EN: bad.append('%s: no key %s' % (os.path.basename(p), key)); continue
                    v = re.search(r'\s%s="([^"]*)"' % re.escape(attr), tag.group(0))
                    if v and '{' not in EN[key] and normal(v.group(1)) != normal(EN[key]):
                        bad.append('%s: %s (%s)\n   template: %s\n   en.json:  %s' % (os.path.basename(p), key, attr, normal(v.group(1))[:90], normal(EN[key])[:90]))
        self.assertEqual(bad, [], '\n' + '\n'.join(bad[:20]))

    def test_every_marker_is_closed_by_the_wrapper_or_an_element(self):
        for p in self.templates():
            src = read(p)
            self.assertEqual(src.count('data-i18w'), len(i18n.WRAP.findall(src)), os.path.basename(p))


# ------------------------------------------------------------------ the build
def build(site, out, *extra):
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', out] + list(extra), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def site(self, language=None, edit=None, name='site'):
        dest = os.path.join(self.tmp, name)
        shutil.copytree(os.path.join(ROOT, 'sample'), dest)
        p = os.path.join(dest, 'site.config.json')
        cfg = json.loads(read(p))
        if language is not None: cfg['language'] = language
        if edit: edit(cfg)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=1, ensure_ascii=False)
        return dest

    def built(self, site, name='out'):
        out = os.path.join(self.tmp, name)
        code, text = build(site, out)
        return code, text, out


def comparable(root):
    """The built files with the engine's own folder set aside: the pages, the settings and the data."""
    out = files(root)
    for k in list(out):
        if k.startswith('engine/'): del out[k]
    if 'engine-build.json' in out:
        d = json.loads(out['engine-build.json']); d.pop('built', None)
        out['engine-build.json'] = json.dumps(d, sort_keys=True).encode()
    return out


class TestOffMeansUnchanged(Base):
    def test_english_only_builds_the_same_with_or_without_the_language_block(self):
        _, _, a = self.built(self.site(), 'a')
        for i, block in enumerate(({'default': 'en', 'available': ['en']}, {'default': 'en'}, {})):
            code, text, b = self.built(self.site(block, name='s%d' % i), 'b%d' % i)
            self.assertEqual(code, 0, text)
            fa, fb = comparable(a), comparable(b)
            self.assertEqual(sorted(set(fa) ^ set(fb)), [], block)
            self.assertEqual([k for k in fa if fa[k] != fb[k]], [], block)

    def test_an_english_site_has_no_trace_of_another_language_in_its_pages(self):
        code, text, out = self.built(self.site())
        self.assertEqual(code, 0, text)
        self.assertNotIn('"language"', read(os.path.join(out, 'site-config.js')))
        info = json.loads(read(os.path.join(out, 'engine-build.json')))
        self.assertNotIn('language', info)
        for page in ('family-tree.html', 'map.html', 'ask.html', 'index.html', 'moreau.html'):
            text = read(os.path.join(out, page))
            for marker in ('data-i18n', 'data-i18w', 'data-label-', 'data-html-', 'lang-switch'):
                self.assertNotIn(marker, text, '%s has %s' % (page, marker))
        for name, body in files(out).items():
            if name.endswith(('.html', '.js', '.json', '.css')):
                self.assertNotIn('@i18n', body.decode('utf-8', 'ignore'), name)
                if not name.startswith('engine/'): self.assertNotIn('Stammbaum'.encode(), body, name)

    def test_the_engines_own_files_do_not_carry_the_dictionaries_they_do_not_use(self):
        _, _, out = self.built(self.site())
        engine = os.path.join(out, 'engine', VERSION)
        self.assertFalse(os.path.exists(os.path.join(engine, 'i18n')), 'the dictionaries are not copied, they are written into the scripts')
        self.assertFalse(os.path.exists(os.path.join(engine, 'i18n.js')))

    def test_the_english_pages_still_say_what_en_json_says(self):
        """The words a page template carries are the English ones, so the same pages come out as before."""
        _, _, out = self.built(self.site())
        tree = read(os.path.join(out, 'family-tree.html'))
        self.assertIn(EN['tree.skip'], tree)
        self.assertIn(EN['tree.legendTitle'], tree)
        self.assertIn(EN['map.skip'], read(os.path.join(out, 'map.html')))


class TestGermanBuild(Base):
    def test_a_site_whose_default_is_german(self):
        site = self.site({'default': 'de', 'available': ['de']})
        code, text, out = self.built(site)
        self.assertEqual(code, 0, text)
        tree, mp = read(os.path.join(out, 'family-tree.html')), read(os.path.join(out, 'map.html'))
        self.assertIn('<html lang="de">', tree)
        self.assertIn('<html lang="de">', mp)
        self.assertIn(i18n.raw('de', 'tree.skip'), tree)
        self.assertIn(i18n.raw('de', 'map.skip'), mp)
        self.assertIn('Stammbaum', tree)                       # the engine's own page name, in the nav
        self.assertNotIn('data-i18n', tree)                    # nothing to switch to, so no markers
        self.assertNotIn('lang-switch', tree)
        cfg = read(os.path.join(out, 'site-config.js'))
        self.assertIn('"language"', cfg)

    def test_two_languages_give_a_switcher_and_keep_the_markers(self):
        site = self.site({'default': 'en', 'available': ['en', 'de']})
        code, text, out = self.built(site)
        self.assertEqual(code, 0, text)
        for page in ('family-tree.html', 'map.html', 'ask.html', 'index.html'):
            body = read(os.path.join(out, page))
            self.assertIn('lang="en', body, page)
            self.assertIn('data-label-de=', body, page)          # the bar says what each link is called in German
        self.assertIn('data-i18n', read(os.path.join(out, 'map.html')))
        cfg = read(os.path.join(out, 'site-config.js'))
        self.assertIn('"language"', cfg)
        self.assertRegex(cfg, r'"available":\s*\[\s*"en",\s*"de"\s*\]')
        self.assertIn('lang-switch', read(os.path.join(out, 'engine', VERSION, 'nav.js')))      # the switcher is drawn by the nav script
        # the scripts carry both languages' words
        engine = os.path.join(out, 'engine', VERSION)
        word = i18n.raw('de', 'map.modeExplore')
        for name in ('map-data.js',):
            body = read(os.path.join(engine, name))
            self.assertTrue(word in body or json.dumps(word)[1:-1] in body, 'the German words are in %s' % name)
        self.assertIn('"nav.tree":"Stammbaum"', read(os.path.join(engine, 'nav.js')).replace(' ', ''))

    def test_the_sites_own_words_in_german(self):
        def edit(cfg):
            cfg['site']['name_de'] = 'Beispielfamilie'
            for it in cfg['nav']:
                if it['href'] == 'moreau.html': it['label_de'] = 'Die Moreaus'
            cfg['pages']['tree']['title_de'] = 'Stammbaum | Beispiel'
        site = self.site({'default': 'de', 'available': ['de', 'en']}, edit)
        code, text, out = self.built(site)
        self.assertEqual(code, 0, text)
        tree = read(os.path.join(out, 'family-tree.html'))
        self.assertIn('Die Moreaus', tree)
        self.assertIn('Beispielfamilie', tree)
        self.assertIn('Stammbaum | Beispiel', tree)
        self.assertIn('data-label-en="The Moreaus"', tree)       # the other language, for the switcher

    def test_the_home_region_chip_is_in_the_default_language(self):
        site = self.site({'default': 'de', 'available': ['de']})
        _, _, out = self.built(site)
        self.assertIn('Zurück', read(os.path.join(out, 'map.html')))


class TestSettings(Base):
    def validate(self, site):
        p = subprocess.run([sys.executable, os.path.join(ROOT, 'build', 'validate.py'), '--site', site], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_the_schema_accepts_the_language_block(self):
        code, text = self.validate(self.site({'default': 'de', 'available': ['en', 'de']}))
        self.assertEqual(code, 0, text)

    def test_a_language_block_with_a_misspelt_key_is_reported(self):
        code, text = self.validate(self.site({'default': 'en', 'availible': ['en', 'de']}))
        self.assertIn('availible', text)

    def test_an_unknown_language_stops_the_build(self):
        code, text, _ = self.built(self.site({'default': 'fr', 'available': ['fr']}))
        self.assertNotEqual(code, 0)
        self.assertIn('language.default', text)
        code, text, _ = self.built(self.site({'default': 'en', 'available': ['en', 'xx']}, name='two'), 'two')
        self.assertNotEqual(code, 0)
        self.assertIn('language.available', text)

    def test_settings(self):
        self.assertEqual(i18n.settings({}), {'default': 'en', 'available': ['en'], 'active': False, 'switcher': False})
        self.assertEqual(i18n.settings({'language': {'default': 'en', 'available': ['en']}})['active'], False)
        s = i18n.settings({'language': {'default': 'en', 'available': ['en', 'de']}})
        self.assertTrue(s['active'] and s['switcher'])
        s = i18n.settings({'language': {'default': 'de'}})
        self.assertEqual((s['default'], s['available'], s['active'], s['switcher']), ('de', ['de'], True, False))

    def test_words_in_another_language_are_allowed_beside_the_originals(self):
        def edit(cfg):
            cfg['nav'][1]['label_de'] = 'Stammbaum'
        code, text, _ = self.built(self.site({'default': 'en', 'available': ['en', 'de']}, edit))
        self.assertEqual(code, 0, text)


class TestDataFields(Base):
    def edit_people(self, site, field, value):
        p = os.path.join(site, 'data', 'people.json')
        d = json.loads(read(p))
        next(x for x in d['people'] if x.get('summary'))[field] = value
        with open(p, 'w', encoding='utf-8') as f: json.dump(d, f, indent=1, ensure_ascii=False)

    def check(self, site):
        p = subprocess.run([sys.executable, os.path.join(ROOT, 'build', 'validate.py'), '--site', site], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_a_field_with_a_language_suffix_is_known_and_other_suffixes_are_not(self):
        site = self.site({'default': 'en', 'available': ['en', 'de']})
        self.edit_people(site, 'summary_de', 'Eine Zusammenfassung.')
        code, text = self.check(site)
        self.assertEqual(code, 0, text)
        self.assertNotIn('summary_de', text)
        self.edit_people(site, 'summary_xx', 'Nope')
        code, text = self.check(site)
        self.assertIn('summary_xx', text, 'a field for a language the engine has no words for is reported like any unknown field')

    def test_a_translated_field_must_be_text(self):
        site = self.site({'default': 'en', 'available': ['en', 'de']})
        self.edit_people(site, 'summary_de', 5)
        code, text = self.check(site)
        self.assertNotEqual(code, 0, text)


if __name__ == '__main__':
    unittest.main(verbosity=1)
