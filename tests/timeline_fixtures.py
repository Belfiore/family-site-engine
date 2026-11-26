"""Sample data for the Discovery Timeline's tests: successive publications of one made-up family.

Everything here is invented. It starts from the engine's own sample site (the Hartley and Moreau families, a made-up
family) and edits it, one publication at a time, the way a researcher would: a census turns up, a date is corrected,
a photograph is added, a living person is added, someone's privacy status changes, a notes file is written.

    python3 tests/timeline_fixtures.py OUTDIR      writes OUTDIR/v1 ... OUTDIR/v7, each a complete site folder

Each version is a full site with the timeline on. VERSIONS says when each was "published" and what changed.
The tests (tests/test_discoveries.py, tests/check-timeline.js) build them in order, each against the one before.
Standard library only: the pictures are small generated PNGs.
"""
import copy, json, os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), 'sample')

# (name, the moment it was published, what changed)
VERSIONS = [
    ('v1', '2026-11-02T09:00:00Z', 'The sample as it stands, with the timeline switched on: the baseline. Nothing is a find.'),
    ('v2', '2026-11-09T10:00:00Z', 'A census turns up: a new source, a new residence and occupation, a new daughter, a corrected birth date.'),
    ('v3', '2026-11-16T10:00:00Z', 'A photograph, a renamed picture file, a higher confidence, a new place and a person born there.'),
    ('v4', '2026-11-20T10:00:00Z', 'A living person is added, a living person is marked deceased, a public person is marked living, a claim is removed.'),
    ('v5', '2026-11-23T10:00:00Z', 'A researcher adds her own notes: on a record, and in data/discoveries.json.'),
    ('v6', '2026-11-26T09:00:00Z', 'A day at the archive, in the morning: a household from a new census and four other records.'),
    ('v7', '2026-11-26T15:00:00Z', 'The same day, in the afternoon: two more records and a photograph. Eight finds on one day.'),
]


