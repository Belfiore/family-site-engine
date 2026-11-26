#!/usr/bin/env python3
"""Checks for the build, the data checker and the migration, run against the sample site.

    python3 tests/test_build.py          (needs only Python 3.9 or later)

Each check builds a copy of the sample site in a temporary folder, so the sample itself is never changed.
"""
import copy, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, 'sample')
sys.path.insert(0, os.path.join(ROOT, 'build'))
import build_site, migrate, sitecfg, validate  # noqa: E402

VERSION = open(os.path.join(ROOT, 'VERSION')).read().strip()
BASE = 'engine/%s/' % VERSION


def run_build(site, out):
    """Build quietly; the exit code and what it printed."""
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', out],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


class SampleCopy:
    """A throwaway copy of the sample site, with its settings or data changed for one check."""
    def __init__(self, tmp):
        self.dir = os.path.join(tmp, 'site')
        shutil.copytree(SAMPLE, self.dir)

    def path(self, *p):
        return os.path.join(self.dir, *p)

    def edit_json(self, rel, fn):
        p = self.path(rel)
        with open(p, encoding='utf-8') as f: doc = json.load(f)
        fn(doc)
        with open(p, 'w', encoding='utf-8') as f: json.dump(doc, f, ensure_ascii=False, indent=1)

    def person(self, doc, pid):
        return next(p for p in doc['people'] if p['id'] == pid)


def read(path):
    with open(path, encoding='utf-8') as f: return f.read()


def jload(path):
    with open(path, encoding='utf-8') as f: return json.load(f)


DASHES = re.compile('[%s%s]' % (chr(0x2013), chr(0x2014)))   # en and em dash
NAV_RE = re.compile(r'<nav\b[^>]*\bclass="main-nav"[^>]*>.*?</nav>', re.S)


