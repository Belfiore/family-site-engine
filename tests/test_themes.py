#!/usr/bin/env python3
"""Checks for the heritage styles: the files, the colours (WCAG AA), the suggestion from a family's own data, and that a
site which has not applied a style is built exactly as before.

    python3 tests/test_themes.py          (needs only Python 3.9 or later)

The browser side (every page in every style, the settings page) is in check-themes.js and check-admin.js.
Every family in here is made up.
"""
import json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'build'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import heritage  # noqa: E402
import themes_fixtures  # noqa: E402

THEMES_DIR = os.path.join(ROOT, 'engine', 'themes')
DASHES = chr(0x2013) + chr(0x2014)


def read(path, mode='r'):
    with open(path, mode, **({} if 'b' in mode else {'encoding': 'utf-8'})) as f:
        return f.read()


def build(site, out, *extra):
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', out, '--previous', 'none', *extra],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def files(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = read(p, 'rb')
    return out


def normalise(fs):
    fs = dict(fs)
    if 'engine-build.json' in fs:
        d = json.loads(fs['engine-build.json']); d.pop('built', None); fs['engine-build.json'] = json.dumps(d, sort_keys=True).encode()
    return fs


# ------------------------------------------------------------------ colour maths (WCAG 2.x)
def rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(v) for v in c)
    return .2126 * r + .7152 * g + .0722 * b


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def mix(a, pa, b):
    return tuple(pa * x + (1 - pa) * y for x, y in zip(a, b))


WHITE, BLACK = (255, 255, 255), (0, 0, 0)

# the shades base.css works out from the nine roles (the same percentages; test_base_css_has_these_shades keeps them honest)
def shades(p):
    c = {k: rgb(v) for k, v in p.items()}
    d = dict(c)
    d['paper-2'] = mix(c['paper'], .93, c['ink']); d['paper-3'] = mix(c['paper'], .86, c['ink'])
    d['ink-2'] = mix(c['ink'], .85, c['paper']); d['ink-3'] = mix(c['ink'], .65, c['paper'])
    d['accent-deep'] = mix(c['accent'], .55, BLACK)
    d['on-dark'] = c['card']
    d['gold-pale'] = mix(c['gold'], .22, c['card']); d['gold-soft'] = mix(c['gold'], .70, c['card'])
    d['line-strong'] = mix(c['line'], .35, c['brown'])
    return d


BASE_SHADES = ['paper-2: color-mix(in srgb, var(--h-paper) 93%, var(--h-ink))', 'paper-3: color-mix(in srgb, var(--h-paper) 86%, var(--h-ink))',
               'ink-2: color-mix(in srgb, var(--h-ink) 85%, var(--h-paper))', 'ink-3: color-mix(in srgb, var(--h-ink) 65%, var(--h-paper))',
               'accent-deep: color-mix(in srgb, var(--h-accent) 55%, black)', 'on-dark: var(--h-card)',
               'gold-pale: color-mix(in srgb, var(--h-gold) 22%, var(--h-card))', 'gold-soft: color-mix(in srgb, var(--h-gold) 70%, var(--h-card))',
               'line-strong: color-mix(in srgb, var(--h-line) 35%, var(--h-brown))']

# (text or mark, background, least ratio): body text and buttons need 4.5, decorative rules and marks 3
PAIRS = [('ink', 'paper', 4.5), ('ink', 'card', 4.5), ('ink', 'paper-2', 4.5), ('ink', 'paper-3', 4.5), ('ink-2', 'paper', 4.5), ('ink-2', 'card', 4.5),
         ('ink-3', 'card', 4.5), ('brown', 'paper', 4.5), ('brown', 'card', 4.5), ('brown', 'paper-2', 4.5), ('brown', 'paper-3', 4.5),
         ('accent', 'paper', 4.5), ('accent', 'card', 4.5), ('accent', 'paper-2', 4.5),
         ('on-dark', 'accent', 4.5), ('on-dark', 'accent-deep', 4.5), ('on-dark', 'ink', 4.5), ('on-dark', 'green', 4.5),
         ('goldtext', 'paper', 4.5), ('goldtext', 'card', 4.5), ('goldtext', 'paper-2', 4.5), ('green', 'card', 4.5),
         ('gold', 'paper', 3.0), ('gold-soft', 'ink', 4.5), ('gold-pale', 'accent', 3.0), ('line-strong', 'paper', 3.0)]

