#!/usr/bin/env python3
"""Suggest Discovery Timeline entries for what a site's git history already holds.

    python3 tools/backfill-discoveries.py --site path/to/site [--out discoveries.suggestions.json] [--since 2026-01-01]

The timeline starts empty on the day a site turns it on. This script reads the site's own git history, replays the
commits that changed its data one after another, and writes down what the timeline would have found at each step.
It never changes the site's data, its history or its settings: it writes one file, which you read through.

The file looks like data/discoveries.json, with one extra "review" note on each suggestion. To use a suggestion,
delete the ones you do not want, check the rest (above all the dates: a find is dated by the commit that added it,
which is not always the day the research was done), take out the "review" notes, and put what is left into
data/discoveries.json in the site. The next build then lists them, with the dates you gave.

Rules it keeps:
  * it asks the same questions as the live build (build/discoveries.py), so a find means the same thing;
  * people who are living now, or in a hidden region, are left out, whatever the old data said about them;
  * a find that a later commit corrected or withdrew is not suggested;
  * the first commit it reads is the starting point, not a find;
  * it needs git, and the site folder must be a git repository.
"""
import argparse, datetime, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ENGINE_ROOT, 'build'))
import discoveries as D, sitecfg  # noqa: E402

BULK = 25      # more finds than this from one commit looks like a bulk import, and is flagged


def git(site, *args, check=True):
    p = subprocess.run(['git', '-C', site] + list(args), capture_output=True)
    if check and p.returncode: raise SystemExit('git %s failed: %s' % (' '.join(args), p.stderr.decode('utf-8', 'replace').strip()))
    return p.stdout


