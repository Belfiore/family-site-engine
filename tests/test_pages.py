#!/usr/bin/env python3
"""Page toggles, the Stories and Records and Research pages, the settings page at /admin/ and the pages schema.

    python3 tests/test_pages.py          (needs only Python 3.9 or later)

Each check builds a throwaway copy of the sample site, so the sample itself is never changed.
"""
import copy, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, 'sample')
sys.path.insert(0, os.path.join(ROOT, 'build'))
import markdown, sitecfg, stories, validate  # noqa: E402

BASE = 'engine/%s/' % open(os.path.join(ROOT, 'VERSION')).read().strip()


def build(site, out, env=None):
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'build', 'build_site.py'), '--site', site, '--out', out, '--previous', 'none'],
                       capture_output=True, text=True, env=dict(os.environ, **(env or {})))
    return p.returncode, p.stdout + p.stderr


def read(*p):
    with open(os.path.join(*p), encoding='utf-8') as f: return f.read()


class Site:
    """A throwaway copy of the sample site."""
    def __init__(self, tmp):
        self.dir = os.path.join(tmp, 'site')
        self.out = os.path.join(tmp, 'out')
        shutil.copytree(SAMPLE, self.dir)

    def config(self, fn):
        p = os.path.join(self.dir, 'site.config.json')
        with open(p, encoding='utf-8') as f: cfg = json.load(f)
        fn(cfg)
        with open(p, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=1)

    def pages(self, **kw):
        def fn(cfg):
            for k, v in kw.items():
                if v == 'unset': cfg['pages'].pop(k, None)
                else: cfg['pages'][k] = v
        self.config(fn)

    def write(self, rel, text):
        p = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f: f.write(text)

    def story(self, name, title='A story', body='Some words.', **meta):
        lines = ['title: %s' % title] + ['%s: %s' % (k, v) for k, v in meta.items()]
        self.write('content/stories/%s.md' % name, '---\n%s\n---\n%s\n' % ('\n'.join(lines), body))

    def build(self, env=None):
        return build(self.dir, self.out, env)

    def has(self, *p): return os.path.exists(os.path.join(self.out, *p))
    def text(self, *p): return read(self.out, *p)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pages-test-')
        self.site = Site(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ok(self, env=None):
        code, log = self.site.build(env)
        self.assertEqual(code, 0, log)
        return log

    def nav_links(self, page='index.html'):
        nav = re.search(r'<div class="nav-links".*?</div>', self.site.text(page), re.S).group(0)
        return re.findall(r'<a href="([^"]+)"', nav)


# ---------------------------------------------------------------------------------------------- the switches
class TestToggles(Case):
    def test_the_same_cases_as_the_settings_page_read_the_same_way(self):
        with open(os.path.join(ROOT, 'tests', 'fixtures', 'pages-cases.json'), encoding='utf-8') as f: cases = json.load(f)
        for c in cases:
            d = os.path.join(self.tmp, 'case')
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)
            with open(os.path.join(d, 'site.config.json'), 'w', encoding='utf-8') as f:
                json.dump(dict({'schemaVersion': 1, 'site': {'name': 'T'}, 'nav': []}, **c['config']), f)
            t = sitecfg.load(d)['_toggles']
            for k, want in c['on'].items():
                self.assertEqual(t[k]['on'], want, '%s: %s' % (c['name'], k))
            self.assertTrue(t['home']['on'])

    def test_on_the_pages_are_built_and_in_the_nav(self):
        self.site.pages(records=True, stories=True)
        self.site.story('first')
        self.ok()
        for f in ('family-tree.html', 'map.html', 'ask.html', 'stories.html', 'records.html', 'story-first.html'):
            self.assertTrue(self.site.has(f), f)
        links = self.nav_links()
        for f in ('family-tree.html', 'map.html', 'stories.html', 'records.html'):
            self.assertIn(f, links)

    def test_off_a_page_is_not_built_not_in_the_nav_and_nothing_engine_made_links_to_it(self):
        self.site.pages(tree=False)
        log = self.ok()
        self.assertFalse(self.site.has('family-tree.html'))
        for page in ('index.html', 'map.html', 'ask.html', 'moreau.html'):
            self.assertNotIn('family-tree.html', self.nav_links(page), page)
        cfgjs = self.site.text('site-config.js')
        self.assertNotIn('family-tree.html', cfgjs)
        self.assertIsNone(json.loads(cfgjs.split('window.FamilySite = ')[1].rstrip(';\n'))['pages']['tree'])
        self.assertIn('family-tree.html', log, 'the site is told that its own pages still link to the page that is off')
        self.assertIn('turned off', log)
        for name in ('index.html', 'moreau.html'):
            self.assertNotRegex(self.site.text(name), r'href="family-tree\.html', name)
        self.assertIn('The family tree', self.site.text('index.html'), 'the words stay, the link goes')
        for name in os.listdir(os.path.join(self.site.out, 'archive')):
            if name.startswith('kb-'):
                kb = json.loads(self.site.text('archive', name))
                self.assertIsNone(kb['site']['pages']['tree'])
                self.assertNotIn('family-tree.html', json.dumps(kb['places']))

    def test_unlinking_touches_only_links_to_pages_that_are_off(self):
        import pages
        off = {'map.html': 'map'}
        src = '<p><a class="x" href="map.html#top">the <b>map</b></a> and <a href="map.html?person=a">again</a> and <a href=\'map.html\'>single</a> and <a href="family-tree.html">tree</a> and <a href="old-map.html">old</a></p>'
        out = pages.unlink_off_pages(src, off)
        self.assertEqual(out, '<p>the <b>map</b> and again and single and <a href="family-tree.html">tree</a> and <a href="old-map.html">old</a></p>')
        self.assertEqual(pages.unlink_off_pages(src, {}), src)

    def test_off_with_an_object_keeps_the_settings_and_drops_the_page(self):
        self.site.config(lambda c: c['pages']['map'].update({'enabled': False}))
        self.ok()
        self.assertFalse(self.site.has('map.html'))
        self.assertNotIn('map.html', self.nav_links())

    def test_every_page_off_leaves_the_home_page(self):
        self.site.pages(tree=False, map=False, ask=False, stories=False, records=False, discoveries=False)
        self.ok()
        self.assertTrue(self.site.has('index.html'))
        self.assertEqual(self.nav_links(), ['index.html', 'moreau.html'] if self.site.has('moreau.html') else ['index.html'])

    def test_home_cannot_be_turned_off(self):
        self.site.config(lambda c: c['pages'].update({'home': False}))
        code, log = self.site.build()
        self.assertNotEqual(code, 0)
        self.assertIn('home page cannot be turned off', log)

    def test_a_missing_key_does_not_change_a_site(self):
        # the sample says nothing about stories, records or discoveries: it gets none of them
        self.ok()
        for f in ('stories.html', 'records.html', 'discoveries.html', 'admin'):
            self.assertFalse(self.site.has(f), f)
        for f in ('admin.js', 'admin.css', 'content-pages.css', 'timeline.js'):
            self.assertFalse(self.site.has(*(BASE + f).split('/')), f)
        self.assertEqual(self.nav_links(), ['index.html', 'family-tree.html', 'map.html', 'moreau.html', 'ask.html'])

    def test_stories_default_to_on_and_appear_when_the_site_has_one(self):
        self.site.story('first', title='First')
        self.ok()
        self.assertTrue(self.site.has('stories.html'))
        self.assertIn('stories.html', self.nav_links())

    def test_stories_off_hides_them_even_when_there_are_some(self):
        self.site.story('first')
        self.site.pages(stories=False)
        self.ok()
        self.assertFalse(self.site.has('stories.html'))
        self.assertFalse(self.site.has('story-first.html'))
        self.assertNotIn('stories.html', self.nav_links())
        self.assertFalse(self.site.has('content'), 'the Markdown is never published as it is')

    def test_records_need_to_be_asked_for(self):
        self.ok()
        self.assertFalse(self.site.has('records.html'))
        self.site.pages(records=True)
        self.ok()
        self.assertTrue(self.site.has('records.html'))

    def test_the_older_timeline_setting_still_works(self):
        self.site.config(lambda c: c.update({'timeline': {'enabled': True}}))
        self.ok()
        self.assertTrue(self.site.has('discoveries.html'))
        self.assertIn('discoveries.html', self.nav_links())

    def test_pages_discoveries_wins_over_the_older_setting(self):
        self.site.config(lambda c: c.update({'timeline': {'enabled': True}}))
        self.site.pages(discoveries=False)
        self.ok()
        self.assertFalse(self.site.has('discoveries.html'))
        self.assertNotIn('discoveries.html', self.nav_links())
        self.assertFalse(self.site.has('discoveries'), 'no history is kept for a page that is off')
        self.assertFalse(self.site.has(*(BASE + 'timeline.js').split('/')))
        self.site.config(lambda c: c.update({'timeline': {'enabled': False}}))
        self.site.pages(discoveries=True)
        self.ok()
        self.assertTrue(self.site.has('discoveries.html'))

    def test_a_nav_link_to_a_page_that_was_never_there_is_still_an_error(self):
        self.site.pages(tree=None)
        code, log = self.site.build()
        self.assertNotEqual(code, 0)
        self.assertIn('nav[1] links to family-tree.html, but pages.tree is off', log)

    def test_false_removes_the_nav_link_but_the_site_can_keep_the_comment_items(self):
        self.site.config(lambda c: c['nav'].append({'comment': 'kept'}))
        self.site.pages(map=False)
        self.ok()
        self.assertIn('<!-- kept -->', self.site.text('index.html'))

    def test_a_sitemap_the_site_keeps_loses_the_pages_that_are_off(self):
        self.site.write('sitemap.xml', '<?xml version="1.0"?>\n<urlset>\n<url><loc>https://x.org/s/</loc></url>\n<url><loc>https://x.org/s/family-tree.html</loc></url>\n'
                        '<url><loc>https://x.org/s/map.html</loc></url>\n<url><loc>https://x.org/s/admin/</loc></url>\n</urlset>\n')
        self.site.pages(tree=False)
        self.site.config(lambda c: c.update({'admin': {'enabled': True, 'repo': 'o/r'}}))
        log = self.ok()
        xml = self.site.text('sitemap.xml')
        self.assertNotIn('family-tree.html', xml)
        self.assertNotIn('/admin', xml)
        self.assertIn('map.html', xml)
        self.assertIn('https://x.org/s/</loc>', xml)
        self.assertIn('removed the entry', log)

    def test_a_sitemap_is_untouched_when_nothing_is_off(self):
        text = '<urlset>\n<url><loc>https://x.org/s/map.html</loc></url>\n</urlset>\n'
        self.site.write('sitemap.xml', text)
        self.ok()
        self.assertEqual(self.site.text('sitemap.xml'), text)