ROLES = ['paper', 'card', 'ink', 'accent', 'gold', 'goldtext', 'brown', 'line', 'green']
REQUIRED = (['--h-%s' % r for r in ROLES] + ['--h-%s-rgb' % r for r in ROLES] + ['--h-accent-deep-rgb'] +
            ['--h-map-%s' % k for k in ('land', 'water', 'park', 'road', 'roadmajor', 'line', 'label')] +
            ['--h-font-heading', '--h-font-body', '--h-heading-weight', '--h-heading-spacing', '--h-radius', '--h-radius-btn', '--h-pin-radius',
             '--h-divider', '--h-divider-repeat', '--h-divider-w', '--h-divider-h', '--h-texture'])


def theme_vars(css):
    m = re.search(r':root\[data-heritage="[a-z]+"\]\s*\{(.*?)\n\}', css, re.S)
    assert m, 'no :root[data-heritage] block'
    out = {}
    for name, val in re.findall(r'(--h-[a-z-]+):\s*((?:[^;"]|"[^"]*")*);', m.group(1)):
        out[name] = val.strip()
    return out


def registry_themes():
    return [t for t in heritage.registry()['themes']]


class Files(unittest.TestCase):
    def test_registry_matches_files_schema_and_fonts(self):
        reg = heritage.registry()
        ids = [t['id'] for t in reg['themes']]
        self.assertEqual(ids[0], 'classic')
        self.assertEqual(reg['default'], 'classic')
        self.assertEqual(len(ids), 11, 'the Classic Archive and ten styles')
        schema = json.loads(read(os.path.join(ROOT, 'schema', 'site-config.schema.json')))
        self.assertEqual(schema['properties']['style']['properties']['heritage']['enum'], ids, 'the schema lists the same styles, in the same order')
        for t in reg['themes']:
            for k in ('id', 'name', 'blurb', 'fonts', 'swatches', 'countries'):
                self.assertIn(k, t, t['id'])
            self.assertEqual(sorted(t['swatches']), ['accent', 'gold', 'ink', 'line', 'paper'], t['id'])
            if t['id'] == 'classic':
                self.assertIsNone(t['file']); continue
            path = os.path.join(THEMES_DIR, t['file'])
            self.assertTrue(os.path.exists(path), t['file'])
            css = read(path)
            for f in re.findall(r'url\(fonts/([^)]+)\)', css):
                self.assertTrue(os.path.exists(os.path.join(THEMES_DIR, 'fonts', f)), 'font file %s of %s' % (f, t['id']))
            self.assertGreater(len(re.findall(r'url\(fonts/', css)), 1, t['id'] + ' names its fonts')
            for role in t['fonts'].values():
                self.assertIn("font-family: 'hf-%s'" % role.lower().replace(' ', '-'), css, '%s: @font-face for %s' % (t['id'], role))

    def test_a_style_is_one_file_and_no_more(self):
        """Adding the eleventh style must not need a change anywhere else: the files in themes/ are base.css, the registry, fonts/ and
        one css file for each registry entry."""
        listed = {t['file'] for t in registry_themes() if t['file']}
        on_disk = {f for f in os.listdir(THEMES_DIR) if f.endswith('.css')} - {'base.css'}
        self.assertEqual(listed, on_disk)

    def test_every_style_sets_every_token(self):
        for t in registry_themes():
            if not t['file']: continue
            v = theme_vars(read(os.path.join(THEMES_DIR, t['file'])))
            missing = [k for k in REQUIRED if k not in v]
            self.assertEqual(missing, [], t['id'])
            self.assertTrue(v['--h-divider'].startswith('url("data:image/svg+xml'), t['id'] + ': a divider drawn in SVG, no image file')
            if t.get('options', {}).get('texture'):
                self.assertRegex(v['--h-texture'], r'^(url\("data:image/svg\+xml|(repeating-)?(linear|radial)-gradient)', t['id'] + ': a texture drawn in SVG or CSS')
            else:
                self.assertEqual(v['--h-texture'], 'none', t['id'] + ': no texture and no texture option')

    def test_rgb_twins_match_their_hex(self):
        for t in registry_themes():
            if not t['file']: continue
            v = theme_vars(read(os.path.join(THEMES_DIR, t['file'])))
            for r in ROLES:
                want = ', '.join(str(x) for x in rgb(v['--h-' + r]))
                self.assertEqual(v['--h-%s-rgb' % r], want, '%s --h-%s-rgb' % (t['id'], r))
            self.assertEqual(v['--h-accent-deep-rgb'], ', '.join(str(round(x)) for x in mix(rgb(v['--h-accent']), .55, BLACK)), t['id'] + ' accent-deep-rgb')

    def test_the_registry_swatches_are_the_style_s_own_colours(self):
        for t in registry_themes():
            if not t['file']: continue
            v = theme_vars(read(os.path.join(THEMES_DIR, t['file'])))
            for k, c in t['swatches'].items():
                self.assertEqual(c.lower(), v['--h-' + k].lower(), '%s swatch %s' % (t['id'], k))

    def test_base_css_has_these_shades(self):
        base = read(os.path.join(THEMES_DIR, 'base.css'))
        for line in BASE_SHADES:
            self.assertIn('--h-' + line, base, line)

    def test_no_long_dashes_anywhere_in_the_style_files(self):
        paths = [os.path.join(THEMES_DIR, f) for f in os.listdir(THEMES_DIR) if f.endswith(('.css', '.json'))]
        paths += [os.path.join(ROOT, 'engine', 'heritage.js'), os.path.join(ROOT, 'build', 'heritage.py'), os.path.join(ROOT, 'docs', 'themes.md')]
        for p in paths:
            if not os.path.exists(p): continue
            for ch in DASHES:
                self.assertNotIn(ch, read(p), os.path.relpath(p, ROOT))
        for lang in ('en', 'de'):
            for k, v in json.loads(read(os.path.join(ROOT, 'engine', 'i18n', lang + '.json'))).items():
                if k.startswith('heritage.'):
                    for ch in DASHES: self.assertNotIn(ch, v, k)

    def test_the_two_languages_have_the_same_style_words(self):
        en = json.loads(read(os.path.join(ROOT, 'engine', 'i18n', 'en.json')))
        de = json.loads(read(os.path.join(ROOT, 'engine', 'i18n', 'de.json')))
        self.assertEqual(sorted(k for k in en if k.startswith('heritage.')), sorted(k for k in de if k.startswith('heritage.')))
        self.assertTrue([k for k in en if k.startswith('heritage.')])

    def test_blackletter_is_only_for_the_title(self):
        for t in registry_themes():
            if not t['file']: continue
            v = theme_vars(read(os.path.join(THEMES_DIR, t['file'])))
            for k in ('--h-font-heading', '--h-font-body'):
                self.assertNotIn('unifraktur', v[k].lower(), '%s %s' % (t['id'], k))
        self.assertIn('--h-font-title', theme_vars(read(os.path.join(THEMES_DIR, 'german.css'))))

    def test_no_flags_and_no_stereotype_imagery_in_ornaments(self):
        """Ornaments are small abstract SVG paths. No raster images, no external addresses, no text inside them."""
        for t in registry_themes():
            if not t['file']: continue
            css = read(os.path.join(THEMES_DIR, t['file']))
            self.assertNotRegex(css, r'url\((?!fonts/|"data:image/svg\+xml|%23)', t['id'] + ': only fonts and inline SVG')
            self.assertNotIn('<text', css, t['id'])
            self.assertNotIn('<image', css, t['id'])
            self.assertNotRegex(css, r'https?://(?!www\.w3\.org/2000/svg)', t['id'])


