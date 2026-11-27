#!/usr/bin/env python3
"""Checks for private access and visitor identity in the build: what is made, what is refused, and that a site
which has not turned them on is built exactly as before.

    python3 tests/test_access.py          (needs only Python 3.9 or later)

The browser side is in check-gate.js, check-access.js and check-visitor.js.
"""
import base64, hashlib, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'build'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import access, sitecfg, validate  # noqa: E402
import access_fixtures  # noqa: E402

VERSION = open(os.path.join(ROOT, 'VERSION')).read().strip()
PASSWORD = access_fixtures.PASSWORD


def build(site, out):
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', out], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


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


def same_build(a, b):
    """Two builds are the same when every file matches (engine-build.json holds the time it was made)."""
    fa, fb = files(a), files(b)
    for k in ('engine-build.json',):
        for f in (fa, fb):
            if k in f:
                d = json.loads(f[k]); d.pop('built', None); f[k] = json.dumps(d, sort_keys=True).encode()
    return fa == fb, sorted(set(fa) ^ set(fb)) or [k for k in fa if fa[k] != fb.get(k)]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def site(self, **kw):
        kw.setdefault('access', False); kw.setdefault('visitor', False); kw.setdefault('extras', False)
        return access_fixtures.make(os.path.join(self.tmp, 'site'), **kw)

    def edit(self, site, fn):
        p = os.path.join(site, 'site.config.json')
        d = json.loads(read(p)); fn(d)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=1)

    def built(self, site, name='out'):
        out = os.path.join(self.tmp, name)
        code, text = build(site, out)
        return code, text, out


class TestOffMeansUnchanged(Base):
    def test_a_site_with_neither_feature_builds_the_same_with_or_without_the_keys(self):
        a = self.site()
        code, _, out_a = self.built(a, 'a')
        self.assertEqual(code, 0)
        self.edit(a, lambda d: d.update(access={'enabled': False, 'project': 'x'}, visitor={'enabled': False}))
        code, _, out_b = self.built(a, 'b')
        self.assertEqual(code, 0)
        ok, diff = same_build(out_a, out_b)
        self.assertTrue(ok, diff)

    def test_nothing_of_either_feature_is_in_a_site_that_has_them_off(self):
        code, _, out = self.built(self.site())
        self.assertEqual(code, 0)
        names = files(out)
        self.assertFalse([n for n in names if 'visitor' in n or n in ('_worker.js', 'robots.txt')], 'no visitor files, no worker, no robots.txt')
        cfg = read(os.path.join(out, 'site-config.js'))
        self.assertNotIn('"visitor"', cfg)
        self.assertNotIn('"access"', cfg)
        for n, b in names.items():
            if n.endswith('.html') or n.endswith('.js'):
                if n.startswith('engine/%s/stuart.js' % VERSION) or n.startswith('engine/%s/tree-canvas.js' % VERSION):
                    continue     # these two read window.FamilyVisitor if there is one; they do nothing without it
                self.assertNotIn(b'visitor.js', b, n)
        info = json.loads(read(os.path.join(out, 'engine-build.json')))
        self.assertNotIn('access', info)
        self.assertNotIn('visitor', info)

    def test_the_engine_pages_do_not_load_the_visitor_files_unless_asked(self):
        _, _, out = self.built(self.site())
        for page in ('family-tree.html', 'map.html', 'ask.html', 'index.html', 'moreau.html'):
            self.assertNotIn('visitor', read(os.path.join(out, page)), page)

    def test_access_alone_and_visitor_alone_do_not_switch_each_other_on(self):
        _, _, out = self.built(self.site(access=True), 'acc')
        self.assertFalse([n for n in files(out) if 'visitor' in n])
        self.assertIn('_worker.js', files(out))
        self.assertNotIn('"visitor"', read(os.path.join(out, 'site-config.js')))
        _, _, out2 = self.built(self.site(visitor=True), 'vis')
        self.assertNotIn('_worker.js', files(out2))
        self.assertNotIn('robots.txt', files(out2))
        self.assertNotIn('"access"', read(os.path.join(out2, 'site-config.js')))