class TestBuiltSample(unittest.TestCase):
    """The sample, built once, and what the build made from it."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out = os.path.join(cls.tmp, '_site')
        code, cls.log = run_build(SAMPLE, cls.out)
        assert code == 0, cls.log
        cls.pages = {n: read(os.path.join(cls.out, n)) for n in os.listdir(cls.out) if n.endswith('.html')}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_sample_data_is_clean(self):
        cfg = sitecfg.load(SAMPLE)
        a, b = validate.check_config(cfg), validate.validate_site(SAMPLE, cfg)
        self.assertEqual(a['errors'] + b['errors'], [])
        self.assertEqual(a['warnings'] + b['warnings'], [], 'the sample should have no warnings either')

    def test_engine_and_settings_are_in_place(self):
        for f in ('tree-canvas.js', 'map-ui.js', 'stuart.js', 'nav.js', 'nav.css', 'tokens.css', 'vendor/maplibre-gl-5.24.1/maplibre-gl.js'):
            self.assertTrue(os.path.exists(os.path.join(self.out, BASE, f)), f)
        info = jload(os.path.join(self.out, 'engine-build.json'))
        self.assertEqual(info['engine'], VERSION)
        self.assertEqual(sorted(info['enginePages']), ['ask.html', 'family-tree.html', 'map.html'])
        self.assertEqual(sorted(info['sitePages']), ['index.html', 'moreau.html'])
        js = read(os.path.join(self.out, 'site-config.js'))
        settings = json.loads(js[js.index('=') + 1:].strip().rstrip(';'))
        self.assertEqual(settings['engine'], {'version': VERSION, 'base': BASE})
        for k in ('people', 'sources', 'places'):
            self.assertRegex(settings['data'][k], r'^data/%s\.json\?v=[0-9a-f]{10}$' % k)
        self.assertTrue(os.path.exists(os.path.join(self.out, settings['archive'])))
        self.assertEqual([a['id'] for a in settings['stuart']['anchors']], ['arthur-hartley', 'marguerite-moreau'])
        self.assertIn('--gold: #8a6a2f;', read(os.path.join(self.out, 'site-theme.css')))
        self.assertFalse(os.path.exists(os.path.join(self.out, 'site.config.json')), 'the settings file is not published')
        self.assertFalse(os.path.exists(os.path.join(self.out, 'README.md')), 'publish.exclude is honoured')

    def test_one_navigation_bar_everywhere(self):
        bars = {}
        for name, html in self.pages.items():
            navs = NAV_RE.findall(html)
            self.assertEqual(len(navs), 1, '%s has %d navigation bars' % (name, len(navs)))
            lit = re.findall(r'<a href="([^"]+)" class="active" aria-current="page">', navs[0])
            self.assertEqual(lit, [name], '%s lights %s' % (name, lit))
            bars[name] = navs[0].replace(' class="active" aria-current="page"', '')
        self.assertEqual(len(set(bars.values())), 1, 'the bar differs between pages')
        self.assertIn('aria-controls="navLinks"', next(iter(bars.values())))

    def test_every_local_link_and_file_resolves(self):
        missing = []
        for name, html in self.pages.items():
            for attr, url in re.findall(r'\b(href|src)="([^"]+)"', html):
                f = validate.local_page(url)
                if f and not os.path.exists(os.path.join(self.out, f)):
                    missing.append('%s: %s' % (name, url))
        self.assertEqual(missing, [])

    def test_engine_files_load_only_from_the_versioned_folder(self):
        names = pages_engine_names()
        stray = []
        for name, html in self.pages.items():
            for url in re.findall(r'\b(?:href|src)="([^"]+)"', html):
                f = url.split('?')[0]
                if os.path.basename(f) in names and not f.startswith(BASE): stray.append('%s: %s' % (name, url))
        self.assertEqual(stray, [])

    def test_settings_and_scripts_order(self):
        for name, html in self.pages.items():
            head = html[:html.lower().index('</head>')]
            sheets = re.findall(r'<link rel="stylesheet" href="([^"]+)"', head)
            self.assertTrue(sheets and sheets[-1] == BASE + 'nav.css', '%s: nav.css should be the last stylesheet, got %s' % (name, sheets[-3:]))
            self.assertEqual(len(re.findall(r'src="site-config\.js\?v=[0-9a-f]{10}"', html)), 1, name)
            self.assertEqual(html.count(BASE + 'nav.js'), 1, name)

    def test_the_theme_comes_after_the_engine_styles(self):
        # a site's theme only wins if it loads after the engine's own colours
        for name, sheet in (('family-tree.html', 'tree-canvas.css'), ('map.html', 'map.css'), ('ask.html', 'stuart.css')):
            html = self.pages[name]
            self.assertLess(html.index(BASE + sheet), html.index('site-theme.css'), name)

    def test_stuart_button_on_site_pages_only(self):
        for name, html in self.pages.items():
            widgets = re.findall(r'<script src="%sstuart\.js"[^>]*\bdata-widget\b' % re.escape(BASE), html)
            if name == 'ask.html':
                self.assertEqual(widgets, [], 'no button on Stuart\'s own page')
                self.assertIn('Content-Security-Policy', html)
            else:
                self.assertEqual(len(widgets), 1, name)

    def test_engine_pages_have_their_titles(self):
        self.assertIn('<title>Family Tree | Hartley &amp; Moreau</title>', self.pages['family-tree.html'])
        self.assertIn('<title>Ask Stuart | Hartley &amp; Moreau</title>', self.pages['ask.html'])
        self.assertIn('Daniel&#x27;s direct line', self.pages['family-tree.html'])
        self.assertIn('<option value="margot">Margot&#x27;s family (Moreau)</option>', self.pages['map.html'])
        self.assertNotIn('{{', ''.join(self.pages.values()))

    def test_stuart_index(self):
        man = jload(os.path.join(self.out, 'archive', 'manifest.json'))
        kb = jload(os.path.join(self.out, 'archive', man['kb']))
        ids = {p['id'] for p in kb['people']}
        self.assertNotIn('auguste-de-moreau', ids, 'a hidden region is left out')
        self.assertIn('pierre-moreau', ids, 'a suspected relative is kept')
        self.assertEqual({p['id'] for p in kb['people'] if p.get('living')}, {'susan-hartley', 'janet-hartley', 'daniel-hartley', 'kate-hartley'})
        daniel = next(p for p in kb['people'] if p['id'] == 'daniel-hartley')
        self.assertEqual(daniel['parents'], ['peter-hartley', 'janet-hartley'], 'living people keep their family links')
        self.assertEqual(kb['site']['anchors'][0]['id'], 'arthur-hartley')
        self.assertEqual(len(kb['examples']), 4, 'the four starter questions in the settings')
        self.assertGreaterEqual(len(kb['sections']), 8)


def pages_engine_names():
    import pages
    return (pages.ENGINE_CSS_GONE | pages.ENGINE_JS_GONE | pages.ENGINE_SHARED) - {'site-config.js'}


class TestBuildChanges(unittest.TestCase):
    """Builds of a changed copy of the sample."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.site = SampleCopy(self.tmp)
        self.out = os.path.join(self.tmp, '_site')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_a_broken_link_stops_the_build_and_leaves_the_last_build(self):
        os.makedirs(self.out)
        with open(os.path.join(self.out, 'marker'), 'w') as f: f.write('the last good build')
        self.site.edit_json('data/people.json', lambda d: self.site.person(d, 'arthur-hartley')['parents'].append('nobody-at-all'))
        code, log = run_build(self.site.dir, self.out)
        self.assertEqual(code, 1)
        self.assertIn('arthur-hartley.parents: no one with the id nobody-at-all', log)
        self.assertTrue(os.path.exists(os.path.join(self.out, 'marker')), 'a failed build must not touch the output')

    def test_data_errors_are_reported(self):
        def break_it(d):
            d['people'].append(copy.deepcopy(d['people'][0]))                       # an id used twice
            self.site.person(d, 'ellen-hartley')['confidence'] = 'certain'         # not on the scale
            self.site.person(d, 'james-hartley')['birth']['date'] = '1880-13'      # not a date
            del self.site.person(d, 'claire-moreau')['sex']                         # required
        self.site.edit_json('data/people.json', break_it)
        cfg = sitecfg.load(self.site.dir)
        errs = '\n'.join(validate.validate_site(self.site.dir, cfg)['errors'])
        self.assertIn('the id thomas-hartley is used twice', errs)
        self.assertIn("'certain' is not one of", errs)
        self.assertIn("'1880-13' is not in the expected form", errs)
        self.assertIn('missing sex', errs)

    def test_unknown_fields_only_warn(self):
        self.site.edit_json('data/people.json', lambda d: self.site.person(d, 'thomas-hartley').update(favouriteColour='green'))
        cfg = sitecfg.load(self.site.dir)
        r = validate.validate_site(self.site.dir, cfg)
        self.assertEqual(r['errors'], [])
        self.assertTrue(any('unknown field "favouriteColour"' in w for w in r['warnings']), r['warnings'])

    def test_settings_naming_people_who_are_not_there(self):
        def bad(c):
            c['tree']['sides']['left'] = 'arthur-hartly'
            c['stuart']['anchors'][1]['id'] = 'margot'
            c['nav'].append({'href': 'gallery.html', 'label': 'Gallery'})
            c['tree']['cardPhotos'] = 'all'
        self.site.edit_json('site.config.json', bad)
        cfg = sitecfg.load(self.site.dir)
        errs = '\n'.join(validate.check_config(cfg)['errors'] + validate.validate_site(self.site.dir, cfg)['errors'])
        self.assertIn('tree.sides.left: no one with the id arthur-hartly', errs)
        self.assertIn('stuart.anchors[1]: no one with the id margot', errs)
        self.assertIn('nav[5] links to gallery.html, which the site does not have', errs)
        self.assertIn("tree.cardPhotos: 'all' is not one of", errs)

    def test_a_business_associate_must_stay_off_the_tree(self):
        def bad(c):
            c['map']['associates']['people']['arthur-hartley'] = 'marguerite-moreau'
            c['map']['associates']['people']['pierre-moreau'] = 'jean-baptiste-moreau'
        self.site.edit_json('site.config.json', bad)
        cfg = sitecfg.load(self.site.dir)
        errs = '\n'.join(validate.check_config(cfg)['errors'] + validate.validate_site(self.site.dir, cfg)['errors'])
        self.assertIn('map.associates.people: arthur-hartley must be in a hidden region', errs)
        self.assertIn('map.associates.people: pierre-moreau is also a suspected relative', errs)

    def test_a_site_without_map_or_stuart(self):
        def off(c):
            c['pages']['map'] = None
            c['pages']['ask'] = None
            c['nav'] = [i for i in c['nav'] if i['href'] not in ('map.html', 'ask.html')]
        self.site.edit_json('site.config.json', off)
        os.remove(self.site.path('data', 'places.json'))
        code, log = run_build(self.site.dir, self.out)
        self.assertEqual(code, 0, log)
        names = os.listdir(self.out)
        self.assertNotIn('map.html', names)
        self.assertNotIn('ask.html', names)
        self.assertNotIn('archive', names)
        for n in ('index.html', 'family-tree.html', 'moreau.html'):
            html = read(os.path.join(self.out, n))
            self.assertNotIn('stuart.js', html, n)
            self.assertNotIn('stuart.css', html, n)
            self.assertNotIn('map.html', html.split('<nav')[1].split('</nav>')[0], n)
        js = read(os.path.join(self.out, 'site-config.js'))
        self.assertIn('"map": null', js)
        self.assertIn('"ask": null', js)

    def test_nav_to_a_page_that_is_off(self):
        self.site.edit_json('site.config.json', lambda c: c['pages'].update(map=None))
        code, log = run_build(self.site.dir, self.out)
        self.assertEqual(code, 1)
        self.assertIn('nav[2] links to map.html, but pages.map is off', log)

    def test_old_pages_are_brought_in_line(self):
        # a page from before the engine: its own copy of the bar, engine files at the top level, its own Stuart tag
        old = ('<!DOCTYPE html><html><head><link rel="stylesheet" href="nav.css"><link rel="stylesheet" href="records.css">'
               '<link rel="stylesheet" href="styles.css"></head><body>'
               '<nav class="main-nav"><div class="nav-inner"><a href="index.html">Old</a><a href="moreau.html" class="active">M</a></div></nav>'
               '<p>Text</p><script src="records.js"></script><script src="config.js"></script>'
               '<script src="stuart.js" data-widget data-avoid=".x"></script></body></html>')
        with open(self.site.path('old.html'), 'w') as f: f.write(old)
        code, log = run_build(self.site.dir, self.out)
        self.assertEqual(code, 0, log)
        html = read(os.path.join(self.out, 'old.html'))
        self.assertNotIn('href="nav.css"', html)
        self.assertNotIn('src="config.js"', html)
        self.assertIn('href="%srecords.css"' % BASE, html)
        self.assertIn('src="%srecords.js"' % BASE, html)
        self.assertIn('<a href="moreau.html" class="active" aria-current="page">The Moreaus</a>', html, 'the lit link is kept')
        self.assertEqual(html.count('stuart.js'), 1)
        self.assertIn('data-avoid=".x"', html, 'the page\'s own placement for the button is kept')
        self.assertIn('<link rel="stylesheet" href="styles.css">', html, 'the site\'s own files are left alone')

    def test_pages_the_build_leaves_alone(self):
        with open(self.site.path('raw.html'), 'w') as f: f.write('<html><body><nav class="main-nav">mine</nav></body></html>')
        self.site.edit_json('site.config.json', lambda c: c.update(process={'exclude': ['raw.html']}))
        code, log = run_build(self.site.dir, self.out)
        self.assertEqual(code, 0, log)
        self.assertEqual(read(os.path.join(self.out, 'raw.html')), '<html><body><nav class="main-nav">mine</nav></body></html>')