# ---------------------------------------------------------------------------------------------- stories
class TestMarkdown(unittest.TestCase):
    def test_what_stories_need(self):
        h = markdown.render('# Title\n\nSome **bold**, *italic* and `code`.\n\n- one\n- two\n\n1. a\n2. b\n\n> quoted\n\n---\n\n![alt](images/a.png)')
        for part in ('<h2>Title</h2>', '<strong>bold</strong>', '<em>italic</em>', '<code>code</code>', '<ul>', '<ol>', '<blockquote>', '<hr>', '<img src="images/a.png" alt="alt" loading="lazy">'):
            self.assertIn(part, h)

    def test_nothing_the_author_types_can_run(self):
        h = markdown.render('<script>alert(1)</script> <img src=x onerror=alert(1)>\n\n[bad](javascript:alert(1)) [data](data:text/html,x) [ok](https://example.org/a?b=1&c=2) [rel](page.html) [up](../secret.html)\n\n![x](javascript:alert(1))')
        self.assertNotIn('<script', h)
        self.assertNotIn('<img src=x', h)
        self.assertNotIn('href="javascript', h)
        self.assertNotIn('href="data:', h)
        self.assertNotIn('../secret', h)
        self.assertIn('&lt;script&gt;', h)
        self.assertIn('<a href="https://example.org/a?b=1&amp;c=2" rel="noopener">ok</a>', h)
        self.assertIn('<a href="page.html">rel</a>', h)
        self.assertNotIn('<img src="javascript', h)

    def test_words_with_underscores_are_not_italic(self):
        self.assertNotIn('<em>', markdown.render('a snake_case_name here'))


