# Changes

Each release, newest first. A major version says what a site has to change.

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
