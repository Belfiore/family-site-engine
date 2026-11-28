#!/usr/bin/env python3
"""Checks for the Discovery Timeline: what counts as a find, how history is kept between publications, what is
never shown, that a site without the timeline is built exactly as before, and the page the build writes.

    python3 tests/test_discoveries.py          (needs only Python 3.9 or later)

The data is tests/timeline_fixtures.py: successive versions of a made-up family, built one after another the way
the live site is, each against the one before.
"""
import contextlib, copy, hashlib, http.server, io, json, os, re, shutil, subprocess, sys, tempfile, threading, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'build'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import build_site, discoveries as D, previous_site, timeline_page, timeline_fixtures as FX  # noqa: E402

BACKFILL = os.path.join(ROOT, 'tools', 'backfill-discoveries.py')

SAMPLE = os.path.join(ROOT, 'sample')
DASHES = re.compile('[%s%s]' % (chr(0x2013), chr(0x2014)))


def read(path):
    with open(path, encoding='utf-8') as f: return f.read()


def jload(path):
    with open(path, encoding='utf-8') as f: return json.load(f)


def build(site, out, previous='none', now='2026-11-26T10:00:00Z'):
    """Run a build in this process. Returns (exit code, what it printed)."""
    buf = io.StringIO()
    args = ['--site', site, '--out', out, '--now', now]
    if previous is not None: args += ['--previous', previous]
    with contextlib.redirect_stdout(buf):
        rc = build_site.main(args)
    return rc, buf.getvalue()


def entries(out):
    return jload(os.path.join(out, 'discoveries', 'history.json'))['entries']


def internal(out):
    """The findings as the engine keeps them for the next build (with the claims each is made of)."""
    return jload(os.path.join(out, 'discoveries', 'state.json'))['entries']


def heads(out):
    return [e['headline'] for e in entries(out)]


def all_text(out):
    """Everything the build wrote that a visitor or a crawler could read, except the engine's own code."""
    chunks = []
    for root, dirs, files in os.walk(out):
        dirs[:] = [d for d in dirs if d not in ('engine', 'archive')]
        for f in files:
            if f.endswith(('.html', '.json', '.js', '.css')): chunks.append(read(os.path.join(root, f)))
    return '\n'.join(chunks)


