#!/usr/bin/env python3
"""The steps of the automatic release (.github/workflows/auto-release.yml), as plain Python.

The workflow only calls this file. All the decisions are here so that tests can run them without GitHub:
which merged pull requests a release holds, how big the bump is, what goes in VERSION, CHANGELOG.md and
channels.json, which sites to tell, how to judge their builds, and what to roll back.

Standard library only. Subcommands (each reads its settings from the environment, see main()):

    plan      decide whether this push to main makes a release, and of what size
    matrix    the sites in sites.json, as the build matrix of the workflow
    sitedir   find the folder of a checked out site that holds site.config.json
    prepare   write the new VERSION and the CHANGELOG.md entry, and the release notes
    channels  move canary, beta and stable to the new version (never for a major release)
    dispatch  send the engine-release request to every site
    verify    wait for each site's build and check its live address answers 200 (a protected site: that it refuses a visitor with no password)
    rollback  put the channels back to the versions they had, and tell the sites again
    issue     write the text of the issue that reports a failure
"""
import datetime, json, os, re, subprocess, sys, time, urllib.error, urllib.request

LEVELS = ('patch', 'minor', 'major')
CHANNELS = ('canary', 'beta', 'stable')
MARK = '[auto-release]'                 # starts the message of every commit this workflow makes
SKIP_CI = '[skip ci]'                   # so that Checks and Tell the sites do not run on them
OWN_FILES = {'VERSION', 'channels.json', 'CHANGELOG.md'}     # a push that changes only these is never a release
SKIP_LABEL = 'no-release'
API = 'https://api.github.com'


# ---- decisions (pure) ------------------------------------------------------------------------------------

def parse_version(text):
    m = re.fullmatch(r'\s*v?(\d+)\.(\d+)\.(\d+)\s*', text or '')
    if not m:
        raise ValueError('Not a version of the form X.Y.Z: %r' % (text,))
    return tuple(int(x) for x in m.groups())


def bump(version, level):
    major, minor, patch = parse_version(version)
    if level == 'major':
        return '%d.0.0' % (major + 1)
    if level == 'minor':
        return '%d.%d.0' % (major, minor + 1)
    if level == 'patch':
        return '%d.%d.%d' % (major, minor, patch + 1)
    raise ValueError('Unknown level %r' % (level,))


def label_names(pr):
    return [str(l.get('name') if isinstance(l, dict) else l).strip().lower() for l in (pr.get('labels') or [])]


def level_from_labels(prs):
    """The biggest bump any of the pull requests asks for: patch unless one is labelled minor or major."""
    names = {n for pr in prs for n in label_names(pr)}
    return 'major' if 'major' in names else 'minor' if 'minor' in names else 'patch'


def release_is_skipped(prs):
    """True when every pull request in the release says no-release. A release with no pull request is not skipped."""
    return bool(prs) and all(SKIP_LABEL in label_names(pr) for pr in prs)


def is_own_commit(message, actor='', files=None):
    """Commits made by this workflow, and pushes that only move VERSION, CHANGELOG.md or channels.json, are no release."""
    if (message or '').lstrip().startswith(MARK):      # only at the start: a PR that quotes it is still released
        return True
    if (actor or '').lower() in ('github-actions[bot]', 'github-actions'):
        return True
    return bool(files) and set(files) <= OWN_FILES


def changelog_entry(version, prs):
    lines = ['## %s' % version, '']
    if not prs:
        lines.append('- Changes pushed directly to main. See the commit history.')
    for pr in prs:
        title = re.sub(r'\s+', ' ', (pr.get('title') or '').strip()) or 'Untitled change'
        who = (pr.get('user') or {}).get('login') if isinstance(pr.get('user'), dict) else None
        lines.append('- %s (#%s)%s' % (title, pr.get('number'), (' by @%s' % who) if who else ''))
    return '\n'.join(lines) + '\n'


def insert_changelog(text, entry):
    """The entry goes above the newest release, below the heading and its one-line intro."""
    m = re.search(r'^## ', text, re.M)
    if not m:
        return text.rstrip('\n') + '\n\n' + entry
    return text[:m.start()] + entry + '\n' + text[m.start():]


def release_notes(version, prs):
    body = changelog_entry(version, prs).split('\n', 2)[2]      # without its own heading: GitHub shows the title
    return body.strip() + '\n'


def read_channels(text):
    doc = json.loads(text)
    return {c: doc['channels'][c] for c in CHANNELS}


def set_channels(text, versions):
    """The text of channels.json with these versions, and nothing else about it changed."""
    for name, v in versions.items():
        pattern = re.compile(r'("%s"\s*:\s*")[^"]*(")' % re.escape(name))
        if not pattern.search(text):
            raise ValueError('channels.json has no "%s"' % name)
        text = pattern.sub(lambda m, v=v: m.group(1) + v + m.group(2), text, count=1)
    return text