class TestStories(Case):
    def test_front_matter(self):
        meta, body = stories.front_matter('---\ntitle: "A: b"\npeople: [a, b]\ncover: x.jpg\ndraft: false\n# a comment\ntags:\n  - x\n---\nBody\n')
        self.assertEqual(meta, {'title': 'A: b', 'people': ['a', 'b'], 'cover': 'x.jpg', 'draft': False, 'tags': ['x']})
        self.assertEqual(body, 'Body\n')
        self.assertEqual(stories.front_matter('No settings')[0], None)

    def test_dates(self):
        self.assertEqual(stories.date_info('1923')[1:], ('1923', '1923'))
        self.assertEqual(stories.date_info('1923-04')[1], 'April 1923')
        self.assertEqual(stories.date_info('1923-04-02')[1], '2 April 1923')
        self.assertIsNone(stories.date_info('1923-13'))
        self.assertIsNone(stories.date_info('1923-02-30'))
        self.assertIsNone(stories.date_info('last spring'))

    def test_the_list_is_newest_first_and_the_undated_go_last(self):
        for name, date in (('a-old', '1901'), ('b-new', '1990-05-01'), ('c-mid', '1950-01')):
            self.site.story(name, title=name, date=date)
        self.site.story('d-none', title='d-none')
        self.ok()
        order = re.findall(r'<h2><a href="(story-[^"]+)"', self.site.text('stories.html'))
        self.assertEqual(order, ['story-b-new.html', 'story-c-mid.html', 'story-a-old.html', 'story-d-none.html'])

    def test_a_story_page(self):
        self.site.story('crossing', title='The Crossing', date='1923-04-02', cover='images/people/arthur-hartley.png', coverAlt='Arthur',
                        people='[arthur-hartley, marguerite-moreau]', body='# Leaving\n\nHe **sailed**.')
        self.ok()
        page = self.site.text('story-crossing.html')
        self.assertIn('<h1>The Crossing</h1>', page)
        self.assertIn('<time datetime="1923-04-02">2 April 1923</time>', page)
        self.assertIn('<img src="images/people/arthur-hartley.png" alt="Arthur" loading="lazy">', page)
        self.assertIn('<a href="family-tree.html#/person/arthur-hartley">Arthur Hartley</a>', page)
        self.assertIn('<h2>Leaving</h2>', page)
        self.assertIn('<title>The Crossing | Hartley &amp; Moreau</title>', page)
        self.assertIn('class="active" aria-current="page">Stories', page)
        self.assertIn(BASE + 'content-pages.css', page)
        self.assertIn('site-config.js', page)

    def test_people_tags_do_not_link_to_a_tree_that_is_off(self):
        self.site.story('crossing', people='[arthur-hartley]')
        self.site.pages(tree=False)
        self.ok()
        page = self.site.text('story-crossing.html')
        self.assertIn('<span>Arthur Hartley</span>', page)
        self.assertNotIn('family-tree.html', page)

    def test_living_people_and_hidden_groups_get_no_tag(self):
        by = stories.people_by_id(self.site.dir, sitecfg.load(self.site.dir))
        living = next(i for i, p in by.items() if p.get('isLiving'))
        hidden = next(i for i, p in by.items() if p.get('region') == 'legend' or p.get('region') == 'associates')
        self.site.story('both', people='[%s, %s, arthur-hartley]' % (living, hidden))
        log = self.ok()
        page = self.site.text('story-both.html')
        self.assertIn('Arthur Hartley', page)
        self.assertNotIn('/person/%s"' % living, page)
        self.assertNotIn('/person/%s"' % hidden, page)
        self.assertNotIn(by[living]['displayName'], page)
        self.assertIn('is not tagged', log)

    def test_mistakes_stop_the_build_with_the_file_named(self):
        for name, body, want in (
                ('no-title', '---\nsummary: x\n---\nText', 'a story needs a title'),
                ('bad-date', '---\ntitle: T\ndate: last spring\n---\nText', 'must be like 1923'),
                ('no-settings', 'Just text', 'must start with a block of settings'),
                ('ghost', '---\ntitle: T\npeople: [nobody-here]\n---\nText', 'who is not in people.json')):
            shutil.rmtree(os.path.join(self.site.dir, 'content'), ignore_errors=True)
            self.site.write('content/stories/%s.md' % name, body)
            code, log = self.site.build()
            self.assertNotEqual(code, 0, name)
            self.assertIn(want, log, name)
            self.assertIn('content/stories/%s.md' % name, log)

    def test_two_files_that_make_the_same_page_are_refused(self):
        self.site.story('Same Name', title='A')
        self.site.story('same-name', title='B')
        code, log = self.site.build()
        self.assertNotEqual(code, 0)
        self.assertIn('story-same-name.html', log)

    def test_a_draft_is_not_published(self):
        self.site.story('secret', title='Secret plan', draft='true')
        self.site.story('shown', title='Shown')
        self.ok()
        self.assertFalse(self.site.has('story-secret.html'))
        self.assertNotIn('Secret plan', self.site.text('stories.html'))
        self.assertTrue(self.site.has('story-shown.html'))

    def test_a_site_page_with_the_same_name_is_not_overwritten(self):
        self.site.write('stories.html', '<html></html>')
        self.site.pages(stories=True)
        code, log = self.site.build()
        self.assertNotEqual(code, 0)
        self.assertIn('already has stories.html', log)

    def test_the_text_is_escaped_in_titles_and_summaries(self):
        self.site.story('x', title='A <b>bold</b> & "title"', summary='<i>hi</i>')
        self.ok()
        self.assertNotIn('<b>bold', self.site.text('stories.html'))
        self.assertIn('A &lt;b&gt;bold&lt;/b&gt; &amp; &quot;title&quot;', self.site.text('stories.html'))

    def test_a_long_dash_in_a_story_is_a_warning_not_a_change(self):
        self.site.write('content/stories/dash.md', '---\ntitle: Dash\n---\nOne %s two.\n' % chr(0x2014))
        log = self.ok()
        self.assertIn('em or en dash', log)
        self.assertIn(chr(0x2014), self.site.text('story-dash.html'), 'the author\'s words are not rewritten')

    def test_explicit_on_with_no_stories_says_so(self):
        self.site.pages(stories=True)
        self.ok()
        self.assertIn('no stories here yet', self.site.text('stories.html').replace('There are no', 'there are no').lower().replace('there are', 'there are'))

    def test_prev_and_next(self):
        self.site.story('one', title='One', date='1900')
        self.site.story('two', title='Two', date='1950')
        self.ok()
        self.assertIn('href="story-one.html"', self.site.text('story-two.html'))
        self.assertIn('class="cp-older"', self.site.text('story-two.html'))
        self.assertIn('class="cp-newer"', self.site.text('story-one.html'))