class TestMigration(unittest.TestCase):
    def test_version_0_comes_up_to_version_1(self):
        tmp = tempfile.mkdtemp()
        try:
            site = SampleCopy(tmp)
            # turn the sample back into version 0: tree settings in people.json meta, "living", "inEngland"
            tree_bits = {}
            def to_v0_config(c):
                for k in ('familyLabel', 'rootPersonId', 'directLineLabel', 'generations', 'sides'):
                    tree_bits[k] = c['tree'].pop(k)
            site.edit_json('site.config.json', to_v0_config)
            def to_v0_people(d):
                d['meta'].pop('schemaVersion')
                d['meta'].update(tree_bits)
                site.person(d, 'kate-hartley')['living'] = True
                site.person(d, 'thomas-hartley')['living'] = False
            site.edit_json('data/people.json', to_v0_people)
            site.edit_json('data/places.json', lambda d: [pl.update(inEngland=pl.pop('inHomeRegion')) for pl in d['places']])
            cfg = sitecfg.load(site.dir)
            self.assertTrue(any('no schemaVersion' in w for w in validate.validate_site(site.dir, cfg)['warnings']))

            with open(os.devnull, 'w') as null:
                stdout, sys.stdout = sys.stdout, null
                try: migrate.migrate(site.dir, write=True)
                finally: sys.stdout = stdout
            after = jload(site.path('data', 'people.json'))
            self.assertEqual(list(after['meta'])[0], 'schemaVersion')
            self.assertEqual(after['meta']['schemaVersion'], 1)
            self.assertFalse(any(k in after['meta'] for k in tree_bits))
            self.assertFalse(any('living' in p for p in after['people']))
            cfg_after = jload(site.path('site.config.json'))
            for k, v in tree_bits.items():
                self.assertEqual(cfg_after['tree'][k], v, k)
            places = jload(site.path('data', 'places.json'))['places']
            self.assertTrue(all('inHomeRegion' in p and 'inEngland' not in p for p in places))
            # and the result is the sample again, as far as the build is concerned
            self.assertEqual(jload(site.path('data', 'people.json')), jload(os.path.join(SAMPLE, 'data', 'people.json')))
            cfg = sitecfg.load(site.dir)
            r = validate.validate_site(site.dir, cfg)
            self.assertEqual(r['errors'] + r['warnings'], [])
        finally:
            shutil.rmtree(tmp)


