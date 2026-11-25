#!/usr/bin/env python3
"""Checking a site's data and settings before anything is built.

    python3 build/validate.py --site path/to/site        print problems; exit 1 if any are errors

Two kinds of check:
  * the shape of each file, against schema/family-data.schema.json and schema/site-config.schema.json
    (a small checker for the parts of JSON Schema those files use, so the build needs nothing installed);
  * the data against itself: every link points at someone who exists, parents and children agree, sources
    and places that are cited exist, files on disk exist.

Errors stop the build: a broken link between people, an id used twice, a missing required field, a wrong
type. Warnings do not: a field the schema does not know, a cited source that is missing, a missing image.
Unknown fields are warnings so that tools adding new kinds of information do not break a site.
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(HERE)
SCHEMAS = {}


def schema(name):
    if name not in SCHEMAS:
        with open(os.path.join(ENGINE_ROOT, 'schema', name), encoding='utf-8') as f:
            SCHEMAS[name] = json.load(f)
    return SCHEMAS[name]


TYPES = {'string': str, 'integer': int, 'number': (int, float), 'boolean': bool, 'object': dict, 'array': list, 'null': type(None)}


def type_ok(v, t):
    if t == 'integer': return isinstance(v, int) and not isinstance(v, bool)
    if t == 'number': return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, TYPES[t])


class Checker:
    """The parts of JSON Schema the engine's schemas use: type, enum, const, pattern, required, properties,
    additionalProperties, items, anyOf, maxItems and $ref to #/$defs."""
    def __init__(self, root):
        self.root = root
        self.errors, self.warnings = [], []

    def check(self, v, s, path):
        if '$ref' in s:
            ref = s['$ref']
            node = self.root
            for part in ref.lstrip('#/').split('/'):
                node = node[part]
            return self.check(v, node, path)
        if 'anyOf' in s:
            tried = []
            for alt in s['anyOf']:
                sub = Checker(self.root)
                sub.check(v, alt, path)
                if not sub.errors:
                    self.warnings += sub.warnings
                    return
                tried.append(sub)
            # say what is wrong inside the form the value is closest to (the one whose type it has)
            near = [t for t in tried if not any(e.startswith(path + ': should be ') for e in t.errors)]
            if len(near) == 1:
                self.errors += near[0].errors
            else:
                self.errors.append('%s: does not match any allowed form' % path)
            return
        t = s.get('type')
        if t:
            ts = t if isinstance(t, list) else [t]
            if not any(type_ok(v, x) for x in ts):
                self.errors.append('%s: should be %s, not %s' % (path, ' or '.join(ts), type(v).__name__))
                return
        if 'const' in s and v != s['const']:
            self.errors.append('%s: should be %r' % (path, s['const']))
        if 'enum' in s and v not in s['enum']:
            self.errors.append('%s: %r is not one of %s' % (path, v, ', '.join(repr(x) for x in s['enum'] if x is not None)))
        if isinstance(v, str) and 'pattern' in s and not re.search(s['pattern'], v):
            self.errors.append('%s: %r is not in the expected form' % (path, v))
        if isinstance(v, dict):
            for r in s.get('required', []):
                if r not in v: self.errors.append('%s: missing %s' % (path, r))
            props = s.get('properties', {})
            for k, x in v.items():
                if k in props:
                    self.check(x, props[k], '%s.%s' % (path, k))
                elif isinstance(s.get('additionalProperties'), dict):
                    self.check(x, s['additionalProperties'], '%s.%s' % (path, k))
                elif s.get('additionalProperties') is False and props:
                    self.warnings.append('%s: unknown field "%s"' % (path, k))
        if isinstance(v, list):
            if 'maxItems' in s and len(v) > s['maxItems']:
                self.errors.append('%s: at most %d items' % (path, s['maxItems']))
            if 'items' in s:
                for i, x in enumerate(v):
                    self.check(x, s['items'], '%s[%d]' % (path, i))


def check_file(doc, defname, label):
    root = schema('family-data.schema.json')
    c = Checker(root)
    c.check(doc, root['$defs'][defname], label)
    return c


def idof(r):
    return r if isinstance(r, str) else (r or {}).get('id')