# ---------------------------------------------------------------------------------------------- records and research
class TestRecords(Case):
    def test_sources_are_listed_by_kind_with_where_they_are_kept(self):
        self.site.pages(records=True)
        self.ok()
        page = self.site.text('records.html')
        src = json.loads(read(self.site.dir, 'data', 'sources.json'))['sources']
        self.assertIn('%d record' % len(src), page)
        for s in src[:3]:
            self.assertIn(s['title'], page.replace('&amp;', '&'))
        self.assertIn('Census', page)
        self.assertIn('class="active" aria-current="page">Records', page)

    def test_open_questions_are_listed_for_people_the_site_shows(self):
        self.site.pages(records=True)
        self.ok()
        page = self.site.text('records.html')
        self.assertIn('Was Pierre Moreau his cousin?', page)
        self.assertIn('family-tree.html#/person/jean-baptiste-moreau', page)

    def test_a_living_persons_questions_are_never_listed(self):
        def fn(doc):
            for p in doc['people']:
                if p.get('isLiving'):
                    p['openQuestions'] = [{'question': 'A private question about someone living'}]
                    break
        p = os.path.join(self.site.dir, 'data', 'people.json')
        doc = json.loads(read(p)); fn(doc)
        with open(p, 'w', encoding='utf-8') as f: json.dump(doc, f)
        self.site.pages(records=True)
        self.ok()
        self.assertNotIn('private question', self.site.text('records.html'))

    def test_a_site_with_no_sources_gets_an_honest_page(self):
        p = os.path.join(self.site.dir, 'data', 'sources.json')
        doc = json.loads(read(p)); doc['sources'] = []
        with open(p, 'w', encoding='utf-8') as f: json.dump(doc, f)
        self.site.pages(records=True)
        self.ok()
        self.assertIn('No records have been added', self.site.text('records.html'))

    def test_text_is_escaped(self):
        p = os.path.join(self.site.dir, 'data', 'sources.json')
        doc = json.loads(read(p)); doc['sources'][0]['title'] = '<script>x</script>'; doc['sources'][0]['url'] = 'javascript:alert(1)'
        with open(p, 'w', encoding='utf-8') as f: json.dump(doc, f)
        self.site.pages(records=True)
        self.ok()
        page = self.site.text('records.html')
        self.assertNotIn('<script>x', page)
        self.assertNotIn('href="javascript', page)


