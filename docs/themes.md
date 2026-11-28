# Heritage styles

A heritage style changes how a whole site looks: fonts, colours, small ornaments (dividers, a paper texture), the shape of buttons and cards, and the colours of the map and its pins. It applies to every page the engine makes: home, family tree and canvas, family map (pins, popups, panel), Ask Stuart, Discoveries, Records and Research and Stories.

It is optional. A site that does not choose one looks exactly as it does today.

## The styles

There is the **Classic Archive** (the look a site has now; choosing it changes nothing) and ten styles. Each one names a look, not a nation's stereotype: type, colour and a few quiet marks from printing and decorative traditions of that region. No flags, no costumes, no caricature.

| Style | Look | Fonts (heading / body) |
| --- | --- | --- |
| `english` | Victorian and Edwardian print: engraved rules, deep green and oxblood | IM Fell English / Libre Baskerville |
| `german` | Bauhaus restraint: charcoal, slate and muted gold, a blackletter face for the page title only | Work Sans / Work Sans (title: UnifrakturCook) |
| `italian` | Renaissance print: terracotta, ochre and olive, a marbled paper grain | Marcellus / EB Garamond |
| `irish` | Illuminated manuscript: uncial headings, moss green and parchment, a knot-work divider | Uncial Antiqua / Crimson Pro |
| `scottish` | Granite grey, heather purple and deep blue, a faint tartan weave | Spectral / Source Serif 4 |
| `french` | Belle Epoque: Art Nouveau curves in ivory, sage and gilt | Playfair Display / Lora |
| `spanish` | Azulejo tile borders: cobalt and white on warm sand, with saffron | Fraunces / Karla |
| `polish` | Paper-cut (wycinanki) motifs: crimson, cream and forest green | Bitter / Alegreya Sans |
| `scandinavian` | Nordic minimal: birch, slate blue, angular rune-like dividers | Josefin Sans / Source Sans 3 |
| `jewish` | Archival letterpress: indigo, parchment and brass, with a restrained geometric border | Frank Ruhl Libre / Crimson Text |

All fonts are free under the SIL Open Font Licence and are served from the site itself (`engine/<version>/themes/fonts/`). Nothing is fetched from another host.

## Turning one on

```json
"style": { "heritage": "german", "options": { "texture": false } }
```

- `style.heritage`: one of `classic`, `english`, `german`, `italian`, `irish`, `scottish`, `french`, `spanish`, `polish`, `scandinavian`, `jewish`. Missing or `classic` means no style.
- `style.options`: settings that belong to a style. Today there is one, `texture` (default `true`), for the styles that have a paper texture. An option the chosen style does not have is ignored with a warning; one no style has is an error.

Most people will use the settings page instead (below). It writes this block for you.

## Choosing and trying a style on the settings page

On the settings page (`/admin/`, see [the settings page](admin.md)) there is a **Language** section and a **Site style** section. They are separate settings: changing the language never changes the style and the other way round.

**Site style** shows one card for the Classic Archive and one for each style: its name, a short description, the heading font, the palette and a small page with a header and a map pin drawn in that style's own colours.

- **Suggested for this family.** The page reads the family's own data (see below) and marks the style it points to. If the family is mixed, the two or three closest matches are marked with their share. If the data says too little, the Classic Archive is suggested and the page says why. A suggestion is only a label: nothing changes until a person applies a style.
- **Click a card** to see that style on the real site straight away, without saving. The colours change over 200 ms and nothing moves. The trial follows you to every page of the site in that browser tab, with a small bar that says it is not saved and a button to stop. A visitor to the site never sees it.
- **Apply this style** opens the usual review ("Check before saving"), then saves `style.heritage` (and `style.options.texture` if it changed) to `site.config.json` in the repository. The site rebuilds by itself.
- **Cancel** puts the page back the way the site is saved.
- A **Paper texture** switch appears for the styles that have one.

Anyone can try a style. Only a person who has signed in with write access can apply one.

