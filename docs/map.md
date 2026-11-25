# The family map

The family map (`pages.map`, usually `map.html`) shows where the family was born, lived, married, worked, sailed, died and was buried, on a map, in a timeline and in a list. Everything it shows comes from the site's three data files, so new research appears on the map the next time the site is built. A site turns the map on with `pages.map`, needs `data/places.json`, and sets it up in `map` in [the settings](site-config.md).

## The files

| File | What it does |
| --- | --- |
| `templates/map.html` | The page: header, mode switcher, map stage, key, panels, timeline dock, Street View overlay, list and tray |
| `engine/map.css` | The map's styling |
| `engine/vendor/maplibre-gl-5.24.1/` | MapLibre GL JS, pinned and shipped with the engine so the page never depends on a CDN |
| `engine/map-glyphs.js` | `FM.glyph(type)`: the line symbols for each kind of event |
| `engine/map-data.js` | `FM.data`: loads the data files and builds the event index. Date rules, sentences, branches, hidden regions |
| `engine/map-player.js` | `FM.Player` (the step player), `FM.Camera` (camera movement) and `FM.geo` |
| `engine/map-ui.js` | Explore mode and everything shared: map styles, markers, peek, panels, key and filters, person search, Street View, list and tray, URL state, modes and keys |
| `engine/map-steps.js` | `FM.eventCard` and `FM.stepStage`, shared by Timeline now and a guided tour later |
| `engine/map-timeline.js` | Timeline mode |
| `engine/map-styles/` | `atlas.json` (the engine's own style over OpenFreeMap tiles) and `fallback.json` with its GeoJSON (a plain map from the engine's own files, used when the tiles do not load) |
| `engine/fonts/` | Cormorant Garamond glyphs for map labels |

Scripts load in this order, and each one only uses what loaded before it: the site settings, MapLibre, `records.js` (the lightbox), `map-glyphs.js`, `map-data.js`, `map-player.js`, `map-ui.js`, `map-steps.js`, `map-timeline.js`.

## The event index

`FM.data.build()` turns the three files into one list of events. Every marker, card, list row and timeline beat is drawn from it.

- An event in `places.json` that mirrors a fact in `people.json` (its `factRef`) takes its date, wording and confidence from `people.json`, so the map never says more than the tree.
- An event that only a page records (`factRef` empty) comes from `places.json` as written.
- Any placed fact in `people.json` that `places.json` does not list yet is added by itself.
- Voyages come from each person's `voyages`.
- A sentence from a person's timeline is borrowed when it fits the event.
- A dated fact with no place yet goes to the "Not yet on the map" tray.
- People in the tree's hidden regions are left out, except suspected relatives.

Living people are on the map like anyone else, with whatever their record holds.

Dates: an exact day or month is kept as it is; a season becomes its quarter; "about", "probably" and "likely" mark a date as approximate; ranges and decades keep both ends. The timeline plays an approximate or ranged date at its earliest possible point and lights its range bar while the playhead is inside it.

## A map with no places yet

A site can turn the map on before its places are collected, with `{ "places": [] }` in `places.json`. The map then opens on the home region with a short note in the site's own words (`map.emptyNote`, default "No places are on the map yet."), keeps the key and the "Not yet on the map" list, and leaves out the years, Timeline, "View as list" and the person search, which have nothing to work on. A person whose facts already name a place (`placeId`) is fine: the build warns once that `places.json` does not have those places yet, and the dated facts wait in "Not yet on the map".

## Drawing places

Each place's `drawAs`:

- `pin`: a known address or building; a teardrop pin, which can open Street View;
- `halo`: a place known only roughly; a dashed pin, with a soft circle of uncertainty while it is in focus;
- `area`: a district, parish, county or country; a dashed pin in the middle, with a dashed circle while in focus.

Every marker is named by who and what ("Arthur Hartley's birth"). Markers cluster in screen space and are ordered by first date, so Tab walks the family's places in date order. Places outside `map.home` are counted on the "Beyond" chip.

## Map styles

- **Today** (default): OpenFreeMap's Liberty style.
- **Atlas**: `atlas.json` over OpenFreeMap vector tiles, with Cormorant labels.
- **Then**: historic maps, when `map.historicMaps` is set. `uk-os` is the National Library of Scotland's Ordnance Survey maps of Great Britain through MapTiler, the edition chosen by year; it needs `map.maptilerKey`.
- **Satellite**: MapTiler's aerial photographs under Today or Atlas, with `map.maptilerKey`.
- If the tiles fail or take more than eight seconds, the page switches to the fallback map and says so.

## Filters

- **Family**: Everyone, or the families in `map.families`, back a chosen number of generations, with or without brothers and sisters. The URL keeps `family`, `gen` and `siblings`.
- The key (kinds of event), the year range and a person with a scope (just them, with partner, parents and children, ancestors, descendants) work on top of the family.

## Modes

A mode is registered with `FM.registerMode(name, { label, enter, leave, urlState, applyState })`. The switcher, the URL and the keyboard read the registry, so a new mode needs no changes elsewhere. A URL naming a mode that is not registered opens Explore.

## The step player

`FM.Player` plays an ordered list of steps and emits `enter`, `transition`, `state` and `end`; a mode decides what to draw. A step:

```json
{
  "id": "soho-1930",
  "places": ["soho"],
  "events": ["pe-soho-married-arthur"],
  "camera": { "center": [-0.1316, 51.5136], "zoom": 16 },
  "card": { "title": "Soho, 7 June 1930", "text": "A short narration for this stop." },
  "dwell": 8000,
  "waitForNext": true
}
```

`camera` and `card` are optional; without a camera, `FM.Camera` frames the step's places for their precision. `FM.stepStage.run(steps)` plays a hand-made list with the shared card, Previous, Next, Finish and Esc. It is all a guided tour needs: a `data/tours.json` of stops in this shape, and a small `map-tour.js` that registers a `tour` mode. Neither is built yet.

## Street View

Without a key, the Street View button opens Google Maps in a new tab at the place's viewpoint. With `map.googleEmbedKey`, it opens Street View inside the page beside the place's old photograph or record.

No Google imagery is ever saved. `tools/streetview-viewpoints.mjs` fills in each place's viewpoint (`panoLat`, `panoLng`, `heading`, `captureDate`) from Google's metadata endpoint, with a key read from the environment and never written down:

```sh
GOOGLE_STREETVIEW_KEY=... node path/to/engine/tools/streetview-viewpoints.mjs --site . --dry   # shows what would change
GOOGLE_STREETVIEW_KEY=... node path/to/engine/tools/streetview-viewpoints.mjs --site .         # writes data/places.json
```

Every viewpoint stays `checked: false` until someone has looked at the view. See [map keys](map-keys.md) for the keys.

## Rebuilding the fonts and styles

```sh
python3 tools/build-glyphs.py /path/to/cormorant-garamond-ttf-files    # writes engine/fonts/
python3 tools/build-styles.py /path/to/positron.json                   # writes engine/map-styles/
```
