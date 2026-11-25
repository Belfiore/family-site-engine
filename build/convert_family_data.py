#!/usr/bin/env python3
"""Convert an older site's family-data.js (const FAMILY_DATA = {...}) into the engine's data format.

    python3 build/convert_family_data.py --input path/to/family-data.js --out path/to/site/data

Some of the first family sites kept their tree in one JavaScript file: people with firstName, lastName,
birthYear, birthDate, birthPlace, deathYear, notes and a free-text source, and a separate list of
relationships (parent_child and spouse). This writes the same family as data/people.json and
data/sources.json (schema version 1). The file is read as data; nothing in it is run.

What it does, so the result can be checked:
  * ids: lower case, underscores become hyphens (giuseppe_circelli becomes giuseppe-circelli);
  * names: displayName is the first and last name; "aka" becomes a name variant ("nee Just" a maiden name);
  * dates: the written date (birthDate) is the display and, where it can be read, the date; otherwise the
    year, with "about" when the year was marked approximate;
  * confidence: verified becomes confirmed; high, medium and estimated become probable; low and anything
    else unverified (the engine's scale has no "high": confirmed means a record says it);
  * generations: shifted so the oldest row is 0;
  * notes become the story, and the first sentence the summary; each distinct "source" text becomes an
    entry in sources.json, cited by the birth, the death and the story;
  * the direct line is everyone the root person descends from.
It never invents a fact. Placeholders in the text ("[PLACEHOLDER: ...]") are kept as they are and counted.
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsdata  # noqa: E402

CONFIDENCE = {'verified': 'confirmed', 'confirmed': 'confirmed', 'high': 'probable', 'medium': 'probable',
              'estimated': 'probable', 'probable': 'probable', 'low': 'unverified'}
MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
                                      'october', 'november', 'december'], 1)}


def pid(x):
    return re.sub(r'[^a-z0-9-]+', '-', str(x).strip().lower().replace('_', '-')).strip('-')


def slug(text, n=60):
    s = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return s[:n].rstrip('-') or 'source'


def iso(text, year):
    """2 March 1912 -> 1912-03-02; March 1912 -> 1912-03; else the year, if any."""
    t = str(text or '').strip()
    m = re.search(r'\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b', t)
    if m and m.group(2).lower() in MONTHS:
        return '%s-%02d-%02d' % (m.group(3), MONTHS[m.group(2).lower()], int(m.group(1)))
    m = re.search(r'\b([A-Za-z]+)\s+(\d{4})\b', t)
    if m and m.group(1).lower() in MONTHS:
        return '%s-%02d' % (m.group(2), MONTHS[m.group(1).lower()])
    m = re.fullmatch(r'(\d{4})-(\d{2})(?:-(\d{2}))?', t)
    if m: return t
    return str(year) if isinstance(year, int) else ''


def life_event(written, year, approx, place, conf, source_ids):
    if not written and year is None and not place: return None
    display = written or ((('about ' if approx else '') + str(year)) if year is not None else '')
    ev = {'date': iso(written, year), 'display': display or None, 'place': place or None, 'placeId': None,
          'confidence': conf, 'sourceIds': list(source_ids)}
    if approx: ev['dateQualifier'] = 'about'
    return ev


def source_type(text):
    t = text.lower()
    for words, kind in ((('testimony', 'family says', 'family memory', 'told by'), 'family testimony'),
                        (('census',), 'census'), (('passenger', 'manifest', 'ship'), 'passenger list'),
                        (('baptism', 'parish'), 'parish register'), (('birth record', 'marriage record', 'death record', 'atto', 'atti', 'act no'), 'civil registration'),
                        (('ahnentafel', 'pedigree'), 'family tree'), (('photo',), 'photograph'), (('newspaper', 'obituary'), 'newspaper'),
                        (('draft card', 'military', 'army'), 'military record'), (('findagrave', 'grave', 'cemetery'), 'grave record')):
        if any(w in t for w in words): return kind
    return 'document'


def convert(data):
    people_in = data.get('people') or []
    rels = data.get('relationships') or []
    notes = []
    ids = {p['id']: pid(p['id']) for p in people_in}
    if len(set(ids.values())) != len(ids): raise SystemExit('two people end up with the same id after conversion')
    gens = [p.get('generation') for p in people_in if isinstance(p.get('generation'), int)]
    shift = -min(gens) if gens and min(gens) < 0 else 0
    if shift: notes.append('generations shifted by %d so the oldest row is 0' % shift)

    sources, by_text = [], {}
    def source_for(text):
        text = str(text or '').strip()
        if not text: return []
        if text not in by_text:
            base, n = slug(text), 2
            sid = base
            while any(s['id'] == sid for s in sources): sid = '%s-%d' % (base, n); n += 1
            by_text[text] = sid
            sources.append({'id': sid, 'title': text, 'type': source_type(text)})
        return [by_text[text]]

    out, by = [], {}
    conf_seen = {}
    placeholders = 0
    for p in people_in:
        i = ids[p['id']]
        raw = str(p.get('confidence') or '').lower()
        conf = CONFIDENCE.get(raw, 'unverified')
        conf_seen[raw or '(none)'] = conf
        src = source_for(p.get('source'))
        first, last = (p.get('firstName') or '').strip(), (p.get('lastName') or '').strip()
        variants = []
        aka = (p.get('aka') or '').strip()
        if aka:
            m = re.match(r'^n[eé]e\s+(.+)$', aka, re.I)
            if m: variants.append({'name': (first + ' ' + m.group(1)).strip(), 'note': 'maiden name', 'sourceIds': list(src)})
            else: variants.append({'name': aka, 'note': 'also known as', 'sourceIds': list(src)})
        story = (p.get('notes') or '').strip()
        summary = re.split(r'(?<=[.!?])\s+', story)[0] if story else None
        if summary and len(summary) > 200: summary = summary[:197].rsplit(' ', 1)[0] + '...'
        sex = str(p.get('sex') or p.get('gender') or '').upper()[:1]
        q = {
            'id': i,
            'displayName': p.get('name') or (first + ' ' + last).strip() or i,
            'givenNames': first or None,
            'surname': last or None,
            'disambiguator': None,
            'sex': sex if sex in ('M', 'F') else 'U',
            'generation': (p['generation'] + shift) if isinstance(p.get('generation'), int) else None,
            'isLiving': bool(p.get('isLiving')),
            'isDirectLine': False,
            'confidence': conf,
            'nameVariants': variants,
            'parents': [], 'children': [], 'spouses': [],
            'birth': life_event(p.get('birthDate'), p.get('birthYear'), p.get('birthYearApprox'), p.get('birthPlace'), conf, src),
            'death': life_event(p.get('deathDate'), p.get('deathYear'), p.get('deathYearApprox'), p.get('deathPlace'), conf, src),
            'cardPlace': p.get('primaryLocation') or None,
            'summary': summary,
            'story': (story + ('[^%s]' % src[0] if src else '')) if story else None,
            'residences': [], 'occupations': [], 'timeline': [], 'facts': [], 'media': [], 'openQuestions': [], 'relatedPages': [],
            'photo': p.get('photo') or None,
        }
        if q['generation'] is None: del q['generation']
        placeholders += len(re.findall(r'\[PLACEHOLDER', json.dumps(q)))
        out.append(q); by[i] = q

    for r in rels:
        a, b = ids.get(r.get('fromPersonId')), ids.get(r.get('toPersonId'))
        if not a or not b:
            notes.append('a %s relationship names someone who is not in the file (%s, %s); left out' % (r.get('type'), r.get('fromPersonId'), r.get('toPersonId')))
            continue
        if r.get('type') == 'parent_child':
            if b not in by[a]['children']: by[a]['children'].append(b)
            if a not in by[b]['parents']: by[b]['parents'].append(a)
        elif r.get('type') == 'spouse':
            year = r.get('startYear')
            for x, y in ((a, b), (b, a)):
                if any(s['id'] == y for s in by[x]['spouses']): continue
                s = {'id': y, 'order': len(by[x]['spouses']) + 1, 'marriageDate': str(year) if year else None,
                     'marriageDisplay': str(year) if year else None, 'place': None, 'placeId': None, 'confidence': by[x]['confidence'], 'sourceIds': []}
                if r.get('endYear'): s['note'] = 'ended %s' % r['endYear']
                by[x]['spouses'].append(s)
        else:
            notes.append('a relationship of type %r was left out' % r.get('type'))

    root = ids.get(data.get('rootPersonId'))
    if root:
        q, seen = [root], set()
        while q:
            x = q.pop()
            if x in seen: continue
            seen.add(x); by[x]['isDirectLine'] = True
            q.extend(by[x]['parents'])
    notes.append('confidence: ' + ', '.join('%s became %s' % (k, v) for k, v in sorted(conf_seen.items())))
    if placeholders: notes.append('%d placeholder%s kept as written ("[PLACEHOLDER: ...]")' % (placeholders, '' if placeholders == 1 else 's'))
    people = {'meta': {'schemaVersion': 1, 'note': 'Converted from family-data.js by the family site engine. Check the confidence grades and the summaries.'},
              'people': out}
    return people, {'sources': sources}, root, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description='Convert family-data.js into the engine\'s data format.')
    ap.add_argument('--input', required=True, help='the family-data.js file')
    ap.add_argument('--out', required=True, help='the data folder to write people.json and sources.json into')
    ap.add_argument('--name', default=None, help='the constant to read (default: the first one in the file)')
    ap.add_argument('--force', action='store_true', help='overwrite people.json and sources.json if they exist')
    a = ap.parse_args(argv)
    with open(a.input, encoding='utf-8') as f:
        name, data = jsdata.read_assignment(f.read(), a.name)
    people, sources, root, notes = convert(data)
    os.makedirs(a.out, exist_ok=True)
    for fn, doc in (('people.json', people), ('sources.json', sources)):
        p = os.path.join(a.out, fn)
        if os.path.exists(p) and not a.force: raise SystemExit('%s exists; add --force to overwrite it' % p)
        with open(p, 'w', encoding='utf-8') as f: f.write(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
    print('read %s: %d people, %d sources' % (name, len(people['people']), len(sources['sources'])))
    for n in notes: print('-', n)
    if root: print('- put "rootPersonId": "%s" in "tree" in site.config.json' % root)
    return 0


if __name__ == '__main__':
    sys.exit(main())