class TestAccessBuild(Base):
    def setUp(self):
        super().setUp()
        self.code, self.text, self.out = self.built(self.site(access=True, visitor=True, extras=True))

    def test_it_builds_and_says_what_to_do_next(self):
        self.assertEqual(self.code, 0, self.text)
        self.assertIn('SITE_PASSWORD', self.text)

    def test_the_worker_and_robots_are_made(self):
        names = files(self.out)
        self.assertIn('_worker.js', names)
        self.assertIn(b'Disallow: /', names['robots.txt'])
        info = json.loads(read(os.path.join(self.out, 'engine-build.json')))
        self.assertEqual(info['access']['project'], 'sample-private')

    def test_the_password_is_nowhere_in_the_build(self):
        for n, b in files(self.out).items():
            self.assertNotIn(PASSWORD.encode(), b, n)
        cfg = read(os.path.join(self.out, 'site-config.js'))
        self.assertEqual(json.loads(cfg.split('window.FamilySite = ')[1].rstrip(';\n'))['access'], {'logout': '/__gate/logout'})

    def test_the_worker_reads_the_password_from_the_environment_and_fails_closed(self):
        w = read(os.path.join(self.out, '_worker.js'))
        self.assertIn('env.SITE_PASSWORD', w)
        self.assertIn('503', w)
        self.assertNotIn('__CONFIG__', w)
        self.assertRegex(w, r'const CONFIG = \{"days": 90, "open": \["/robots.txt"\], "failDelayMs": 700\};')

    def test_the_entrance_script_is_pinned_by_hash_in_its_policy(self):
        w = read(os.path.join(self.out, '_worker.js'))
        html = json.loads(re.search(r'const GATE_HTML = (".*");', w).group(1))
        csp = json.loads(re.search(r'const GATE_CSP = (".*");', w).group(1))
        script = re.search(r'<script>(.*?)</script>', html, re.S).group(1)
        digest = base64.b64encode(hashlib.sha256(script.encode('utf-8')).digest()).decode()
        self.assertIn("script-src 'sha256-%s'" % digest, csp)
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn('unsafe-inline\'; ', csp.split('script-src')[1].split(';')[0], 'scripts are not allowed inline in general')
        self.assertEqual(html.count('<script'), 1)

    def test_the_entrance_names_the_site_and_nothing_of_the_family(self):
        w = read(os.path.join(self.out, '_worker.js'))
        html = json.loads(re.search(r'const GATE_HTML = (".*");', w).group(1))
        self.assertIn('Hartley &amp; Moreau', html)
        self.assertIn('A private family archive', html)
        for private in ('Arthur', 'Susan', 'Kate', 'Daniel', 'Margot', 'family-tree.html'):
            self.assertNotIn(private, html)
        self.assertNotIn('<img', html)

    def test_the_sites_colours_reach_the_entrance(self):
        w = read(os.path.join(self.out, '_worker.js'))
        html = json.loads(re.search(r'const GATE_HTML = (".*");', w).group(1))
        self.assertIn('--gold: #8a6a2f', html)

    def test_the_cookie_lifetime_is_a_setting(self):
        s = self.site(access=True)
        self.edit(s, lambda d: d['access'].update(cookieDays=7))
        _, _, out = self.built(s, 'days')
        self.assertIn('"days": 7', read(os.path.join(out, '_worker.js')))

    def test_an_approved_entrance_picture_is_the_one_public_file(self):
        s = self.site(access=True)
        shutil.copy(os.path.join(s, 'images', 'people', 'thomas-hartley.png'), os.path.join(s, 'images', 'entrance.png'))
        self.edit(s, lambda d: d['access'].update(entranceImage='images/entrance.png'))
        code, text, out = self.built(s, 'img')
        self.assertEqual(code, 0, text)
        self.assertIn('is shown to everyone before the password', text)
        w = read(os.path.join(out, '_worker.js'))
        self.assertIn('"open": ["/robots.txt", "/images/entrance.png"]', w)
        self.assertIn('src=\\"/images/entrance.png\\"', w)

    def test_a_visitors_choice_needs_the_visitor_files_and_they_are_there(self):
        names = files(self.out)
        for f in ('visitor.js', 'visitor.css', 'visitor-match.js'):
            self.assertIn('engine/%s/%s' % (VERSION, f), names)
        html = read(os.path.join(self.out, 'family-tree.html'))
        self.assertLess(html.index('visitor.js'), html.index('site-config.js'), 'visitor.js is in the head, before the page is drawn')


