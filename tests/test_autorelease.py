#!/usr/bin/env python3
"""The automatic release (tools/autorelease.py and .github/workflows/auto-release.yml), without GitHub.

Run:  python3 tests/test_autorelease.py
"""
import contextlib, datetime, io, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import autorelease as A  # noqa: E402

UTC = datetime.timezone.utc
CHANNELS_TEXT = '{\n "$comment": "x",\n "channels": {\n  "canary": "1.2.0",\n  "beta": "1.1.0",\n  "stable": "1.0.1"\n }\n}\n'


def pr(number, title, labels=(), user='someone', merged=True):
    return {'number': number, 'title': title, 'labels': [{'name': l} for l in labels], 'user': {'login': user},
            'merged_at': '2026-11-26T10:00:00Z' if merged else None}


class FakeApi:
    """Answers the GitHub calls the release makes, from a table of (method, url prefix) -> (status, body)."""
    def __init__(self, routes=None):
        self.routes, self.calls = routes or {}, []

    def request(self, method, url, body=None):
        self.calls.append((method, url, body))
        for (m, prefix), answer in self.routes.items():
            if m == method and url.startswith(prefix):
                a = answer(url, body) if callable(answer) else answer
                return a
        return 404, None

    def get(self, url):
        return self.request('GET', url)

    def post(self, url, body):
        return self.request('POST', url, body)


