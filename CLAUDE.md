# CLAUDE.md: family-site-engine

The shared engine behind three public family history sites. Each site keeps its own data, photos, pages and `site.config.json` in its own repo. This repo holds the code they all run and the build that combines the two. Read `README.md` and `docs/` for detail; this file is the working rules.

## Rules for all engine work

1. **Never push to main and never tag or publish a release by hand.** Work on a branch, open a PR, stop. The maintainer merges, and the automatic release (`auto-release.yml`) does the rest. Do not edit `VERSION`, `CHANGELOG.md` or `channels.json` in a PR.
2. **Every change must be backward compatible.** A release reaches all three sites at once. A site that does not use a new feature must build and look exactly as it does today. New settings must be optional, with a default that reproduces current behavior. Do not rename or remove settings, data fields, CSS custom properties, file names or page structure in a minor or patch release. If a site has to change something, that is a major version and needs the maintainer's decision.
3. **Never put living people's details on any public page or map.** The engine does not redact living people by itself (since 1.0.0 they are shown like anyone else, marked as living on the tree). So never add output, example data, tests, fixtures or docs that contain a real living person's name, dates, places or photos. Use the made-up `sample/` family for anything new.
4. **Never commit secrets or API keys.** That includes MapTiler and Google keys, `SITES_DISPATCH_TOKEN`, and tokens in test output. Keys belong in a site's own settings and in GitHub secrets, never here.
5. **No em dashes in any site text.** That covers templates, engine UI strings, Stuart's answers, docs and CHANGELOG entries. Use commas, colons, parentheses or full stops.
6. **Private access and visitor identity stay optional and separate.** Both are off by default, and a site with them off must build byte for byte as before. The family password for private access is never a setting, a build input or a file: only the `SITE_PASSWORD` secret. See [Private access and visitor identity](#private-access-and-visitor-identity). The one other password feature is the stopgap `basicAccess`, with its own rules in [A basic family password](#a-basic-family-password).

## Layout

| Path | What it is |
| --- | --- |
| `engine/` | Everything the browser runs: tree, map, Stuart, nav, lightbox, default tokens, MapLibre, fonts, and `visitor.js`, `visitor-match.js`, `visitor.css` ("Who are you?", copied only when `visitor.enabled`) |
| `templates/` | `tree.html`, `map.html`, `ask.html`, `timeline.html`, filled in from a site's settings; `gate-worker.js`, `gate.html`, `gate.js` (the password gate, built into `_worker.js` only when `access.enabled`) |
| `build/` | `build_site.py` (the build), `basic_access.py` (the stopgap basic password: settings checks and the page tag), `validate.py`, `migrate.py`, `archive.py`, `pages.py`, `sitecfg.py`, and the Discovery Timeline: `discoveries.py` (detection), `timeline.py` (history between builds), `timeline_page.py` (the page), `previous_site.py` (fetches the live history), and private access: `access.py` (settings checks for `access` and `visitor`, and the gate build) |
| `schema/` | `family-data.schema.json` and `site-config.schema.json` |
| `sample/` | Made-up family used by tests and as a starter site |
| `tests/` | `test_build.py` and `test_discoveries.py` (Python), `test_access.py` (Python), `test_basic_access.py` (Python), `check-basic-access.js` (Playwright), `check-sample.js`, `check-timeline.js`, `check-gate.js`, `check-visitor.js` and `check-access.js` (Playwright and Node), `timeline_fixtures.py` (seven made-up versions of a family), `access_fixtures.py` (the sample with access and visitor on, plus extra made-up people), `gate-server.js` (runs the real `_worker.js` locally), `helpers.js` |
| `tools/` | Map fonts and styles, Street View viewpoints, `backfill-discoveries.py`, `basic-password.py` (makes the salt and hash for `basicAccess`) |
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
4b. When `timeline.enabled` is true, first reads the live site's `discoveries/state.json` (`build/previous_site.py`) and passes it as `--previous previous`. Without that history the build stops.
5. Runs the site's own checks (`site-tests`, with `DIST` set to the build).
6. Publishes to GitHub Pages only if all of that passed. On pull requests it runs with `deploy: false`.

Because the workflow is pinned by tag in each site's `deploy.yml` and `check.yml`, a change to `build-site.yml` does not reach sites through a channel. After such a release, each site's two workflows need a PR to bump the tag. Keep changes to that file rare.

## Site settings

`site.config.json` is validated against `schema/site-config.schema.json` (`additionalProperties: false` nearly everywhere). Required: `schemaVersion` (const 1), `site` (with `name`), `nav`. Top-level sections: `engine` (`channel` of stable, beta or canary, or `version` pin which overrides the channel), `site`, `pages` (home, tree, map, ask), `nav`, `head`, `theme` (CSS custom properties written to `site-theme.css`), `data`, `tree`, `map`, `stuart`, `widget`, `publish`, `process`. Document every new key in `docs/site-config.md` and add it to the schema. A new key must be optional.

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
python3 tests/test_basic_access.py      # the basic family password: settings, refusals, a site without it unchanged
python3 build/validate.py --site sample
npm ci && npx playwright install chromium
node tests/check-sample.js
node tests/check-timeline.js            # SHOTS=dir saves screenshots; DIST=path checks a real site's build
node tests/check-gate.js                # the gate worker: every way in without the password
node tests/check-visitor.js             # SHOTS=dir saves screenshots
node tests/check-access.js              # SHOTS=dir for screenshots, VIDEO=dir for recordings of the first visit
node tests/check-basic-access.js        # the basic password screen in a browser; SHOTS=dir for screenshots
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

Optional (`timeline.enabled`, default false). Full design in `docs/discovery-timeline.md`. What to keep true when changing it:

- **A site that has it off must build byte for byte as before.** The page, the navigation entry, `timeline.css` and `timeline.js`, the `timeline` key of `engine-build.json` and the `discoveries/` files exist only when it is on. `tests/test_discoveries.py` compares a build with and without the engine's change. Do the same `diff -r` on a real site (see the backward compatibility check above).
- **The history is the published site.** `discoveries/state.json` (internal) and `discoveries/history.json` (the page's view) are written by every publication and fetched from the live site by the next one. Do not add a second store. A failed build publishes nothing, so it cannot move the baseline.
- **Fail loudly, never reset.** A missing `--previous`, an unreadable live history or a history from a newer format stops the build. Only a 404 from a live site that never had the timeline is a first activation.
- **Privacy has one door.** `discoveries.is_living` plus `tree.hiddenRegions` decide who is withheld. Withheld people never become claims, are stored only as hashes, and `public_ok` is re-run on every kept find on every build. Anything new that puts a name, a link, a count, a filter value, a picture or a place on the page goes through it. Add the case to `TestPrivacy`.
- **Changing how claims are derived** means bumping `ATOM_SCHEMA`. Sites then rebaseline silently, with no flood.
- **Notes (`discovery` objects, `data/discoveries.json`) override generated finds.** `data/discoveries.json` and `discoveries.suggestions.json` are never copied to the published site.
- **`tools/backfill-discoveries.py` only writes its suggestions file.** Never make it edit data.
- **No dependencies, no network, no model** in detection or headlines. Headlines must be deterministic and contain no long dashes.
- **Tests use made-up data only** (`tests/timeline_fixtures.py`, built from `sample/`). To check real data, build a temporary copy of a site in `/tmp`; never write to a site repo.

## Private access and visitor identity

Two optional, independent features. Full design in `docs/access.md` and `docs/visitor.md`. What to keep true:

- **Off means unchanged.** With `access` and `visitor` absent or not enabled, the build has no `_worker.js`, no `robots.txt` the site did not have, no visitor files, no `access` or `visitor` key in `site-config.js` or `engine-build.json`, and no extra tags in any page. `tests/test_access.py` compares builds; also `diff -r` a real site (see the backward compatibility check). Neither feature switches the other on.
- **A password screen in the browser is not security, and the engine does not offer one as security.** The only browser password screen is `basicAccess` (see [A basic family password](#a-basic-family-password)), added at the maintainer's request for sites that are still on GitHub Pages, and it is never described as protection. Genuine protection is the Cloudflare Pages worker (`templates/gate-worker.js`, built to `_worker.js`) that checks a signed cookie before serving any file, with `env.ASSETS.fetch` behind it. GitHub Pages cannot do this and the repository of a protected site must be private. Do not add any other client-side check, an encrypted-page scheme or anything else that sends the files first and hides them after, and do not stretch `basicAccess` into one.
- **The password has one home: the `SITE_PASSWORD` secret.** Never in `site.config.json` (`access.check` rejects keys called password, secret, token or key), the schema defaults, the build output, `engine-build.json`, a test that prints it, a log, a cookie or browser storage. The cookie holds an expiry and an HMAC only, signed with a key derived from the password, so a password change ends every session. `tests/check-gate.js` greps the build for the password.
- **The gate fails closed.** No `SITE_PASSWORD`, no content (503). Every response before the cookie check is the entrance page or a refusal. Changes to the worker need a case in `tests/check-gate.js` (and a quick mutation: break the check, see the test fail). The entrance page carries no family names and no picture unless `access.entranceImage` is named, and that picture is public.
- **Access, identity and visibility stay three things.** The password decides who reaches the site. Visitor identity is a preference (where the tree starts), never authentication, never sent anywhere, never in a URL or cookie, stored as one person id in `localStorage`. Which people appear is `isLiving`, `tree.hiddenRegions` and the rest of the site's own rules. Do not let one feed another. The picker offers nobody a page does not already show: living only by default (`visitor.scope`), never placeholders or hidden regions, no living photographs unless `visitor.livingPhotos`.
- **Future features read the visitor through `window.FamilyVisitor`** (see `docs/visitor.md`), after checking it exists. Do not read the storage key directly, and do not use identity to restrict anything.
- **Workflow changes.** `build-site.yml` has the Cloudflare steps. A site that is not protected must run exactly as before. After a release that changes the workflow, each site's `deploy.yml` and `check.yml` tags need a PR. A protected site in `sites.json` carries `"protected": true` and a `"url"`; `tools/autorelease.py` then checks the gate answers 401 instead of expecting 200. Do not edit `sites.json` in a feature PR.
- **Not done, on purpose:** per-person passwords, lockout counters (the free Workers plan keeps no state), the Discovery Timeline on a protected site (it reads the live site's history).
- **Tests use made-up data only** (`tests/access_fixtures.py`, built from `sample/`). To check a real site, build a temporary copy in `/tmp` with names and photographs of living people replaced; never write to a site repo, never print its private data.

## A basic family password

Optional (`basicAccess`, default off), for a site that is still on GitHub Pages and wants something in front of its home page. It exists because the maintainer asked for it while sites are not on Cloudflare yet. Full design in `docs/basic-access.md`. What to keep true:

- **It is not protection, and every word says so.** The pages, data and pictures stay public; the script only holds a page back in the browser. No doc, setting description, UI string, warning or PR text may call it private, secure, protected or locked down. `basic_access.check` always warns, and `docs/basic-access.md` leads with what it does not do. Anything that needs real protection goes to private access.
- **Off means unchanged.** With `basicAccess` absent or not enabled, the build has no `basic-gate.js`, no script tag, no `basicAccess` key in `engine-build.json`. `tests/test_basic_access.py` compares builds; also `diff -r` a real site against the branch base.
- **The password is never stored.** Only a random salt and a PBKDF2-SHA256 hash (made by `tools/basic-password.py` or the settings page), never the password, a hint, or a test that prints one. The build refuses keys called password, passphrase, secret, token or key, and refuses `enabled` with no valid salt and hash (that would leave the page open). The browser stores the hash and an expiry only.
- **One implementation of the hash.** `FamilyBasicAccess.derive` in `engine/basic-gate.js` and `make` in `tools/basic-password.py` must give the same hash (NFKC normalised, UTF-8). `tests/check-basic-access.js` checks it. The settings page uses the browser one.
- **It never combines with `access`.** Both on is a build error.
- **Do not grow it.** No lockout claims, no per-person passwords, no hiding of data files, no encrypted pages. Those are what private access is for.

## Style

Plain words, no em dashes, no marketing tone. Match the existing docs and comments.
