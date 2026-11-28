# Crosby family heritage

The Crosby, Magwire, Farr, Richardson, Pierce, Spaulding and Putnam families, built with [Belfiore/family-site-engine](https://github.com/Belfiore/family-site-engine) the same way as Vigliotti Heritage: `engine.channel` is `stable`, the Discovery Timeline is on, and the Pages workflow calls `build-site.yml@v1.2.0`.

This folder is ready to become its own repository, `Belfiore/crosby-heritage`. The agent that prepared it could not create that repository (the GitHub app cannot create repos). Nothing here should be merged until Sebastian says so.

## What is published

Confirmed and probable claims are on the tree, the map and the line pages. Leads and possible claims are only on `research.html`. Family tradition is labeled in the prose. Six living people have a name and a relationship only.

The map has no API key. It uses the engine's keyless OpenFreeMap style. `map.maptilerKey` and `map.googleEmbedKey` are omitted on purpose. Do not commit a key. Historic maps and in-page Street View stay off until a restricted key is added in the site's own settings, not in this engine repository.

## Build locally

From a checkout of the engine, with this folder beside it or inside it:

```sh
python3 path/to/family-site-engine/build/validate.py --site path/to/crosby-heritage
python3 path/to/family-site-engine/build/build_site.py \
  --site path/to/crosby-heritage --out /tmp/crosby-site --previous none
python3 -m http.server -d /tmp/crosby-site 8000
```

`--previous none` is only for a first build, before the site has a published `discoveries/state.json`. After GitHub Pages is on, `build-site.yml` fetches that file itself.

Then, against the build:

```sh
DIST=/tmp/crosby-site node tests/verify-site.js
```

## Before the first publication

1. Create the repository `Belfiore/crosby-heritage` (private is appropriate while living relatives are named).
2. Move this folder to the root of that repository. Do not push it onto `main` of an existing family site.
3. In Settings, Pages, set Source to GitHub Actions.
4. Open a pull request. The check workflow builds without publishing. Merge only when Sebastian says so. A push to `main` is what publishes.
5. Add the repository to `sites.json` in the engine, in a separate change, so a later engine release can tell this site to rebuild.

`_site/` is gitignored. The build is not committed.