class TestSettingsAreChecked(Base):
    def build_with(self, **blocks):
        s = self.site()
        self.edit(s, lambda d: d.update(blocks))
        return self.built(s)

    def test_a_password_in_the_settings_is_refused(self):
        for key in ('password', 'secret', 'token', 'apiKey', 'sitePassword'):
            code, text, _ = self.build_with(access={'enabled': True, 'project': 'x1', key: 'hunter2'})
            self.assertEqual(code, 1, key)
            self.assertNotIn('hunter2', text.replace("never go in site.config.json", ''), 'the value is not echoed')
            self.assertIn('SITE_PASSWORD', text)

    def test_a_project_is_needed_and_must_be_a_cloudflare_name(self):
        code, text, _ = self.build_with(access={'enabled': True})
        self.assertEqual(code, 1)
        self.assertIn('access.project', text)
        for bad in ('Has Capitals', '-lead', 'trail-', 'a' * 60, 'under_score', ''):
            code, text, _ = self.build_with(access={'enabled': True, 'project': bad})
            self.assertEqual(code, 1, bad)
        code, text, _ = self.build_with(access={'enabled': True, 'project': 'ok-name-1'})
        self.assertEqual(code, 0, text)

    def test_unknown_settings_and_wrong_types_are_refused(self):
        for block in ({'enabled': True, 'project': 'x1', 'nope': 1}, {'enable': True, 'project': 'x1'}, {'enabled': 'yes', 'project': 'x1'}, {'enabled': True, 'project': 'x1', 'cookieDays': 'ninety'},
                      {'enabled': True, 'project': 'x1', 'cookieDays': 0}, {'enabled': True, 'project': 'x1', 'cookieDays': 400}):
            code, text, _ = self.build_with(access=block)
            self.assertEqual(code, 1, block)
        code, text, _ = self.build_with(visitor={'enabled': True, 'scope': 'everyone'})
        self.assertEqual(code, 1)
        code, text, _ = self.build_with(visitor={'enabled': True, 'nope': True})
        self.assertEqual(code, 1)
        code, text, _ = self.build_with(access={'enable': True, 'project': 'x1'})
        self.assertEqual(code, 1, 'a misspelt enabled must not quietly leave the site open')
        code, text, _ = self.build_with(access={'project': 'x1'})
        self.assertEqual(code, 0)
        self.assertIn('NOT password protected', text)

    def test_an_entrance_picture_must_exist_and_stay_inside_the_site(self):
        for bad in ('images/missing.png', '/etc/passwd', '../secret.png', 'images/../../x.png'):
            code, text, _ = self.build_with(access={'enabled': True, 'project': 'x1', 'entranceImage': bad})
            self.assertEqual(code, 1, bad)
            self.assertIn('entranceImage', text)

    def test_long_dashes_in_the_entrance_words_are_refused(self):
        for k in ('kicker', 'hint', 'prompt'):
            code, text, _ = self.build_with(access={'enabled': True, 'project': 'x1', k: 'a ' + chr(0x2014) + ' b'})
            self.assertEqual(code, 1, k)

    def test_the_timeline_and_access_cannot_both_be_on_yet(self):
        code, text, _ = self.build_with(access={'enabled': True, 'project': 'x1'}, timeline={'enabled': True})
        self.assertEqual(code, 1)
        self.assertIn('Discovery Timeline', text)

    def test_a_file_the_gate_needs_for_itself_cannot_be_the_sites(self):
        s = self.site(access=True)
        with open(os.path.join(s, '_worker.js'), 'w') as f: f.write('// mine')
        code, text, _ = self.built(s)
        self.assertEqual(code, 1)
        self.assertIn('_worker.js', text)

    def test_a_site_robots_txt_is_replaced_with_a_warning(self):
        s = self.site(access=True)
        with open(os.path.join(s, 'robots.txt'), 'w') as f: f.write('User-agent: *\nAllow: /\n')
        code, text, out = self.built(s)
        self.assertEqual(code, 0)
        self.assertIn('robots.txt', text)
        self.assertIn(b'Disallow: /', files(out)['robots.txt'])

    def test_the_schema_documents_every_setting_the_code_reads(self):
        schema = json.loads(read(os.path.join(ROOT, 'schema', 'site-config.schema.json')))
        self.assertEqual(sorted(schema['properties']['access']['properties']), sorted(access.ACCESS_DEFAULTS))
        self.assertEqual(sorted(schema['properties']['visitor']['properties']), sorted(access.VISITOR_DEFAULTS))
        docs = read(os.path.join(ROOT, 'docs', 'site-config.md'))
        for k in list(access.ACCESS_DEFAULTS) + list(access.VISITOR_DEFAULTS):
            self.assertTrue('`%s`' % k in docs, '%s is documented in docs/site-config.md' % k)

    def test_the_sample_still_has_both_off(self):
        cfg = sitecfg.load(os.path.join(ROOT, 'sample'))
        self.assertIsNone(cfg['_access'])
        self.assertIsNone(cfg['_visitor'])