## How the family's data suggests a style

`build/heritage.py` (`suggest`) reads the site's `places.json` and `people.json` at build time. No network, no model, the same answer every time. It counts:

| Evidence | Weight |
| --- | --- |
| Country of each place (its `country` field, then its words, then its coordinates) | 50% |
| Birthplace of each person who may be shown | 30% |
| Where people sailed from (`immigration.port` "(from X)" and `voyages.from`) | 15% |
| Surname endings (a tie-breaker only) | 5% |

The United States, Canada, Australia and New Zealand are where many families came to, so they do not count towards a style. If at least 60% of the weight points one way the answer is that style; otherwise the top two or three styles with at least 15% are listed with their percentages. With fewer than 5 pieces of evidence the answer is the Classic Archive, and the reason says so.

- **Living people and hidden regions are not counted** (`isLiving`, `tree.hiddenRegions`, placeholders). The same privacy rule as everything else.
- **No name leaves the function.** The reasons are numbers and countries only: "62% of places with a known country are in England (5 of 8)".
- **The Jewish and Ashkenazi style is never suggested.** Nothing in a family's places or names can say who they are, and the engine does not guess it. It is there for a family that chooses it.
- The suggestion on the settings page is made when the site is built, so it reflects the data as of the last build.

## What a style changes, and what it does not

A style is a set of values for design tokens. The engine's own CSS reads them everywhere (`var(--h-accent, #8b0000)`: with no style the fallback is the original colour, so nothing changes). The shared rules for ornaments, buttons and the texture are in `engine/themes/base.css`, and there are no per-style copies of any component.

Pages the site wrote itself (`index.html`, `moreau.html` and the like) get the style's fonts and colours where they use the usual names (`--ink`, `--cream`, `--gold`, `--burgundy`, `--parchment`, the fonts). Colours written straight into a site's own stylesheet do not change. This is why a site's own pages may look partly themed. That is a decision for the site, not the engine.

Research content is never changed by a style: names, dates, places, photographs and the site's own wording stay as they are.

## Accessibility

Every style is checked against WCAG 2.x AA by `tests/test_themes.py`: body text on every surface it can sit on (4.5:1), links and the accent colour on paper (4.5:1), button text on the accent and dark fills (4.5:1), and decorative rules and gold marks (3:1). The lowest body text ratio of any style is 4.6:1 and the lowest button text ratio is 5.6:1 (both French).

- The paper texture, dividers and ornaments are small SVG or CSS. They are turned off for a visitor whose browser asks for less data (`prefers-reduced-data` or Save-Data). The 200 ms colour change is turned off for `prefers-reduced-motion`.
- A style never changes layout: the same sizes, spacing and page structure. Only colour, type face, rule and corner shapes change.
- The blackletter face (German) is used only for the page title, never for body text or controls.

## Adding another style

One file and one registry entry.

1. Copy `engine/themes/english.css` to `engine/themes/<id>.css` and change the values on `:root[data-heritage="<id>"]`: nine palette roles (each with its `-rgb` twin), the map colours, the two fonts, the radii, the divider and the texture. Put the `@font-face` rules for the fonts at the top (`tools/build-theme-fonts.py` copies the free fonts from `@fontsource` packages).
2. Add an entry to `engine/themes/registry.json` (id, name, short description, fonts, five swatches, the country codes it stands for, and its options) and add the id to the `style.heritage` list in `schema/site-config.schema.json`.

`python3 tests/test_themes.py` then checks that every token is set, the `-rgb` values match, the fonts exist, the registry matches the files and the contrast passes. The settings page, the suggestion and the build pick the new style up from the registry. Nothing else changes.

## Checks

```sh
python3 tests/test_themes.py       # files, tokens, WCAG AA, the suggestion and its privacy cases, builds with and without a style
node tests/check-themes.js         # every page in every style at desktop and phone width; SHOTS=dir saves screenshots
node tests/check-admin.js          # the settings page: try, apply and cancel a style, language, read-only
```