def move_channels(text, version, level):
    """(new text, previous versions, moved). A major release is published but held: its sites must change first."""
    before = read_channels(text)
    if level == 'major':
        return text, before, False
    return set_channels(text, {c: version for c in CHANNELS}), before, True


def sites_from(doc):
    out = []
    for s in doc['sites']:
        site = {'repo': s['repo'], 'name': s.get('name') or s['repo'], 'channel': s.get('channel', 'stable')}
        if s.get('dir'):
            site['dir'] = s['dir']
        # a protected site (access.enabled in its site.config.json) is on Cloudflare Pages and asks for a password,
        # so it has an address of its own and is checked for being closed, not for answering 200
        if s.get('protected'):
            site['protected'] = True
            site['url'] = s.get('url') or ''
        out.append(site)
    return out


def find_site_dir(root, hint=''):
    """The folder of a checked out site repository that holds site.config.json, as a path under `root` ('' for the root).

    A site whose files live in a sub-folder (its deploy.yml sets site-dir) is found without being told: the one folder
    within two levels that holds the file. `hint` (the optional "dir" of a site in sites.json) wins when given.
    Raises ValueError when there is none, or more than one and no hint."""
    def has(d):
        return os.path.isfile(os.path.join(root, d, 'site.config.json'))
    hint = (hint or '').strip().strip('/')
    if hint:
        if '..' in hint.split('/'):
            raise ValueError('the dir %r must stay inside the site' % hint)
        if not has(hint):
            raise ValueError('no site.config.json in %r of the site' % hint)
        return hint
    if has(''):
        return ''
    found = []
    for a in sorted(os.listdir(root)):
        if a.startswith('.') or a == 'node_modules' or not os.path.isdir(os.path.join(root, a)):
            continue
        if has(a):
            found.append(a)
            continue
        for b in sorted(os.listdir(os.path.join(root, a))):
            if not b.startswith('.') and b != 'node_modules' and os.path.isdir(os.path.join(root, a, b)) and has(a + '/' + b):
                found.append(a + '/' + b)
    if len(found) == 1:
        return found[0]
    if not found:
        raise ValueError('no site.config.json in the site, at its top or within two folders')
    raise ValueError('more than one site.config.json (%s): set "dir" for this site in sites.json' % ', '.join(found))


def when(ts):
    return datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)


def judge_runs(runs, since):
    """('ok'|'failed'|'waiting'|'none', note) from the workflow runs a site started after the dispatch at `since`."""
    mine = [r for r in runs if r.get('created_at') and when(r['created_at']) >= since - datetime.timedelta(seconds=5)]
    if not mine:
        return 'none', 'no build was started by the request'
    if any(r.get('status') != 'completed' for r in mine):
        return 'waiting', 'a build is still running'
    bad = [r for r in mine if r.get('conclusion') not in ('success', 'skipped', 'neutral')]
    if bad:
        return 'failed', '; '.join('%s %s (%s)' % (r.get('name') or 'build', r.get('conclusion'), r.get('html_url')) for r in bad)
    return 'ok', 'built'


def issue_text(version, failures, rolled_back, previous):
    lines = ['Release v%s was published and sent to the sites, but %d of them did not come up.' % (version, len(failures)), '',
             '| Site | What went wrong |', '| --- | --- |']
    for f in failures:
        lines.append('| %s | %s |' % (f['repo'], f['why'].replace('|', '/').replace('\n', ' ')))
    lines.append('')
    if rolled_back:
        lines.append('The channels were put back (%s) and the sites were told again, so they rebuild with the last good version. '
                     'v%s stays published and is not deleted or re-tagged: fix forward with a new release.' %
                     (', '.join('%s %s' % (c, v) for c, v in previous.items()), version))
    else:
        lines.append('The channels could not be put back automatically. Set them to the last good version in channels.json on main.')
    return '\n'.join(lines) + '\n'


# ---- talking to GitHub -----------------------------------------------------------------------------------

class Api:
    """A small GitHub REST client. Tests replace it with a fake that has the same two methods."""

    def __init__(self, token):
        self.token = token

    def request(self, method, url, body=None):
        if not url.startswith('http'):
            url = API + url
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'family-site-engine-autorelease'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw and r.headers.get('Content-Type', '').startswith('application/json') else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, None

    def get(self, url):
        return self.request('GET', url)

    def post(self, url, body):
        return self.request('POST', url, body)


def live_url(api, repo):
    code, doc = api.get('/repos/%s/pages' % repo)
    if code == 200 and isinstance(doc, dict) and doc.get('html_url'):
        return doc['html_url']
    owner, name = repo.split('/', 1)
    return 'https://%s.github.io/%s/' % (owner.lower(), name)