# ---------------------------------------------------------------------------------------------- the settings page
class TestAdminPage(Case):
    def turn_on(self, **kw):
        self.site.config(lambda c: c.update({'admin': dict({'enabled': True, 'repo': 'Belfiore/sample-site'}, **kw)}))

    def test_a_site_that_does_not_turn_it_on_has_none(self):
        self.ok()
        self.assertFalse(self.site.has('admin'))
        self.assertFalse(self.site.has(*(BASE + 'admin.js').split('/')))

    def test_the_page_is_made_hidden_and_out_of_the_nav_and_the_search_index(self):
        self.turn_on()
        self.ok()
        page = self.site.text('admin', 'index.html')
        self.assertIn('<meta name="robots" content="noindex, nofollow, noarchive">', page)
        self.assertIn("connect-src https://api.github.com", page)
        self.assertIn("script-src 'self'", page)
        self.assertNotIn('main-nav', page)
        self.assertNotIn('stuart', page.lower())
        for f in os.listdir(self.site.out):
            if f.endswith('.html'): self.assertNotIn('admin', ' '.join(self.nav_links(f)), f)
        self.assertNotIn('admin', self.site.text('site-config.js'))
        for name in os.listdir(os.path.join(self.site.out, 'archive')):
            self.assertNotIn('admin/', self.site.text('archive', name))
        self.assertTrue(self.site.has(*(BASE + 'admin.js').split('/')))
        self.assertIn('../' + BASE + 'admin.js', page)

    def test_the_page_carries_the_pages_and_the_repository(self):
        self.turn_on()
        self.site.pages(map=False)
        self.ok()
        page = self.site.text('admin', 'index.html')
        data = json.loads(re.search(r'<script type="application/json" id="ad-data">(.*?)</script>', page, re.S).group(1))
        self.assertEqual(data['repo'], 'Belfiore/sample-site')
        self.assertEqual([p['key'] for p in data['pages']], ['home', 'stories', 'tree', 'map', 'records', 'discoveries'])
        on = {p['key']: p['on'] for p in data['pages']}
        self.assertEqual(on, {'home': True, 'stories': True, 'tree': True, 'map': False, 'records': False, 'discoveries': False})
        self.assertTrue(next(p for p in data['pages'] if p['key'] == 'home')['locked'])

    def test_the_repository_can_come_from_the_build(self):
        self.site.config(lambda c: c.update({'admin': {'enabled': True}}))
        self.ok(env={'GITHUB_REPOSITORY': 'Belfiore/from-env'})
        self.assertIn('Belfiore/from-env', self.site.text('admin', 'index.html'))

    def test_the_words_of_the_site_cannot_break_out_of_the_page(self):
        self.turn_on()
        self.site.config(lambda c: c['site'].update({'name': '</script><script>alert(1)</script>', 'description': 'a & b <!-- c'}))
        self.ok()
        page = self.site.text('admin', 'index.html')
        self.assertNotIn('<script>alert', page)
        self.assertEqual(page.count('<script'), 2)

    def test_no_token_or_secret_is_in_the_page_or_the_script(self):
        self.turn_on()
        self.ok()
        for text in (self.site.text('admin', 'index.html'), read(ROOT, 'engine', 'admin.js')):
            self.assertNotRegex(text, r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}')
        js = read(ROOT, 'engine', 'admin.js')
        self.assertNotRegex(js, r'console\.\w+\(', 'nothing is logged')
        self.assertNotIn('localStorage', js, 'the token is kept in this tab only')
        self.assertNotIn('location.search', js)
        self.assertNotIn('location.hash', js)
        self.assertEqual(js.count("'https://api.github.com'"), 1, 'the token is sent to one address only')
        self.assertNotIn('innerHTML', js, 'what comes from GitHub or the site is never put in as HTML')

    def test_a_site_that_already_has_an_admin_folder_is_not_overwritten(self):
        self.turn_on()
        self.site.write('admin/index.html', '<p>x</p>')
        code, log = self.site.build()
        self.assertNotEqual(code, 0)
        self.assertIn('admin/', log)


