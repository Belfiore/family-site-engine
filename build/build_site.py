#!/usr/bin/env python3
"""Build a family site with the engine.

    python3 build/build_site.py --site path/to/site --out path/to/_site

The site folder holds site.config.json, data/ (people.json, sources.json, and places.json if the site has a
map), images and the site's own pages. The result in --out is a complete static site, ready for GitHub Pages
or any static host, with this engine's files inside it under engine/<version>/. Nothing in the result loads
code from anywhere else, so a copy of it keeps working on its own.

Steps, in order (any failure stops the build and leaves the live site as it was):
  1. read site.config.json and check it;
  2. check the data against the schema and against itself (validate.py);
  3. copy the site's files;
  4. copy the engine's files to engine/<version>/;
  5. build Stuart's index, if the site has Stuart;
  6. write the site settings for the browser (site-config.js) and the theme;
  7. build the chat index, if the site turns the chat on (chat/index.json);
  8. make the engine's pages (tree, map, Stuart) from the templates;
  9. bring the site's own pages in line: the navigation bar, the engine's files, Stuart's button,
     and the chat button when the site turns the chat on;
  10. write engine-build.json, saying what was built from what.

A site that turns on the Discovery Timeline (timeline.enabled) also gets, after step 4, the history of what has
been found since it was published last (--previous says where that history is; see docs/discovery-timeline.md),
and its page, made in step 7. A site that does not is built exactly as before.
"""
import argparse, datetime, fnmatch, hashlib, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import archive, chat_index, pages, sitecfg, timeline, validate  # noqa: E402

ALWAYS_SKIP = {'.git', '.github', 'node_modules', '.DS_Store', '_site', 'site.config.json', '__pycache__'}


def engine_version():
    with open(os.path.join(ENGINE_ROOT, 'VERSION'), encoding='utf-8') as f:
        return f.read().strip()


def short_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()[:10]


def engine_ignore(timeline_on, chat_on):
    """Files a site does not use are not copied, so its build stays as it was."""
    skip = []
    if not timeline_on:
        skip += ['timeline.css', 'timeline.js']
    if not chat_on:
        skip += ['chat.css', 'chat.js']
    return shutil.ignore_patterns(*skip) if skip else None


def skipped(rel, patterns):
    parts = rel.split(os.sep)
    if any(p in ALWAYS_SKIP for p in parts): return True
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel + '/', p) or rel.startswith(p.rstrip('/') + '/') for p in patterns)


def copy_site(site, out, patterns):
    n = 0
    for root, dirs, files in os.walk(site):
        rel_root = os.path.relpath(root, site)
        rel_root = '' if rel_root == '.' else rel_root
        dirs[:] = [d for d in dirs if not skipped(os.path.join(rel_root, d), patterns)]
        for f in files:
            rel = os.path.join(rel_root, f)
            if skipped(rel, patterns): continue
            dst = os.path.join(out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(site, rel), dst)
            n += 1
    return n


