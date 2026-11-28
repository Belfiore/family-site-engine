#!/usr/bin/env python3
"""Checks for the basic family password (basicAccess) in the build: what is made, what is refused, that the password is
never kept, and that a site which has not turned it on is built exactly as before.

    python3 tests/test_basic_access.py          (needs only Python 3.9 or later)

The browser side is in check-basic-access.js.
"""
import base64, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'build'))
import basic_access  # noqa: E402

spec = importlib.util.spec_from_file_location('basic_password', os.path.join(ROOT, 'tools', 'basic-password.py'))
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

PASSWORD = 'plum lantern harbour quiet 47'


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


def run(*args):
    p = subprocess.run([sys.executable] + list(args), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def site(self, block=None, name='site', edit=None):
        dest = os.path.join(self.tmp, name)
        shutil.copytree(os.path.join(ROOT, 'sample'), dest)
        p = os.path.join(dest, 'site.config.json')
        cfg = json.loads(read(p))
        if block is not None: cfg['basicAccess'] = block
        if edit: edit(cfg)
        with open(p, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        return dest

    def good(self, **kw):
        return dict({'enabled': True, 'scope': 'home', 'days': 30}, **tool.make(PASSWORD), **kw)

    def build(self, site, name='out'):
        out = os.path.join(self.tmp, name)
        code, text = run(os.path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', out)
        return code, text, out

    def validate(self, site):
        return run(os.path.join(ROOT, 'build', 'validate.py'), '--site', site)


def comparable(root):
    out = files(root)
    if 'engine-build.json' in out:
        d = json.loads(out['engine-build.json']); d.pop('built', None)
        out['engine-build.json'] = json.dumps(d, sort_keys=True).encode()
    return out


class TestTool(unittest.TestCase):
    def test_the_hash_is_pbkdf2_sha256_and_matches_a_known_vector(self):
        # RFC 7914 section 11 gives PBKDF2-HMAC-SHA256 for "passwd" with salt "salt", 1 iteration
        got = tool.make('passwd', 1, b'salt')
        self.assertEqual(base64.b64decode(got['hash']).hex()[:64], hashlib.pbkdf2_hmac('sha256', b'passwd', b'salt', 1, 32).hex())
        self.assertEqual(base64.b64decode(got['salt']), b'salt')
        self.assertEqual(len(base64.b64decode(tool.make('x')['hash'])), 32)

    def test_a_new_salt_each_time(self):
        a, b = tool.make('same'), tool.make('same')
        self.assertNotEqual(a['salt'], b['salt'])
        self.assertNotEqual(a['hash'], b['hash'])

    def test_accents_are_normalised_the_same_way_everywhere(self):
        composed, decomposed = 'café', 'café'
        self.assertEqual(tool.make(composed, 1000, b'0123456789abcdef')['hash'], tool.make(decomposed, 1000, b'0123456789abcdef')['hash'])


class TestOffMeansUnchanged(Base):
    def test_a_site_without_the_setting_builds_as_before(self):
        a = self.build(self.site(name='a-src'), 'a')[2]
        for i, block in enumerate(({'enabled': False}, {'enabled': False, 'scope': 'all'})):
            code, text, b = self.build(self.site(block, name='s%d-src' % i), 'b%d' % i)
            self.assertEqual(code, 0, text)
            fa, fb = comparable(a), comparable(b)
            self.assertEqual(sorted(set(fa) ^ set(fb)), [], block)
            self.assertEqual([k for k in fa if fa[k] != fb[k]], [], block)

    def test_nothing_of_it_is_in_a_site_that_has_it_off(self):
        _, _, out = self.build(self.site())
        for name, body in files(out).items():
            self.assertNotIn(b'basic-gate', body, name)
            self.assertNotIn(b'basicAccess', body, name)
            self.assertNotIn(b'fse-basic-access', body, name)

    def test_a_block_that_is_not_enabled_warns_that_the_site_is_open(self):
        code, text = self.validate(self.site({'enabled': False}))
        self.assertEqual(code, 0, text)
        self.assertIn('NOT password protected', text)


class TestOn(Base):
    def test_the_home_page_gets_the_script_and_the_other_pages_do_not(self):
        code, text, out = self.build(self.site(self.good()))
        self.assertEqual(code, 0, text)
        self.assertIn('basic-gate.js', read(os.path.join(out, 'index.html')))
        for page in ('family-tree.html', 'map.html', 'ask.html'):
            self.assertNotIn('basic-gate', read(os.path.join(out, page)), page)
        self.assertTrue(os.path.isfile(os.path.join(out, 'engine', read(os.path.join(ROOT, 'VERSION')).strip(), 'basic-gate.js')))

    def test_scope_all_covers_every_page(self):
        code, text, out = self.build(self.site(self.good(scope='all')))
        self.assertEqual(code, 0, text)
        for page in ('index.html', 'family-tree.html', 'map.html', 'ask.html'):
            self.assertIn('basic-gate.js', read(os.path.join(out, page)), page)

    def test_the_tag_carries_the_salt_and_hash_and_no_password(self):
        block = self.good()
        _, _, out = self.build(self.site(block))
        page = read(os.path.join(out, 'index.html'))
        tag = re.search(r'<script src="[^"]*basic-gate\.js"[^>]*>', page).group(0)
        for want in ('data-salt="%s"' % block['salt'], 'data-hash="%s"' % block['hash'], 'data-iter="210000"', 'data-days="30"'):
            self.assertIn(want, tag.replace('&#x27;', "'"))
        for name, body in files(out).items():
            self.assertNotIn(PASSWORD.encode(), body, name)

    def test_the_site_name_is_escaped_in_the_tag(self):
        site = self.site(self.good(), edit=lambda c: c['site'].update(name='A "quoted" <name> & more'))
        _, _, out = self.build(site)
        tag = re.search(r'<script src="[^"]*basic-gate\.js"[^>]*>', read(os.path.join(out, 'index.html'))).group(0)
        self.assertNotIn('<name>', tag)
        self.assertIn('&quot;quoted&quot;', tag)

    def test_the_build_info_says_so_without_the_hash(self):
        _, _, out = self.build(self.site(self.good()))
        info = json.loads(read(os.path.join(out, 'engine-build.json')))
        self.assertEqual(info['basicAccess'], {'scope': 'home'})

    def test_the_warning_says_it_is_not_protection(self):
        code, text = self.validate(self.site(self.good()))
        self.assertEqual(code, 0, text)
        self.assertIn('nothing else', text)
        self.assertIn('still public', text)


class TestRefusals(Base):
    def refused(self, block, *words, **kw):
        site = self.site(block, **kw)
        code, text = self.validate(site)
        self.assertNotEqual(code, 0, text)
        for w in words: self.assertIn(w, text)
        code, text, _ = self.build(site)
        self.assertNotEqual(code, 0, 'the build stops too')

    def test_a_password_in_the_settings(self):
        for key in ('password', 'passphrase', 'secret', 'token', 'apiKey'):
            self.refused(dict(self.good(), **{key: PASSWORD}), 'never goes in site.config.json', name='k' + key)

    def test_a_misspelt_setting(self):
        self.refused(dict(self.good(), scpoe='all'), 'not a setting')

    def test_enabled_without_a_hash_would_leave_the_page_open(self):
        self.refused({'enabled': True, 'scope': 'home'}, 'tools/basic-password.py')
        self.refused({'enabled': True, 'salt': 'AAAAAAAAAAAAAAAAAAAAAA==', 'hash': 'not base64!'}, 'basicAccess.hash', name='b')
        self.refused(dict(self.good(), salt='AAAA'), 'basicAccess.salt', name='c')

    def test_bad_scope_iterations_and_days(self):
        self.refused(dict(self.good(), scope='some'), 'scope', name='a')
        self.refused(dict(self.good(), iterations=10), 'iterations', name='b')
        self.refused(dict(self.good(), days=0), 'days', name='c')

    def test_it_cannot_sit_on_top_of_the_real_password(self):
        site = self.site(self.good(), edit=lambda c: c.update(access={'enabled': True, 'project': 'a-project'}))
        code, text = self.validate(site)
        self.assertNotEqual(code, 0, text)
        self.assertIn('use one or the other', text)

    def test_it_works_with_the_timeline_and_the_visitor_question(self):
        site = self.site(self.good(), edit=lambda c: c.update(visitor={'enabled': True}))
        code, text, _ = self.build(site)
        self.assertEqual(code, 0, text)


class TestModule(unittest.TestCase):
    def test_settings(self):
        self.assertIsNone(basic_access.settings({}))
        self.assertIsNone(basic_access.settings({'basicAccess': {'enabled': False}}))
        s = basic_access.settings({'basicAccess': {'enabled': True, 'salt': 's', 'hash': 'h'}})
        self.assertEqual((s['scope'], s['iterations'], s['days']), ('home', 210000, 30))

    def test_no_head_without_settings(self):
        self.assertEqual(basic_access.head({'_basic': None}, {'base': 'engine/1/'}, 'index.html'), [])


if __name__ == '__main__':
    unittest.main(verbosity=1)
