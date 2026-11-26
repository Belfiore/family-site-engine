# CLAUDE.md: family-site-engine

The shared engine behind three public family history sites. Each site keeps its own data, photos, pages and `site.config.json` in its own repo. This repo holds the code they all run and the build that combines the two. Read `README.md` and `docs/` for detail; this file is the working rules.

## Rules for all engine work

1. **Never push to main and never tag or publish a release.** Work on a branch, open a PR, stop. The maintainer merges and releases.
2. **Every change must be backward compatible.** A release reaches all three sites at once. A site that does not use a new feature must build and look exactly as it does today. New settings must be optional, with a default that reproduces current behavior. Do not rename or remove settings, data fields, CSS custom properties, file names or page structure in a minor or patch release. If a site has to change something, that is a major version and needs the maintainer's decision.
3. **Never put living people's details on any public page or map.** The engine does not redact living people by itself (since 1.0.0 they are shown like anyone else, marked as living on the tree). So never add output, example data, tests, fixtures or docs that contain a real living person's name, dates, places or photos. Use the made-up `sample/` family for anything new.
4. **Never commit secrets or API keys.** That includes MapTiler and Google keys, `SITES_DISPATCH_TOKEN`, and tokens in test output. Keys belong in a site's own settings and in GitHub secrets, never here.
5. **No em dashes in any site text.** That covers templates, engine UI strings, Stuart's answers, docs and CHANGELOG entries. Use commas, colons, parentheses or full stops.

## Layout

| Path | What it is |
| --- | --- |
| `engine/` | Everything the browser runs: tree, map, Stuart, nav, lightbox, default tokens, MapLibre, fonts |
| `templates/` | `tree.html`, `map.html`, `ask.html`, filled in from a site's settings |
| `build/` | `build_site.py` (the build), `validate.py`, `migrate.py`, `archive.py`, `pages.py`, `sitecfg.py` |
| `schema/` | `family-data.schema.json` and `site-config.schema.json` |
| `sample/` | Made-up family used by tests and as a starter site |
| `tests/` | `test_build.py` (Python) and `check-sample.js` (Playwright on the sample) |
| `channels.json` | Which engine version each channel (canary, beta, stable) builds with |
| `sites.json` | Sites to notify when `channels.json` changes |
| `VERSION`, `CHANGELOG.md` | Current version and release notes |
| `.github/workflows/` | `ci.yml`, `build-site.yml`, `release.yml`, `notify-sites.yml` |

## How a site is built

Each site's `deploy.yml` calls `build-site.yml@vX.Y.Z` (a reusable workflow, pinned by tag). That workflow:

1. Checks out the site, and `channels.json` from this repo's `main`.
2. Picks the engine version: the `engine-version` input for that run, else `engine.version` in `site.config.json`, else the version its `engine.channel` points to (default `stable`).
3. Checks out this repo at tag `v<version>`.
4. Runs `build/build_site.py --site <site> --out _site`. This validates settings and data against the schemas and runs cross-checks, copies the site, copies `engine/` to `_site/engine/<version>/`, builds the tree, map and Stuart pages from templates, normalizes the site's pages (one nav bar, engine files, Stuart button) and writes Stuart's index. Any error stops the build.
5. Runs the site's own checks (`site-tests`, with `DIST` set to the build).
6. Publishes to GitHub Pages only if all of that passed. On pull requests it runs with `deploy: false`.

Because the workflow is pinned by tag in each site's `deploy.yml` and `check.yml`, a change to `build-site.yml` does not reach sites through a channel. After such a release, each site's two workflows need a PR to bump the tag. Keep changes to that file rare.

## Site settings

`site.config.json` is validated against `schema/site-config.schema.json` (`additionalProperties: false` nearly everywhere). Required: `schemaVersion` (const 1), `site` (with `name`), `nav`. Top-level sections: `engine` (`channel` of stable, beta or canary, or `version` pin which overrides the channel), `site`, `pages` (home, tree, map, ask), `nav`, `head`, `theme` (CSS custom properties written to `site-theme.css`), `data`, `tree`, `map`, `stuart`, `widget`, `publish`, `process`. Document every new key in `docs/site-config.md` and add it to the schema. A new key must be optional.

## Releases

Versions: patch is a fix, minor is something new that needs no site change, major needs site changes (spelled out in CHANGELOG). Full process in `docs/releasing.md`. The maintainer does these steps:

1. Change on a branch, PR, **Checks** (`ci.yml`) passes.
2. Add the CHANGELOG entry and set `VERSION`. Merge.
3. Publish a GitHub release with new tag `vX.Y.Z` on `main`. `release.yml` re-runs checks, verifies tag equals `VERSION`, puts the CHANGELOG notes on the release. No site changes yet.
4. Move `canary` in `channels.json` on `main`. `notify-sites.yml` sends an `engine-release` `repository_dispatch` to every repo in `sites.json` (needs the `SITES_DISPATCH_TOKEN` secret; without it nothing is sent and sites rebuild manually). Each site's workflow rebuilds with whatever its channel now points to.
5. Check the canary site, then move `beta`, then `stable`.

Sites today: English-Family-History (FitzMaurice) is on canary; italian-belfiore-hertiage-lineage (Belfiore) and kohlmann-heritage (Kohlmann) are on stable. A release in use is never deleted or re-tagged; a fix is a new release. Rollback is a channel move in `channels.json`, a per-run `engine-version` input, or an `engine.version` pin in one site.

Claude's part ends at the PR. Do not edit `channels.json` or `sites.json` in a feature PR, and do not bump `VERSION` unless the maintainer asks for it in that PR.

## Checks

```sh
python3 tests/test_build.py
python3 build/validate.py --site sample
npm ci && npx playwright install chromium
node tests/check-sample.js
```

## Previewing an engine change against a real site

`build_site.py` uses the `VERSION` file and the `engine/` folder of the checkout it lives in. It does not read `channels.json`. So running it from the local engine checkout builds a site with your uncommitted engine code. Layout assumed: engine and site checkouts side by side.

```sh
# from the folder that holds both checkouts
python3 family-site-engine/build/build_site.py \
  --site English-Family-History --out preview/fitzmaurice
python3 -m http.server -d preview/fitzmaurice 8000      # open http://localhost:8000
```

Run the site's own checks against that build (from the site folder, with `DIST` pointing at it):

```sh
cd English-Family-History
npm install --no-save --no-package-lock playwright@1.63.0 && npx playwright install chromium
DIST=../preview/fitzmaurice node tests/verify-canvas.js
DIST=../preview/fitzmaurice node tests/verify-map.js
DIST=../preview/fitzmaurice node tests/verify-archive.js
```

Keep `--out` outside the site repo, and never commit to or push from a site repo. Site repos are read-only test beds.

### Backward compatibility check (do this before every PR)

Build each site twice, once with the last release and once with the branch, and compare. With `VERSION` unchanged, the output should be identical for any site that does not use the new feature.

```sh
git -C family-site-engine worktree add ../engine-baseline v$(cat family-site-engine/VERSION)
python3 engine-baseline/build/build_site.py --site English-Family-History --out preview/base
python3 family-site-engine/build/build_site.py --site English-Family-History --out preview/new
diff -r preview/base preview/new
```

Repeat for the Italian and Kohlmann sites when they are checked out. Any difference on a site that did not opt in is a bug. A version bump changes the `engine/<version>/` path, so compare before bumping `VERSION`.

## Style

Plain words, no em dashes, no marketing tone. Match the existing docs and comments.