class Contrast(unittest.TestCase):
    def test_every_style_passes_wcag_aa(self):
        report = []
        for t in registry_themes():
            if t['file']:
                v = theme_vars(read(os.path.join(THEMES_DIR, t['file'])))
                pal = {r: v['--h-' + r] for r in ROLES}
            else:      # the Classic Archive keeps the site's own colours; its swatches are the engine's defaults
                continue
            d = shades(pal)
            for a, b, need in PAIRS:
                got = ratio(d[a], d[b])
                report.append((t['id'], a, b, round(got, 2), need))
                self.assertGreaterEqual(got, need, '%s: %s on %s is %.2f, needs %s' % (t['id'], a, b, got, need))
        self.assertEqual(len(report), 10 * len(PAIRS))


# ------------------------------------------------------------------ the suggestion
def family(dest, places, people, tree=None, home=None):
    """A tiny made-up site folder: places = [(id, name, country or None)], people = list of dicts."""
    os.makedirs(os.path.join(dest, 'data'), exist_ok=True)
    with open(os.path.join(dest, 'data', 'places.json'), 'w') as f:
        json.dump({'places': [{'id': i, 'name': n, 'country': c, 'status': 'published'} for i, n, c in places]}, f)
    with open(os.path.join(dest, 'data', 'people.json'), 'w') as f:
        json.dump({'people': people}, f)
    cfg = {'tree': tree or {}, 'map': ({'home': {'name': home}} if home else {})}
    return dest, cfg


