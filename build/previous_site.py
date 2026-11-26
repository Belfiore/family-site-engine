#!/usr/bin/env python3
"""Fetch the Discovery Timeline's history from the live site, so the next build can compare against it.

    python3 build/previous_site.py --url https://owner.github.io/repo/ --out previous

The engine builds from files and keeps nothing between builds, so what was published last time is read from
the published site itself: discoveries/state.json. The files are written under --out, which build_site.py then
takes as --previous.

  * state.json found                    written; exit 0.
  * state.json not there (HTTP 404)     if the live site is not one that was built with the timeline, this is the first
                                        publication with it on: nothing is written, exit 0.
                                        If the live site says it was (engine-build.json has "timeline"), the history
                                        is missing, and carrying on would wipe it: exit 1.
  * anything else (network, 5xx, bad JSON)  exit 1. A build that cannot see its baseline must not publish.

Used by .github/workflows/build-site.yml. Python's standard library only.
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

STATE = 'discoveries/state.json'


def fetch(url, tries=3):
    """(status, bytes). 404 is an answer; other failures are retried, then raised."""
    last = None
    for i in range(tries):
        sep = '&' if '?' in url else '?'
        req = urllib.request.Request('%s%scb=%d' % (url, sep, int(time.time() * 1000)),
                                     headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'User-Agent': 'family-site-engine'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return 404, b''
            last = 'HTTP %d from %s' % (e.code, url)
        except (urllib.error.URLError, OSError) as e:
            last = 'could not reach %s: %s' % (url, e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(last)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Fetch the live site\'s discovery history.')
    ap.add_argument('--url', required=True, help='the live site\'s address (its GitHub Pages address, or its own domain)')
    ap.add_argument('--out', required=True, help='a folder to write discoveries/state.json into')
    args = ap.parse_args(argv)
    base = args.url if args.url.endswith('/') else args.url + '/'
    os.makedirs(args.out, exist_ok=True)
    try:
        status, body = fetch(base + STATE)
        if status == 404:
            s2, b2 = fetch(base + 'engine-build.json')
            if s2 == 200:
                try:
                    had = bool((json.loads(b2.decode('utf-8')) or {}).get('timeline'))
                except ValueError:
                    had = False
                if had:
                    print('error: %s says the live site was built with the Discovery Timeline, but %s%s is missing. Not carrying on: '
                          'that would erase the history. Check the live site, then run this again.' % (base + 'engine-build.json', base, STATE))
                    return 1
            print('No history on the live site yet (%s): this is the first publication with the timeline on.' % (base + STATE))
            return 0
        try:
            state = json.loads(body.decode('utf-8'))
            if not isinstance(state, dict) or 'schema' not in state: raise ValueError('not a state file')
        except ValueError as e:
            print('error: %s is not a valid history file: %s' % (base + STATE, e))
            return 1
    except RuntimeError as e:
        print('error: %s. Not publishing without the previous history.' % e)
        return 1
    dst = os.path.join(args.out, STATE)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'wb') as f: f.write(body)
    print('Previous history: %d finds, published %s.' % (len(state.get('entries') or []), state.get('published')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
