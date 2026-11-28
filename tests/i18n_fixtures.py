#!/usr/bin/env python3
"""A made-up two-language site for the language checks, built from the sample family (sample/).

    python3 tests/i18n_fixtures.py DEST [--default de] [--only de] [--visitor]

Makes a copy of sample/ in DEST with language settings and a few German words:
  thomas-hartley     summary_de and story_de (shown when German is chosen)
  mary-ann-briggs    disambiguator_de only, so her story stays as written
  meta               directLineLabel_de
  the Moreaus page   label_de in the navigation bar
Nothing here is a real person.
"""
import argparse, json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STORY_DE = 'Thomas Hartley handelte vierzig Jahre lang in Leeds mit Wolle. Dieser Text steht nur in der deutschen Fassung.'


def make(dest, default='en', only=None, visitor=False):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(os.path.join(ROOT, 'sample'), dest)
    cfg_path = os.path.join(dest, 'site.config.json')
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)
    cfg['language'] = {'default': only or default, 'available': [only] if only else ['en', 'de']}
    for item in cfg['nav']:
        if item.get('href') == 'moreau.html':
            item['label_de'] = 'Die Moreaus'
    if visitor:
        cfg['visitor'] = {'enabled': True}
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)
    p_path = os.path.join(dest, 'data', 'people.json')
    with open(p_path, encoding='utf-8') as f:
        doc = json.load(f)
    by = {p['id']: p for p in doc['people']}
    doc['meta']['directLineLabel_de'] = 'Daniels direkte Linie'
    by['thomas-hartley']['summary_de'] = 'Ein Wollhändler in Leeds.'
    by['thomas-hartley']['story_de'] = STORY_DE
    by['mary-ann-briggs']['disambiguator_de'] = 'geborene Briggs, die Frau von Thomas'
    with open(p_path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('dest')
    ap.add_argument('--default', default='en')
    ap.add_argument('--only')
    ap.add_argument('--visitor', action='store_true')
    a = ap.parse_args(argv)
    make(a.dest, a.default, a.only, a.visitor)
    print(a.dest)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