class TestDecisions(unittest.TestCase):
    def test_bump(self):
        self.assertEqual(A.bump('1.2.0', 'patch'), '1.2.1')
        self.assertEqual(A.bump('1.2.9', 'minor'), '1.3.0')
        self.assertEqual(A.bump('1.2.9', 'major'), '2.0.0')
        self.assertEqual(A.bump('v0.9.10', 'patch'), '0.9.11')
        with self.assertRaises(ValueError): A.bump('1.2', 'patch')
        with self.assertRaises(ValueError): A.bump('1.2.0', 'huge')

    def test_the_label_decides_the_size_and_the_biggest_wins(self):
        self.assertEqual(A.level_from_labels([pr(1, 'a')]), 'patch')
        self.assertEqual(A.level_from_labels([]), 'patch')
        self.assertEqual(A.level_from_labels([pr(1, 'a'), pr(2, 'b', ['minor'])]), 'minor')
        self.assertEqual(A.level_from_labels([pr(1, 'a', ['Minor']), pr(2, 'b', ['major']), pr(3, 'c', ['minor'])]), 'major')
        self.assertEqual(A.level_from_labels([pr(1, 'a', ['bug', 'docs'])]), 'patch')

    def test_no_release_label(self):
        self.assertTrue(A.release_is_skipped([pr(1, 'a', ['no-release'])]))
        self.assertFalse(A.release_is_skipped([pr(1, 'a', ['no-release']), pr(2, 'b')]))
        self.assertFalse(A.release_is_skipped([]), 'a push with no pull request is still released')

    def test_the_workflows_own_pushes_never_start_a_release(self):
        self.assertTrue(A.is_own_commit('[auto-release] Release v1.2.1 [skip ci]'))
        self.assertTrue(A.is_own_commit('anything', actor='github-actions[bot]'))
        quoted = 'Add the release workflow\n\nIts own commits start with [auto-release] and end with [skip ci].'
        self.assertFalse(A.is_own_commit(quoted), 'a merge that only mentions the marker is still released')
        self.assertTrue(A.is_own_commit('Move the canary by hand', files=['channels.json']))
        self.assertTrue(A.is_own_commit('x', files=['VERSION', 'CHANGELOG.md', 'channels.json']))
        self.assertFalse(A.is_own_commit('Add a thing', files=['VERSION', 'build/build_site.py']))
        self.assertFalse(A.is_own_commit('Add a thing', actor='someone', files=['docs/x.md']))
        self.assertFalse(A.is_own_commit('Add a thing', files=[]))

    def test_changelog_entry_and_notes(self):
        entry = A.changelog_entry('1.2.1', [pr(7, 'Fix the map', user='sam'), pr(9, 'Add  a page')])
        self.assertEqual(entry, '## 1.2.1\n\n- Fix the map (#7) by @sam\n- Add a page (#9) by @someone\n')
        self.assertEqual(A.release_notes('1.2.1', [pr(7, 'Fix the map', user='sam')]), '- Fix the map (#7) by @sam\n')
        self.assertIn('directly to main', A.changelog_entry('1.2.1', []))

    def test_the_entry_goes_above_the_newest_release(self):
        text = '# Changes\n\nIntro line.\n\n## 1.2.0\n\n- old\n\n## 1.1.0\n\n- older\n'
        out = A.insert_changelog(text, A.changelog_entry('1.2.1', [pr(1, 'x')]))
        self.assertEqual(out.index('## 1.2.1') < out.index('## 1.2.0') < out.index('## 1.1.0'), True)
        self.assertTrue(out.startswith('# Changes\n\nIntro line.\n\n## 1.2.1'))
        self.assertIn('- old', out)
        self.assertEqual(A.insert_changelog('# Changes\n', '## 1.0.0\n\n- x\n').count('## 1.0.0'), 1)

    def test_channels_move_without_changing_anything_else(self):
        new, before, moved = A.move_channels(CHANNELS_TEXT, '1.2.1', 'patch')
        self.assertTrue(moved)
        self.assertEqual(before, {'canary': '1.2.0', 'beta': '1.1.0', 'stable': '1.0.1'})
        self.assertEqual(json.loads(new)['channels'], {'canary': '1.2.1', 'beta': '1.2.1', 'stable': '1.2.1'})
        self.assertEqual(new, CHANNELS_TEXT.replace('1.2.0', '1.2.1').replace('1.1.0', '1.2.1').replace('1.0.1', '1.2.1'))

    def test_a_major_release_is_published_but_no_channel_moves(self):
        new, before, moved = A.move_channels(CHANNELS_TEXT, '2.0.0', 'major')
        self.assertFalse(moved)
        self.assertEqual(new, CHANNELS_TEXT)

    def test_rollback_restores_the_file_exactly(self):
        moved, before, _ = A.move_channels(CHANNELS_TEXT, '1.2.1', 'minor')
        self.assertEqual(A.set_channels(moved, before), CHANNELS_TEXT)

    def test_a_missing_channel_is_an_error_not_a_silent_skip(self):
        with self.assertRaises(ValueError): A.set_channels('{"channels": {"canary": "1.0.0"}}', {'beta': '1.0.0'})

    def test_the_real_files_are_readable(self):
        with open(os.path.join(ROOT, 'channels.json'), encoding='utf-8') as f: text = f.read()
        before = A.read_channels(text)
        self.assertEqual(set(before), set(A.CHANNELS))
        self.assertEqual(A.set_channels(A.set_channels(text, {c: '9.9.9' for c in A.CHANNELS}), before), text)
        with open(os.path.join(ROOT, 'sites.json'), encoding='utf-8') as f: sites = A.sites_from(json.load(f))
        self.assertGreaterEqual(len(sites), 4)
        self.assertTrue(all('/' in s['repo'] for s in sites))
        with open(os.path.join(ROOT, 'CHANGELOG.md'), encoding='utf-8') as f: log = f.read()
        out = A.insert_changelog(log, A.changelog_entry('99.0.0', [pr(1, 'x')]))
        self.assertLess(out.index('## 99.0.0'), out.index('## 1.2.0'))


