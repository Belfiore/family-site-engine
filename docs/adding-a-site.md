# Adding a site

From an empty repository to a family site that is built with the engine and published on GitHub Pages. The made-up family in `sample/` is a complete site to copy from.

## 1. The repository

A site is its own GitHub repository, public or private (GitHub Pages on a private repository needs a paid plan). It holds only the family's things:

```
site.config.json        the settings (docs/site-config.md)
data/people.json        the family (docs/data-format.md)
data/sources.json
data/places.json        only if the site has a map
index.html              the home page, and any story pages
images/ ...             photographs and records
styles.css              the site's own look for its own pages
tests/                  the site's own checks (optional)
.github/workflows/deploy.yml
```

No engine file goes in the site. If the site's pages came from before the engine, they can keep their old `<nav>` blocks and their references to `nav.css`, `stuart.js` and the rest: the build replaces or removes them.

## 2. The settings

Copy `sample/site.config.json` and change it for the family. At the least: `site.name`, `site.familyName`, `nav`, and which pages the site has (`pages.tree`, `pages.map`, `pages.ask`, each a file name or `null`). Set `engine.channel` to `stable` unless the site is meant to try releases early.

## 3. The data

Write `data/people.json` and `data/sources.json` in the [format](data-format.md), and `data/places.json` if the site has a map. Data from before the engine can be brought up to date with:

```sh
python3 path/to/engine/build/migrate.py --site .            # shows what would change
python3 path/to/engine/build/migrate.py --site . --write    # changes the files
```

A site whose tree is kept in a `family-data.js` file (`const FAMILY_DATA = { people: [...], relationships: [...] }`, the format some of the first sites used) can be converted. The file is read as data, not run:

```sh
python3 path/to/engine/build/convert_family_data.py --input family-data.js --out data
```

It prints what it did (how confidence grades were mapped, how many placeholders it kept); read that before going on.

Then check it:

```sh
python3 path/to/engine/build/validate.py --site .
```

Fix every error. Read the warnings: each one is either a real gap in the data or something to accept knowingly.

## 4. Build and look at it

With a copy of this repository next to the site:

```sh
python3 path/to/engine/build/build_site.py --site . --out _site
python3 -m http.server -d _site 8000        # then open http://localhost:8000
```

Add `_site/` to the site's `.gitignore`. The build is never committed: GitHub builds it on every publish.

## 5. Publishing

In the site's repository, under **Settings > Pages**, set **Source** to **GitHub Actions**. Then add `.github/workflows/deploy.yml`:

```yaml
name: Build and publish the site

on:
  push:
    branches: [main]
  repository_dispatch:
    types: [engine-release]
  workflow_dispatch:
    inputs:
      engine-version:
        description: Build with this engine version instead of the channel (for a rollback). Leave empty to follow the channel.
        required: false
        default: ''

permissions:
  contents: read
  pages: write
  id-token: write
  actions: read

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  site:
    uses: Belfiore/family-site-engine/.github/workflows/build-site.yml@v1.0.0
    with:
      engine-version: ${{ inputs.engine-version || '' }}
      # the site's own checks, run against the build before it is published (optional)
      site-tests: |
        node tests/verify-canvas.js
```

- `branches` is the branch the live site comes from. Only that branch should publish.
- `@v1.0.0` is the release whose build workflow the site uses. It only changes when a release changes that workflow (see [releases](releasing.md)); the engine version the site builds with comes from its channel.
- The four `permissions` are what publishing needs: `pages` and `id-token` to publish, and `actions: read` so the publishing step can find the built site it was handed.
- If the site's files are in a folder of the repository rather than at the top, add `site-dir: that-folder`.
- `site-tests` are run from the site folder with `DIST` set to the built site. A test can find the build with `process.env.DIST`.
- `repository_dispatch` is how the engine tells the site that its channel moved (see [releases](releasing.md)). It only works on the repository's default branch.

A push to `main` now checks the data, builds the site, runs the site's checks and publishes it. If any step fails, nothing is published and the live site stays as it was; the run's page in the **Actions** tab says what failed.

## 6. Tell the engine about the site

Add the repository to `sites.json` in this repository, so it is told when a release reaches its channel:

```json
{ "repo": "Belfiore/new-family-site", "name": "The New family", "channel": "stable" }
```

The token that sends those messages (`SITES_DISPATCH_TOKEN`, see [releases](releasing.md)) must be able to reach the new repository too.

## Checklist

- [ ] `python3 path/to/engine/build/validate.py --site .` shows no errors
- [ ] the site builds and looks right locally
- [ ] Pages source is GitHub Actions; `deploy.yml` publishes only from the live branch
- [ ] map keys, if any, are restricted to the site's address ([map keys](map-keys.md))
- [ ] the site is in `sites.json`, and the dispatch token can reach it
