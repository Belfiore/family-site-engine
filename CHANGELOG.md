# Changes

Each release, newest first. A major version says what a site has to change.

## 1.1.0

- **"Who are you?"** The family tree now asks the reader who they are on their first visit, and again from the **You are** button in the header at any time. They type part of their name and pick themselves from the matches (living people first). From then on everything is said from where they stand: each card shows its relationship to them ("Great-grandfather", "2nd cousin"), their own card is marked **You**, the panel and the full story say "Your great-grandfather" with a **See how** link to the relationship finder, the search results say how each match is related to them, and the relationship finder speaks to them ("Joseph Belfiore is your grandfather. You are Joseph's grandson."). The choice is kept in the browser. **Just looking** shows the tree from its own person (`tree.rootPersonId`) for that visit.
- **Stories follow the reader.** Stories are written from the tree's own person ("Robert, Seb's father"). For a reader who has said who they are, each "<root's name>'s <relationship>" becomes their own relationship to the same person ("Robert, your second cousin", or "Robert (you)" for Robert himself). A phrase is only changed when it is clear who it means: the one person who is that relation, or, when several are, the person whose story it is or the one named in the same sentence. Anything else, and anyone with no recorded link to the reader, keeps its original words. Nothing in the data changes.
- **Replaces the "Relationships to" list** in the header, which only changed one line in the panel and was hidden on phones and narrow windows. The **You are** button shows on every screen size.
- **For a site's checks:** a first visit now opens the picker over the tree. Checks that click the tree should close it first with `#whoSkip` ("Just looking"). `window.__tree` adds `setViewer(id)` and `personalize(text, personId)`.

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
