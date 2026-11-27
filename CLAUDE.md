# CLAUDE.md: family-site-engine

The shared engine behind three public family history sites. Each site keeps its own data, photos, pages and `site.config.json` in its own repo. This repo holds the code they all run and the build that combines the two. Read `README.md` and `docs/` for detail; this file is the working rules.

## Rules for all engine work

1. **Never push to main and never tag or publish a release by hand.** Work on a branch, open a PR, stop. The maintainer merges, and the automatic release (`auto-release.yml`) does the rest. Do not edit `VERSION`, `CHANGELOG.md` or `channels.json` in a PR.
2. **Every change must be backward compatible.** A release reaches all three sites at once. A site that does not use a new feature must build and look exactly as it does today. New settings must be optional, with a default that reproduces current behavior. Do not rename or remove settings, data fields, CSS custom properties, file names or page structure in a minor or patch release. If a site has to change something, that is a major version and needs the maintainer's decision.
3. **Never put living people's details on any public page or map.** The engine does not redact living people by itself (since 1.0.0 they are shown like anyone else, marked as living on the tree). So never add output, example data, tests, fixtures or docs that contain a real living person's name, dates, places or photos. Use the made-up `sample/` family for anything new.
4. **Never commit secrets or API keys.** That includes MapTiler and Google keys, `SITES_DISPATCH_TOKEN`, and tokens in test output. Keys belong in a site's own settings and in GitHub secrets, never here.
5. **No em dashes in any site text.** That covers templates, engine UI strings, Stuart's answers, docs and CHANGELOG entries. Use commas, colons, parentheses or full stops.
6. **Private access and visitor identity stay optional and separate.** Both are off by default, and a site with them off must build byte for byte as before. The family password is never a setting, a build input or a file: only the `SITE_PASSWORD` secret. See [Private access and visitor identity](#private-access-and-visitor-identity).

## Layout

| Path | What it is |
| --- | --- |
| `engine/` | Everything the browser runs (the words are in `engine/i18n/en.json` and `de.json`): tree, map, Stuart, nav, lightbox, default tokens, MapLibre, fonts, `kinship.js` (how two people are related: the only code that works it out), `map-viewpoint.js`, `source-preview.js` and `.css`, and `visitor.js`, `visitor-match.js`, `visitor.css` ("Who are you?", copied only when `visitor.enabled`) |
| `templates/` | `tree.html`, `map.html`, `ask.html`, `timeline.html`, filled in from a site's settings; `gate-worker.js`, `gate.html`, `gate.js` (the password gate, built into `_worker.js` only when `access.enabled`) |
| `build/` | `build_site.py` (the build), `i18n.py` (languages: the dictionaries written into the scripts, dates, plurals), `validate.py`, `migrate.py`, `archive.py`, `pages.py`, `sitecfg.py`, and the Discovery Timeline: `discoveries.py` (detection), `timeline.py` (history between builds), `timeline_page.py` (the page), `previous_site.py` (fetches the live history), and private access: `access.py` (settings checks for `access` and `visitor`, and the gate build) |
| `schema/` | `family-data.schema.json` and `site-config.schema.json` |
| `sample/` | Made-up family used by tests and as a starter site |
| `tests/` | `test_build.py` and `test_discoveries.py` (Python), `test_access.py` (Python), `test_i18n.py` (Python), `check-i18n.js` (Playwright, with `i18n_fixtures.py`), `check-sample.js`, `check-timeline.js`, `check-gate.js`, `check-visitor.js`, `check-access.js` and `check-map-relations.js` (Playwright and Node), `timeline_fixtures.py` (seven made-up versions of a family), `access_fixtures.py` (the sample with access and visitor on, plus extra made-up people), `gate-server.js` (runs the real `_worker.js` locally), `helpers.js` |
| `tools/` | Map fonts and styles, Street View viewpoints, `backfill-discoveries.py` |
| `channels.json` | Which engine version each channel (canary, beta, stable) builds with |
| `sites.json` | Sites to notify when `channels.json` changes |
| `VERSION`, `CHANGELOG.md` | Current version and release notes |
| `.github/workflows/` | `ci.yml`, `build-site.yml`, `auto-release.yml`, `release.yml`, `notify-sites.yml` |

## How a site is built

Each site's `deploy.yml` calls `build-site.yml@vX.Y.Z` (a reusable workflow, pinned by tag). That workflow:

1. Checks out the site, and `channels.json` from this repo's `main`.
2. Picks the engine version: the `engine-version` input for that run, else `engine.version` in `site.config.json`, else the version its `engine.channel` points to (default `stable`).
3. Checks out this repo at tag `v<version>`.
4. Runs `build/build_site.py --site <site> --out _site`. This validates settings and data against the schemas and runs cross-checks, copies the site, copies `engine/` to `_site/engine/<version>/`, builds the tree, map and Stuart pages from templates, normalizes the site's pages (one nav bar, engine files, Stuart button) and writes Stuart's index. Any error stops the build.
4b. When the Discovery Timeline is on (`pages.discoveries`, or `timeline.enabled` when that is not set), first reads the live site's `discoveries/state.json` (`build/previous_site.py`) and passes it as `--previous previous`. Without that history the build stops.
5. Runs the site's own checks (`site-tests`, with `DIST` set to the build).
6. Publishes to GitHub Pages only if all of that passed. On pull requests it runs with `deploy: false`.

Because the workflow is pinned by tag in each site's `deploy.yml` and `check.yml`, a change to `build-site.yml` does not reach sites through a channel. After such a release, each site's two workflows need a PR to bump the tag. Keep changes to that file rare.

## Site settings

`site.config.json` is validated against `schema/site-config.schema.json` (`additionalProperties: false` nearly everywhere). Required: `schemaVersion` (const 1), `site` (with `name`), `nav`. Top-level sections: `engine` (`channel` of stable, beta or canary, or `version` pin which overrides the channel), `site`, `pages` (home, stories, tree, map, records, discoveries, ask; see Page toggles below), `admin`, `nav`, `head`, `theme` (CSS custom properties written to `site-theme.css`), `data`, `tree`, `map`, `stuart`, `widget`, `publish`, `process`. Document every new key in `docs/site-config.md` and add it to the schema. A new key must be optional.

## Releases

Versions: patch is a fix, minor is something new that needs no site change, major needs site changes (spelled out in the PR description, which becomes the release note). Full process in `docs/releasing.md`.

A merge to `main` releases by itself (`auto-release.yml`, logic in `tools/autorelease.py`, tests in `tests/test_autorelease.py`):

1. Full checks and a test build of every site in `sites.json`. Any failure stops everything.
2. `VERSION` is bumped (patch by default; the PR label `minor` or `major` raises it; the label `no-release` skips the release), `CHANGELOG.md` gets the merged PRs, tag `vX.Y.Z` and a GitHub release are made.
3. `canary`, `beta` and `stable` in `channels.json` move to the new version. A major release is published but holds the channels and opens an issue.
4. Every site in `sites.json` gets the `engine-release` dispatch.
5. Each site's build and live URL (`200`) are checked. On any failure the channels go back to the previous versions, the sites are dispatched again and an issue lists the failures.

The workflow's own commits carry `[auto-release] [skip ci]` and the workflow ignores them, so it cannot loop. It needs the `RELEASE_TOKEN` secret (a fine-grained token that can push to `main` and read and dispatch the sites); without it the first step fails with a message and nothing changes. Do not remove the `[auto-release]` guard, the `concurrency` block or the stale-main check from the workflow: `tests/test_autorelease.py` reads the file to make sure they stay.

Sites today: English-Family-History (FitzMaurice) is on canary; italian-belfiore-hertiage-lineage (Belfiore) and kohlmann-heritage (Kohlmann) are on stable. A release in use is never deleted or re-tagged; a fix is a new release. Rollback is a channel move in `channels.json` (done automatically after a failed release), a per-run `engine-version` input, or an `engine.version` pin in one site.

Claude's part ends at the PR. If `gh` is not signed in, push nothing: leave the commits on the branch and give the maintainer a bundle and the exact commands. Do not edit `channels.json`, `sites.json`, `CHANGELOG.md` or `VERSION` in a feature PR; the release does that.

## Checks

```sh
python3 tests/test_build.py
python3 tests/test_discoveries.py       # the backfill tests need git
python3 tests/test_autorelease.py
python3 tests/test_access.py            # private access and visitor identity
python3 tests/test_i18n.py              # languages: the dictionaries, the templates, a site without `language` unchanged
python3 build/validate.py --site sample
npm ci && npx playwright install chromium
node tests/check-sample.js
node tests/check-timeline.js            # SHOTS=dir saves screenshots; DIST=path checks a real site's build
node tests/check-gate.js                # the gate worker: every way in without the password
node tests/check-visitor.js             # SHOTS=dir saves screenshots
node tests/check-access.js              # SHOTS=dir for screenshots, VIDEO=dir for recordings of the first visit
node tests/check-i18n.js                # the switcher, German dates, translated fields; SHOTS=dir for screenshots
node tests/check-map-relations.js       # the map's Relationships to, no Street View message, source card and drawer; SHOTS=dir
python3 tests/test_pages.py
node tests/check-admin-edit.js
node tests/check-admin.js               # SHOTS=dir saves screenshots of /admin and a nav with pages off
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

A site that has turned the Discovery Timeline on also needs `--previous`: `--previous none` for a first build or a trial, or the folder of an earlier build (`--previous preview/old`) to see what the next publication would add. The build stops without it, on purpose.

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

## The Discovery Timeline

Optional (`pages.discoveries`, or the older `timeline.enabled`; default off). Full design in `docs/discovery-timeline.md`. What to keep true when changing it:

- **A site that has it off must build byte for byte as before.** The page, the navigation entry, `timeline.css` and `timeline.js`, the `timeline` key of `engine-build.json` and the `discoveries/` files exist only when it is on. `tests/test_discoveries.py` compares a build with and without the engine's change. Do the same `diff -r` on a real site (see the backward compatibility check above).
- **The history is the published site.** `discoveries/state.json` (internal) and `discoveries/history.json` (the page's view) are written by every publication and fetched from the live site by the next one. Do not add a second store. A failed build publishes nothing, so it cannot move the baseline.
- **Fail loudly, never reset.** A missing `--previous`, an unreadable live history or a history from a newer format stops the build. Only a 404 from a live site that never had the timeline is a first activation.
- **Privacy has one door.** `discoveries.is_living` plus `tree.hiddenRegions` decide who is withheld, except that `timeline.showRegions` can release the deceased people of the hidden regions it names (living people are withheld whatever it says, and those finds carry no tree or map link). Withheld people never become claims, are stored only as hashes, and `public_ok` is re-run on every kept find on every build. Anything new that puts a name, a link, a count, a filter value, a picture or a place on the page goes through it. Add the case to `TestPrivacy`.
- **Changing how claims are derived** means bumping `ATOM_SCHEMA`. Sites then rebaseline silently, with no flood.
- **Notes (`discovery` objects, `data/discoveries.json`) override generated finds.** `data/discoveries.json` and `discoveries.suggestions.json` are never copied to the published site.
- **`tools/backfill-discoveries.py` only writes its suggestions file.** Never make it edit data.
- **No dependencies, no network, no model** in detection or headlines. Headlines must be deterministic and contain no long dashes.
- **Tests use made-up data only** (`tests/timeline_fixtures.py`, built from `sample/`). To check real data, build a temporary copy of a site in `/tmp`; never write to a site repo.

## Private access and visitor identity

Two optional, independent features. Full design in `docs/access.md` and `docs/visitor.md`. What to keep true:

- **Off means unchanged.** With `access` and `visitor` absent or not enabled, the build has no `_worker.js`, no `robots.txt` the site did not have, no visitor files, no `access` or `visitor` key in `site-config.js` or `engine-build.json`, and no extra tags in any page. `tests/test_access.py` compares builds; also `diff -r` a real site (see the backward compatibility check). Neither feature switches the other on.
- **A password screen in the browser is not security, and the engine does not offer one.** Genuine protection is the Cloudflare Pages worker (`templates/gate-worker.js`, built to `_worker.js`) that checks a signed cookie before serving any file, with `env.ASSETS.fetch` behind it. GitHub Pages cannot do this and the repository of a protected site must be private. Do not add a client-side check, an encrypted-page scheme or anything that sends the files first and hides them after.
- **The password has one home: the `SITE_PASSWORD` secret.** Never in `site.config.json` (`access.check` rejects keys called password, secret, token or key), the schema defaults, the build output, `engine-build.json`, a test that prints it, a log, a cookie or browser storage. The cookie holds an expiry and an HMAC only, signed with a key derived from the password, so a password change ends every session. `tests/check-gate.js` greps the build for the password.
- **The gate fails closed.** No `SITE_PASSWORD`, no content (503). Every response before the cookie check is the entrance page or a refusal. Changes to the worker need a case in `tests/check-gate.js` (and a quick mutation: break the check, see the test fail). The entrance page carries no family names and no picture unless `access.entranceImage` is named, and that picture is public.
- **Access, identity and visibility stay three things.** The password decides who reaches the site. Visitor identity is a preference (where the tree starts), never authentication, never sent anywhere, never in a URL or cookie, stored as one person id in `localStorage`. Which people appear is `isLiving`, `tree.hiddenRegions` and the rest of the site's own rules. Do not let one feed another. The picker offers nobody a page does not already show: living only by default (`visitor.scope`), never placeholders or hidden regions, no living photographs unless `visitor.livingPhotos`.
- **Future features read the visitor through `window.FamilyVisitor`** (see `docs/visitor.md`), after checking it exists. Do not read the storage key directly, and do not use identity to restrict anything.
- **Workflow changes.** `build-site.yml` has the Cloudflare steps. A site that is not protected must run exactly as before. After a release that changes the workflow, each site's `deploy.yml` and `check.yml` tags need a PR. A protected site in `sites.json` carries `"protected": true` and a `"url"`; `tools/autorelease.py` then checks the gate answers 401 instead of expecting 200. Do not edit `sites.json` in a feature PR.
- **Not done, on purpose:** per-person passwords, lockout counters (the free Workers plan keeps no state), the Discovery Timeline on a protected site (it reads the live site's history).
- **Tests use made-up data only** (`tests/access_fixtures.py`, built from `sample/`). To check a real site, build a temporary copy in `/tmp` with names and photographs of living people replaced; never write to a site repo, never print its private data.

## Languages

Optional (`language`, default English only). Full design in `docs/languages.md`. What to keep true:

- **A site without `language` builds the same as before.** Its pages and `site-config.js` are byte for byte unchanged (no `language` key, no `data-i18n*` markers, no switcher). Only `engine/<version>/*` differ, because the scripts carry the English words. `tests/test_i18n.py` compares builds; also `diff -r` a real site against the branch base.
- **Every piece of interface text lives in `engine/i18n/en.json` and `de.json`**, with the same keys. A script asks for its words on its first line (`/* @i18n tree kin */`); the build writes them in. Never hard-code English in a script or a template without a key, and never edit one dictionary without the other: `tests/test_i18n.py` fails on any gap.
- **English text in a template equals the English dictionary value**, so an English site gets the same page. Change both together.
- **Research content is never translated by the engine.** A site adds `story_de` style fields; the original shows when the German is missing.
- **Dictionary keys with `_one` and `_other` are plurals**; do not use those endings for anything else. German addresses the reader as Sie. No long dashes in either file.

## The map's relationships and sources

- **One relationship calculation.** `engine/kinship.js` is the only code that works out how two people are related. The tree page and the map both call it, on the same people (`FamilyKinship.pruneHidden`). Do not add a second algorithm, and do not extend the map's older `kinOf` (it serves `map.kinAnchors` only). `tests/check-map-relations.js` compares the map's words with the tree page's for every person, in English and German.
- **One choice.** "Relationships to" is one person id in `localStorage` `tc_viewpoint`, read and written through `FamilyKinship.viewpoint`. A visitor's own answer (`visitor.enabled`) overrides it and is never written to it. Nothing chosen means the map adds nothing.
- **Sources show only what they hold.** `source-preview.js` makes no link, thumbnail or summary the source does not have. A source with neither `file` nor `url` is plain text. See `docs/source-preview.md`.
- **A place without Street View says nothing.** No message, no empty button.
## Page toggles, Stories and the settings page

Docs: `docs/site-config.md#pages`, `docs/stories.md`, `docs/admin.md`. What to keep true when changing them:

- **One door for "is this page on".** `build/sitecfg.py` (`page_state`, `load`) decides, and everything else (nav, sitemap, Stuart's index, the tree's map link, validation, the settings page) reads `cfg['_pages']`, `cfg['_off_files']` and `cfg['_toggles']`. Do not test `pages.x` anywhere else.
- **A missing key keeps its old meaning.** `tree`, `map` and `ask` are made only when set; `stories` appears only when `content/stories/*.md` exists (or the key is `true`); `records` is opt-in; `discoveries` follows `timeline.enabled` unless `pages.discoveries` is a boolean. A site that changes nothing must build byte for byte as before. New engine files (`content-pages.css`, `admin.js`, `admin.css`, the timeline files) are copied only when the page is on. Do the `diff -r` on the real sites (see above) after touching any of this.
- **Off means gone.** Not built, not in the nav, not in the sitemap, not in Stuart's index, not linked from the engine's pages; links in the site's own pages become plain text with a warning. `home` cannot be off.
- **`content/stories/` is never published** (the Markdown and drafts stay in the repo). The Markdown renderer (`build/markdown.py`) escapes everything and allows only http, https, mailto, relative and `#` links. Do not add raw HTML.
- **Story tags go through the privacy rule.** Living people and people in a hidden region get no tag (`stories.taggable`). Add the case to `tests/test_pages.py` when changing it.
- **The settings page is static and opt-in** (`admin.enabled`). `noindex`, no nav, no sitemap, no Stuart. The token lives only in `sessionStorage` and goes only to `api.github.com` in an `Authorization` header; never log it, never put it in a URL, never commit one. The CSP in `templates/admin.html` allows no other host. Saving edits `site.config.json` in place and `verify()` refuses any change outside the settings the page owns.
- **The switch rules exist twice** (`build/sitecfg.py`, `engine/admin.js`). `tests/fixtures/pages-cases.json` is the shared set of cases; add a case there whenever the rules change, and both test suites must pass.
- **The pages block has a schema** (`schema/pages.schema.json`, also inlined in `site-config.schema.json`); keep them in step. CI runs the page tests.

## Style

Plain words, no em dashes, no marketing tone. Match the existing docs and comments.