def browser_settings(cfg, version, base, data_urls, kb_url):
    """What the engine's scripts read in the browser, as window.FamilySite."""
    site = cfg.get('site') or {}
    st = cfg.get('stuart') or {}
    return {
        'engine': {'version': version, 'base': base},
        'site': {'name': site.get('name'), 'familyName': site.get('familyName'), 'lang': site.get('lang')},
        'pages': cfg['_pages'],
        'data': data_urls,
        'archive': kb_url,
        'tree': cfg.get('tree') or {},
        'map': cfg.get('map') or {},
        'stuart': {'anchors': st.get('anchors') or []},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build a family site with the engine.')
    ap.add_argument('--site', default='.', help='the site folder (with site.config.json)')
    ap.add_argument('--out', default='_site', help='where to write the built site')
    ap.add_argument('--keep', action='store_true', help='do not empty --out first')
    ap.add_argument('--previous', help='the site as last published (a folder holding discoveries/state.json, or the file), or "none" for the '
                                       'first build with the Discovery Timeline on. Used only when timeline.enabled is true.')
    ap.add_argument('--now', help='the time of this publication, like 2026-11-26T10:00:00Z (default: now). For tests.')
    args = ap.parse_args(argv)
    site, out = os.path.abspath(args.site), os.path.abspath(args.out)
    version = engine_version()
    base = 'engine/%s/' % version

    # 1. settings
    cfg = sitecfg.load(site)
    problems = validate.check_config(cfg)
    # 2. data
    report = validate.validate_site(site, cfg)
    for w in report['warnings'] + problems['warnings']:
        print('warning:', w)
    errors = report['errors'] + problems['errors']
    chat_problem = chat_index.problem(site, cfg)
    if chat_problem:
        errors.append(chat_problem)
    if errors:
        for e in errors: print('error:', e)
        print('The build stopped: %d problem%s to fix (see docs/data-format.md).' % (len(errors), '' if len(errors) == 1 else 's'))
        return 1

    # 3. the site's own files
    if os.path.exists(out) and not args.keep:
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    exclude = list((cfg.get('publish') or {}).get('exclude') or [])
    tl_on = bool(cfg['_pages'].get('timeline'))
    if tl_on:      # the researcher's notes and the backfill script's suggestions are read here, never published as they are
        exclude += [os.path.relpath(timeline.curated_path(site, cfg), site), 'discoveries.suggestions.json']
    n = copy_site(site, out, exclude)

    # 4. the engine
    # the timeline's files, and the chat's, go only to a site that turned that feature on
    chat_on = bool((cfg.get('chat') or {}).get('enabled'))
    shutil.copytree(os.path.join(ENGINE_ROOT, 'engine'), os.path.join(out, base), dirs_exist_ok=True,
                    ignore=engine_ignore(tl_on, chat_on))

    # 4b. the Discovery Timeline: what is new since the last publication
    tl_body, tl_info = None, None
    if tl_on:
        try:
            tl_body, tl_info = timeline.run(site, cfg, out, args.previous, args.now, version)
        except timeline.TimelineError as e:
            print('error: Discovery Timeline: %s' % e)
            print('The build stopped. The live site is as it was.')
            return 1
        for w in tl_info['warnings']: print('warning: Discovery Timeline:', w)

    # 5. Stuart's index
    kb_url, counts = None, None
    if cfg['_pages'].get('ask'):
        kb_url, counts, size = archive.build_archive(site, cfg, out)

    # 6. settings for the browser, and the theme
    ddir = (cfg.get('data') or {}).get('dir') or 'data'
    data_urls = {}
    for k in ('people', 'sources', 'places'):
        p = os.path.join(site, ddir, k + '.json')
        if os.path.exists(p): data_urls[k] = '%s/%s.json?v=%s' % (ddir, k, short_hash(p))
    settings = browser_settings(cfg, version, base, data_urls, kb_url)
    body = ('/* Written by the family site engine (%s) from site.config.json. Do not edit: change site.config.json. */\n'
            'window.FamilySite = %s;\n') % (version, json.dumps(settings, ensure_ascii=False, indent=1))
    with open(os.path.join(out, 'site-config.js'), 'w', encoding='utf-8') as f: f.write(body)
    ctx = {'base': base, 'config': 'site-config.js?v=%s' % short_hash(os.path.join(out, 'site-config.js'))}
    theme = cfg.get('theme') or {}
    if theme:
        css = '/* Written by the family site engine from "theme" in site.config.json. */\n:root {\n%s}\n' % ''.join(
            '    %s: %s;\n' % (k if k.startswith('--') else '--' + k, v) for k, v in theme.items())
        with open(os.path.join(out, 'site-theme.css'), 'w', encoding='utf-8') as f: f.write(css)
        ctx['theme'] = 'site-theme.css?v=%s' % short_hash(os.path.join(out, 'site-theme.css'))

    # 7. the chat index, only when the site turns the chat on
    chat_info = None
    if chat_on:
        chat_info = chat_index.build(site, cfg, out)
        ctx['chat'] = 'chat/index.json?v=%s' % short_hash(os.path.join(out, 'chat', 'index.json'))

    # 8. the engine's pages
    made = []
    for kind in ('tree', 'map', 'ask', 'timeline'):
        page = cfg['pages'].get(kind)
        if not page: continue
        with open(os.path.join(ENGINE_ROOT, 'templates', kind + '.html'), encoding='utf-8') as f:
            tpl = f.read()
        with open(os.path.join(out, page['file']), 'w', encoding='utf-8') as f:
            f.write(pages.render_engine_page(kind, tpl, cfg, ctx, {'timelineBody': tl_body} if kind == 'timeline' else None))
        made.append(page['file'])

    # 9. the site's own pages
    widget = cfg.get('widget') or {}
    excluded = set((cfg.get('process') or {}).get('exclude') or [])
    processed = []
    for name in sorted(os.listdir(out)):
        if not name.endswith('.html') or name in made or name in excluded: continue
        path = os.path.join(out, name)
        with open(path, encoding='utf-8') as f:
            src = f.read()
        opts = None
        if cfg['_pages'].get('ask') and widget.get('enabled', True) and name not in (widget.get('exclude') or []):
            opts = dict((widget.get('pages') or {}).get(name) or {})
        with open(path, 'w', encoding='utf-8') as f:
            f.write(pages.process_site_page(src, name, cfg, ctx, opts))
        processed.append(name)

    # 10. what was built
    info = {'engine': version, 'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'site': (cfg.get('site') or {}).get('name'), 'channel': (cfg.get('engine') or {}).get('channel'),
            'enginePages': made, 'sitePages': processed, 'files': n, 'stuart': counts,
            'warnings': len(report['warnings'] + problems['warnings'])}
    if chat_info:     # only a site with the chat on has this key, so other sites' files are unchanged
        info['chat'] = {'passages': chat_info['passages']}
    if tl_info:       # only a site with the timeline on has this key, so other sites' files are unchanged
        info['timeline'] = {k: tl_info[k] for k in ('file', 'mode', 'new', 'entries', 'since')}
    with open(os.path.join(out, 'engine-build.json'), 'w', encoding='utf-8') as f: json.dump(info, f, indent=1)
    print('built %s with engine %s: %d files, engine pages %s, %d site pages%s%s' % (
        info['site'] or site, version, n, ', '.join(made) or 'none', len(processed),
        ', Stuart: %d people, %d sections' % (counts['people'], counts['sections']) if counts else '',
        ', chat: %d passages' % chat_info['passages'] if chat_info else ''))
    if tl_info:
        print('discovery timeline: %s; %d new find%s, %d in the history (%s)' % (
            tl_info['mode'], tl_info['new'], '' if tl_info['new'] == 1 else 's', tl_info['entries'], tl_info['previous']))
        for n_ in tl_info['notes']: print('note:', n_)
    return 0


if __name__ == '__main__':
    sys.exit(main())