def validate_site(site, cfg):
    """Errors and warnings for a site's data files."""
    errors, warnings = [], []
    ddir = os.path.join(site, (cfg.get('data') or {}).get('dir') or 'data')

    def load(name, required=True):
        p = os.path.join(ddir, name)
        if not os.path.exists(p):
            if required: errors.append('data/%s is missing' % name)
            return None
        try:
            with open(p, encoding='utf-8') as f:
                return json.load(f)
        except ValueError as e:
            errors.append('data/%s is not valid JSON: %s' % (name, e))
            return None

    pdoc = load('people.json')
    sdoc = load('sources.json')
    has_map = bool(cfg['_pages'].get('map'))
    ldoc = load('places.json', required=has_map)
    if pdoc is None or sdoc is None:
        return {'errors': errors, 'warnings': warnings}

    # shape
    meta = pdoc.get('meta') or {}
    if meta.get('schemaVersion') is None:
        warnings.append('people.json meta has no schemaVersion; read as version 0. Run build/migrate.py to bring it to version 1.')
        pdoc = dict(pdoc, meta=dict(meta, schemaVersion=1))
    for doc, d, label in ((pdoc, 'peopleFile', 'people.json'), (sdoc, 'sourcesFile', 'sources.json')) + (((ldoc, 'placesFile', 'places.json'),) if ldoc else ()):
        c = check_file(doc, d, label)
        errors += c.errors
        warnings += c.warnings

    people = pdoc.get('people') or []
    by = {}
    for p in people:
        if not isinstance(p, dict) or 'id' not in p: continue
        if p['id'] in by: errors.append('people.json: the id %s is used twice' % p['id'])
        by[p['id']] = p
    sources = {s.get('id') for s in sdoc.get('sources') or [] if isinstance(s, dict)}
    if len(sources) != len(sdoc.get('sources') or []): errors.append('sources.json: an id is used twice, or a source has no id')
    places = {p.get('id') for p in (ldoc or {}).get('places') or [] if isinstance(p, dict)}

    # links between people
    for pid, p in by.items():
        for k in ('parents', 'children'):
            for r in p.get(k) or []:
                o = idof(r)
                if o not in by: errors.append('%s.%s: no one with the id %s' % (pid, k, o))
                elif k == 'parents' and pid not in [idof(x) for x in by[o].get('children') or []]:
                    warnings.append('%s lists %s as a parent, but %s does not list %s as a child' % (pid, o, o, pid))
                elif k == 'children' and pid not in [idof(x) for x in by[o].get('parents') or []]:
                    warnings.append('%s lists %s as a child, but %s does not list %s as a parent' % (pid, o, o, pid))
        for s in p.get('spouses') or []:
            o = idof(s)
            if o not in by: errors.append('%s.spouses: no one with the id %s' % (pid, o))
            elif pid not in [idof(x) for x in by[o].get('spouses') or []]:
                warnings.append('%s lists %s as a partner, but not the other way round' % (pid, o))
        for k in ('layoutJoin', 'uncertainBeside'):
            if p.get(k) and p[k] not in by: errors.append('%s.%s: no one with the id %s' % (pid, k, p[k]))
        if isinstance(p.get('generation'), int):
            for r in p.get('parents') or []:
                q = by.get(idof(r))
                if q and isinstance(q.get('generation'), int) and q['generation'] >= p['generation']:
                    warnings.append('%s is in generation %d but their parent %s is in generation %d' % (pid, p['generation'], q['id'], q['generation']))

    # sources and places cited, and files on disk
    def walk(o, path, pid):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == 'sourceIds':
                    for s in v or []:
                        if s not in sources: warnings.append('%s: cites %s, which is not in sources.json' % (path, s))
                elif k in ('sourceId',) and v and v not in sources:
                    warnings.append('%s: cites %s, which is not in sources.json' % (path, v))
                elif k in ('placeId', 'fromPlaceId', 'toPlaceId') and v and ldoc is not None and v not in places:
                    if places: warnings.append('%s: place %s is not in places.json' % (path, v))
                    else: unplaced.setdefault(v, []).append(path)   # a map with no places yet: one warning below
                else:
                    walk(v, path + '.' + k, pid)
        elif isinstance(o, list):
            for i, v in enumerate(o): walk(v, '%s[%d]' % (path, i), pid)
    unplaced = {}
    for pid, p in by.items():
        walk(p, pid, pid)
        for fn in re.findall(r'\[\^([a-z0-9-]+)\]', p.get('story') or ''):
            if fn not in sources: warnings.append('%s.story: footnote [^%s] is not in sources.json' % (pid, fn))
        for k in ('photo', 'portrait'):
            if p.get(k) and not re.match(r'^(https?:)?//', p[k]) and not os.path.exists(os.path.join(site, p[k])):
                warnings.append('%s.%s: %s is not in the site' % (pid, k, p[k]))
        for i, m in enumerate(p.get('media') or []):
            for k in ('file', 'thumb'):
                f = m.get(k)
                if f and not re.match(r'^(https?:)?//', f) and not os.path.exists(os.path.join(site, f)):
                    warnings.append('%s.media[%d].%s: %s is not in the site' % (pid, i, k, f))
    if unplaced:
        n = sum(len(v) for v in unplaced.values())
        warnings.append('places.json has no places yet, but %d fact%s name%s a place (%s); the map cannot show %s until places.json has %s'
                        % (n, '' if n == 1 else 's', 's' if n == 1 else '', ', '.join(sorted(unplaced)), 'it' if n == 1 else 'them', 'it' if len(unplaced) == 1 else 'them'))
    if ldoc:
        for pl in ldoc.get('places') or []:
            for e in pl.get('events') or []:
                for o in e.get('personIds') or []:
                    if o not in by: errors.append('places.json %s: event %s names %s, who is not in people.json' % (pl.get('id'), e.get('id'), o))
    e2, w2 = check_settings_refs(site, cfg, by)
    return {'errors': errors + e2, 'warnings': warnings + w2}