def answers_200(url, fetch=None):
    """GET the address, following redirects. fetch(url) -> status code is replaceable for tests."""
    if fetch:
        return fetch(url)
    req = urllib.request.Request(url, headers={'User-Agent': 'family-site-engine-autorelease', 'Cache-Control': 'no-cache'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return 0


def answers_closed(url, fetch=None):
    """GET a protected site's address with no cookie. Returns (status, has the gate's header). fetch(url) may give
    either that pair or just a status code (no header then), for tests."""
    if fetch:
        r = fetch(url)
        return r if isinstance(r, tuple) else (r, False)
    req = urllib.request.Request(url, headers={'User-Agent': 'family-site-engine-autorelease', 'Cache-Control': 'no-cache'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, bool(r.headers.get('X-Family-Gate'))
    except urllib.error.HTTPError as e:
        return e.code, bool(e.headers.get('X-Family-Gate'))
    except (urllib.error.URLError, OSError):
        return 0, False


def check_protected(site, fetch=None):
    """(ok, why) for a protected site: the address must refuse a visitor with no password, and the gate must be what says so.
    A site that answers 200 is open and that is the failure this exists to catch."""
    url = (site.get('url') or '').strip()
    if not url:
        return False, 'it is protected but sites.json gives no url for it'
    base = url if url.endswith('/') else url + '/'
    status, gate = answers_closed(base, fetch)
    if status == 401 and gate:
        # a data file too, so a site that serves its front page closed but its data open is caught
        s2, _ = answers_closed(base + 'data/people.json', fetch)
        if s2 == 200:
            return False, 'built, but %sdata/people.json answers 200 with no password: the site is open' % base
        return True, 'built, and %s asks for the password (401 from the gate)' % base
    if status == 200:
        return False, 'built, but %s answers 200 with no password: the site is open' % base
    return False, 'built, but %s answered %s%s instead of 401 from the gate' % (base, status, '' if gate else ' with no gate header')


def dispatch(api, sites, channels):
    """Send engine-release to every site. Returns [(repo, status code)]."""
    out = []
    for s in sites:
        code, _ = api.post('/repos/%s/dispatches' % s['repo'], {'event_type': 'engine-release', 'client_payload': {'channels': channels}})
        out.append((s['repo'], code))
    return out


def verify_sites(api, sites, since, timeout=2400, appear=600, poll=30, fetch=None, sleep=time.sleep, now=time.time):
    """Wait for each site's build and check its address. Returns [{'repo', 'ok', 'why'}], one per site."""
    start = now()
    results = {}
    by_repo = {s['repo']: s for s in sites}
    pending = {s['repo'] for s in sites}
    stamp = since.strftime('%Y-%m-%dT%H:%M:%SZ')
    while pending:
        for repo in sorted(pending):
            code, doc = api.get('/repos/%s/actions/runs?event=repository_dispatch&created=%%3E%%3D%s&per_page=30' % (repo, stamp))
            if code != 200:
                results[repo] = {'repo': repo, 'ok': False, 'why': 'could not read its builds (GitHub answered %s)' % code}
                pending.discard(repo)
                continue
            state, note = judge_runs((doc or {}).get('workflow_runs') or [], since)
            if state == 'waiting' or (state == 'none' and now() - start < appear):
                continue
            if state != 'ok':
                results[repo] = {'repo': repo, 'ok': False, 'why': note}
            elif by_repo[repo].get('protected'):
                good, why = check_protected(by_repo[repo], fetch)
                results[repo] = {'repo': repo, 'ok': good, 'why': why}
            else:
                url = live_url(api, repo)
                status = answers_200(url, fetch)
                results[repo] = {'repo': repo, 'ok': status == 200, 'why': 'built, and %s answers 200' % url if status == 200 else 'built, but %s answered %s' % (url, status)}
            pending.discard(repo)
        if pending:
            if now() - start > timeout:
                for repo in sorted(pending):
                    results[repo] = {'repo': repo, 'ok': False, 'why': 'its build did not finish in %d minutes' % (timeout // 60)}
                break
            sleep(poll)
    return [results[s['repo']] for s in sites]


# ---- steps used by the workflow --------------------------------------------------------------------------

def git(*args, cwd='.'):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def output(**kv):
    """Set outputs for the workflow's later steps (and print them, for the log)."""
    path = os.environ.get('GITHUB_OUTPUT')
    for k, v in kv.items():
        line = '%s=%s' % (k, v if isinstance(v, str) else json.dumps(v))
        print(line)
        if path:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')


def last_tag(version):
    tag = 'v' + version.strip()
    ok = subprocess.run(['git', 'rev-parse', '-q', '--verify', 'refs/tags/' + tag], capture_output=True).returncode == 0
    return tag if ok else None


def merged_prs(api, repo, sha, since_tag):
    """The pull requests behind the commits on main since the last release, once each, oldest first."""
    rng = '%s..%s' % (since_tag, sha) if since_tag else sha
    shas = git('rev-list', '--reverse', '--max-count=100', rng).split()
    seen, prs = set(), []
    for c in shas:
        code, doc = api.get('/repos/%s/commits/%s/pulls' % (repo, c))
        for pr in (doc if code == 200 and isinstance(doc, list) else []):
            if pr.get('number') not in seen and pr.get('merged_at'):
                seen.add(pr['number'])
                prs.append(pr)
    return prs


def cmd_plan(env, api):
    message = env.get('HEAD_MESSAGE', '')
    before, sha = env.get('BEFORE', ''), env['SHA']
    base = before if before and set(before) != {'0'} else sha + '~1'
    try:
        files = [f for f in git('diff', '--name-only', base, sha).split('\n') if f]
    except subprocess.CalledProcessError:
        files = []
    if is_own_commit(message, env.get('ACTOR', ''), files):
        output(release='false', why='the push is the release workflow itself, or moves only VERSION, CHANGELOG.md or channels.json')
        return 0
    version = read('VERSION').strip()
    prs = merged_prs(api, env['REPO'], sha, last_tag(version))
    if release_is_skipped(prs):
        output(release='false', why='every merged pull request is labelled %s' % SKIP_LABEL)
        return 0
    write('release-prs.json', json.dumps(prs))
    output(release='true', level=level_from_labels(prs), why='%d merged pull request(s)' % len(prs))
    return 0


def cmd_matrix(env, api):
    output(matrix={'include': sites_from(json.loads(read('sites.json')))})
    return 0


def cmd_sitedir(env, api):
    try:
        output(dir=find_site_dir(env['SITE_ROOT'], env.get('SITE_DIR_HINT', '')))
    except ValueError as e:
        print('::error::%s' % e)
        return 1
    return 0


def cmd_prepare(env, api):
    level = env['LEVEL']
    prs = json.loads(read('release-prs.json')) if os.path.exists('release-prs.json') else []
    old = read('VERSION').strip()
    new = bump(old, level)
    write('VERSION', new + '\n')
    write('CHANGELOG.md', insert_changelog(read('CHANGELOG.md'), changelog_entry(new, prs)))
    write('release-notes.md', release_notes(new, prs))
    output(version=new, previous=old, tag='v' + new)
    return 0


def cmd_channels(env, api):
    text, before, moved = move_channels(read('channels.json'), env['VERSION'], env['LEVEL'])
    if moved:
        write('channels.json', text)
    output(moved='true' if moved else 'false', previous=before)
    return 0


def cmd_dispatch(env, api):
    channels = read_channels(read('channels.json'))
    sites = sites_from(json.loads(read('sites.json')))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    bad = [(r, c) for r, c in dispatch(api, sites, channels) if c != 204]
    for r, c in bad:
        print('::warning::%s answered %s to the rebuild request' % (r, c))
    output(at=stamp, sent=str(len(sites) - len(bad)))
    return 1 if bad else 0


def cmd_verify(env, api):
    sites = sites_from(json.loads(read('sites.json')))
    results = verify_sites(api, sites, when(env['SINCE']), timeout=int(env.get('TIMEOUT', 2400)), appear=int(env.get('APPEAR', 600)),
                           poll=int(env.get('POLL', 30)))
    for r in results:
        print('%s  %s  %s' % ('ok  ' if r['ok'] else 'FAIL', r['repo'], r['why']))
    failures = [r for r in results if not r['ok']]
    write('failures.json', json.dumps(failures))
    output(ok='false' if failures else 'true', failed=str(len(failures)))
    return 0


def cmd_rollback(env, api):
    previous = json.loads(env['PREVIOUS'])
    write('channels.json', set_channels(read('channels.json'), previous))
    return 0


def cmd_issue(env, api):
    failures = json.loads(read('failures.json'))
    previous = json.loads(env.get('PREVIOUS') or '{}')
    write('issue.md', issue_text(env['VERSION'], failures, env.get('ROLLED_BACK') == 'true', previous))
    return 0


COMMANDS = {'plan': cmd_plan, 'matrix': cmd_matrix, 'sitedir': cmd_sitedir, 'prepare': cmd_prepare, 'channels': cmd_channels,
            'dispatch': cmd_dispatch, 'verify': cmd_verify, 'rollback': cmd_rollback, 'issue': cmd_issue}


def main(argv=None, env=None, api=None):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    if api is None:
        api = Api(env.get('TOKEN', ''))
    return COMMANDS[argv[0]](env, api)


if __name__ == '__main__':
    sys.exit(main())