class Chain(unittest.TestCase):
    """v1 to v7 published in order; the folders are kept for every test in the class."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='timeline-')
        cls.versions = FX.build_all(os.path.join(cls.tmp, 'src'))
        cls.out = {}
        prev = 'none'
        for name, folder, now in cls.versions:
            o = os.path.join(cls.tmp, 'out', name)
            rc, text = build(folder, o, prev, now)
            assert rc == 0, text
            cls.out[name] = o
            prev = o

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestDetection(Chain):
    def test_first_publication_is_a_baseline_not_a_flood(self):
        self.assertEqual(entries(self.out['v1']), [])
        st = jload(os.path.join(self.out['v1'], 'discoveries', 'state.json'))
        self.assertEqual(st['since'], '2026-11-02')
        self.assertGreater(len(st['atoms']), 50)

    def test_turning_it_on_for_a_site_with_a_long_history_lists_nothing(self):
        # the last version, built as the first publication with the timeline on
        o = os.path.join(self.tmp, 'late')
        build(self.versions[-1][1], o, 'none', '2026-11-30T10:00:00Z')
        # the engine lists nothing of its own; only what a researcher wrote down on purpose (v5's notes) is there
        self.assertEqual([e.get('origin') for e in internal(o)], ['manual'] * 3)
        o1 = os.path.join(self.tmp, 'late1')
        build(self.versions[0][1], o1, 'none', '2026-11-30T10:00:00Z')
        self.assertEqual(entries(o1), [])
        self.assertIn('Nothing has been found', read(os.path.join(o1, 'discoveries.html')))

    def test_each_publication_finds_what_changed(self):
        h = {n: heads(self.out[n]) for n, _, _ in self.versions}
        self.assertEqual(len(h['v2']), 2)
        self.assertTrue(any('1891 census' in x and 'Hannah Hartley' in x for x in h['v2']))
        self.assertTrue(any(x.startswith('Corrected William Hartley') for x in h['v2']))
        new3 = [x for x in h['v3'] if x not in h['v2']]
        self.assertEqual(len(new3), 5, new3)
        self.assertTrue(any('Ruth Hartley' in x and 'Halifax' in x for x in new3))
        self.assertTrue(any('Alice Hartley' in x and 'photograph' in x for x in new3))
        self.assertTrue(any('Ilkley' in x and 'map' in x for x in new3))
        self.assertTrue(any('Jean-Baptiste Moreau' in x and 'rue Mercière' in x for x in new3))

    def test_grouped_into_one_find_per_discovery(self):
        census = [e for e in internal(self.out['v2']) if '1891 census' in e['headline']]
        self.assertEqual(len(census), 1)
        # the residence, the occupation, the new daughter and her birth are all in that one find
        self.assertGreaterEqual(len(census[0]['atoms']), 4)
        house = [e for e in entries(self.out['v7']) if '1911 census' in e['headline']]
        self.assertEqual(len(house), 1)
        self.assertEqual(house[0]['type'], 'person')
        self.assertNotIn('husband', house[0]['headline'])

    def test_a_correction_keeps_what_it_replaced(self):
        e = next(e for e in entries(self.out['v2']) if e['type'] == 'correction')
        self.assertEqual(e['headline'], "Corrected William Hartley's birth date from 10 June 1875 to 10 June 1876.")
        self.assertEqual(e['change'][0]['from'], '10 June 1875')
        self.assertEqual(e['change'][0]['to'], '10 June 1876')
        self.assertEqual(e['source']['text'], 'Baptism of William Hartley, Leeds, 1875')
        page = read(os.path.join(self.out['v2'], 'discoveries.html'))
        self.assertNotIn('Previously', page)       # the headline already says it; the card does not repeat it

    def test_a_renamed_picture_is_not_a_new_photo(self):
        self.assertFalse(any('Thomas Hartley' in x and 'photograph' in x for x in heads(self.out['v3'])))

    def test_people_given_the_very_same_new_details_share_one_find(self):
        src = os.path.join(self.tmp, 'household')
        shutil.copytree(self.versions[0][1], src)
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        for pid in ('thomas-hartley', 'mary-ann-briggs'):
            next(p for p in doc['people'] if p['id'] == pid)['residences'].append(
                {'place': 'Leeds', 'placeId': 'leeds', 'address': '4 Park Row, Leeds', 'years': '1895', 'confidence': 'confirmed'})
        next(p for p in doc['people'] if p['id'] == 'william-hartley')['residences'].append(
            {'place': 'Leeds', 'placeId': 'leeds', 'address': '6 Park Row, Leeds', 'years': '1895', 'confidence': 'confirmed'})
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'household-out')
        rc, text = build(src, o, self.out['v1'], '2026-11-05T10:00:00Z')
        self.assertEqual(rc, 0, text)
        found = heads(o)
        self.assertEqual(len(found), 2, found)
        both = [h for h in found if '4 Park Row' in h]
        self.assertEqual(len(both), 1, found)
        self.assertIn('Found where Thomas Hartley and Mary Ann Hartley lived', both[0])
        self.assertTrue(any('6 Park Row' in h and 'William Hartley' in h and 'Thomas' not in h for h in found), found)

    def test_a_removal_is_not_a_find_and_marks_the_find_it_undoes(self):
        # v4 removed the occupation the 1891 census find mentions
        before = {e['id'] for e in entries(self.out['v3'])}
        new4 = [e for e in entries(self.out['v4']) if e['id'] not in before]
        self.assertEqual([e['headline'] for e in new4], ['Found where Peter Hartley lived: 5 Headingley Lane, Leeds (1960).'])
        census = next(e for e in entries(self.out['v4']) if '1891 census' in e['headline'])
        self.assertEqual(census['status'], 'revised')
        self.assertIn('since been withdrawn', read(os.path.join(self.out['v4'], 'discoveries.html')))

    def test_nothing_is_listed_twice_across_all_publications(self):
        ids = [e['id'] for e in entries(self.out['v7'])]
        self.assertEqual(len(ids), len(set(ids)))
        seen = {}
        for n in ('v2', 'v3', 'v5', 'v7'):
            for e in entries(self.out[n]):
                if e['id'] in seen and e['status'] == 'current' and seen[e['id']]['status'] == 'current' and not e.get('auto'):
                    self.assertEqual(e['found'], seen[e['id']]['found'], 'a find keeps the day it was first made')
                seen[e['id']] = e

    def test_the_same_data_published_again_changes_nothing(self):
        for name, folder, now in self.versions[1:]:
            o = os.path.join(self.tmp, 'again-' + name)
            idx = [v[0] for v in self.versions].index(name)
            prev = self.out[self.versions[idx - 1][0]]
            build(folder, o, prev, now)
            self.assertEqual(entries(o), entries(self.out[name]))
            # and a rebuild from its own output, a day later
            o2 = os.path.join(self.tmp, 'again2-' + name)
            rc, text = build(folder, o2, self.out[name], '2026-12-01T10:00:00Z')
            self.assertEqual(rc, 0)
            self.assertIn('unchanged; 0 new finds', text)
            self.assertEqual(entries(o2), entries(self.out[name]))

    def test_new_finds_get_the_publication_time_and_old_ones_keep_theirs(self):
        final = entries(self.out['v7'])
        self.assertEqual({e['published'] for e in final if e['found'] == '2026-11-26'}, {'2026-11-26T09:00:00Z', '2026-11-26T15:00:00Z'})
        corr = next(e for e in final if e['type'] == 'correction')
        self.assertEqual(corr['published'], '2026-11-09T10:00:00Z')
        self.assertEqual(corr['found'], '2026-11-09')

    def test_wording_never_uses_long_dashes_and_is_plain(self):
        for n in self.out:
            for h in heads(self.out[n]):
                self.assertFalse(DASHES.search(h), h)
                self.assertTrue(h.endswith('.'), h)
                self.assertNotIn('  ', h)

    def test_only_meaning_counts(self):
        """Case, punctuation, spacing and spelling variants of the same words are not a discovery. A changed digit is."""
        self.assertFalse(D.differs('14 Park Row, Leeds', '14 park row leeds'))
        self.assertFalse(D.differs('Mary-Ann Briggs', 'Mary Ann  Briggs'))
        self.assertFalse(D.differs('Café Royal', 'Cafe Royal'))
        self.assertTrue(D.differs('14 Park Row', '41 Park Row'))
        self.assertTrue(D.differs('1875', '1876'))
        o = os.path.join(self.tmp, 'tidy')
        src = os.path.join(self.tmp, 'tidy-src')
        shutil.copytree(self.versions[-1][1], src)
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        for p in doc['people']:
            for r in p.get('residences') or []:
                r['address'] = (r.get('address') or '').upper() + ' '
            for ev in ('birth', 'death'):
                if p.get(ev) and p[ev].get('place'): p[ev]['place'] = p[ev]['place'].replace(', ', ',')
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, ensure_ascii=False, indent=1)
        rc, text = build(src, o, self.out['v7'], '2026-12-02T10:00:00Z')
        self.assertIn('unchanged; 0 new finds', text)


class TestManualNotes(Chain):
    def test_notes_on_a_record_replace_the_wording_and_add_provenance(self):
        e = next(e for e in entries(self.out['v5']) if 'Greek Street' in e['headline'])
        self.assertEqual(e['headline'], 'Henri Moreau was lodging at 22 Greek Street in Soho by 1891.')
        self.assertEqual((e['found'], e['foundIs']), ('2026-11-18', 'researcher'))
        self.assertEqual(e['foundBy'], 'Sebastian')
        self.assertEqual(e['source'], {'text': '1891 census, Soho (a made-up source)', 'url': 'https://example.org/census-1891'})
        self.assertEqual(e['confidence'], 'probable')
        self.assertEqual(e['image'], 'images/records/census-1891-soho.png')
        self.assertEqual(e['changeNote'], 'The household was thought to have left Soho in 1885.')
        self.assertEqual(e['published'], '2026-11-23T10:00:00Z')      # "new since your last visit" goes by publication, not by the day it was found

    def test_a_note_for_a_find_the_engine_also_made_gives_one_find_not_two(self):
        hannah = [e for e in internal(self.out['v5']) if 'person:hannah-hartley' in e['atoms']]
        self.assertEqual(len(hannah), 1)
        self.assertEqual(hannah[0]['headline'], 'Hannah Hartley, a sister nobody had listed, was born in Leeds in 1884.')
        self.assertEqual(hannah[0]['found'], '2026-11-12')
        self.assertEqual(hannah[0]['foundBy'], 'Stuart - Hartley')

    def test_a_note_with_nothing_generated_stands_alone(self):
        e = next(e for e in internal(self.out['v5']) if 'photograph album' in e['headline'])
        self.assertEqual((e['type'], e['origin'], e['confidence'], e['found']), ('photo', 'manual', 'family tradition', '2026-11-21'))
        self.assertEqual(e['source']['text'], 'Family photograph album (a made-up source)')

    def test_taking_a_note_away_brings_the_engines_wording_back(self):
        src = os.path.join(self.tmp, 'nonotes')
        shutil.copytree(self.versions[4][1], src)
        os.remove(os.path.join(src, 'data', 'discoveries.json'))
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        for p in doc['people']:
            for r in p.get('residences') or []: r.pop('discovery', None)
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'nonotes-out')
        build(src, o, self.out['v5'], '2026-11-24T10:00:00Z')
        hs = heads(o)
        self.assertFalse(any('photograph album' in x for x in hs))           # the stand-alone note is gone
        self.assertFalse(any('Greek Street in Soho by 1891' in x for x in hs))
        self.assertTrue(any('Hannah Hartley' in x and '1891 census' in x for x in hs))     # the generated wording is back
        self.assertEqual(sum('person:hannah-hartley' in e['atoms'] for e in internal(o)), 1)

    def test_the_notes_file_is_read_but_never_published_as_it_is(self):
        self.assertTrue(os.path.exists(os.path.join(self.versions[4][1], 'data', 'discoveries.json')))
        self.assertFalse(os.path.exists(os.path.join(self.out['v5'], 'data', 'discoveries.json')))

    def test_every_manual_field_is_optional(self):
        src = os.path.join(self.tmp, 'bare')
        shutil.copytree(self.versions[3][1], src)
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        next(p for p in doc['people'] if p['id'] == 'henri-moreau')['residences'].append(
            {'place': 'Soho', 'placeId': 'soho', 'address': '4 Dean Street, Soho', 'years': '1893', 'confidence': 'confirmed',
             'sourceIds': ['census-1881-soho'], 'discovery': {}})
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'bare-out')
        rc, text = build(src, o, self.out['v4'], '2026-11-22T10:00:00Z')
        self.assertEqual(rc, 0, text)
        e = next(e for e in entries(o) if 'Dean Street' in e['headline'])
        self.assertEqual(e['foundIs'], 'published')


class TestPrivacy(Chain):
    LIVING = ('Susan Hartley', 'Kate Hartley', 'Daniel Hartley', 'Janet Hartley', 'Lucy Hartley')
    IDS = ('susan-hartley', 'kate-hartley', 'daniel-hartley', 'janet-hartley', 'lucy-hartley')

    def test_living_people_appear_nowhere_in_what_the_timeline_publishes(self):
        for n in ('v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7'):
            out = self.out[n]
            mine = [os.path.join(out, 'discoveries.html'), os.path.join(out, 'discoveries', 'history.json'), os.path.join(out, 'discoveries', 'state.json')]
            text = '\n'.join(read(p) for p in mine)
            for name in self.LIVING[1:]:
                self.assertNotIn(name, text, '%s in %s' % (name, n))
            for pid in self.IDS[1:]:
                self.assertNotIn(pid, text, '%s in %s' % (pid, n))
            if n in ('v1', 'v2', 'v3'):
                self.assertNotIn('Susan Hartley', text)
                self.assertNotIn('susan-hartley', text)

    def test_a_living_person_added_with_a_photograph_and_a_new_home_is_not_a_find(self):
        # v4 adds Lucy (living, with a photograph) and a new home for Kate (living)
        new = [e for e in entries(self.out['v4']) if e['published'] == '2026-11-20T10:00:00Z']
        self.assertEqual(len(new), 1)
        self.assertIn('Peter Hartley', new[0]['headline'])

    def test_a_living_person_who_is_marked_deceased_does_not_flood_the_page(self):
        new = [e for e in entries(self.out['v4']) if e['published'] == '2026-11-20T10:00:00Z']
        self.assertFalse(any('Susan' in e['headline'] for e in new))
        # from then on she is like anyone else: a later find about her shows
        src = os.path.join(self.tmp, 'susan')
        shutil.copytree(self.versions[3][1], src)
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        next(p for p in doc['people'] if p['id'] == 'susan-hartley')['residences'].append(
            {'place': 'Leeds', 'placeId': 'leeds', 'address': '12 Moor Road, Leeds', 'years': '1975', 'confidence': 'confirmed', 'sourceIds': ['family-testimony']})
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'susan-out')
        build(src, o, self.out['v4'], '2026-11-21T10:00:00Z')
        self.assertTrue(any('Susan Hartley' in x and 'Moor Road' in x for x in heads(o)))

    def test_a_public_person_marked_living_takes_what_was_found_about_them_with_them(self):
        self.assertTrue(any('James Hartley' in x for x in heads(self.out['v3'])))
        out = self.out['v4']
        text = read(os.path.join(out, 'discoveries.html')) + read(os.path.join(out, 'discoveries', 'history.json')) + read(os.path.join(out, 'discoveries', 'state.json'))
        self.assertFalse(any('James Hartley' in x for x in heads(out)))
        self.assertNotIn('james-hartley', text)
        self.assertNotIn('James Hartley', text)
        # a find that only names him goes too: Ruth's was "a daughter of James Hartley"
        self.assertFalse(any('Ruth Hartley' in x for x in heads(out)))
        # and it stays gone, publication after publication
        self.assertNotIn('James Hartley', read(os.path.join(self.out['v7'], 'discoveries.html')))

    def test_the_withheld_are_kept_only_as_hashes(self):
        st = jload(os.path.join(self.out['v4'], 'discoveries', 'state.json'))
        self.assertTrue(all(re.match(r'^[0-9a-f]{12}$', h) for h in st['withheld']))
        self.assertGreaterEqual(len(st['withheld']), 4)

    def test_no_link_goes_to_a_living_person_or_a_place_only_they_were_in(self):
        for n in self.out:
            page = read(os.path.join(self.out[n], 'discoveries.html'))
            for pid in self.IDS + ('james-hartley',):
                if n in ('v1', 'v2', 'v3') and pid == 'james-hartley': continue
                self.assertNotIn('#/person/%s' % pid, page)
                self.assertNotIn('person=%s' % pid, page)

    def test_a_find_whose_words_name_a_living_person_is_dropped(self):
        src = os.path.join(self.tmp, 'named')
        shutil.copytree(self.versions[0][1], src)
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        next(p for p in doc['people'] if p['id'] == 'alice-turner')['media'].append(
            {'id': 'm-alice-kate', 'type': 'photo', 'file': 'images/people/arthur-hartley.png', 'thumb': 'images/people/arthur-hartley.png',
             'caption': 'Alice with Kate Hartley', 'alt': 'Alice with Kate Hartley', 'sourceId': 'family-photographs'})
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'named-out')
        rc, text = build(src, o, self.out['v1'], '2026-11-05T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertEqual(entries(o), [])
        self.assertNotIn('Kate Hartley', read(os.path.join(o, 'discoveries.html')))

    def test_people_in_a_hidden_region_are_treated_as_withheld(self):
        src = os.path.join(self.tmp, 'hidden')
        shutil.copytree(self.versions[0][1], src)
        cf = os.path.join(src, 'site.config.json')
        cfg = jload(cf)
        tree = cfg.setdefault('tree', {})
        # legend is the region this case withholds. Keep every region the sample already hides:
        # an associate's region has to stay in hiddenRegions, or the 1.1.0 check stops the build.
        regions = list(tree.get('hiddenRegions') or [])
        if 'legend' not in regions:
            regions.append('legend')
        tree['hiddenRegions'] = regions
        with open(cf, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        next(p for p in doc['people'] if p['id'] == 'pierre-moreau')['residences'].append(
            {'place': 'Lyon', 'placeId': 'lyon', 'address': '9 rue Neuve, Lyon', 'years': '1870', 'confidence': 'confirmed', 'sourceIds': ['family-testimony']})
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o1, o2 = os.path.join(self.tmp, 'hid1'), os.path.join(self.tmp, 'hid2')
        rc1, text1 = build(src, o1, 'none', '2026-11-02T10:00:00Z')
        self.assertEqual(rc1, 0, text1)
        rc, text = build(src, o2, o1, '2026-11-03T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertEqual(entries(o2), [])
        self.assertNotIn('Pierre', read(os.path.join(o2, 'discoveries.html')))

    # ---- timeline.showRegions: hidden regions (leads, associates) that the page may name, while the tree still leaves them off
    def _region_site(self, name, show, now_hidden=True):
        src = os.path.join(self.tmp, name)
        shutil.copytree(self.versions[0][1], src)
        cf = os.path.join(src, 'site.config.json')
        cfg = jload(cf)
        cfg['timeline']['showRegions'] = show
        with open(cf, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        return src

    def _lyon(self, src, pid='pierre-moreau', discovery=None):
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        res = {'place': 'Lyon', 'placeId': 'lyon', 'address': '9 rue Neuve, Lyon', 'years': '1870', 'confidence': 'confirmed', 'sourceIds': ['family-testimony']}
        if discovery: res['discovery'] = discovery
        next(p for p in doc['people'] if p['id'] == pid)['residences'].append(res)
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)

    def _two(self, name, src):
        o1, o2 = os.path.join(self.tmp, name + '1'), os.path.join(self.tmp, name + '2')
        rc, text = build(src, o1, 'none', '2026-11-02T10:00:00Z')
        self.assertEqual(rc, 0, text)
        return o1, o2

    def test_a_region_named_in_showRegions_is_on_the_timeline_with_no_link_to_the_tree(self):
        src = self._region_site('sr-shown', ['legend'])
        o1, o2 = self._two('sr-shown', src)
        self._lyon(src)
        rc, text = build(src, o2, o1, '2026-11-03T10:00:00Z')
        self.assertEqual(rc, 0, text)
        found = [e for e in entries(o2) if 'Pierre' in e['headline']]
        self.assertEqual(len(found), 1, heads(o2))
        self.assertTrue(found[0].get('offTree'))
        page = read(os.path.join(o2, 'discoveries.html'))
        card = next(c for c in re.findall(r'<li class="tl-card[^"]*".*?</li>', page, re.S) if 'Pierre' in c)
        self.assertNotIn('tl-action', card)
        self.assertNotIn('person/pierre-moreau', page)
        self.assertNotIn('See it in the tree', card)

    def test_a_living_person_in_a_shown_region_is_still_withheld(self):
        src = self._region_site('sr-living', ['legend'])
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        kate = next(p for p in doc['people'] if p['id'] == 'kate-hartley')
        self.assertTrue(kate.get('isLiving'))
        kate['region'] = 'legend'
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o1, o2 = self._two('sr-living', src)
        self._lyon(src, 'kate-hartley')
        rc, text = build(src, o2, o1, '2026-11-03T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertEqual(entries(o2), [])
        text = '\n'.join(read(os.path.join(o2, f)) for f in ('discoveries.html', 'discoveries/history.json', 'discoveries/state.json'))
        self.assertNotIn('Kate', text)
        self.assertNotIn('kate-hartley', text)
        self.assertIn(D.hid('kate-hartley'), text)        # only the one-way mark of her id

    def test_a_hidden_region_that_is_not_named_stays_withheld(self):
        src = self._region_site('sr-other', ['associates'])         # legend is hidden too, and not named
        o1, o2 = self._two('sr-other', src)
        self._lyon(src)
        rc, text = build(src, o2, o1, '2026-11-03T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertEqual(entries(o2), [])
        self.assertNotIn('Pierre', read(os.path.join(o2, 'discoveries.html')))

    def test_turning_it_on_does_not_flood_the_page_and_later_finds_show(self):
        src = self._region_site('sr-flood', [])
        o1, o2 = self._two('sr-flood', src)
        cf = os.path.join(src, 'site.config.json')
        cfg = jload(cf)
        cfg['timeline']['showRegions'] = ['legend']
        with open(cf, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        rc, text = build(src, o2, o1, '2026-11-03T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertEqual(entries(o2), [], 'what the family already knew about the region is not news')
        self._lyon(src)
        o3 = os.path.join(self.tmp, 'sr-flood3')
        rc, text = build(src, o3, o2, '2026-11-04T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertTrue(any('Pierre' in h for h in heads(o3)))

    def test_leaving_showRegions_out_or_empty_changes_nothing(self):
        a = self._region_site('sr-none-a', [])
        b = os.path.join(self.tmp, 'sr-none-b')
        shutil.copytree(a, b)
        cf = os.path.join(b, 'site.config.json')
        cfg = jload(cf)
        del cfg['timeline']['showRegions']
        with open(cf, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        oa, ob = os.path.join(self.tmp, 'sr-none-oa'), os.path.join(self.tmp, 'sr-none-ob')
        for src, o in ((a, oa), (b, ob)):
            rc, text = build(src, o, 'none', '2026-11-02T10:00:00Z')
            self.assertEqual(rc, 0, text)
        for f in ('discoveries.html', 'discoveries/history.json', 'discoveries/state.json'):
            self.assertEqual(read(os.path.join(oa, f)), read(os.path.join(ob, f)), f)

    def test_a_researchers_note_on_someone_in_a_shown_region_stands(self):
        src = self._region_site('sr-note', ['legend'])
        o1, o2 = self._two('sr-note', src)
        self._lyon(src, discovery={'headline': 'Pierre Moreau was a lead in Lyon in 1870.', 'foundBy': 'Sebastian'})
        rc, text = build(src, o2, o1, '2026-11-03T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertIn('Pierre Moreau was a lead in Lyon in 1870.', heads(o2))

    def test_a_find_about_a_place_only_those_people_have_is_marked_off_the_tree(self):
        from types import SimpleNamespace
        snap = SimpleNamespace(off_tree={'lead'}, off_places={'lyon'})
        self.assertTrue(D.off_tree({'personIds': ['lead'], 'focus': 'lead'}, snap))
        self.assertFalse(D.off_tree({'personIds': ['kin'], 'focus': 'kin'}, snap))
        self.assertTrue(D.off_tree({'type': 'place', 'placeIds': ['lyon'], 'personIds': []}, snap))
        self.assertFalse(D.off_tree({'type': 'place', 'placeIds': ['lyon', 'leeds'], 'personIds': []}, snap))

    def test_showRegions_is_checked_against_the_data(self):
        for show, want in ((['nowhere'], "'nowhere' is not in tree.hiddenRegions"), (['legend', 'ghosts'], "'ghosts' is not in tree.hiddenRegions")):
            src = self._region_site('sr-check', show)
            rc, text = build(src, os.path.join(self.tmp, 'sr-check-o'), 'none', '2026-11-02T10:00:00Z')
            self.assertEqual(rc, 0, text)
            self.assertIn(want, text)
            shutil.rmtree(src); shutil.rmtree(os.path.join(self.tmp, 'sr-check-o'))

    def test_a_note_on_a_living_person_is_ignored_and_warned_about(self):
        src = os.path.join(self.tmp, 'livingnote')
        shutil.copytree(self.versions[0][1], src)
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        next(p for p in doc['people'] if p['id'] == 'kate-hartley')['residences'] = [
            {'place': 'Leeds', 'placeId': 'leeds', 'address': '1 High Street, Leeds', 'years': '2020', 'confidence': 'confirmed', 'sourceIds': ['family-testimony'],
             'discovery': {'headline': 'Kate Hartley moved to 1 High Street.'}}]
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'livingnote-out')
        rc, text = build(src, o, self.out['v1'], '2026-11-05T10:00:00Z')
        self.assertEqual(rc, 0)
        self.assertIn('a discovery note on someone who is living is ignored', text)
        self.assertEqual(entries(o), [])
        self.assertNotIn('1 High Street', read(os.path.join(o, 'discoveries.html')))


class TestKeepingHistory(Chain):
    def test_the_build_line_counts_a_researchers_standalone_note_as_a_new_find(self):
        # v5 adds one note on a record (a new find) and one in data/discoveries.json that stands alone, and one that rewords an old find
        o = os.path.join(self.tmp, 'count-out')
        rc, text = build(self.versions[4][1], o, self.out['v4'], '2026-11-23T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertIn('updated; 2 new finds, 8 in the history', text)

    def test_a_build_not_told_what_was_published_last_stops_instead_of_forgetting(self):
        o = os.path.join(self.tmp, 'noprev-out')
        rc, text = build(self.versions[1][1], o, None, '2026-11-10T10:00:00Z')
        self.assertEqual(rc, 1)
        self.assertIn('was not told what was published last', text)
        self.assertIn('The live site is as it was', text)
        self.assertFalse(os.path.exists(os.path.join(o, 'discoveries', 'state.json')))
        # said on purpose, it is a first publication
        rc, text = build(self.versions[1][1], o, 'none', '2026-11-10T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertEqual(entries(o), [])

    def test_an_empty_folder_from_the_fetch_is_a_first_publication(self):
        empty = os.path.join(self.tmp, 'empty-previous')
        os.makedirs(empty)
        o = os.path.join(self.tmp, 'empty-out')
        rc, text = build(self.versions[1][1], o, empty, '2026-11-10T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertIn('initial', text)

    def test_a_failed_build_leaves_the_baseline_alone(self):
        before = read(os.path.join(self.out['v2'], 'discoveries', 'state.json'))
        broken = os.path.join(self.tmp, 'broken')
        shutil.copytree(self.versions[2][1], broken)
        pf = os.path.join(broken, 'data', 'people.json')
        doc = jload(pf)
        doc['people'][0]['children'].append('nobody-by-this-id')
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'broken-out')
        rc, text = build(broken, o, self.out['v2'], '2026-11-16T10:00:00Z')
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(os.path.join(o, 'discoveries', 'state.json')))
        self.assertEqual(read(os.path.join(self.out['v2'], 'discoveries', 'state.json')), before)
        # fixed and published: the same finds as if nothing had failed, none missing and none twice
        o2 = os.path.join(self.tmp, 'fixed-out')
        build(self.versions[2][1], o2, self.out['v2'], '2026-11-16T10:00:00Z')
        self.assertEqual(entries(o2), entries(self.out['v3']))

    def test_a_publication_that_was_never_deployed_is_found_again_next_time(self):
        """v3 built but not published; v4 is built against v2, the live site. v3's finds are found then, once."""
        o = os.path.join(self.tmp, 'skip3')
        build(self.versions[3][1], o, self.out['v2'], '2026-11-20T10:00:00Z')
        hs = heads(o)
        self.assertTrue(any('Ruth Hartley' in x for x in hs))
        self.assertTrue(any('Peter Hartley' in x for x in hs))
        self.assertEqual(len(hs), len(set(hs)))

    def test_rebaselining_when_claims_are_read_differently_keeps_finds_and_adds_none(self):
        o = os.path.join(self.tmp, 'rebase')
        old = D.ATOM_SCHEMA
        try:
            D.ATOM_SCHEMA = old + 1
            rc, text = build(self.versions[-1][1], o, self.out['v7'], '2026-12-01T10:00:00Z')
        finally:
            D.ATOM_SCHEMA = old
        self.assertEqual(rc, 0, text)
        self.assertIn('rebaselined', text)
        self.assertEqual(entries(o), entries(self.out['v7']))
        st = jload(os.path.join(o, 'discoveries', 'state.json'))
        self.assertEqual(st['atomSchema'], old + 1)

    def test_a_history_in_a_format_this_engine_does_not_read_stops_the_build(self):
        bad = os.path.join(self.tmp, 'badprev')
        os.makedirs(os.path.join(bad, 'discoveries'))
        with open(os.path.join(bad, 'discoveries', 'state.json'), 'w') as f: json.dump({'schema': 99, 'entries': []}, f)
        rc, text = build(self.versions[0][1], os.path.join(self.tmp, 'badprev-out'), bad, '2026-11-05T10:00:00Z')
        self.assertEqual(rc, 1)
        self.assertIn('format this engine does not read', text)

    def test_a_missing_or_unreadable_previous_stops_the_build(self):
        rc, text = build(self.versions[0][1], os.path.join(self.tmp, 'm1'), os.path.join(self.tmp, 'no-such-folder'))
        self.assertEqual(rc, 1)
        self.assertIn('no such file or folder', text)
        junk = os.path.join(self.tmp, 'junk')
        os.makedirs(os.path.join(junk, 'discoveries'))
        with open(os.path.join(junk, 'discoveries', 'state.json'), 'w') as f: f.write('{not json')
        rc, text = build(self.versions[0][1], os.path.join(self.tmp, 'm2'), junk)
        self.assertEqual(rc, 1)
        self.assertIn('not valid JSON', text)

    def test_two_sites_do_not_share_anything(self):
        """A second site on the same engine, built in between the first one's publications, has its own history."""
        site_b = os.path.join(self.tmp, 'siteB')
        shutil.copytree(self.versions[0][1], site_b)
        cf = os.path.join(site_b, 'site.config.json')
        cfg = jload(cf)
        cfg['site']['name'] = 'Another family'
        cfg['timeline']['file'] = 'finds.html'
        with open(cf, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        ob1 = os.path.join(self.tmp, 'B1')
        build(site_b, ob1, 'none', '2026-11-02T09:00:00Z')
        # site A publishes v2, then site B (still at its baseline) publishes the same data as v1: nothing
        oa = os.path.join(self.tmp, 'A2')
        build(self.versions[1][1], oa, self.out['v1'], '2026-11-09T10:00:00Z')
        ob = os.path.join(self.tmp, 'B1again')
        build(site_b, ob, ob1, '2026-11-09T11:00:00Z')
        self.assertEqual(len(entries(oa)), 2)
        self.assertEqual(entries(ob), [])
        self.assertTrue(os.path.exists(os.path.join(ob, 'finds.html')))
        self.assertFalse(os.path.exists(os.path.join(ob, 'discoveries.html')))
        self.assertEqual(jload(os.path.join(ob, 'discoveries', 'state.json'))['site'], 'Another family')


class TestSitesWithoutTheTimeline(unittest.TestCase):
    """A site that does not turn the timeline on builds exactly as it did before."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='timeline-off-')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def snapshot(self, out):
        files = {}
        for root, dirs, fs in os.walk(out):
            for f in fs:
                p = os.path.join(root, f)
                with open(p, 'rb') as fh: files[os.path.relpath(p, out)] = fh.read()
        files['engine-build.json'] = re.sub(rb'"built": "[^"]*"', b'"built": "x"', files['engine-build.json'])
        return files

    def test_off_or_missing_makes_no_page_no_folder_no_files_no_settings(self):
        a = os.path.join(self.tmp, 'a')
        build(SAMPLE, a, None)
        files = self.snapshot(a)
        mine = [k for k in files if ('discover' in k or 'timeline' in k) and not k.endswith('map-timeline.js')]
        self.assertEqual(mine, [])
        self.assertNotIn('timeline', jload(os.path.join(a, 'engine-build.json')))
        self.assertNotIn('timeline', read(os.path.join(a, 'site-config.js')))
        self.assertNotIn('Discoveries', read(os.path.join(a, 'index.html')))
        # saying "false" is the same as saying nothing
        src = os.path.join(self.tmp, 'src')
        shutil.copytree(SAMPLE, src)
        cf = os.path.join(src, 'site.config.json')
        cfg = jload(cf)
        cfg['timeline'] = {'enabled': False}
        with open(cf, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        b = os.path.join(self.tmp, 'b')
        build(src, b, None)
        self.assertEqual(self.snapshot(a), self.snapshot(b))

    def test_off_and_a_notes_file_present_is_still_just_a_file(self):
        src = os.path.join(self.tmp, 'src')
        shutil.copytree(SAMPLE, src)
        with open(os.path.join(src, 'data', 'discoveries.json'), 'w') as f: json.dump({'discoveries': []}, f)
        o = os.path.join(self.tmp, 'o')
        rc, text = build(src, o, None)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(o, 'data', 'discoveries.json')))     # unchanged behaviour: copied like any other file

    def test_the_engine_pages_a_site_already_has_are_unchanged_by_the_new_code(self):
        a = os.path.join(self.tmp, 'a')
        build(SAMPLE, a, None)
        on = os.path.join(self.tmp, 'on')
        src = os.path.join(self.tmp, 'src')
        shutil.copytree(SAMPLE, src)
        cf = os.path.join(src, 'site.config.json')
        cfg = jload(cf)
        cfg['timeline'] = {'enabled': True}
        with open(cf, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        build(src, on, 'none')
        # the tree, the map and Stuart are the same pages whether or not the timeline is on, apart from the navigation bar
        nav = re.compile(r'<nav\b.*?</nav>', re.S)
        ver = re.compile(r'\?v=[0-9a-f]+')        # the settings file's version tag, which changes with the settings
        for page in ('family-tree.html', 'map.html', 'ask.html'):
            self.assertEqual(ver.sub('', nav.sub('', read(os.path.join(a, page)))), ver.sub('', nav.sub('', read(os.path.join(on, page)))), page)


class TestPage(Chain):
    def page(self, n):
        return read(os.path.join(self.out[n], 'discoveries.html'))

    def cards(self, n):
        return re.findall(r'<li class="tl-card[^"]*".*?</li>', self.page(n), re.S)

    def test_the_page_and_its_place_in_the_navigation(self):
        page = self.page('v7')
        self.assertIn('<title>Discovery Timeline</title>', page)
        self.assertEqual(page.count('class="main-nav"'), 1)
        self.assertIn('<a href="discoveries.html" class="active" aria-current="page">Discoveries</a>', page)
        self.assertIn('<a href="discoveries.html">Discoveries</a>', read(os.path.join(self.out['v7'], 'index.html')))
        self.assertTrue(os.path.exists(os.path.join(self.out['v7'], 'engine', jload(os.path.join(self.out['v7'], 'engine-build.json'))['engine'], 'timeline.js')))

    def test_days_run_newest_first_with_the_long_date_and_a_summary(self):
        page = self.page('v7')
        days = re.findall(r'<time datetime="(\d{4}-\d{2}-\d{2})">([^<]+)</time>', page)
        self.assertEqual([d for d, _ in days], sorted((d for d, _ in days), reverse=True))
        self.assertEqual(days[0], ('2026-11-26', 'Thursday, 26 November 2026'))
        self.assertIn('8 new finds across The Hartleys and The Moreaus.', page)

    def test_a_find_has_at_most_one_action_link_and_the_headline_is_never_a_link(self):
        # the quiet "See it in the tree" link is one per find. A source address and a picture can also be links (below), and nothing else is.
        for n in self.out:
            for c in self.cards(n):
                self.assertLessEqual(c.count('class="tl-action"'), 1, c)
                self.assertFalse(re.search(r'<h3[^>]*>\s*<a', c))
                for a in re.findall(r'<a\b[^>]*>', c):
                    self.assertTrue('tl-action' in a or 'tl-source' in a or 'tl-thumb-link' in a or 'target="_blank"' in a, a)
        c = next(c for c in self.cards('v3') if 'Ilkley' in c)
        self.assertIn('href="map.html?place=ilkley"', c)
        self.assertIn('Show on the map', c)
        c = next(c for c in self.cards('v3') if 'Ruth Hartley' in c)
        self.assertIn('href="family-tree.html#/person/ruth-hartley"', c)
        self.assertIn('See it in the tree', c)

    def test_a_card_has_a_type_a_source_and_a_confidence_and_a_picture_only_when_it_has_one(self):
        cards = self.cards('v5')
        c = next(c for c in cards if 'Greek Street' in c)
        self.assertIn('New record', c)
        self.assertIn('1891 census, Soho (a made-up source)', c)
        self.assertNotIn('Probable', c)          # confidence is kept in the data and left off the page unless timeline.showConfidence is true
        self.assertNotIn('tl-conf', c)
        self.assertIn('Found by Sebastian', c)
        self.assertIn('<img class="tl-thumb" src="images/records/census-1891-soho.png"', c)
        self.assertIn('alt="A census page with one line marked"', c)
        self.assertIn('The household was thought to have left Soho in 1885.', c)
        plain = next(c for c in cards if 'Peter Hartley lived' in c)
        self.assertNotIn('<img', plain)
        self.assertNotIn('tl-has-thumb', plain)

    def test_type_labels_are_the_six_the_page_promises(self):
        seen = set()
        for n in self.out:
            seen |= set(re.findall(r'<p class="tl-type">.*?<span>([^<]+)</span></p>', self.page(n), re.S))
        self.assertEqual(seen, {'New person', 'New record', 'New photo', 'Correction', 'New place'})

    def test_a_connection_find_has_its_own_label(self):
        src = os.path.join(self.tmp, 'conn')
        shutil.copytree(self.versions[0][1], src)
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        by = {p['id']: p for p in doc['people']}
        by['unknown-sitter']['parents'] = ['mary-ann-briggs']
        by['mary-ann-briggs']['children'].append('unknown-sitter')
        by['unknown-sitter']['parentLinkConfidence'] = 'probable'
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'conn-out')
        rc, text = build(src, o, self.out['v1'], '2026-11-05T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertIn('New connection', read(os.path.join(o, 'discoveries.html')))
        self.assertTrue(any('unknown' in x.lower() or 'Woman in a studio portrait' in x for x in heads(o)))

    def test_a_busy_day_is_folded_and_every_find_is_still_in_the_page(self):
        page = self.page('v7')
        day = re.search(r'<li class="tl-day" data-date="2026-11-26".*?</section></li>', page, re.S).group(0)
        self.assertEqual(day.count('<li class="tl-card'), 8)
        self.assertEqual(day.count('tl-extra'), 3)         # the first five show; the rest wait behind "Show all 8 finds"
        self.assertIn('Show all 8 finds', day)
        quiet = re.search(r'<li class="tl-day" data-date="2026-11-16".*?</section></li>', page, re.S).group(0)
        self.assertNotIn('tl-more', quiet)

    def test_cards_carry_what_the_script_needs_and_nothing_private(self):
        c = self.cards('v7')[0]
        self.assertRegex(c, r'data-published="2026-11-26T09:00:00Z"')
        self.assertRegex(c, r'data-lines="[a-z ]+"')
        self.assertRegex(c, r'id="find-[a-z]-[0-9a-f]+"')

    # ---- source addresses, pictures that open large, and confidence off by default
    @staticmethod
    def one(text, url=None, image=None, conf=None, cfg=None, full_of=None):
        e = [{'id': 'x-1', 'type': 'record', 'headline': 'Found one.', 'found': '2026-11-01', 'published': '2026-11-01T00:00:00Z', 'status': 'current',
              'lines': ['a'], 'personIds': [], 'placeIds': [], 'source': {'text': text, 'url': url} if text else None, 'confidence': conf,
              'image': image, 'imageAlt': 'A page'}]
        return timeline_page.render_body(e, [{'id': 'a', 'label': 'A'}], cfg or {}, {}, full_of=full_of)

    def test_a_source_address_is_a_link_that_opens_in_a_new_tab(self):
        c = next(c for c in self.cards('v5') if 'Greek Street' in c)
        self.assertIn('<a class="tl-source" href="https://example.org/census-1891" target="_blank" rel="noopener">1891 census, Soho (a made-up source)</a>', c)
        self.assertIn('class="tl-action"', c)       # the card still has its own quiet link into the tree

    def test_an_address_written_in_a_sources_words_is_a_link_too(self):
        a = '<a href="https://example.org/reg/12" target="_blank" rel="noopener">https://example.org/reg/12</a>'
        self.assertIn('<span class="tl-source">%s</span>' % a, self.one('https://example.org/reg/12'))
        self.assertIn('see %s. Page 4</span>' % a, self.one('Parish register, see https://example.org/reg/12. Page 4'))
        h = self.one('Wikipedia (https://example.org/wiki/A_(b))')
        self.assertIn('<a href="https://example.org/wiki/A_(b)" target="_blank" rel="noopener">https://example.org/wiki/A_(b)</a>)</span>', h)
        h = self.one('See https://example.org/b', 'https://example.org/a')       # a named address wins, and there is one link, not two
        self.assertEqual(h.count('<a '), 1)
        self.assertIn('href="https://example.org/a"', h)
        for plain in ('An archive entry, box 4', 'javascript:alert(1) and ftp://example.org/y', 'www.example.org/no-scheme'):
            self.assertNotIn('<a ', self.one(plain), plain)
        h = self.one('<b>https://example.org/x</b>')
        self.assertNotIn('<b>', h)
        self.assertEqual(h.count('<a '), 1)

    def test_a_picture_opens_full_size_and_the_page_loads_the_lightbox_only_then(self):
        c = next(c for c in self.cards('v5') if 'Greek Street' in c)
        self.assertIn('<a class="record-link tl-thumb-link" href="images/records/census-1891-soho.png" target="_blank" rel="noopener" '
                      'aria-label="View full size: A census page with one line marked"><img class="tl-thumb"', c)
        for n in self.out:
            page = self.page(n)
            has = 'tl-thumb-link' in page
            self.assertEqual('records.js' in page, has, n)
            self.assertEqual('records.css' in page, has, n)

    def test_a_thumbnail_opens_the_full_size_file_not_itself(self):
        src = os.path.join(self.tmp, 'thumbfull')
        shutil.copytree(self.versions[2][1], src)
        rel = next(e['image'] for e in entries(self.out['v3']) if 'Alice Hartley' in e['headline'] and 'photograph' in e['headline'])
        thumb = 'images/thumbs/' + os.path.basename(rel)
        os.makedirs(os.path.join(src, 'images', 'thumbs'), exist_ok=True)
        shutil.copy(os.path.join(src, rel), os.path.join(src, thumb))
        pf = os.path.join(src, 'data', 'people.json')
        doc = jload(pf)
        hit = [m for p in doc['people'] for m in p.get('media') or [] if m.get('file') == rel]
        self.assertTrue(hit)
        for m in hit: m['thumb'] = thumb
        with open(pf, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        o = os.path.join(self.tmp, 'thumbfull-out')
        rc, text = build(src, o, self.out['v2'], self.versions[2][2])
        self.assertEqual(rc, 0, text)
        card = next(c for c in re.findall(r'<li class="tl-card[^"]*".*?</li>', read(os.path.join(o, 'discoveries.html')), re.S) if 'Alice Hartley' in c)
        self.assertIn('href="%s"' % rel, card)
        self.assertIn('<img class="tl-thumb" src="%s"' % thumb, card)
        h = self.one('S', image='images/t/a.jpg', full_of={'images/t/a.jpg': 'images/full/a.jpg'})
        self.assertIn('href="images/full/a.jpg"', h)
        self.assertIn('src="images/t/a.jpg"', h)
        self.assertNotIn('<a ', self.one('S'))          # no picture, no link

    def test_confidence_is_kept_in_the_data_and_off_the_page_unless_asked(self):
        self.assertTrue(any(e.get('confidence') for e in entries(self.out['v5'])))      # history.json keeps it
        for n in self.out: self.assertNotIn('tl-conf', self.page(n), n)
        self.assertNotIn('tl-conf', self.one('S', conf='probable'))
        self.assertNotIn('tl-conf', self.one('S', conf='probable', cfg={'timeline': {'showConfidence': False}}))
        h = self.one('S', conf='probable', cfg={'timeline': {'showConfidence': True}})
        self.assertIn('<span class="tl-conf" data-conf="probable">Probable</span>', h)
        src = os.path.join(self.tmp, 'showconf')
        shutil.copytree(self.versions[4][1], src)
        cf = os.path.join(src, 'site.config.json')
        cfg = jload(cf)
        cfg['timeline']['showConfidence'] = True
        with open(cf, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)
        o = os.path.join(self.tmp, 'showconf-out')
        rc, text = build(src, o, self.out['v4'], self.versions[4][2])
        self.assertEqual(rc, 0, text)
        page = read(os.path.join(o, 'discoveries.html'))
        self.assertIn('<span class="tl-conf" data-conf="probable">Probable</span>', page)
        self.assertEqual(entries(o), entries(self.out['v5']))       # the option changes the page, never the history


    def test_nothing_in_the_page_is_a_long_dash_or_loads_from_elsewhere(self):
        for n in self.out:
            page = self.page(n)
            self.assertFalse(DASHES.search(page))
            # nothing is loaded from elsewhere (a script, a style, a picture); a source can be a link out, in a new tab
            for u in re.findall(r'<(?:script|img|link|iframe|source)\b[^>]*\b(?:src|href)="(https?://[^"]+)"', page):
                self.fail('the page loads %s' % u)
            for a in re.findall(r'<a\b[^>]*href="https?://[^"]+"[^>]*>', page):
                self.assertIn('target="_blank"', a)
                self.assertIn('rel="noopener"', a)

    def test_the_headline_text_is_escaped(self):
        e = [{'id': 'x-1', 'type': 'record', 'headline': 'Found <b>"A" & B</b>.', 'found': '2026-11-01', 'published': '2026-11-01T00:00:00Z', 'status': 'current',
              'lines': ['a'], 'personIds': ['p1'], 'placeIds': [], 'source': {'text': 'S <i>', 'url': 'javascript:alert(1)'}, 'confidence': 'confirmed'}]
        html = timeline_page.render_body(e, [{'id': 'a', 'label': 'A'}], {}, {'tree': 'family-tree.html', 'map': None})
        self.assertNotIn('<b>', html)
        self.assertIn('&lt;b&gt;', html)
        self.assertNotIn('javascript:', html)

    def test_a_site_with_one_line_and_one_type_has_no_pointless_filters(self):
        e = [{'id': 'x-1', 'type': 'record', 'headline': 'Found one.', 'found': '2026-11-01', 'published': '2026-11-01T00:00:00Z', 'status': 'current',
              'lines': ['a'], 'personIds': [], 'placeIds': [], 'source': None, 'confidence': None}]
        html = timeline_page.render_body(e, [{'id': 'a', 'label': 'A'}], {}, {})
        self.assertNotIn('tlFilters', html)
        self.assertIn('1 new find.', html)
        self.assertNotIn('across', html)

    def test_validation(self):
        src = os.path.join(self.tmp, 'val')
        shutil.copytree(self.versions[4][1], src)
        df = os.path.join(src, 'data', 'discoveries.json')
        doc = jload(df)
        doc['discoveries'][0]['findType'] = 'rumour'
        doc['discoveries'][1]['headline'] = 'Something ' + chr(0x2014) + ' new'
        doc['discoveries'][1]['found'] = '2099-01-01'
        with open(df, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        rc, text = build(src, os.path.join(self.tmp, 'val-out'), self.out['v4'])
        self.assertEqual(rc, 1)
        self.assertIn("'rumour' is not one of", text)
        doc['discoveries'][0]['findType'] = 'person'
        with open(df, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=1)
        rc, text = build(src, os.path.join(self.tmp, 'val-out2'), self.out['v4'])
        self.assertEqual(rc, 0, text)
        self.assertIn('long dash', text)
        self.assertIn('in the future', text)
        # the build never writes over a page or a folder the site has
        os.makedirs(os.path.join(src, 'discoveries'))
        rc, text = build(src, os.path.join(self.tmp, 'val-out3'), self.out['v4'])
        self.assertEqual(rc, 1)
        self.assertIn('discoveries/ folder', text)


class TestFetchingTheLiveHistory(unittest.TestCase):
    """build/previous_site.py against a small web server standing in for the live site."""
    def serve(self, routes):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(h):
                path = h.path.split('?')[0]
                status, body = routes.get(path, (404, b''))
                h.send_response(status); h.end_headers(); h.wfile.write(body)

            def log_message(h, *a): pass
        srv = http.server.HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return 'http://127.0.0.1:%d/' % srv.server_address[1]

    def run_fetch(self, url):
        out = tempfile.mkdtemp(prefix='prev-')
        self.addCleanup(shutil.rmtree, out, True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = previous_site.main(['--url', url, '--out', out])
        return rc, buf.getvalue(), os.path.join(out, 'discoveries', 'state.json')

    def test_found(self):
        url = self.serve({'/discoveries/state.json': (200, b'{"schema": 1, "entries": [{"id": "x"}], "published": "t"}')})
        rc, text, path = self.run_fetch(url)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(path))
        self.assertIn('1 finds', text)

    def test_never_had_the_timeline(self):
        url = self.serve({'/engine-build.json': (200, b'{"engine": "1.0.1"}')})
        rc, text, path = self.run_fetch(url)
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(path))
        self.assertIn('first publication', text)

    def test_a_brand_new_site_with_nothing_live_yet(self):
        rc, text, path = self.run_fetch(self.serve({}))
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(path))

    def test_the_live_site_had_the_timeline_but_the_history_is_missing(self):
        url = self.serve({'/engine-build.json': (200, b'{"timeline": {"file": "discoveries.html"}}')})
        rc, text, path = self.run_fetch(url)
        self.assertEqual(rc, 1)
        self.assertIn('would erase the history', text)

    def test_a_server_error_stops_the_publication(self):
        previous_site.time.sleep = lambda s: None
        rc, text, path = self.run_fetch(self.serve({'/discoveries/state.json': (503, b'')}))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(path))

    def test_a_page_that_is_not_a_history_stops_the_publication(self):
        rc, text, path = self.run_fetch(self.serve({'/discoveries/state.json': (200, b'<html>Not found</html>')}))
        self.assertEqual(rc, 1)


COMMIT_DAYS = {'v1': '2026-11-02', 'v2': '2026-11-09', 'v3': '2026-11-16', 'v4': '2026-11-20'}


def tree_hashes(root):
    """Every file under root (not .git) and a hash of what is in it."""
    out = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != '.git']
        for f in files:
            p = os.path.join(base, f)
            with open(p, 'rb') as fh: out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


@unittest.skipUnless(shutil.which('git'), 'git is not installed')
class TestBackfill(unittest.TestCase):
    """tools/backfill-discoveries.py on a git history made from the fixture versions (v1 to v4), one commit each."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='backfill-')
        cls.versions = FX.build_all(os.path.join(cls.tmp, 'src'), upto=4)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def git(self, repo, *args, env=None):
        e = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, **(env or {}))
        subprocess.run(['git', '-C', repo, *args], check=True, capture_output=True, env=e)

    def repo(self, name, upto=4, sub=''):
        """A repository with one commit per version, dated as COMMIT_DAYS says. With sub, the site sits in that folder."""
        repo = os.path.join(self.tmp, name)
        os.makedirs(repo)
        self.git(repo, 'init', '-q')
        self.git(repo, 'config', 'user.email', 'test@example.org')
        self.git(repo, 'config', 'user.name', 'Test')
        site = os.path.join(repo, sub) if sub else repo
        for vname, folder, _now in self.versions[:upto]:
            for item in os.listdir(repo):
                if item != '.git':
                    full = os.path.join(repo, item)
                    shutil.rmtree(full) if os.path.isdir(full) else os.remove(full)
            shutil.copytree(folder, site, dirs_exist_ok=True)
            when = COMMIT_DAYS[vname] + 'T09:00:00+00:00'
            self.git(repo, 'add', '-A')
            self.git(repo, 'commit', '-q', '-m', 'Data as of ' + vname, env={'GIT_AUTHOR_DATE': when, 'GIT_COMMITTER_DATE': when})
        return repo, site

    def run_backfill(self, site, *extra):
        p = subprocess.run([sys.executable, BACKFILL, '--site', site, *extra], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def suggestions(self, site, *extra):
        out = os.path.join(self.tmp, 'sugg-%d.json' % len(os.listdir(self.tmp)))
        rc, text = self.run_backfill(site, '--out', out, *extra)
        self.assertEqual(rc, 0, text)
        return jload(out)

    def test_each_find_is_dated_by_the_commit_that_added_it(self):
        repo, site = self.repo('dated')
        doc = self.suggestions(site)
        by = {e['id']: e for e in doc['discoveries']}
        self.assertTrue(by)
        text = lambda e: e['headline']
        census = [e for e in by.values() if 'Kirkgate' in text(e) or 'Hannah' in text(e)]
        lyon = [e for e in by.values() if 'Mercière' in text(e) or 'Lyon' in text(e)]
        self.assertTrue(census and lyon, [text(e) for e in by.values()])
        self.assertTrue(all(e['found'] == COMMIT_DAYS['v2'] for e in census))
        self.assertTrue(all(e['found'] == COMMIT_DAYS['v3'] for e in lyon))
        self.assertTrue(all(e['found'] in (COMMIT_DAYS['v2'], COMMIT_DAYS['v3'], COMMIT_DAYS['v4']) for e in by.values()),
                        'the first commit is the starting point, never a find')

    def test_every_suggestion_says_when_and_why_to_look_twice(self):
        repo, site = self.repo('review')
        for e in self.suggestions(site)['discoveries']:
            self.assertTrue(e['id'].startswith('suggested-'))
            self.assertTrue(e['covers'], e)
            self.assertIn('committed', e['review'])
            self.assertTrue(any('day the change was committed' in n for n in e['review']['notes']))

    def test_the_correction_is_suggested_with_both_values(self):
        repo, site = self.repo('correction')
        fixes = [e for e in self.suggestions(site)['discoveries'] if e['findType'] == 'correction']
        self.assertEqual(len(fixes), 1, fixes)
        self.assertIn('1876', fixes[0]['headline'])
        self.assertEqual(fixes[0]['found'], COMMIT_DAYS['v2'])

    def test_a_claim_that_was_later_removed_is_flagged_not_hidden(self):
        # v2 found Thomas as a wool broker in the 1891 census; v4 took the occupation out again
        repo, site = self.repo('revised')
        revised = [e for e in self.suggestions(site)['discoveries'] if any('later withdrawn' in n for n in e['review']['notes'])]
        self.assertEqual(len(revised), 1, revised)
        self.assertIn('Kirkgate', revised[0]['headline'])

    def test_people_who_are_living_now_are_nowhere_in_the_suggestions(self):
        repo, site = self.repo('privacy')
        text = json.dumps(self.suggestions(site), ensure_ascii=False)
        # Lucy and Kate are living in v4; James was public in v3 and is marked living in v4, so what v3 found about him goes too
        for needle in ('lucy-hartley', 'Lucy Hartley', 'kate-hartley', 'Kate Hartley', 'james-hartley', 'James Hartley', 'Mill Lane'):
            self.assertNotIn(needle, text)
        ruth = [e for e in json.loads(text)['discoveries'] if 'Ruth' in e['headline']]
        self.assertEqual(ruth, [], 'Ruth is a daughter of someone who is now withheld, so the find that names the father goes too')

    def test_a_person_marked_living_after_the_last_commit_is_left_out_too(self):
        # the data is committed up to v3, where James Hartley is public and has a new photograph; the folder already says (v4, not
        # committed yet) that he is living. What the site says today decides.
        repo, site = self.repo('uncommitted', upto=3)
        before = self.suggestions(site)
        self.assertIn('james-hartley', json.dumps(before), 'the test needs the photograph find to exist to be meaningful')
        shutil.copytree(self.versions[3][1], site, dirs_exist_ok=True)
        after = json.dumps(self.suggestions(site), ensure_ascii=False)
        for needle in ('james-hartley', 'James Hartley', 'lucy-hartley', 'kate-hartley'):
            self.assertNotIn(needle, after)

    def test_nothing_in_the_site_or_its_history_is_changed(self):
        repo, site = self.repo('untouched')
        head = subprocess.run(['git', '-C', repo, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout
        before = tree_hashes(site)
        rc, text = self.run_backfill(site, '--out', os.path.join(self.tmp, 'elsewhere.json'))
        self.assertEqual(rc, 0, text)
        self.assertEqual(tree_hashes(site), before)
        self.assertEqual(subprocess.run(['git', '-C', repo, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout, head)
        status = subprocess.run(['git', '-C', repo, 'status', '--porcelain'], capture_output=True, text=True).stdout
        self.assertEqual(status, '')

    def test_by_default_the_only_thing_written_is_the_suggestions_file(self):
        repo, site = self.repo('default-out')
        before = tree_hashes(site)
        rc, text = self.run_backfill(site)
        self.assertEqual(rc, 0, text)
        after = tree_hashes(site)
        self.assertEqual(set(after) - set(before), {'discoveries.suggestions.json'})
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)

    def test_it_will_not_overwrite_a_file_unless_told_to(self):
        repo, site = self.repo('overwrite')
        out = os.path.join(self.tmp, 'overwrite-out.json')
        self.assertEqual(self.run_backfill(site, '--out', out)[0], 0)
        first = jload(out)['discoveries']
        with open(out, 'w', encoding='utf-8') as f: f.write('{"mine": true}')
        rc, text = self.run_backfill(site, '--out', out)
        self.assertNotEqual(rc, 0)
        self.assertIn('--force', text)
        self.assertEqual(read(out), '{"mine": true}')
        self.assertEqual(self.run_backfill(site, '--out', out, '--force')[0], 0)
        self.assertEqual(jload(out)['discoveries'], first)

    def test_one_commit_is_not_enough_to_compare(self):
        repo, site = self.repo('single', upto=1)
        rc, text = self.run_backfill(site, '--out', os.path.join(self.tmp, 'single.json'))
        self.assertNotEqual(rc, 0)
        self.assertIn('at least two', text)

    def test_since_makes_the_first_commit_read_the_starting_point(self):
        repo, site = self.repo('since')
        doc = self.suggestions(site, '--since', COMMIT_DAYS['v3'])
        self.assertTrue(doc['discoveries'])
        self.assertTrue(all(e['found'] in (COMMIT_DAYS['v4'],) for e in doc['discoveries']), [e['found'] for e in doc['discoveries']])

    def test_a_site_in_a_folder_of_a_larger_repository_works(self):
        repo, site = self.repo('nested', sub='sites/hartley')
        doc = self.suggestions(site)
        self.assertTrue(any('Hannah' in e['headline'] or 'Kirkgate' in e['headline'] for e in doc['discoveries']))

    def test_the_suggestions_can_be_used_as_they_are(self):
        # copy the file into the site as data/discoveries.json: it must validate, and the build must list the notes with their dates
        repo, site = self.repo('usable')
        doc = self.suggestions(site)
        v4 = self.versions[3][1]
        use = os.path.join(self.tmp, 'use-v4')
        shutil.copytree(v4, use)
        with open(os.path.join(use, 'data', 'discoveries.json'), 'w', encoding='utf-8') as f: json.dump(doc, f, ensure_ascii=False)
        out = os.path.join(self.tmp, 'use-out')
        rc, text = build(use, out, 'none', '2026-11-26T10:00:00Z')
        self.assertEqual(rc, 0, text)
        self.assertNotIn('ERROR', text)
        found = {e['headline']: e['found'] for e in entries(out)}
        for e in doc['discoveries']:
            self.assertEqual(found.get(e['headline']), e['found'], e['headline'])


class TestFamilyLines(unittest.TestCase):
    """A find belongs to a family line the way the map puts a person on a branch (engine/map-data.js, branchOf)."""
    CFG = {'map': {'branches': [
        {'id': 'main', 'label': 'Main', 'default': True, 'pages': ['main.html']},
        {'id': 'north', 'label': 'North', 'pages': ['north.html'], 'people': ['named']},
        {'id': 'far', 'label': 'Far', 'regions': ['faraway']}]}}

    def lines(self, *people):
        return D.branch_lines(self.CFG, list(people))[0]

    def test_a_story_page_places_a_person_on_its_line(self):
        got = self.lines({'id': 'a', 'relatedPages': [{'title': 'x', 'url': 'north.html#section'}]},
                         {'id': 'b', 'relatedPages': ['north.html']})
        self.assertEqual(got, {'a': 'north', 'b': 'north'})

    def test_a_region_beats_a_name_and_a_name_beats_a_page(self):
        got = self.lines({'id': 'r', 'region': 'faraway', 'relatedPages': ['north.html']},
                         {'id': 'named', 'relatedPages': ['main.html']},
                         {'id': 'p', 'relatedPages': ['north.html', 'main.html']})
        self.assertEqual(got, {'r': 'far', 'named': 'north', 'p': 'north'})

    def test_everyone_else_goes_to_the_default_line(self):
        got = self.lines({'id': 'x'}, {'id': 'y', 'relatedPages': ['main.html', 'elsewhere.html']})
        self.assertEqual(got, {'x': 'main', 'y': 'main'})


if __name__ == '__main__':
    unittest.main(verbosity=1)