# ------------------------------------------------------------------ pictures
def png(path, seed, w=160, h=120):
    """A small, plain picture, different for each seed. Only the bytes matter to the tests, so it is a gradient."""
    rows = []
    r0, g0, b0 = (seed * 53) % 200 + 30, (seed * 97) % 200 + 30, (seed * 29) % 200 + 30
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            k = (x * 255 // w + y * 255 // h) // 2
            row += bytes(((r0 + k) % 256, (g0 + k // 2) % 256, (b0 + 255 - k) % 256))
        rows.append(bytes(row))
    raw = zlib.compress(b''.join(rows), 9)

    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', raw) + chunk(b'IEND', b''))


# ------------------------------------------------------------------ the data
class Site:
    def __init__(self):
        with open(os.path.join(SAMPLE, 'data', 'people.json'), encoding='utf-8') as f: self.people = json.load(f)
        with open(os.path.join(SAMPLE, 'data', 'sources.json'), encoding='utf-8') as f: self.sources = json.load(f)
        with open(os.path.join(SAMPLE, 'data', 'places.json'), encoding='utf-8') as f: self.places = json.load(f)
        with open(os.path.join(SAMPLE, 'site.config.json'), encoding='utf-8') as f: self.config = json.load(f)
        self.config['timeline'] = {'enabled': True}
        self.config['site']['description'] += ' (Test data for the Discovery Timeline.)'
        self.discoveries = None
        self.images = {}          # path in the site -> seed of a generated picture
        self.moved = {}           # new path -> old path of a picture from the sample, moved without changing it
        self.removed_images = set()

    def p(self, pid):
        return next(x for x in self.people['people'] if x['id'] == pid)

    def add_person(self, pid, name, sex, parents=(), birth=None, living=False, generation=3, **extra):
        given, _, surname = name.rpartition(' ')
        person = {'id': pid, 'displayName': name, 'givenNames': given, 'surname': surname, 'sex': sex, 'generation': generation, 'isLiving': living,
                  'isDirectLine': False, 'confidence': 'confirmed', 'parents': list(parents), 'children': [], 'spouses': [], 'nameVariants': [],
                  'residences': [], 'occupations': [], 'facts': [], 'timeline': [], 'media': [], 'openQuestions': [], 'relatedPages': [],
                  'disambiguator': '', 'summary': '', 'story': '', 'cardPlace': None, 'photo': None}
        if birth: person['birth'] = birth
        person.update(extra)
        self.people['people'].append(person)
        for par in parents:
            if pid not in self.p(par)['children']: self.p(par)['children'].append(pid)
        return person

    def add_source(self, sid, title, kind='census', date=''):
        self.sources['sources'].append({'id': sid, 'title': title, 'type': kind, 'repository': 'Sample archive', 'date': date})

    def add_photo(self, pid, path, seed, caption, kind='photo'):
        self.images[path] = seed
        self.p(pid)['media'].append({'id': 'm-' + os.path.basename(path).split('.')[0], 'type': kind, 'file': path, 'thumb': path,
                                     'caption': caption, 'alt': caption, 'sourceId': 'family-photographs'})

    def write(self, dest):
        if os.path.exists(dest): shutil.rmtree(dest)
        shutil.copytree(SAMPLE, dest)
        for path, seed in self.images.items():
            png(os.path.join(dest, path), seed)
        for new, old in self.moved.items():
            shutil.copy2(os.path.join(SAMPLE, old), os.path.join(dest, new))
        for path in self.removed_images:
            f = os.path.join(dest, path)
            if os.path.exists(f): os.remove(f)
        d = os.path.join(dest, 'data')
        for name, doc in (('people', self.people), ('sources', self.sources), ('places', self.places)):
            with open(os.path.join(d, name + '.json'), 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
        if self.discoveries is not None:
            with open(os.path.join(d, 'discoveries.json'), 'w', encoding='utf-8') as f:
                json.dump(self.discoveries, f, ensure_ascii=False, indent=1)
        with open(os.path.join(dest, 'site.config.json'), 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=1)
        # the sample's README is not part of a site; leave the rest as the sample has it
        return dest


def place(site, pid, name, like='bradford', lat=53.72, lng=-1.86):
    pl = copy.deepcopy(next(x for x in site.places['places'] if x['id'] == like))
    pl.update({'id': pid, 'name': name, 'historicName': name, 'address': name, 'modernAddress': name, 'lat': lat, 'lng': lng, 'events': []})
    site.places['places'].append(pl)


def edit(site, n):
    """Change the site from version n-1 to version n."""
    if n == 1:
        return
    if n == 2:
        site.add_source('census-1891-leeds', '1891 census, Kirkgate, Leeds', date='1891')
        t = site.p('thomas-hartley')
        t['residences'].append({'place': 'Leeds', 'placeId': 'leeds', 'address': '3 Kirkgate, Leeds', 'years': '1891', 'confidence': 'confirmed',
                                'sourceIds': ['census-1891-leeds']})
        t['occupations'].append({'title': 'Wool broker', 'place': 'Leeds', 'placeId': 'leeds', 'years': '1891', 'confidence': 'confirmed',
                                 'sourceIds': ['census-1891-leeds']})
        site.add_person('hannah-hartley', 'Hannah Hartley', 'F', ['thomas-hartley', 'mary-ann-briggs'],
                        birth={'date': '1884', 'display': '1884', 'place': 'Leeds', 'placeId': 'leeds', 'confidence': 'confirmed',
                               'sourceIds': ['census-1891-leeds']})
        w = site.p('william-hartley')
        w['birth']['date'] = '1876-06-10'
        w['birth']['display'] = '10 June 1876'
    elif n == 3:
        site.add_photo('alice-turner', 'images/people/alice-turner.png', 71, 'Alice Hartley, about 1900')
        thomas = site.p('thomas-hartley')
        old = thomas['media'][0]['file']
        new = 'images/people/portrait-of-thomas.png'
        site.moved[new] = old           # the same picture under a new name: not a find
        thomas['media'][0]['file'] = thomas['media'][0]['thumb'] = new
        thomas['photo'] = new
        site.removed_images.add(old)
        site.p('jean-baptiste-moreau')['residences'].append({'place': 'Lyon', 'placeId': 'lyon', 'address': 'rue Mercière, Lyon', 'years': '1881',
                                                             'confidence': 'probable', 'sourceIds': ['family-testimony']})
        place(site, 'halifax', 'Halifax, Yorkshire', lat=53.7248, lng=-1.8658)
        place(site, 'ilkley', 'Ilkley, Yorkshire', lat=53.9246, lng=-1.8215)      # on the map, with nothing yet to say about it
        site.add_person('ruth-hartley', 'Ruth Hartley', 'F', ['james-hartley'],
                        birth={'date': '1905', 'display': '1905', 'place': 'Halifax, Yorkshire', 'placeId': 'halifax', 'confidence': 'probable',
                               'sourceIds': ['family-testimony']})
        site.add_photo('james-hartley', 'images/people/james-hartley.png', 33, 'James Hartley, about 1925')
    elif n == 4:
        site.add_person('lucy-hartley', 'Lucy Hartley', 'F', ['kate-hartley'], living=True, generation=5,
                        birth={'date': '2012', 'display': '2012', 'place': 'Leeds', 'placeId': 'leeds', 'confidence': 'confirmed', 'sourceIds': ['family-testimony']})
        site.add_photo('lucy-hartley', 'images/people/lucy-hartley.png', 11, 'Lucy Hartley at school')
        site.p('kate-hartley')['residences'].append({'place': 'Bradford', 'placeId': 'bradford', 'address': '8 Mill Lane, Bradford', 'years': '2020 to now',
                                                     'confidence': 'confirmed', 'sourceIds': ['family-testimony']})
        susan = site.p('susan-hartley')
        susan['isLiving'] = False
        susan['death'] = {'date': '2026-09-30', 'display': '30 September 2026', 'place': 'Leeds', 'placeId': 'leeds', 'confidence': 'confirmed',
                          'sourceIds': ['family-testimony']}
        site.p('james-hartley')['isLiving'] = True            # a public person is marked living: what was found about him goes with him
        site.p('thomas-hartley')['occupations'] = [o for o in site.p('thomas-hartley')['occupations'] if o['title'] != 'Wool broker']
        site.p('peter-hartley')['residences'].append({'place': 'Leeds', 'placeId': 'leeds', 'address': '5 Headingley Lane, Leeds', 'years': '1960',
                                                      'confidence': 'confirmed', 'sourceIds': ['family-testimony']})
    elif n == 5:
        h = site.p('henri-moreau')
        site.images['images/records/census-1891-soho.png'] = 90
        h['residences'].append({'place': 'Soho', 'placeId': 'soho', 'address': '22 Greek Street, Soho', 'years': '1891', 'confidence': 'probable',
                                'sourceIds': ['census-1881-soho'],
                                'discovery': {'found': '2026-11-18', 'headline': 'Henri Moreau was lodging at 22 Greek Street in Soho by 1891.',
                                              'foundBy': 'Sebastian', 'source': {'text': '1891 census, Soho (a made-up source)', 'url': 'https://example.org/census-1891'},
                                              'confidence': 'probable', 'image': 'images/records/census-1891-soho.png',
                                              'imageAlt': 'A census page with one line marked', 'changeNote': 'The household was thought to have left Soho in 1885.'}})
        site.discoveries = {'meta': {'note': 'Researcher notes for the Discovery Timeline (made-up).'}, 'discoveries': [
            {'id': 'hannah-note', 'covers': ['person:hannah-hartley'], 'headline': 'Hannah Hartley, a sister nobody had listed, was born in Leeds in 1884.',
             'foundBy': 'Stuart - Hartley', 'found': '2026-11-12', 'findType': 'person'},
            {'id': 'hartley-photo-album', 'personIds': ['mary-ann-briggs'], 'headline': 'Mary Ann Hartley appears in a family photograph album held by a cousin.',
             'findType': 'photo', 'foundBy': 'Sebastian', 'found': '2026-11-21', 'confidence': 'family tradition',
             'source': 'Family photograph album (a made-up source)'}]}
    elif n == 6:
        # a day at the archive: the Ogden household from one census, and six other records, each from a source of its own
        site.add_source('census-1911-halifax', '1911 census, Halifax', date='1911')
        site.images['images/records/census-1911-halifax.png'] = 120
        for pid, name, sex, yr, gen in [('walter-ogden', 'Walter Ogden', 'M', '1871', 2), ('agnes-ogden', 'Agnes Ogden', 'F', '1874', 2),
                                        ('frank-ogden', 'Frank Ogden', 'M', '1899', 3), ('dora-ogden', 'Dora Ogden', 'F', '1902', 3),
                                        ('nell-ogden', 'Nell Ogden', 'F', '1906', 3)]:
            parents = ['walter-ogden', 'agnes-ogden'] if gen == 3 else []
            site.add_person(pid, name, sex, parents, generation=gen,
                            birth={'date': yr, 'display': yr, 'place': 'Halifax, Yorkshire', 'placeId': 'halifax', 'confidence': 'confirmed',
                                   'sourceIds': ['census-1911-halifax']})
        marriage = {'order': 1, 'marriageDate': '1897', 'marriageDisplay': '1897', 'place': 'Halifax, Yorkshire', 'placeId': 'halifax',
                    'confidence': 'confirmed', 'sourceIds': ['census-1911-halifax']}
        site.p('walter-ogden')['spouses'].append(dict(marriage, id='agnes-ogden'))
        site.p('agnes-ogden')['spouses'].append(dict(marriage, id='walter-ogden'))
        records = [
            ('census-1901-bradford', '1901 census, Bradford', 'census', '1901', 'william-hartley', 'residences',
             {'place': 'Bradford', 'placeId': 'bradford', 'address': '2 Manor Row, Bradford', 'years': '1901', 'confidence': 'confirmed'}),
            ('directory-1895-leeds', 'Leeds trade directory, 1895', 'directory', '1895', 'thomas-hartley', 'facts',
             {'label': 'Trade directory', 'value': 'Listed as a wool broker in Leeds in 1895'}),
            ('probate-turner-1919', 'Probate calendar, 1919', 'probate', '1919', 'george-turner', 'facts',
             {'label': 'Probate', 'value': 'His will was proved at Wakefield in 1919'}),
            ('school-register-1912', 'Leeds Grammar School register, 1912', 'school', '1912', 'arthur-hartley', 'facts',
             {'label': 'School', 'value': 'Pupil at Leeds Grammar School in 1912'}),
        ]
        for sid, title, kind, date, pid, field, item in records:
            site.add_source(sid, title, kind, date)
            site.p(pid)[field].append(dict(item, sourceIds=[sid]))
    elif n == 7:
        site.add_photo('frank-ogden', 'images/people/frank-ogden.png', 140, 'Frank Ogden, about 1915')
        for sid, title, kind, date, pid, field, item in [
                ('naturalisation-1893', 'Naturalisation record, 1893', 'official', '1893', 'henri-moreau', 'facts',
                 {'label': 'Naturalisation', 'value': 'Became a British subject in 1893'}),
                ('electoral-roll-1925', 'Electoral roll, Leeds, 1925', 'electoral', '1925', 'peter-hartley', 'residences',
                 {'place': 'Leeds', 'placeId': 'leeds', 'address': '9 Cardigan Road, Leeds', 'years': '1925', 'confidence': 'probable'})]:
            site.add_source(sid, title, kind, date)
            site.p(pid)[field].append(dict(item, sourceIds=[sid]))


def build_all(root, upto=None):
    """Write v1 ... to root. Returns [(name, folder, now)]."""
    site, out = Site(), []
    for i, (name, now, _what) in enumerate(VERSIONS, 1):
        if upto and i > upto: break
        edit(site, i)
        out.append((name, site.write(os.path.join(root, name)), now))
    return out


if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit(__doc__)
    for name, folder, now in build_all(sys.argv[1]):
        print(name, now, folder)