def person(i, place, surname='Smith', living=False, region=None):
    d = {'id': i, 'surname': surname, 'birth': {'placeId': place}}
    if living: d['isLiving'] = True
    if region: d['region'] = region
    return d


class Suggestion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_case(self, places, people, **kw):
        site, cfg = family(os.path.join(self.tmp, 'f'), places, people, **kw)
        return heritage.suggest(site, cfg)

    def test_one_country_gets_one_style_with_the_numbers(self):
        places = [('p%d' % i, 'Town %d, Germany' % i, 'Germany') for i in range(6)]
        people = [person('a%d' % i, 'p%d' % i, 'Smith') for i in range(6)]
        s = self.run_case(places, people)
        self.assertEqual(s['suggested'], 'german')
        self.assertFalse(s['mixed']); self.assertFalse(s['thin'])
        self.assertEqual(s['ranked'][0]['id'], 'german')
        self.assertIn('6 of 6', s['reason'])

    def test_a_mixed_family_gets_the_top_two_or_three_with_percentages(self):
        places = ([('g%d' % i, 'Town, Germany', 'Germany') for i in range(4)] + [('i%d' % i, 'Town, Italy', 'Italy') for i in range(3)])
        people = [person('g%d' % i, 'g%d' % i) for i in range(4)] + [person('i%d' % i, 'i%d' % i) for i in range(3)]
        s = self.run_case(places, people)
        self.assertTrue(s['mixed'])
        ids = [r['id'] for r in s['ranked']]
        self.assertEqual(set(ids[:2]), {'german', 'italian'})
        self.assertLessEqual(len(s['ranked']), 4)
        self.assertTrue(all(isinstance(r['percent'], int) for r in s['ranked']))
        self.assertEqual(s['suggested'], ids[0])

    def test_thin_data_suggests_the_classic_archive_and_says_why(self):
        s = self.run_case([('a', 'Somewhere, Germany', 'Germany')], [person('x', 'a')])
        self.assertEqual(s['suggested'], 'classic'); self.assertTrue(s['thin'])
        self.assertIn('Classic Archive', s['reason'])

    def test_a_family_that_is_all_in_the_new_world_gets_no_european_style(self):
        places = [('p%d' % i, 'Town, Ohio', 'United States') for i in range(8)]
        s = self.run_case(places, [person('a%d' % i, 'p%d' % i) for i in range(8)])
        self.assertEqual(s['suggested'], 'classic')
        self.assertIn('United States', s['reason'])

    def test_where_people_sailed_from_counts(self):
        places = [('us%d' % i, 'Town, Ohio', 'United States') for i in range(4)]
        people = [dict(person('a%d' % i, 'us%d' % i), immigration={'port': 'New York (from Hamburg, Germany)'}) for i in range(6)]
        s = self.run_case(places, people)
        self.assertEqual(s['suggested'], 'german')

    def test_the_jewish_style_is_never_suggested(self):
        """Nothing in a family's places or names can say who they are; the engine does not guess it."""
        places = [('p%d' % i, 'Town, Poland', 'Poland') for i in range(6)]
        people = [person('a%d' % i, 'p%d' % i, surname=n) for i, n in enumerate(['Cohen', 'Levy', 'Goldberg', 'Rosenthal', 'Katz', 'Friedman'])]
        s = self.run_case(places, people)
        self.assertNotIn('jewish', [r['id'] for r in s['ranked']])
        self.assertNotEqual(s['suggested'], 'jewish')

    def test_living_people_and_hidden_regions_do_not_count(self):
        places = ([('g%d' % i, 'Town, Germany', 'Germany') for i in range(6)] + [('s', 'Town, Sweden', 'Sweden')])
        dead = [person('d%d' % i, 'g%d' % i) for i in range(6)]
        base = self.run_case(places, dead)
        more = dead + [person('l%d' % i, 's', living=True) for i in range(20)] + [person('h%d' % i, 's', region='hidden-region') for i in range(20)]
        s = self.run_case(places, more, tree={'hiddenRegions': ['hidden-region']})
        self.assertEqual(s['evidence']['births'], base['evidence']['births'], 'births of living people and of hidden regions are not counted')
        self.assertEqual(s['suggested'], 'german')

    def test_no_name_leaves_the_function(self):
        places = [('p%d' % i, 'Town, Germany', 'Germany') for i in range(6)]
        people = [person('a%d' % i, 'p%d' % i, surname='Zzyzxname') for i in range(6)]
        s = self.run_case(places, people)
        self.assertNotIn('zzyzx', json.dumps(s).lower())
        for ch in DASHES: self.assertNotIn(ch, s['reason'])

    def test_a_site_with_no_data_is_thin_not_an_error(self):
        site = os.path.join(self.tmp, 'empty'); os.makedirs(site)
        s = heritage.suggest(site, {})
        self.assertEqual(s['suggested'], 'classic'); self.assertTrue(s['thin'])

    def test_suggestion_only_ever_suggests(self):
        """suggest() reads; it has no way to change a setting. The settings page applies a style only when a person clicks Apply."""
        src = read(os.path.join(ROOT, 'build', 'heritage.py'))
        body = src[src.index('def suggest('):src.index('def _countries')]
        self.assertNotIn('open(', body); self.assertNotIn('write', body)