class TestJudgingTheSites(unittest.TestCase):
    SINCE = datetime.datetime(2026, 11, 26, 12, 0, 0, tzinfo=UTC)

    def run_(self, at, status='completed', conclusion='success', url='https://x/run/1'):
        return {'created_at': at, 'status': status, 'conclusion': conclusion, 'html_url': url, 'name': 'Build and publish the site'}

    def test_judge(self):
        j = lambda runs: A.judge_runs(runs, self.SINCE)[0]
        self.assertEqual(j([]), 'none')
        self.assertEqual(j([self.run_('2026-11-26T11:00:00Z')]), 'none', 'an older run is not this release')
        self.assertEqual(j([self.run_('2026-11-26T12:00:03Z')]), 'ok')
        self.assertEqual(j([self.run_('2026-11-26T12:01:00Z', 'in_progress', None)]), 'waiting')
        self.assertEqual(j([self.run_('2026-11-26T12:01:00Z', conclusion='failure')]), 'failed')
        self.assertEqual(j([self.run_('2026-11-26T12:01:00Z'), self.run_('2026-11-26T12:02:00Z', conclusion='cancelled')]), 'failed')
        self.assertIn('https://x/run/1', A.judge_runs([self.run_('2026-11-26T12:01:00Z', conclusion='failure')], self.SINCE)[1])

    def clock(self):
        t = [0.0]
        return (lambda s: t.__setitem__(0, t[0] + s)), (lambda: t[0])

    def api(self, builds):
        """builds: repo -> list of run dicts (or an int status for the call itself)."""
        def runs(url, body):
            repo = re.search(r'/repos/([^/]+/[^/]+)/actions', url).group(1)
            v = builds[repo]
            return (v, None) if isinstance(v, int) else (200, {'workflow_runs': v})
        return FakeApi({('GET', '/repos/'): lambda url, body: runs(url, body) if '/actions/runs' in url else (200, {'html_url': 'https://live/' + url.split('/')[3]})})

    SITES = [{'repo': 'o/a', 'name': 'A', 'channel': 'stable'}, {'repo': 'o/b', 'name': 'B', 'channel': 'canary'}]

    def verify(self, builds, fetch=lambda url: 200, **kw):
        sleep, now = self.clock()
        return A.verify_sites(self.api(builds), self.SITES, self.SINCE, fetch=fetch, sleep=sleep, now=now, **kw)

    def good(self): return [self.run_('2026-11-26T12:01:00Z')]

    def test_every_site_ok(self):
        res = self.verify({'o/a': self.good(), 'o/b': self.good()})
        self.assertEqual([r['ok'] for r in res], [True, True])

    def test_a_failed_build_is_reported_with_its_run(self):
        res = self.verify({'o/a': self.good(), 'o/b': [self.run_('2026-11-26T12:01:00Z', conclusion='failure', url='https://x/run/9')]})
        self.assertEqual([r['ok'] for r in res], [True, False])
        self.assertIn('https://x/run/9', res[1]['why'])

    def test_a_site_that_built_but_does_not_answer_200_fails(self):
        res = self.verify({'o/a': self.good(), 'o/b': self.good()}, fetch=lambda url: 404 if url.endswith('/b') else 200)
        self.assertEqual([r['ok'] for r in res], [True, False])
        self.assertIn('answered 404', res[1]['why'])

    def test_a_site_that_never_started_a_build_fails_after_the_wait(self):
        res = self.verify({'o/a': self.good(), 'o/b': []}, appear=120, poll=30)
        self.assertFalse(res[1]['ok'])
        self.assertIn('no build was started', res[1]['why'])

    def test_a_build_that_never_finishes_times_out(self):
        res = self.verify({'o/a': self.good(), 'o/b': [self.run_('2026-11-26T12:01:00Z', 'in_progress', None)]}, timeout=300, poll=60)
        self.assertFalse(res[1]['ok'])
        self.assertIn('did not finish', res[1]['why'])

    def test_a_site_that_cannot_be_read_fails(self):
        res = self.verify({'o/a': 403, 'o/b': self.good()})
        self.assertFalse(res[0]['ok'])
        self.assertIn('403', res[0]['why'])

    PROTECTED = [{'repo': 'o/a', 'name': 'A', 'channel': 'stable'},
                 {'repo': 'o/p', 'name': 'P', 'channel': 'stable', 'protected': True, 'url': 'https://p.pages.dev'}]

    def verify_protected(self, fetch):
        sleep, now = self.clock()
        return A.verify_sites(self.api({'o/a': self.good(), 'o/p': self.good()}), self.PROTECTED, self.SINCE, fetch=fetch, sleep=sleep, now=now)

    def test_a_protected_site_passes_when_the_gate_answers_401(self):
        seen = []
        def fetch(url):
            seen.append(url)
            return (401, True) if url.startswith('https://p.pages.dev') else 200
        res = self.verify_protected(fetch)
        self.assertEqual([r['ok'] for r in res], [True, True])
        self.assertIn('asks for the password', res[1]['why'])
        self.assertIn('https://p.pages.dev/data/people.json', seen, 'its data is looked at too')
        self.assertNotIn('github.io', ' '.join(seen), 'a protected site is not looked for on GitHub Pages')

    def test_a_protected_site_that_answers_200_is_open_and_fails(self):
        res = self.verify_protected(lambda url: 200)
        self.assertFalse(res[1]['ok'])
        self.assertIn('the site is open', res[1]['why'])

    def test_a_protected_site_with_open_data_fails_even_if_the_front_page_is_closed(self):
        res = self.verify_protected(lambda url: 200 if url.endswith('people.json') else (401, True))
        self.assertFalse(res[1]['ok'])
        self.assertIn('data/people.json', res[1]['why'])

    def test_a_401_that_is_not_the_gates_fails(self):
        res = self.verify_protected(lambda url: 401 if 'pages.dev' in url else 200)
        self.assertFalse(res[1]['ok'])
        self.assertIn('no gate header', res[1]['why'])

    def test_a_protected_site_with_no_address_fails_and_says_why(self):
        ok, why = A.check_protected({'repo': 'o/p', 'protected': True})
        self.assertFalse(ok)
        self.assertIn('no url', why)

    def test_protected_and_url_reach_the_matrix_and_are_otherwise_left_out(self):
        m = A.sites_from({'sites': [{'repo': 'o/a'}, {'repo': 'o/p', 'protected': True, 'url': 'https://p.pages.dev/'}]})
        self.assertNotIn('protected', m[0])
        self.assertNotIn('url', m[0])
        self.assertEqual((m[1]['protected'], m[1]['url']), (True, 'https://p.pages.dev/'))

    def test_dispatch_sends_the_channels_to_every_site(self):
        api = FakeApi({('POST', '/repos/'): (204, None)})
        out = A.dispatch(api, self.SITES, {'canary': '1.2.1', 'beta': '1.2.1', 'stable': '1.2.1'})
        self.assertEqual(out, [('o/a', 204), ('o/b', 204)])
        self.assertEqual(api.calls[0][1], '/repos/o/a/dispatches')
        self.assertEqual(api.calls[0][2]['event_type'], 'engine-release')
        self.assertEqual(api.calls[0][2]['client_payload']['channels']['stable'], '1.2.1')

    def test_live_url_comes_from_pages_with_a_fallback(self):
        self.assertEqual(A.live_url(FakeApi({('GET', '/repos/o/a/pages'): (200, {'html_url': 'https://custom.example/'})}), 'o/a'), 'https://custom.example/')
        self.assertEqual(A.live_url(FakeApi(), 'Belfiore/Site-X'), 'https://belfiore.github.io/Site-X/')

    def test_issue_text(self):
        text = A.issue_text('1.2.1', [{'repo': 'o/b', 'why': 'build failure | see\nrun'}], True, {'canary': '1.2.0', 'beta': '1.2.0', 'stable': '1.2.0'})
        self.assertIn('| o/b | build failure / see run |', text)
        self.assertIn('stable 1.2.0', text)
        self.assertIn('not deleted or re-tagged', text)
        self.assertIn('could not be put back', A.issue_text('1.2.1', [{'repo': 'o/b', 'why': 'x'}], False, {}))


