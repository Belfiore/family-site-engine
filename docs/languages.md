# Languages

The engine speaks English and German. English is the default, and a site that says nothing about languages is built exactly as it was before this existed. This page is for the person who runs a site. The files are in `engine/i18n/`.

## Turning it on

In `site.config.json`:

```json
"language": { "default": "en", "available": ["en", "de"] }
```

- `default`: the language of the site until a visitor chooses another. `en` or `de`.
- `available`: the languages a visitor can choose from. Leave it out and only the default is offered.

What follows from that:

- No `language` block, or `available` holding only `en` with `default` `en`: English only. The pages, `site-config.js` and the data are byte for byte what they were. Only the engine's own files under `engine/<version>/` change, because they now carry the English words inside them.
- `default: "de"` and nothing else available: a German site. No switcher. `<html lang="de">`.
- More than one language available: the navigation bar shows a small `EN | DE` switcher. The choice is kept in the visitor's browser (`localStorage`, key `fse-language`), overrides the default, and sets `<html lang>` to match. Nothing is sent anywhere and nothing goes in a cookie or a URL. A saved choice for a language the site does not offer is ignored.

## What is translated

All of the engine's own interface text: the navigation bar and page names (Home, Family Tree, Family Map, Ask Stuart, Discoveries), every label, button and message on the tree, the map, the Discovery Timeline, Stuart's page and button, the password entrance page, and "Who are you?". Months, weekdays, dates, numbers, lists and plurals follow the language too: `12 March 1891` becomes `12. März 1891`, `12,345` becomes `12.345`.

The words are in `engine/i18n/en.json` and `engine/i18n/de.json`, one flat list of keys. The build writes the words a script needs into that script, so a page does no extra request and the dictionaries are not published as files. The German addresses the visitor as Sie.

## The site's own words and research

Research content stays exactly as written: stories, notes, summaries, source titles, Discoveries notes. To offer a translation, add the same field with a language ending. The German is used when German is chosen, and the original is used when the German is missing or empty:

```json
{ "id": "thomas-hartley", "summary": "A wool merchant in Leeds.", "summary_de": "Ein Wollhändler in Leeds.",
  "story": "...", "story_de": "..." }
```

This works for any text field the data format already has (`summary`, `story`, `disambiguator`, a place's `name`, `directLineLabel` in `meta`, and so on). The same ending works in `site.config.json` for the words a site chooses for itself:

```json
"site": { "name": "Hartley & Moreau", "name_de": "Hartley und Moreau" },
"nav": [ { "label": "The Moreaus", "label_de": "Die Moreaus", "href": "moreau.html" } ],
"pages": { "tree": { "file": "family-tree.html", "title": "Family Tree | Hartley", "title_de": "Stammbaum | Hartley" } }
```

For the engine's own pages (Home, Family Tree, Family Map, Ask Stuart, Discoveries) a site that has not named them gets the German words from `de.json`. A page the site wrote itself keeps its own title and label unless it adds `title_de` and `label_de`.

Discoveries notes (`discovery` objects and `data/discoveries.json`) take `headline_de`, `changeNote_de`, `foundBy_de`, `imageAlt_de` and `sourceText_de`.

The build accepts an ending only for a language the engine has words for. Any other ending (`story_fr`) is reported as an unknown field, like any other.

## What stays English, on purpose

These are limits of this first version, not accidents:

- **Stuart's answers.** Stuart's page, button and messages are translated, and the German page says so. What Stuart finds and how he reads a question are still English: question parsing, the starter chips and the "Tell me about" wording.
- **Headlines the engine writes.** A new Discoveries find such as "Found William Hartley in the 1901 census" is made by the build in English, so that it is the same on every build. Add `headline_de` to a note to replace it. Dates around the headlines follow the language.
- **The password gate's HTTP refusals.** The entrance page is translated. The plain-text refusals the worker sends to a script (401, 503) are English.
- **Kin words** (grandmother, great-aunt, cousin once removed) are written for English and German only.
- **Place names, people's names and source titles** are data, and stay as they are.
- **Hard-coded text** in the FitzMaurice map ("bomb" note for `23-sutton-court-road`) is not translated.
- **`archive-search.js`** is untouched.

## Adding another language

Copy `engine/i18n/en.json` to `engine/i18n/<code>.json` and translate every value. Keep the `{placeholders}` and the `_one` and `_other` pairs. Then add `<code>` to `lang.<code>` in every dictionary so the switcher can name it, and teach `date.*`, `fmt.*` and `list.*` the language's habits. `python3 tests/test_i18n.py` fails if any key is missing from a language, so it says what is left. Adding a language to the engine is a minor release. Kin words need real work per language (`tree-canvas.js`, `KIN`), so say so in the pull request.

## Checks

- `python3 tests/test_i18n.py`: both dictionaries have the same keys, no empty German string, the same `{values}`, no long dashes, every key the code asks for exists, the templates and `en.json` agree, a site without `language` builds the same with or without the block, and the settings are checked.
- `node tests/check-i18n.js`: the switcher, the saved choice, `<html lang>`, German dates, `story_de` and its fallback, the map, Stuart's page, "Who are you?" and the Discovery Timeline in German. `SHOTS=dir` saves screenshots.