class TestConverter(unittest.TestCase):
    """family-data.js, the format some of the first sites used, into the engine's format."""
    SOURCE = """// The Testers. Comments, single quotes, apostrophes in double quotes and trailing commas.
const FAMILY_DATA = {
    rootPersonId: 'tom_tester',
    people: [
        { id: 'old_tester', firstName: 'Old', lastName: 'Tester', birthYear: 1850, birthYearApprox: true,
          deathYear: 1920, isLiving: false, confidence: 'low', generation: -1, notes: "The family's founder. Sold bread.",
          source: 'Family testimony', },
        { id: 'ann_tester', firstName: 'Ann', lastName: 'Tester', aka: 'n\u00e9e Baker', birthYear: 1855,
          birthDate: '2 March 1855', birthPlace: 'Leeds', deathYear: null, isLiving: false, confidence: 'verified',
          generation: -1, notes: 'Baker by birth.', source: '1881 census', },
        { id: 'tom_tester', firstName: 'Tom', lastName: 'Tester', birthYear: 1880, isLiving: false, confidence: 'high',
          generation: 0, notes: '', source: '1881 census' },
    ],
    relationships: [
        { type: 'spouse', fromPersonId: 'old_tester', toPersonId: 'ann_tester', startYear: 1878 },
        { type: 'parent_child', fromPersonId: 'old_tester', toPersonId: 'tom_tester' },
        { type: 'parent_child', fromPersonId: 'ann_tester', toPersonId: 'tom_tester' },
    ],
};
if (typeof module !== 'undefined') module.exports = FAMILY_DATA;
"""

    def test_convert(self):
        import convert_family_data, jsdata
        name, data = jsdata.read_assignment(self.SOURCE)
        self.assertEqual(name, 'FAMILY_DATA')
        people, sources, root, notes = convert_family_data.convert(data)
        by = {p['id']: p for p in people['people']}
        self.assertEqual(root, 'tom-tester')
        self.assertEqual(by['old-tester']['generation'], 0, 'generations start at 0')
        self.assertEqual(by['old-tester']['birth']['display'], 'about 1850')
        self.assertEqual(by['ann-tester']['birth']['date'], '1855-03-02')
        self.assertEqual(by['ann-tester']['nameVariants'][0], {'name': 'Ann Baker', 'note': 'maiden name', 'sourceIds': ['1881-census']})
        self.assertEqual([by[i]['confidence'] for i in ('old-tester', 'ann-tester', 'tom-tester')], ['unverified', 'confirmed', 'probable'])
        self.assertEqual(by['tom-tester']['parents'], ['old-tester', 'ann-tester'])
        self.assertEqual(by['ann-tester']['spouses'][0]['marriageDate'], '1878')
        self.assertTrue(all(by[i]['isDirectLine'] for i in by))
        self.assertEqual(by['old-tester']['summary'], "The family's founder.")
        self.assertEqual(sorted(s['id'] for s in sources['sources']), ['1881-census', 'family-testimony'])
        # and the result passes the data checker
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, 'data'))
            for fn, doc in (('people.json', people), ('sources.json', sources)):
                with open(os.path.join(tmp, 'data', fn), 'w') as f: json.dump(doc, f)
            with open(os.path.join(tmp, 'index.html'), 'w') as f: f.write('<html></html>')
            with open(os.path.join(tmp, 'site.config.json'), 'w') as f:
                json.dump({'schemaVersion': 1, 'site': {'name': 'Testers'}, 'pages': {'tree': 'family-tree.html', 'map': None, 'ask': None},
                           'nav': [{'href': 'index.html', 'label': 'Home'}], 'tree': {'rootPersonId': root}}, f)
            r = validate.validate_site(tmp, sitecfg.load(tmp))
            self.assertEqual(r['errors'], [])
        finally:
            shutil.rmtree(tmp)

    def test_code_is_not_data(self):
        import jsdata
        with self.assertRaises(ValueError):
            jsdata.read_assignment("const FAMILY_DATA = { people: fetchPeople() };")