def utc(iso):
    d = datetime.datetime.fromisoformat(iso.replace('Z', '+00:00'))
    return d.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Suggest Discovery Timeline entries from a site\'s git history.')
    ap.add_argument('--site', default='.', help='the site folder (with site.config.json), inside a git repository')
    ap.add_argument('--out', help='where to write the suggestions (default: discoveries.suggestions.json in the site folder)')
    ap.add_argument('--since', help='only read commits on or after this date (YYYY-MM-DD); the first one read is the starting point')
    ap.add_argument('--force', action='store_true', help='replace the suggestions file if it is already there')
    args = ap.parse_args(argv)
    site = os.path.abspath(args.site)
    cfg = sitecfg.load(site)
    top = git(site, 'rev-parse', '--show-toplevel').decode().strip()
    prefix = os.path.relpath(site, top)
    prefix = '' if prefix == '.' else prefix.replace(os.sep, '/') + '/'
    ddir = (cfg.get('data') or {}).get('dir') or 'data'
    out = os.path.abspath(args.out or os.path.join(site, 'discoveries.suggestions.json'))
    if os.path.exists(out) and not args.force:
        raise SystemExit('%s is already there. Rename it, or use --force to replace it.' % out)

    files = ['%s/%s.json' % (ddir, n) for n in ('people', 'sources', 'places')]      # git log reads paths from the site folder; git show reads them from the top
    log = git(site, 'log', '--reverse', '--format=%H%x09%aI%x09%s', '--', *files).decode('utf-8').splitlines()
    commits = [l.split('\t', 2) for l in log if l.strip()]
    if args.since:
        commits = [c for c in commits if c[1][:10] >= args.since]
    if len(commits) < 2:
        raise SystemExit('Only %d commit(s) of the data to read; at least two are needed (the first is the starting point).' % len(commits))

    def doc(sha, name):
        p = subprocess.run(['git', '-C', site, 'show', '%s:%s%s/%s.json' % (sha, prefix, ddir, name)], capture_output=True)
        if p.returncode: return None
        return json.loads(p.stdout.decode('utf-8'))

    version = open(os.path.join(ENGINE_ROOT, 'VERSION')).read().strip()
    state, entries_by_commit, skipped = None, {}, []
    for sha, when, subject in commits:
        try:
            people, sources, places = doc(sha, 'people'), doc(sha, 'sources'), doc(sha, 'places')
        except ValueError as e:
            skipped.append((sha[:8], 'the data was not valid JSON (%s)' % e))
            continue
        if people is None:
            skipped.append((sha[:8], 'no people.json'))
            continue
        blobs = {}
        for l in git(site, 'ls-tree', '-r', sha, check=False).decode('utf-8', 'replace').splitlines():
            meta, _, name = l.partition('\t')
            blobs[name] = meta.split()[2][:10]
        try:
            snap = D.build_snapshot(site, cfg, people, sources, places, None, file_id=lambda rel, b=blobs: b.get(prefix + rel))
            before = {e['id'] for e in (state or {}).get('entries') or []}
            state, rep = D.update(state, snap, utc(when), version, cfg)
        except Exception as e:      # an old commit in a shape the engine cannot read is skipped, not fatal
            skipped.append((sha[:8], 'could not be read (%s: %s)' % (type(e).__name__, e)))
            continue
        for e in state['entries']:
            if e['id'] not in before and e.get('origin') != 'manual':
                entries_by_commit.setdefault(sha, []).append(e['id'])
        entries_by_commit.setdefault('_meta', []).append((sha, when, subject))
    if state is None:
        raise SystemExit('No commit could be read.')

    # what the site says today decides who may be named
    def now_doc(n):
        p = os.path.join(site, ddir, n + '.json')
        if not os.path.exists(p): return None
        with open(p, encoding='utf-8') as f: return json.load(f)
    cur = D.build_snapshot(site, cfg, now_doc('people'), now_doc('sources'), now_doc('places'), None)
    meta = {m[0]: m for m in entries_by_commit.get('_meta', [])}
    origin = {i: sha for sha, ids in entries_by_commit.items() if sha != '_meta' for i in ids}
    per_commit = {sha: len(ids) for sha, ids in entries_by_commit.items() if sha != '_meta'}
    out_entries, left_out = [], {'living or hidden': 0, 'corrected or withdrawn': 0, 'from the starting point': 0, 'sources a later find cites': 0}
    for e in state['entries']:
        if e['id'] not in origin:
            left_out['from the starting point'] += 1
            continue
        if not D.public_ok(e, cur):
            left_out['living or hidden'] += 1
            continue
        if e.get('status') in ('corrected', 'withdrawn'):
            left_out['corrected or withdrawn'] += 1
            continue
        atoms = e.get('atoms') or []
        if atoms and all(a.startswith('source:') and a[7:] in cur.refs['src_public'] for a in atoms):
            left_out['sources a later find cites'] += 1      # "added to the sources" is noise once the records that use it are found
            continue
        sha = origin[e['id']]
        notes = ['The date is the day the change was committed, not necessarily the day the research was done.']
        if per_commit.get(sha, 0) > BULK: notes.append('This commit added %d finds at once; it may be a bulk import rather than research.' % per_commit[sha])
        if e.get('status') == 'revised': notes.append('Part of what this find mentions was later withdrawn.')
        src = e.get('source') or {}
        item = {'id': 'suggested-' + e['id'], 'covers': e.get('atoms') or [], 'personIds': e.get('personIds') or [], 'placeIds': e.get('placeIds') or [],
                'headline': e['headline'], 'found': e['found'], 'findType': e['type']}
        if src.get('text'): item['source'] = {'text': src['text'], **({'url': src['url']} if src.get('url') else {})}
        if e.get('confidence'): item['confidence'] = e['confidence']
        if e.get('image'): item['image'] = e['image']
        item['review'] = {'commit': sha[:10], 'committed': meta[sha][1], 'subject': meta[sha][2], 'notes': notes}
        out_entries.append(item)
    out_entries.sort(key=lambda i: (i['found'], i['id']), reverse=True)
    doc_out = {'meta': {'note': 'Suggestions from the git history, for a person to read through. Not used by the build until they are in data/discoveries.json.',
                        'generated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'engine': version,
                        'commitsRead': len(commits) - len(skipped), 'startingPoint': commits[0][0][:10] + ' ' + commits[0][1][:10],
                        'skipped': ['%s: %s' % s for s in skipped], 'leftOut': left_out},
               'discoveries': out_entries}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(doc_out, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print('Read %d commits of the data (the first, %s, is the starting point).' % (len(commits) - len(skipped), commits[0][0][:8]))
    print('%d suggestions written to %s' % (len(out_entries), out))
    print('Left out: %s.' % (', '.join('%d %s' % (n, k) for k, n in left_out.items() if n) or 'nothing'))
    for s in skipped: print('Skipped commit %s: %s' % s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
