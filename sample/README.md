# The sample site

A made-up family, the Hartleys of Leeds and the Moreaus of Lyon and Soho, built with the engine. Nothing here is a real person: the names, dates, records and pictures were all made up for testing.

It does two jobs:

- **The engine's tests run against it** (`tests/test_build.py` and `tests/check-sample.js`). It uses almost every setting, including the ones the real sites leave off (pictures on cards from a person's media, couples drawn together automatically, a hidden region with a suspected relative kept, living people with dates), so a change that breaks any of them shows up here first.
- **It is a starting point for a new site**: copy `site.config.json`, the data files and a page, and change them for the family. See `docs/adding-a-site.md`.

Build it with:

```sh
python3 build/build_site.py --site sample --out _site
```

This file is not published (`publish.exclude` in `site.config.json`).