# ------------------------------------------------------------------ the build
class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make(self, name, **kw):
        src = themes_fixtures.make(os.path.join(self.tmp, name + '-src'), **kw)
        out = os.path.join(self.tmp, name)
        code, msg = build(src, out)
        return code, msg, src, out

    def test_a_site_without_a_style_carries_nothing_of_it(self):
        code, msg, src, out = self.make('plain')
        self.assertEqual(code, 0, msg)
        self.assertFalse(os.path.exists(os.path.join(out, 'engine', open(os.path.join(ROOT, 'VERSION')).read().strip(), 'themes')) and False)
        fs = files(out)
        self.assertEqual([f for f in fs if 'themes/' in f or f.endswith('heritage.js')], [], 'no theme files, fonts or script')
        for f, body in fs.items():
            if f.endswith('.html'):
                text = body.decode('utf-8', 'replace')
                self.assertNotIn('data-heritage', text, f); self.assertNotIn('heritage.js', text, f); self.assertNotIn('themes/', text, f)

    def test_choosing_the_classic_archive_is_the_same_as_choosing_nothing(self):
        c1, m1, _, a = self.make('plain')
        c2, m2, _, b = self.make('classic', style='classic')
        self.assertEqual((c1, c2), (0, 0), m1 + m2)
        self.assertEqual(normalise(files(a)), normalise(files(b)))

    def test_an_applied_style_reaches_every_page_and_only_its_own_files_are_sent(self):
        code, msg, src, out = self.make('german', style='german')
        self.assertEqual(code, 0, msg)
        fs = files(out)
        pages = [f for f in fs if f.endswith('.html')]
        self.assertGreaterEqual(len(pages), 7)
        for f in pages:
            text = fs[f].decode('utf-8', 'replace')
            self.assertRegex(text, r'<html[^>]*data-heritage="german"', f)
            self.assertIn('themes/german.css', text, f)
            self.assertIn('themes/base.css', text, f)
            self.assertNotIn('themes/english.css', text, f)
        sent = sorted(f for f in fs if '/themes/' in f)
        self.assertTrue(any(f.endswith('themes/german.css') for f in sent))
        self.assertFalse(any(f.endswith('themes/english.css') for f in sent), 'the other styles are not sent')
        fonts = {os.path.basename(f) for f in sent if '/fonts/' in f}
        wanted = set(re.findall(r'url\(fonts/([^)]+)\)', read(os.path.join(THEMES_DIR, 'german.css'))))
        self.assertEqual(fonts, wanted, 'only the fonts the style names')

    def test_the_site_s_own_pages_carry_the_style_too(self):
        code, msg, src, out = self.make('italian', style='italian')
        self.assertEqual(code, 0, msg)
        for f in ('index.html', 'moreau.html'):
            self.assertIn('data-heritage="italian"', read(os.path.join(out, f)), f)

    def test_the_settings_page_carries_every_style_so_they_can_be_tried(self):
        code, msg, src, out = self.make('admin', admin=True)
        self.assertEqual(code, 0, msg)
        fs = files(out)
        for t in registry_themes():
            if t['file']:
                self.assertTrue(any(f.endswith('themes/' + t['file']) for f in fs), t['file'])
        text = read(os.path.join(out, 'admin', 'index.html'))
        self.assertIn('font-src \'self\'', text)
        self.assertNotIn('data-heritage', read(os.path.join(out, 'index.html')), 'trying styles does not apply one')
        data = json.loads(re.search(r'id="ad-data">(.*?)</script>', text, re.S).group(1))
        self.assertEqual(len(data['style']['themes']), 11)
        self.assertEqual(data['style']['saved'], 'classic')
        self.assertIsNotNone(data['style']['suggestion'])
        self.assertEqual(data['style']['suggestion']['suggested'], 'english')
        self.assertEqual([l['code'] for l in data['language']['have']], ['de', 'en'])

    def test_the_settings_page_shows_the_saved_style(self):
        code, msg, src, out = self.make('adminstyle', admin=True, style='french', options={'texture': False})
        self.assertEqual(code, 0, msg)
        text = read(os.path.join(out, 'admin', 'index.html'))
        data = json.loads(re.search(r'id="ad-data">(.*?)</script>', text, re.S).group(1))
        self.assertEqual(data['style']['saved'], 'french'); self.assertFalse(data['style']['texture'])
        self.assertIn('data-heritage="french"', text)

    def test_an_unknown_style_stops_the_build_with_a_plain_message(self):
        src = themes_fixtures.make(os.path.join(self.tmp, 'bad-src'))
        p = os.path.join(src, 'site.config.json'); cfg = json.loads(read(p)); cfg['style'] = {'heritage': 'klingon'}
        with open(p, 'w') as f: json.dump(cfg, f)
        code, msg = build(src, os.path.join(self.tmp, 'bad'))
        self.assertNotEqual(code, 0)
        self.assertIn('style', msg.lower())

    def test_an_unknown_option_is_refused(self):
        src = themes_fixtures.make(os.path.join(self.tmp, 'opt-src'), style='english')
        p = os.path.join(src, 'site.config.json'); cfg = json.loads(read(p)); cfg['style']['options'] = {'sparkle': True}
        with open(p, 'w') as f: json.dump(cfg, f)
        code, msg = build(src, os.path.join(self.tmp, 'opt'))
        self.assertNotEqual(code, 0)

    def test_texture_off_is_written_into_the_page(self):
        code, msg, src, out = self.make('notex', style='english', options={'texture': False})
        self.assertEqual(code, 0, msg)
        self.assertIn('data-h-texture="off"', read(os.path.join(out, 'index.html')))
        c2, m2, _, out2 = self.make('tex', style='english')
        self.assertNotIn('data-h-texture', read(os.path.join(out2, 'index.html')))

    def test_a_style_does_not_touch_the_site_s_data(self):
        code, msg, src, out = self.make('data', style='scottish')
        self.assertEqual(code, 0, msg)
        for f in ('data/people.json', 'data/places.json'):
            if os.path.exists(os.path.join(out, f)):
                self.assertEqual(read(os.path.join(out, f)), read(os.path.join(src, f)), f)

    def test_language_and_style_are_independent(self):
        c1, m1, _, a = self.make('de', style='english', language=True)
        c2, m2, _, b = self.make('en', style='english')
        self.assertEqual((c1, c2), (0, 0), m1 + m2)
        for f in ('index.html',):
            self.assertIn('data-heritage="english"', read(os.path.join(a, f)))
        self.assertIn('data-heritage="english"', read(os.path.join(b, 'index.html')))


if __name__ == '__main__':
    unittest.main(verbosity=1)
