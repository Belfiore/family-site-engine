# Changes

Each release, newest first. A major version says what a site has to change.

## 1.0.2

- **A map with no places yet says so.** A site can have the family map before its places are collected (`"places": []`). The map opens on the home region with a short note in the site's own words, the new setting `map.emptyNote` (default "No places are on the map yet."), and leaves out the years slider, Timeline, "View as list" and the person search until there are places. It used to open on an empty map with a slider reading "50 to 50".
- **Facts whose place is not in `places.json` yet** go to "Not yet on the map" instead of disappearing from the map altogether. While `places.json` has no places, the data checker gives one warning for all of them instead of one per fact; the build carries on as before.
- **New check:** a copy of the sample with no places shows the note, hides the controls, frames the home region and has no page errors.

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
