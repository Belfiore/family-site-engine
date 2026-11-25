#!/usr/bin/env python3
"""Bring a site's data up to the current schema version.

    python3 build/migrate.py --site path/to/site            show what would change
    python3 build/migrate.py --site path/to/site --write    change the files

Version 0 to 1 (the data the sites had before the engine):
  * people.json meta gets "schemaVersion": 1;
  * settings about how the tree looks move from people.json meta into "tree" in site.config.json:
    familyLabel, rootPersonId, directLineLabel, generations, rootOrder, kinAnchor, kinLabel, regions,
    regionKicker, initialView, sides (a value already in site.config.json wins);
  * a person's duplicate "living" flag is folded into "isLiving";
  * places.json "inEngland" becomes "inHomeRegion".
Nothing else is touched, and nothing is deleted except the duplicates named above.

Each later version adds a step here, so a site on any older version can be brought up to date in one run.
"""
import argparse, json, os, sys

CURRENT = 1
MOVE_TO_TREE = ['familyLabel', 'rootPersonId', 'directLineLabel', 'generations', 'rootOrder', 'kinAnchor', 'kinLabel',
                'regions', 'regionKicker', 'initialView', 'sides']


def v0_to_v1(people, places, config, notes):
    meta = people.setdefault('meta', {})
    tree = config.setdefault('tree', {}) if config is not None else None
    moved = []
    for k in MOVE_TO_TREE:
        if k in meta:
            if tree is not None:
                if k not in tree: tree[k] = meta[k]
                del meta[k]
                moved.append(k)
    if moved: notes.append('moved from people.json meta to site.config.json tree: ' + ', '.join(moved))
    folded = 0
    for p in people.get('people') or []:
        if 'living' in p:
            if p['living'] and not p.get('isLiving'):
                p['isLiving'] = True
                notes.append('%s: "living" was true but "isLiving" was not; isLiving is now true' % p['id'])
            del p['living']
            folded += 1
    if folded: notes.append('folded the duplicate "living" flag into "isLiving" on %d people' % folded)
    if places:
        n = 0
        for pl in places.get('places') or []:
            if 'inEngland' in pl:
                # renamed where it stands, so the order of the fields in the file is kept; an existing inHomeRegion wins
                keep = pl.get('inHomeRegion', pl['inEngland'])
                items = [('inHomeRegion', keep) if k == 'inEngland' else (k, val) for k, val in pl.items() if k != 'inHomeRegion']
                pl.clear(); pl.update(items)
                n += 1
        if n: notes.append('places.json: "inEngland" is now "inHomeRegion" on %d places' % n)
    # keep meta keys in a stable order: schemaVersion first
    people['meta'] = dict([('schemaVersion', 1)] + [(k, v) for k, v in meta.items() if k != 'schemaVersion'])
    notes.append('people.json is now schema version 1')


STEPS = {0: v0_to_v1}


def migrate(site, write=False):
    data = os.path.join(site, 'data')
    styles = {}
    def load(p):
        if not os.path.exists(p): return None
        with open(p, encoding='utf-8') as f: text = f.read()
        doc = json.loads(text)
        # keep each file's own layout (indent and final newline) so a review shows only what changed
        indent = next((i for i in (1, 2, 4) if json.dumps(doc, ensure_ascii=False, indent=i) == text.rstrip('\n')), 2)
        styles[p] = (indent, text.endswith('\n'))
        return doc
    people = load(os.path.join(data, 'people.json'))
    places = load(os.path.join(data, 'places.json'))
    cfg_path = os.path.join(site, 'site.config.json')
    config = load(cfg_path)
    if people is None: raise SystemExit('no data/people.json in %s' % site)
    version = (people.get('meta') or {}).get('schemaVersion', 0)
    notes = []
    while version < CURRENT:
        STEPS[version](people, places, config, notes)
        version += 1
    if not notes:
        print('already at schema version %d; nothing to do' % CURRENT)
        return 0
    for n in notes: print('-', n)
    if write:
        def dump(p, doc):
            indent, newline = styles.get(p, (2, True))
            with open(p, 'w', encoding='utf-8') as f:
                f.write(json.dumps(doc, ensure_ascii=False, indent=indent) + ('\n' if newline else ''))
        dump(os.path.join(data, 'people.json'), people)
        if places is not None: dump(os.path.join(data, 'places.json'), places)
        if config is not None: dump(cfg_path, config)
        print('written')
    else:
        print('(nothing written: add --write to change the files)')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Bring a site\'s data up to the current schema version.')
    ap.add_argument('--site', default='.')
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    sys.exit(migrate(os.path.abspath(a.site), a.write))