def local_page(href):
    """The file a link points at on this site, or None for a link elsewhere or to a place on the same page."""
    if not href or re.match(r'^([a-z][a-z0-9+.-]*:|//|#)', href, re.I): return None
    return href.split('#')[0].split('?')[0] or None


def check_settings_refs(site, cfg, by):
    """The settings against the data and the site's files: every person the settings name exists, and every page
    the navigation bar links to will be there. A wrong id here does not fail loudly in the browser (the tree just
    has no sides, Stuart no anchors), so it stops the build instead."""
    errors, warnings = [], []
    made = {v for k, v in cfg['_pages'].items() if k != 'home' and v}
    off = {PAGE: k for k, PAGE in (('tree', 'family-tree.html'), ('map', 'map.html'), ('ask', 'ask.html')) if not cfg['_pages'].get(k)}

    def exists(f):
        return f in made or os.path.exists(os.path.join(site, f))

    for i, it in enumerate(cfg.get('nav') or []):
        f = local_page((it or {}).get('href'))
        if f and not exists(f):
            if f in off: errors.append('nav[%d] links to %s, but pages.%s is off' % (i, f, off[f]))
            else: errors.append('nav[%d] links to %s, which the site does not have' % (i, f))
    if not os.path.exists(os.path.join(site, cfg['_pages']['home'])):
        errors.append('pages.home is %s, which the site does not have' % cfg['_pages']['home'])

    def person(pid, where):
        if pid and pid not in by: errors.append('%s: no one with the id %s in people.json' % (where, pid))

    tree, mp, st = cfg.get('tree') or {}, cfg.get('map') or {}, cfg.get('stuart') or {}
    sides = tree.get('sides') or {}
    person(sides.get('left'), 'tree.sides.left')
    person(sides.get('right'), 'tree.sides.right')
    person(tree.get('rootPersonId'), 'tree.rootPersonId')
    person(tree.get('kinAnchor'), 'tree.kinAnchor')
    for k, v in (tree.get('suspectedRelatives') or {}).items():
        person(k, 'tree.suspectedRelatives')
        person(v, 'tree.suspectedRelatives.%s' % k)
    for i, a in enumerate(st.get('anchors') or []):
        person(a.get('id'), 'stuart.anchors[%d]' % i)
    for i, a in enumerate(mp.get('kinAnchors') or []):
        person(a.get('id'), 'map.kinAnchors[%d]' % i)
    for i, fam in enumerate(mp.get('families') or []):
        for r in fam.get('roots') or []: person(r, 'map.families[%d].roots' % i)
    for i, b in enumerate(mp.get('branches') or []):
        for r in b.get('people') or []: person(r, 'map.branches[%d].people' % i)

    # pages the settings mention: a missing one only makes Stuart or the map a little less useful
    named = [('stuart.pages', p) for p in st.get('pages') or []] + [('stuart.generalPages', p) for p in st.get('generalPages') or []]
    if (st.get('stories') or {}).get('page'): named.append(('stuart.stories.page', st['stories']['page']))
    for i, b in enumerate(mp.get('branches') or []):
        named += [('map.branches[%d].pages' % i, p) for p in b.get('pages') or []]
    named += [('widget.exclude', p) for p in (cfg.get('widget') or {}).get('exclude') or []]
    named += [('widget.pages', p) for p in ((cfg.get('widget') or {}).get('pages') or {})]
    named += [('process.exclude', p) for p in (cfg.get('process') or {}).get('exclude') or []]
    for where, f in named:
        f2 = local_page(f)
        if f2 and not exists(f2): warnings.append('%s: %s is not in the site' % (where, f))
    return errors, warnings


def check_config(cfg):
    errors, warnings = [], []
    root = schema('site-config.schema.json')
    c = Checker(root)
    c.check(cfg['_raw'], root, 'site.config.json')
    return {'errors': c.errors, 'warnings': c.warnings + warnings}


def main(argv=None):
    sys.path.insert(0, HERE)
    import sitecfg
    ap = argparse.ArgumentParser(description="Check a site's data and settings.")
    ap.add_argument('--site', default='.')
    ap.add_argument('--quiet', action='store_true', help='print errors only')
    args = ap.parse_args(argv)
    cfg = sitecfg.load(os.path.abspath(args.site))
    a = check_config(cfg)
    b = validate_site(os.path.abspath(args.site), cfg)
    errs, warns = a['errors'] + b['errors'], a['warnings'] + b['warnings']
    if not args.quiet:
        for w in warns: print('warning:', w)
    for e in errs: print('error:', e)
    print('%d error%s, %d warning%s' % (len(errs), '' if len(errs) == 1 else 's', len(warns), '' if len(warns) == 1 else 's'))
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
