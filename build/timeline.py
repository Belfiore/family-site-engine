"""The Discovery Timeline step of a build: read the data, compare it with what was published last time, and write
the history and the page's content.

Nothing here runs unless the site sets "timeline": {"enabled": true} in site.config.json. See docs/discovery-timeline.md.

What goes into the built site:
  discoveries/state.json    everything the next build needs to compare against (claims, findings, hashed ids of
                            people left out). Public, and written without anything about people who are left out.
  discoveries/history.json  the findings as the page shows them, for anyone who wants to read them as data.
  <timeline file>.html      the page (made by build_site.py from templates/timeline.html and the body made here).
"""
import datetime, json, os, sys

import discoveries as D
import timeline_page

STATE_REL = os.path.join('discoveries', 'state.json')
HISTORY_REL = os.path.join('discoveries', 'history.json')
CURATED = 'discoveries.json'


class TimelineError(Exception):
    pass


def read_json(path, what, required=False):
    if not os.path.exists(path):
        if required: raise TimelineError('%s: %s is not there' % (what, path))
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except ValueError as e:
        raise TimelineError('%s (%s) is not valid JSON: %s' % (what, path, e))


def load_previous(arg):
    """The state published last time. arg is the --previous option:
         None       not given: the build stops. A build that does not know what was published last would
                    forget every find and start the history again on each publication.
         'none'     no history yet, said on purpose (the first build with the timeline on, or a local trial)
         a folder   a copy of the last published site, or of just its discoveries/ folder
         a file     a state.json
       Returns (state or None, a few words on where it came from)."""
    if arg is None:
        raise TimelineError('this site has the Discovery Timeline on, but the build was not told what was published last, so it would '
                            'forget every find. In a workflow, use build-site.yml from engine 1.2.0 or later (it fetches the live '
                            'history). For a local trial, add --previous none.')
    if arg.strip().lower() == 'none':
        return None, 'first publication with the timeline on'
    p = os.path.abspath(arg)
    if os.path.isdir(p):
        for rel in (STATE_REL, 'state.json'):
            f = os.path.join(p, rel)
            if os.path.isfile(f):
                return read_json(f, 'The previous discovery history', True), 'from %s' % f
        return None, 'first publication with the timeline on (%s has no discoveries/state.json)' % p
    if os.path.isfile(p):
        return read_json(p, 'The previous discovery history', True), 'from %s' % p
    raise TimelineError('--previous %s: no such file or folder' % arg)


def parse_now(arg):
    if not arg: return D.now_utc()
    try:
        d = datetime.datetime.strptime(arg, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        raise TimelineError('--now %r is not a time like 2026-11-26T10:00:00Z' % arg)
    return arg


def curated_path(site, cfg):
    return os.path.join(site, (cfg.get('data') or {}).get('dir') or 'data', CURATED)


def snapshot(site, cfg):
    ddir = os.path.join(site, (cfg.get('data') or {}).get('dir') or 'data')
    doc = lambda n: read_json(os.path.join(ddir, n + '.json'), n + '.json')
    return D.build_snapshot(site, cfg, doc('people'), doc('sources'), doc('places'), read_json(curated_path(site, cfg), CURATED))


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write('\n')


def run(site, cfg, out, previous_arg, now_arg, version):
    """Make the history and the page body. Returns (body_html, info)."""
    now = parse_now(now_arg)
    snap = snapshot(site, cfg)
    prev, how = load_previous(previous_arg)
    try:
        state, report = D.update(prev, snap, now, version, cfg)
    except ValueError as e:
        raise TimelineError(str(e))
    hist = D.public_history(state, snap)
    write_json(os.path.join(out, STATE_REL), state)
    write_json(os.path.join(out, HISTORY_REL), hist)
    body = timeline_page.render_body(hist['entries'], hist['lines'], cfg, cfg['_pages'], since=hist.get('since'))
    info = {'file': cfg['_pages']['timeline'], 'mode': report['mode'], 'new': report['new'], 'entries': len(hist['entries']),
            'since': hist.get('since'), 'previous': how, 'warnings': snap.warnings, 'notes': report['notes']}
    return body, info