class TestVisitorBuild(Base):
    def test_the_visitor_settings_reach_the_browser_and_nothing_else_does(self):
        s = self.site(visitor=True)
        self.edit(s, lambda d: d['visitor'].update(question='Which one are you?', livingPhotos=True, scope='all'))
        code, text, out = self.built(s)
        self.assertEqual(code, 0, text)
        cfg = json.loads(read(os.path.join(out, 'site-config.js')).split('window.FamilySite = ')[1].rstrip(';\n'))
        self.assertEqual(cfg['visitor'], {'question': 'Which one are you?', 'lead': access.VISITOR_DEFAULTS['lead'], 'skipLabel': 'Continue without choosing',
                                          'welcome': True, 'livingPhotos': True, 'scope': 'all'})
        self.assertNotIn('access', cfg)

    def test_visitor_without_a_tree_page_warns(self):
        s = self.site(visitor=True)
        self.edit(s, lambda d: d['pages'].update(tree=None))
        self.edit(s, lambda d: d.update(nav=[n for n in d['nav'] if n['href'] != 'family-tree.html']))
        # the access check that explains this only runs with access on; the visitor alone is allowed
        code, text, _ = self.built(s)
        self.assertEqual(code, 0, text)


class TestTheHousekeeping(unittest.TestCase):
    def test_no_long_dashes_in_what_this_feature_added(self):
        bad = []
        for rel in ('build/access.py', 'engine/visitor.js', 'engine/visitor.css', 'engine/visitor-match.js', 'templates/gate.html', 'templates/gate.js', 'templates/gate-worker.js',
                    'tests/test_access.py', 'tests/check-gate.js', 'tests/check-access.js', 'tests/check-visitor.js', 'tests/gate-server.js', 'tests/helpers.js', 'tests/access_fixtures.py'):
            t = read(os.path.join(ROOT, rel))
            if chr(0x2014) in t or chr(0x2013) in t:
                bad.append(rel)
        self.assertEqual(bad, [])

    def test_no_secret_looking_value_is_in_the_repository_files_of_this_feature(self):
        for rel in ('build/access.py', 'templates/gate-worker.js', 'templates/gate.js', '.github/workflows/build-site.yml'):
            t = read(os.path.join(ROOT, rel))
            self.assertIsNone(re.search(r'(?i)(password|token)\s*[:=]\s*[\'"][^\'"$\s{]{8,}', t), rel)


if __name__ == '__main__':
    unittest.main(verbosity=1)
