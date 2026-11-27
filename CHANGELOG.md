# Changes

Each release, newest first. A major version says what a site has to change.

## 1.3.0

- Add optional private site access and visitor identity (#16) by @Belfiore

## 1.2.2

- Show Stuart and the live sites on the GitHub landing page (#13) by @Belfiore

## 1.2.1

- Register the Vigliotti site on the stable channel (#9) by @Belfiore
- Release automatically when a pull request is merged to main (#11) by @Belfiore
- Find a site folder in the release test build (#14) by @Belfiore

## 1.2.0

- **Discovery Timeline, optional and off by default.** `"timeline": { "enabled": true }` adds `discoveries.html`, a page of what the family has newly learned, newest first, with a "new since your last visit" banner. The build compares the meaning of the data with what was published last time. No network and no model. A correction keeps the previous value and the updated value. A removal is not a discovery. A site that leaves the timeline off builds byte for byte as before.
- **The history lives in the published site.** `discoveries/state.json` is the next build's baseline and `discoveries/history.json` is what the page shows. `build-site.yml` fetches the live history before the build, so a failed build cannot move the baseline, a rebuild does not list a find twice, and the first publication with the timeline on is a baseline rather than a flood. A missing or unreadable history stops the build.
- **Privacy.** Living people and people in `tree.hiddenRegions` never become claims and are stored only as hashes. Every kept find is checked again on every build, so a person marked living later takes their finds with them.
- **Researcher notes.** A `discovery` object on a record, or `data/discoveries.json`, can give `found`, `headline`, `findType`, `foundBy`, `source`, `confidence`, `image` and `changeNote`. `tools/backfill-discoveries.py` replays a site's git history into a suggestions file for review. It never changes the data. The history starts empty until a researcher approves those suggestions.
- **Turning it on.** Move `build-site.yml` to `v1.2.0` in the site's `deploy.yml` and `check.yml`, grant `pages: write` to the deploy job, then set `timeline.enabled`. A site still on an older workflow that turns the timeline on gets a build error, not a page that forgets its history.
- **Working rules.** `CLAUDE.md` at the root of the repo: how a site is built, how to preview a change, how a release is made, and the rules for engine work.

## 1.1.0

- **Business associates on the map.** `map.associates` lists people who are not family but belong to the story, such as a firm's co-founder: `{ "label": "Business associate", "note": "Not family", "people": { associateId: familyPersonId } }`. They stay in a hidden region, so the tree leaves them off, and the map draws their places in slate green with a "Business associate. Not family" badge on the pin, the place panel, the person panel and the timeline cards. They are never drawn as family or as "no proven link". A Family filter keeps an associate's places when it includes the family member they are tied to. Two new colours, `--fm-assoc` and `--fm-assoc-bg`.
- **Known-as names.** A person may have `knownAs`, the name they went by when it is not their first given name (a German call name such as Bruno for Max Bruno, or a nickname). Map pin labels, cards, timeline tips and sentences use it; without it they use the first given name as before, so no site has to change.
- **New checks:** the data checker refuses an associate who is not in a hidden region, or who is also a suspected relative; the sample family has a made-up associate, and the browser checks that his print shop is on the map with the badge and that he is not on the tree; the sample associate is John Edwin Pratt, known as Edwin, and the map must call him Edwin Pratt; a blank `knownAs` is an error.

## 1.0.1

- **Stuart takes a site's own words.** `stuart.synonyms` in a site's settings adds words Stuart treats as alike when he searches the story pages (`{ "earl": ["orkney"] }`). The two words that only made sense for the FitzMaurice and Andrews family (Orkney, the Evening News) moved out of the engine into that site's settings.
- **A fix in Stuart's search:** a question containing a word such as "constructor" could break the search, because the table of alike words was looked up without checking the word was really in it.
- **Publishing uses configure-pages 6 and upload-pages-artifact 5,** which run on Node 24, as GitHub now expects. Sites take this by moving their workflows to `build-site.yml@v1.0.1`.
- **New checks:** a site's theme loads after the engine's own colours on every engine page, and the sample's theme really changes them; Stuart's passage search with a site's own words.

## 1.0.0

The first release: the family tree, the family map, Stuart and the navigation bar, taken from the FitzMaurice and Andrews site and made to work for any family from its settings.

- **One engine for every site.** The site keeps its data, pictures, pages and `site.config.json`; the engine is copied into the build under `engine/<version>/`. Sites take releases through a channel (canary, beta, stable) or pin a version.
- **A build that checks first.** `build/build_site.py` checks the settings and the data against the schemas and against themselves, builds the tree, map and Stuart pages from templates, brings the site's own pages in line (one navigation bar, the engine's files, Stuart's button) and writes Stuart's index. A site whose data has an error is not published.
- **A documented data format**, version 1 (`schema/family-data.schema.json`), with `build/migrate.py` to bring older data up to date.
- **Living people are shown like anyone else.** The rule that reduced living people to their name and relationship is gone from the tree, the map and Stuart. The tree marks them as living, and Stuart answers about them in the present tense, from whatever their record holds.
- **New settings** for what used to be fixed to one family: the two sides of the tree, the kin box, hidden regions and suspected relatives, the page headings, the map's home region, branches and families, historic maps, Stuart's anchors, pages and starter questions, and the theme.
- **Every colour on the tree is a setting.** A site's `theme` can give the tree its own palette (the Belfiore & Circelli site keeps its green), down to the badges, tooltips, confidence labels, the document viewer and the minimap, which used to draw the direct line in green on every site.
- **From the Italian site**: pictures on cards from a person's media (`tree.cardPhotos: "best"`) and couples drawn together automatically (`tree.coupleBlocks: "auto"`). Both are off unless a site turns them on.
- **A made-up sample family** with checks for the build, the data checker, the migration, and every page in a browser.
- **`build/convert_family_data.py`** turns a `family-data.js` (the format some of the first sites used) into the engine's format, reading it as data rather than running it.
