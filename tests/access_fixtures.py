#!/usr/bin/env python3
"""Made-up sites for the private access and visitor tests, built from the sample family (sample/).

    python3 tests/access_fixtures.py DEST [--no-access] [--no-visitor] [--no-extras] [--living-photos] [--scope all]

Makes a copy of sample/ in DEST with access and visitor turned on and a few extra made-up living people, so the
tests have names that are easy to confuse. Nothing here is a real person.

The extras:
  daniel-hartley-2   a second "Daniel Hartley", Susan's son, to tell apart from Peter and Janet's Daniel
  zoe-hartley        "Zoë Hartley", Peter and Janet's daughter, with a photo (living photos are held back by default)
  kate-hartley       gets two other names: "Katie Hartley" and the maiden name "Kate Marsh"
"""
import argparse, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PASSWORD = 'correct horse battery staple'      # made up; the tests pass it to the gate as the SITE_PASSWORD secret


def make(dest, access=True, visitor=True, extras=True, living_photos=False, scope=None):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(os.path.join(ROOT, 'sample'), dest)
    cfg_path = os.path.join(dest, 'site.config.json')
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)
    if access:
        cfg['access'] = {'enabled': True, 'project': 'sample-private', 'hint': 'Ask a family member for it.'}
    if visitor:
        cfg['visitor'] = {'enabled': True}
        if living_photos: cfg['visitor']['livingPhotos'] = True
        if scope: cfg['visitor']['scope'] = scope
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)
    if extras:
        p_path = os.path.join(dest, 'data', 'people.json')
        with open(p_path, encoding='utf-8') as f:
            doc = json.load(f)
        by = {p['id']: p for p in doc['people']}
        shutil.copy(os.path.join(dest, 'images', 'people', 'thomas-hartley.png'), os.path.join(dest, 'images', 'people', 'zoe-hartley.png'))

        def person(base, **kw):
            p = json.loads(json.dumps(by[base]))
            for k in ('timeline', 'facts', 'media', 'residences', 'occupations', 'openQuestions', 'relatedPages', 'birth', 'order'):
                p.pop(k, None)
            p.update(kw)
            for k in ('timeline', 'facts', 'media', 'residences', 'occupations', 'openQuestions', 'relatedPages'):
                p[k] = []
            return p
        doc['people'].append(person('kate-hartley', id='daniel-hartley-2', displayName='Daniel Hartley', givenNames='Daniel', sex='M', parents=['susan-hartley'],
                                    disambiguator="Susan's son, lives in Leeds", summary="Susan's son.", story="Daniel is Susan's son.[^family-testimony]",
                                    birth={'date': '1991', 'display': '1991', 'place': 'Leeds, Yorkshire', 'placeId': 'leeds', 'confidence': 'family tradition', 'sourceIds': ['family-testimony']}))
        doc['people'].append(person('daniel-hartley', id='zoe-hartley', displayName='Zoë Hartley', givenNames='Zoë', sex='F', parents=['peter-hartley', 'janet-hartley'],
                                    disambiguator="Peter and Janet's daughter", summary="Peter and Janet's daughter.", story="Zoë is Peter and Janet's daughter.[^family-testimony]",
                                    photo='images/people/zoe-hartley.png', isDirectLine=False))
        by['susan-hartley']['children'].append('daniel-hartley-2')
        by['peter-hartley']['children'].append('zoe-hartley')
        by['janet-hartley']['children'].append('zoe-hartley')
        by['kate-hartley']['nameVariants'] = [
            {'name': 'Katie Hartley', 'note': 'what the family call her', 'sourceIds': ['family-testimony']},
            {'name': 'Kate Marsh', 'note': 'maiden name', 'sourceIds': ['family-testimony']}]
        with open(p_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('dest')
    ap.add_argument('--no-access', action='store_true')
    ap.add_argument('--no-visitor', action='store_true')
    ap.add_argument('--no-extras', action='store_true')
    ap.add_argument('--living-photos', action='store_true')
    ap.add_argument('--scope')
    a = ap.parse_args(argv)
    make(a.dest, not a.no_access, not a.no_visitor, not a.no_extras, a.living_photos, a.scope)
    print(a.dest)
    return 0


if __name__ == '__main__':
    sys.exit(main())