class TestTheSteps(unittest.TestCase):
    """The workflow's steps, run in a throwaway git repository with a fake GitHub."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='autorelease-')
        self.old = os.getcwd()
        os.chdir(self.tmp)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 't@example.org'); self.git('config', 'user.name', 'T')
        self.write('VERSION', '1.2.0\n')
        self.write('channels.json', CHANNELS_TEXT)
        self.write('CHANGELOG.md', '# Changes\n\nIntro.\n\n## 1.2.0\n\n- old\n')
        self.write('sites.json', json.dumps({'sites': [{'repo': 'o/a', 'name': 'A', 'channel': 'stable'}, {'repo': 'o/b'}]}))
        self.write('code.py', 'x = 1\n')
        self.commit('Start')
        self.git('tag', 'v1.2.0')
        self.out = os.path.join(self.tmp, 'gh-output')
        self.env['GITHUB_OUTPUT'] = self.out
        os.environ['GITHUB_OUTPUT'] = self.out

    def tearDown(self):
        os.chdir(self.old)
        os.environ.pop('GITHUB_OUTPUT', None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *a):
        return subprocess.run(['git', *a], cwd=self.tmp, env=self.env, capture_output=True, text=True, check=True).stdout.strip()

    def write(self, name, text):
        with open(os.path.join(self.tmp, name), 'w', encoding='utf-8') as f: f.write(text)

    def commit(self, msg):
        self.git('add', '-A'); self.git('commit', '-q', '-m', msg)
        return self.git('rev-parse', 'HEAD')

    def outputs(self):
        out = {}
        if os.path.exists(self.out):
            with open(self.out, encoding='utf-8') as fh: lines = fh.read().splitlines()
            for line in lines:
                k, _, v = line.partition('=')
                out[k] = v
        return out

    def plan(self, before, sha, message, prs, actor='sam'):
        routes = {('GET', '/repos/o/e/commits/'): (200, prs)}
        env = {'REPO': 'o/e', 'SHA': sha, 'BEFORE': before, 'ACTOR': actor, 'HEAD_MESSAGE': message}
        with contextlib.redirect_stdout(io.StringIO()):
            return A.main(['plan'], env, FakeApi(routes))

    def test_a_merged_pull_request_makes_a_patch_release(self):
        before = self.git('rev-parse', 'HEAD')
        self.write('code.py', 'x = 2\n')
        sha = self.commit('Merge pull request #5 from x/y')
        self.assertEqual(self.plan(before, sha, 'Merge pull request #5', [pr(5, 'Fix it')]), 0)
        o = self.outputs()
        self.assertEqual((o['release'], o['level']), ('true', 'patch'))
        self.assertEqual(json.load(open('release-prs.json'))[0]['number'], 5)

    def test_a_minor_label_makes_a_minor_release(self):
        before = self.git('rev-parse', 'HEAD')
        self.write('code.py', 'x = 2\n')
        sha = self.commit('m')
        self.plan(before, sha, 'm', [pr(5, 'New page', ['minor'])])
        self.assertEqual(self.outputs()['level'], 'minor')

    def test_two_pull_requests_since_the_last_tag_are_both_in_the_release(self):
        self.write('code.py', 'x = 2\n'); self.commit('one')
        before = self.git('rev-parse', 'HEAD')
        self.write('code.py', 'x = 3\n'); sha = self.commit('two')
        numbers = iter([[pr(5, 'a')], [pr(6, 'b', ['major'])]])
        routes = {('GET', '/repos/o/e/commits/'): lambda url, body: (200, next(numbers))}
        with contextlib.redirect_stdout(io.StringIO()):
            A.main(['plan'], {'REPO': 'o/e', 'SHA': sha, 'BEFORE': before, 'ACTOR': 'sam', 'HEAD_MESSAGE': 'two'}, FakeApi(routes))
        self.assertEqual(self.outputs()['level'], 'major')
        self.assertEqual([p['number'] for p in json.load(open('release-prs.json'))], [5, 6])

    def test_the_release_commit_does_not_start_another_release(self):
        before = self.git('rev-parse', 'HEAD')
        self.write('VERSION', '1.2.1\n')
        sha = self.commit('[auto-release] Release v1.2.1 [skip ci]')
        self.plan(before, sha, '[auto-release] Release v1.2.1 [skip ci]', [])
        self.assertEqual(self.outputs()['release'], 'false')

    def test_a_push_that_only_moves_a_channel_is_not_a_release(self):
        before = self.git('rev-parse', 'HEAD')
        self.write('channels.json', CHANNELS_TEXT.replace('1.0.1', '1.1.0'))
        sha = self.commit('Move stable')
        self.plan(before, sha, 'Move stable', [])
        self.assertEqual(self.outputs()['release'], 'false')

    def test_a_pull_request_labelled_no_release_is_skipped(self):
        before = self.git('rev-parse', 'HEAD')
        self.write('code.py', 'x = 2\n'); sha = self.commit('docs')
        self.plan(before, sha, 'docs', [pr(5, 'Typo', ['no-release'])])
        self.assertEqual(self.outputs()['release'], 'false')

    def test_a_push_without_a_pull_request_is_a_patch(self):
        before = self.git('rev-parse', 'HEAD')
        self.write('code.py', 'x = 2\n'); sha = self.commit('direct')
        self.plan(before, sha, 'direct', [])
        o = self.outputs()
        self.assertEqual((o['release'], o['level']), ('true', 'patch'))

    def test_prepare_channels_and_rollback_end_to_end(self):
        self.write('release-prs.json', json.dumps([pr(5, 'Fix it', user='sam'), pr(6, 'Add a page', ['minor'])]))
        with contextlib.redirect_stdout(io.StringIO()):
            A.main(['prepare'], {'LEVEL': 'minor'}, FakeApi())
        self.assertEqual(open('VERSION').read(), '1.3.0\n')
        log = open('CHANGELOG.md').read()
        self.assertTrue(log.index('## 1.3.0') < log.index('## 1.2.0'))
        self.assertIn('- Fix it (#5) by @sam', log)
        self.assertEqual(open('release-notes.md').read(), '- Fix it (#5) by @sam\n- Add a page (#6) by @someone\n')
        o = self.outputs()
        self.assertEqual((o['version'], o['previous'], o['tag']), ('1.3.0', '1.2.0', 'v1.3.0'))
        os.remove(self.out)
        with contextlib.redirect_stdout(io.StringIO()):
            A.main(['channels'], {'VERSION': '1.3.0', 'LEVEL': 'minor'}, FakeApi())
        self.assertEqual(A.read_channels(open('channels.json').read()), {'canary': '1.3.0', 'beta': '1.3.0', 'stable': '1.3.0'})
        previous = self.outputs()['previous']
        with contextlib.redirect_stdout(io.StringIO()):
            A.main(['rollback'], {'PREVIOUS': previous}, FakeApi())
        self.assertEqual(open('channels.json').read(), CHANNELS_TEXT)

    def test_a_major_release_bumps_the_version_and_holds_the_channels(self):
        with contextlib.redirect_stdout(io.StringIO()):
            A.main(['prepare'], {'LEVEL': 'major'}, FakeApi())
            A.main(['channels'], {'VERSION': '2.0.0', 'LEVEL': 'major'}, FakeApi())
        self.assertEqual(open('VERSION').read(), '2.0.0\n')
        self.assertEqual(open('channels.json').read(), CHANNELS_TEXT)
        self.assertEqual(self.outputs()['moved'], 'false')

    def test_dispatch_step_reports_sites_it_could_not_reach(self):
        api = FakeApi({('POST', '/repos/o/a'): (204, None), ('POST', '/repos/o/b'): (404, None)})
        with contextlib.redirect_stdout(io.StringIO()):
            code = A.main(['dispatch'], {}, api)
        self.assertEqual(code, 1)
        self.assertEqual(self.outputs()['sent'], '1')
        self.assertTrue(self.outputs()['at'].endswith('Z'))

    def test_matrix_lists_every_site(self):
        with contextlib.redirect_stdout(io.StringIO()):
            A.main(['matrix'], {}, FakeApi())
        m = json.loads(self.outputs()['matrix'])
        self.assertEqual([s['repo'] for s in m['include']], ['o/a', 'o/b'])

    def test_a_dir_in_sites_json_reaches_the_matrix_and_is_otherwise_left_out(self):
        doc = {'sites': [{'repo': 'o/a', 'name': 'A'}, {'repo': 'o/b', 'name': 'B', 'dir': 'Folder'}]}
        m = A.sites_from(doc)
        self.assertNotIn('dir', m[0])
        self.assertEqual(m[1]['dir'], 'Folder')

    def test_the_sites_folder_is_found(self):
        import tempfile
        def site(*parts):
            d = tempfile.mkdtemp()
            for p in parts:
                path = os.path.join(d, p)
                os.makedirs(os.path.dirname(path) or d, exist_ok=True)
                open(path, 'w').write('{}')
            return d
        self.assertEqual(A.find_site_dir(site('site.config.json')), '')
        self.assertEqual(A.find_site_dir(site('Italian-Family-History/site.config.json', 'README.md')), 'Italian-Family-History')
        self.assertEqual(A.find_site_dir(site('a/b/site.config.json')), 'a/b')
        self.assertEqual(A.find_site_dir(site('site.config.json', 'sub/site.config.json')), '', 'the top wins')
        two = site('x/site.config.json', 'y/site.config.json')
        self.assertEqual(A.find_site_dir(two, 'y'), 'y', 'dir from sites.json wins')
        with self.assertRaises(ValueError):
            A.find_site_dir(two)
        with self.assertRaises(ValueError):
            A.find_site_dir(site('README.md'))
        with self.assertRaises(ValueError):
            A.find_site_dir(two, '../x')
        with self.assertRaises(ValueError):
            A.find_site_dir(two, 'nope')
        self.assertEqual(A.find_site_dir(site('node_modules/p/site.config.json', 'real/site.config.json')), 'real')

    def test_sitedir_step_writes_the_folder_and_fails_with_a_message(self):
        import tempfile
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, 'F'))
        open(os.path.join(d, 'F', 'site.config.json'), 'w').write('{}')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(A.main(['sitedir'], {'SITE_ROOT': d}, FakeApi()), 0)
        self.assertEqual(self.outputs()['dir'], 'F')
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(A.main(['sitedir'], {'SITE_ROOT': tempfile.mkdtemp()}, FakeApi()), 1)
        self.assertIn('no site.config.json', out.getvalue())

    def test_verify_step_writes_the_failures_and_the_issue(self):
        calls = {'n': 0}
        def runs(url, body):
            return 200, {'workflow_runs': [{'created_at': '2026-11-26T12:01:00Z', 'status': 'completed',
                                            'conclusion': 'failure' if '/o/b/' in url else 'success', 'html_url': 'https://x/run', 'name': 'Build'}]}
        api = FakeApi({('GET', '/repos/o/a/actions'): runs, ('GET', '/repos/o/b/actions'): runs,
                       ('GET', '/repos/o/a/pages'): (200, {'html_url': 'https://live/a'})})
        real = A.answers_200
        A.answers_200 = lambda url, fetch=None: 200
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                A.main(['verify'], {'SINCE': '2026-11-26T12:00:00Z', 'POLL': '1', 'APPEAR': '0', 'TIMEOUT': '5'}, api)
        finally:
            A.answers_200 = real
        self.assertEqual(self.outputs()['ok'], 'false')
        self.assertEqual([f['repo'] for f in json.load(open('failures.json'))], ['o/b'])
        with contextlib.redirect_stdout(io.StringIO()):
            A.main(['issue'], {'VERSION': '1.3.0', 'ROLLED_BACK': 'true', 'PREVIOUS': json.dumps({'stable': '1.2.0'})}, FakeApi())
        self.assertIn('o/b', open('issue.md').read())


class TestTheWorkflowFile(unittest.TestCase):
    """The pieces of auto-release.yml that keep it safe. A YAML parser is not in the standard library, so these read the text."""
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, '.github', 'workflows', 'auto-release.yml'), encoding='utf-8') as f: cls.text = f.read()
        cls.release = cls.text[cls.text.index('\n  release:'):]

    def test_it_runs_on_pushes_to_main_only(self):
        self.assertRegex(self.text, r'on:\n  push:\n    branches: \[main\]')
        self.assertNotIn('pull_request', self.text)

    def test_the_site_test_build_uses_the_sites_folder(self):
        self.assertIn('autorelease.py sitedir', self.text)
        self.assertIn('--site "site${SITE_DIR:+/$SITE_DIR}"', self.text)

    def test_a_token_that_cannot_push_is_found_before_the_tests(self):
        plan = self.text[self.text.index('  plan:'):self.text.index('  tests:')]
        self.assertIn('push --dry-run origin FETCH_HEAD:refs/heads/main', plan)
        self.assertLess(plan.index('The token can push to main'), plan.index('Decide whether this push makes a release'))
        self.assertIn('add-mask', plan)
        self.assertNotIn('PUSH_TOKEN@', self.text, 'the token never goes into a URL')

    def test_it_cannot_loop(self):
        self.assertIn("!startsWith(github.event.head_commit.message, '[auto-release]')", self.text)
        self.assertIn("github.actor != 'github-actions[bot]'", self.text)
        commits = re.findall(r'git commit -m "([^"]+)"', self.text)
        self.assertEqual(len(commits), 3, commits)           # the release, the channels, the rollback
        for c in commits:
            self.assertTrue(c.startswith('[auto-release] '), c)
            self.assertTrue(c.endswith(' [skip ci]'), c)

    def test_releases_run_one_at_a_time_and_none_is_dropped(self):
        self.assertRegex(self.text, r'concurrency:\n  group: auto-release\n  cancel-in-progress: false')

    def test_nothing_is_published_unless_the_tests_and_every_site_passed(self):
        self.assertIn('needs: [plan, tests, sites]', self.release)
        self.assertIn('uses: ./.github/workflows/ci.yml', self.text)
        self.assertIn('fail-fast: false', self.text)
        self.assertIn('build_site.py --site "site${SITE_DIR:+/$SITE_DIR}"', self.text)

    def test_only_the_release_job_can_write(self):
        before_release = self.text[:self.text.index('\n  release:')]
        self.assertNotIn('contents: write', before_release)
        self.assertNotIn('git push', before_release)
        self.assertIn('contents: write', self.release)
        self.assertIn('issues: write', self.release)

    def test_the_steps_run_in_the_order_the_release_needs(self):
        order = ['autorelease.py prepare', 'gh release create', 'autorelease.py channels', 'autorelease.py dispatch',
                 'autorelease.py verify', 'autorelease.py rollback']
        at = [self.release.index(o) for o in order]
        self.assertEqual(at, sorted(at), 'the tag must exist before a channel points at it')

    def test_rollback_dispatches_again_and_opens_an_issue(self):
        step = self.release[self.release.index('name: Roll back'):]
        self.assertIn("steps.verify.outputs.ok == 'false'", step)
        for needle in ('autorelease.py rollback', 'autorelease.py dispatch', 'gh issue create', 'exit 1'):
            self.assertIn(needle, step)

    def test_a_major_release_is_held(self):
        self.assertIn("steps.channels.outputs.moved == 'false'", self.release)
        self.assertIn("steps.channels.outputs.moved == 'true'", self.release)

    def test_a_stale_run_does_not_release(self):
        self.assertIn('stale=true', self.release)
        self.assertGreaterEqual(self.release.count("steps.fresh.outputs.stale != 'true'"), 5)

    def test_no_secret_is_written_into_the_file(self):
        self.assertNotRegex(self.text, r'gh[pousr]_[A-Za-z0-9]{20,}')
        self.assertIn('secrets.RELEASE_TOKEN', self.text)
        self.assertIn('secrets.SITES_DISPATCH_TOKEN', self.text)

    def test_no_long_dashes(self):
        for name in ('.github/workflows/auto-release.yml', 'tools/autorelease.py'):
            with open(os.path.join(ROOT, name), encoding='utf-8') as f: text = f.read()
            self.assertNotRegex(text, '[' + chr(0x2013) + chr(0x2014) + ']', name)


if __name__ == '__main__':
    unittest.main()
