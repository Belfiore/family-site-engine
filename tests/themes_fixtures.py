#!/usr/bin/env python3
"""A made-up site for the heritage style tests, built from the sample family (sample/).

    python3 tests/themes_fixtures.py DEST [--style ID] [--admin] [--language]

Every page the engine makes is on (tree, map, Ask Stuart, Stories, Records and Research, the Discovery Timeline), so a
style can be checked on all of them. --style applies one; --admin turns the settings page on (which carries every
style so they can be tried); --language turns on English and German. Nothing here is a real person.
"""
import argparse, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STORY = """---
title: The Crossing
summary: How Arthur Hartley came over.
people: [arthur-hartley]
---
Arthur sailed in the spring. This story is made up, like the family it is about.
"""


def make(dest, style=None, admin=False, language=False, options=None):
    if os.path.exists(dest): shutil.rmtree(dest)
    shutil.copytree(os.path.join(ROOT, 'sample'), dest)
    path = os.path.join(dest, 'site.config.json')
    cfg = json.load(open(path, encoding='utf-8'))
    cfg['pages'].update({'records': True, 'discoveries': True, 'stories': True})
    if style: cfg['style'] = {'heritage': style, **({'options': options} if options else {})}
    if admin: cfg['admin'] = {'enabled': True, 'repo': 'example/sample-family'}
    if language: cfg['language'] = {'default': 'en', 'available': ['en', 'de']}
    json.dump(cfg, open(path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    os.makedirs(os.path.join(dest, 'content', 'stories'), exist_ok=True)
    open(os.path.join(dest, 'content', 'stories', 'the-crossing.md'), 'w', encoding='utf-8').write(STORY)
    return dest


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('dest'); ap.add_argument('--style'); ap.add_argument('--admin', action='store_true'); ap.add_argument('--language', action='store_true')
    a = ap.parse_args()
    make(a.dest, a.style, a.admin, a.language)