class TestHousekeeping(unittest.TestCase):
    def test_no_em_or_en_dashes(self):
        bad = []
        for top in ('build', 'engine', 'templates', 'schema', 'docs', 'sample', 'tests', '.github', 'tools'):
            for root, dirs, files in os.walk(os.path.join(ROOT, top)):
                dirs[:] = [d for d in dirs if d not in ('vendor', 'fonts', '__pycache__', 'map-styles')]
                for f in files:
                    if not f.endswith(('.py', '.js', '.css', '.html', '.json', '.md', '.yml', '.mjs', '.txt')): continue
                    p = os.path.join(root, f)
                    if DASHES.search(read(p)): bad.append(os.path.relpath(p, ROOT))
        for f in ('README.md', 'CHANGELOG.md', 'channels.json', 'LICENSE'):
            p = os.path.join(ROOT, f)
            if os.path.exists(p) and DASHES.search(read(p)): bad.append(f)
        self.assertEqual(bad, [])

    def test_schemas_are_valid_json_and_documented(self):
        for name in ('family-data.schema.json', 'site-config.schema.json'):
            s = jload(os.path.join(ROOT, 'schema', name))
            self.assertEqual(s['$schema'], 'https://json-schema.org/draft/2020-12/schema')


if __name__ == '__main__':
    unittest.main(verbosity=1)
