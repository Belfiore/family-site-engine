# Family site engine

The shared engine behind the family history sites: the family tree, the family map, Stuart (the family archivist) and the navigation bar. Each family's site keeps its own data, photographs, stories and look in its own repository; this repository holds the code they all run, and the build that puts the two together.

A fix or a new feature made here reaches every site through a release, without anyone copying files between repositories.

## How it fits together

```
 site repository (one per family)          this repository
 ──────────────────────────────            ───────────────
 site.config.json   what the site has      engine/     the tree, map, Stuart, nav
 data/              people, sources,       templates/  the tree, map and Stuart pages
                    places                 build/      check the data, build the site
 images/, pages     the family's own       schema/     the data format and the settings
 tests/             the site's checks      channels.json   which version each channel gets
        │                                         │
        └──────────────► GitHub Actions ◄─────────┘
                 1. pick the engine version (the site's channel, or a pin)
                 2. check the data against the schema and against itself
                 3. build: site files + engine/<version>/ + pages + Stuart's index
                 4. run the site's own checks on the build
                 5. publish to GitHub Pages (only if every step passed)
```

The built site is a plain static site. Nothing in it loads code from anywhere else at run time, so a copy of it keeps working on its own, on GitHub Pages or any other static host.

## What is here

| Folder | What it holds |
| --- | --- |
| `engine/` | Everything the browser runs: `tree-canvas.js` (the family tree), `map-*.js` (the family map), `stuart.js` and `archive-*.js` (Stuart), `nav.js` and `nav.css` (the navigation bar), `records.js` (the lightbox), `tokens.css` (default colours and fonts), MapLibre, the map styles and the map fonts |
| `templates/` | The family tree, map and Stuart pages, filled in from each site's settings |
| `build/` | `build_site.py` (the build), `validate.py` (the data checker), `migrate.py` (brings older data up to date), `archive.py` (Stuart's index), `pages.py` and `sitecfg.py` |
| `schema/` | `family-data.schema.json` (people, sources, places) and `site-config.schema.json` (a site's settings) |
| `sample/` | A made-up family that the tests run against, and a starting point for a new site |
| `tests/` | `test_build.py` (the build, the checker, the migration) and `check-sample.js` (the sample in a browser) |
| `tools/` | Map fonts, map styles, Street View viewpoints |
| `docs/` | How to add a site, the data format, the settings, releases, and how the map and Stuart work |
| `channels.json`, `sites.json` | Which engine version each release channel builds with, and which sites to tell when that changes |

## Try it

```sh
python3 build/build_site.py --site sample --out _site     # build the sample family
python3 -m http.server -d _site 8000                      # then open http://localhost:8000
```

To check your own changes:

```sh
python3 tests/test_build.py          # the build, the data checker and the migration (Python only)
npm ci && npx playwright install chromium
node tests/check-sample.js           # the sample site in a browser
```

## Documentation

- [Adding a site](docs/adding-a-site.md): from an empty repository to a published site.
- [The data format](docs/data-format.md): `people.json`, `sources.json` and `places.json`, and how they are checked.
- [Site settings](docs/site-config.md): everything `site.config.json` can say.
- [Releases](docs/releasing.md): versions, channels, rolling out and rolling back.
- [The family map](docs/map.md), [map keys](docs/map-keys.md) and [Stuart](docs/stuart.md): how they work inside.

## Licence

All rights reserved; see [LICENSE](LICENSE). The repository is public so that the family sites, which are public, can build from it. MapLibre GL JS and the Cormorant Garamond fonts keep their own licences (`engine/vendor/` and `engine/fonts/OFL.txt`).