# ---------------------------------------------------------------------------------------------- the schema
class TestSchema(unittest.TestCase):
    def schema(self, name):
        with open(os.path.join(ROOT, 'schema', name), encoding='utf-8') as f: return json.load(f)

    def check(self, pages):
        root = self.schema('pages.schema.json')
        c = validate.Checker(root)
        c.check(pages, root, 'pages')
        return c.errors, c.warnings

    def test_the_standalone_schema_matches_the_one_inside_site_config(self):
        a = self.schema('pages.schema.json')
        b = self.schema('site-config.schema.json')['properties']['pages']
        a = {k: v for k, v in a.items() if not k.startswith('$') and k != 'title'}
        self.assertEqual(a, b)

    def test_good_blocks(self):
        for pages in ({}, {'home': 'index.html'}, {'home': True}, {'stories': True, 'tree': True, 'map': True, 'records': True, 'discoveries': True},
                      {'tree': False, 'map': None, 'ask': 'ask.html'}, {'tree': {'file': 'a/b.html', 'enabled': False, 'title': 't'}},
                      {'stories': {'enabled': True, 'title': 'Our stories', 'heading': 'Stories'}}, {'records': {'file': 'research.html'}},
                      {'home': 'index.html', 'tree': {'file': 'tree-canvas.html', 'title': 'x', 'stylesheets': ['styles.css']}}):
            e, _ = self.check(pages)
            self.assertEqual(e, [], pages)

    def test_bad_blocks(self):
        for pages, why in (({'stories': 'stories.html'}, 'stories'), ({'discoveries': 'yes'}, 'discoveries'), ({'tree': 1}, 'tree'),
                           ({'home': 5}, 'home'), ({'records': {'enabled': 'no'}}, 'records'), ({'map': {'file': 3}}, 'map'),
                           ({'discoveries': {'enabled': True}}, 'discoveries'), ({'stories': None}, 'stories')):
            e, _ = self.check(pages)
            self.assertTrue(any(why in x for x in e), (pages, e))

    def test_a_key_the_schema_does_not_know_is_a_warning(self):
        e, w = self.check({'blog': True})
        self.assertEqual(e, [])
        self.assertTrue(any('blog' in x for x in w))

    def test_every_site_config_in_the_repository_passes(self):
        for rel in ('sample/site.config.json',):
            with open(os.path.join(ROOT, rel), encoding='utf-8') as f: cfg = json.load(f)
            root = self.schema('pages.schema.json')
            c = validate.Checker(root)
            c.check(cfg['pages'], root, 'pages')
            self.assertEqual(c.errors, [], rel)

    def test_the_site_config_schema_knows_admin(self):
        root = self.schema('site-config.schema.json')
        c = validate.Checker(root)
        c.check({'schemaVersion': 1, 'site': {'name': 'x'}, 'nav': [], 'admin': {'enabled': True, 'repo': 'o/r', 'branch': 'main'}}, root, 's')
        self.assertEqual(c.errors, [])
        c = validate.Checker(root)
        c.check({'schemaVersion': 1, 'site': {'name': 'x'}, 'nav': [], 'admin': {'enabled': True, 'repo': 'not a repo'}}, root, 's')
        self.assertTrue(c.errors)


# ---------------------------------------------------------------------------------------------- housekeeping
class TestHousekeeping(unittest.TestCase):
    def test_the_build_workflow_reads_the_effective_timeline_setting(self):
        text = read(ROOT, '.github', 'workflows', 'build-site.yml')
        self.assertIn("get('discoveries')", text)
        self.assertIn("(cfg.get('timeline') or {}).get('enabled') is True", text)

    def test_ci_validates_the_pages_schema_and_runs_these_tests(self):
        text = read(ROOT, '.github', 'workflows', 'ci.yml')
        self.assertIn('tests/test_pages.py', text)
        self.assertIn('tests/check-admin-edit.js', text)

    def test_the_new_engine_files_have_no_long_dashes(self):
        bad = []
        for rel in ('engine/admin.js', 'engine/admin.css', 'engine/content-pages.css', 'templates/admin.html', 'templates/stories.html', 'templates/records.html',
                    'build/markdown.py', 'build/stories.py', 'build/records_page.py', 'build/admin_page.py', 'schema/pages.schema.json'):
            if re.search('[' + chr(0x2013) + chr(0x2014) + ']', read(ROOT, rel)): bad.append(rel)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
