# Site settings: site.config.json

Each site has one settings file, `site.config.json`, at the top of its folder. It says which engine the site takes, what the site is called, which of the engine's pages it has, what is in the navigation bar, and how the tree, the map and Stuart behave for this family. The family itself is in the data files ([the data format](data-format.md)); nothing about how the site looks belongs there.

The settings are checked against `schema/site-config.schema.json` on every build. Pointing an editor at the schema gives completion and checking as you type:

```json
{ "$schema": "https://raw.githubusercontent.com/Belfiore/family-site-engine/main/schema/site-config.schema.json", "schemaVersion": 1 }
```

Only `schemaVersion`, `site` and `nav` are required. Everything else has a default. `sample/site.config.json` uses almost every setting and is the best starting point.

## engine

```json
"engine": { "channel": "stable" }
```

- `channel`: which releases the site takes: `stable` (most sites), `beta` or `canary`. See [releases](releasing.md).
- `version`: pins the site to one engine version (`"1.0.0"`), whatever its channel says. For a site that must not change while something is checked, or to roll one site back. Remove the pin to follow the channel again.

## site

```json
"site": { "name": "Hartley & Moreau", "familyName": "the Hartley and Moreau families", "lang": "en-GB", "description": "..." }
```

- `name`: the short name, used as the logo in the navigation bar and at the end of page titles.
- `familyName`: how Stuart names the family in a sentence ("I look after the records of the Hartley and Moreau families").
- `lang`: the language of the pages.

## pages

The site's home page, and which of the standard pages it has. Every page can be turned on or off from here (or from the [settings page](admin.md) at `/admin/`):

```json
"pages": {
  "home": "index.html",
  "stories": true,
  "tree": { "file": "family-tree.html", "title": "Family Tree | Hartley & Moreau", "description": "...", "stylesheets": ["styles.css"] },
  "map": "map.html",
  "records": true,
  "discoveries": true,
  "ask": false
}
```

| Page | Made when | What it is |
| --- | --- | --- |
| `home` | always | The site's own home page (a file name, default `index.html`). It cannot be turned off, and `"home": false` is an error. |
| `stories` | not switched off, and the site has a story in `content/stories/` (or `stories` is `true`) | Stories, articles and essays written as Markdown. See [Stories](stories.md). |
| `tree` | `true`, a file name, or an object | The family tree. |
| `map` | `true`, a file name, or an object | The family map. Needs `data/places.json`. |
| `records` | `true`, or an object | Records and Research: every record in `data/sources.json`, and the open questions on people the site shows. |
| `discoveries` | `true`, or (when `discoveries` is not there) `timeline.enabled` is `true` | The [Discovery Timeline](discovery-timeline.md). |
| `ask` | `true`, a file name, or an object | Stuart's page. |

Each of these can be `true` (on, with the engine's file name and wording), `false` (off), or an object with `file`, `title`, `description`, `heading`, `stylesheets` and `enabled`. `tree`, `map` and `ask` can also be a file name, and `null` (or leaving the key out) means the site has no such page. `heading` replaces the engine's heading at the top of the page ("The Family Tree"). `stylesheets` are the site's own stylesheets for that page; without them the page uses `head.stylesheets`. An object with `"enabled": false` is off but keeps its other settings, so switching the page back on brings its title and file name with it.

**A key that is not there.** For the three pages that are new (`stories`, `records`, `discoveries`) a missing key means "not switched off", so a site that says nothing gets what it already had: no Stories page until the site has a story, no Records and Research page (every site has sources, and some already have a page for them), and the Discovery Timeline only if `timeline.enabled` is on. For `tree`, `map` and `ask`, a missing key (or `null`) has always meant "this site has no such page", and still does, so a site that did not have a tree does not suddenly get one.

**What turning a page off does.** The page is not built, so its address does not exist. The navigation bar is made without it, on every page. A link to it in a page's own words is shown as plain text, and the build prints a warning naming the page and the link. The engine's own pages leave out every link to it (the tree's "Show on the family map", Stuart's button), Stuart's index does not point to it, and a `sitemap.xml` the site keeps itself loses the entry. A navigation entry that links to a page that was never there (`null`, or a key left out) is still an error, as it was; `false` is the way to say "off, and take the link out".

**The navigation bar adds the new pages by itself.** A page the build adds (Stories, Records and Research, Discoveries) gets an entry at the end of the bar unless `nav` already links to its file. To put it somewhere else, add the entry to `nav` yourself.

**The older timeline setting.** `timeline.enabled` is still read, and still works when `pages.discoveries` is not there. When `pages.discoveries` is there, it decides: `true` turns the page on even if `timeline.enabled` is false, and `false` turns it off even if `timeline.enabled` is true.

The pages block is described by `schema/pages.schema.json`, which the build and CI check every site against.

## admin

Optional. The settings page at `/admin/`: a static page where people with write access to the site's repository switch pages on and off, and change the site's title, tagline and engine channel. Off unless turned on; a site that leaves it off builds exactly as before. See [the settings page](admin.md).

| Setting | Default | |
| --- | --- | --- |
| `enabled` | `false` | Make the page at `/admin/` |
| `repo` | the repository the build runs in | The site's GitHub repository, `owner/name` |
| `branch` | the repository's default branch | Where saved settings are committed |
| `configPath` | `site.config.json` | Where the settings file is, for a site in a sub-folder |

```json
"admin": { "enabled": true }
```

## nav

The navigation bar, in order. It is the same on every page, built by the engine, and replaces whatever bar a page had:

```json
"nav": [
  { "href": "index.html", "label": "Home" },
  { "href": "family-tree.html", "label": "Family Tree", "match": ["family-tree-classic.html"] },
  { "href": "branches.html", "label": "Branches", "match": ["falcke.html", "bennett.html"] },
  { "comment": "Family Crest is switched off for now." }
]
```

- The link for the page being read is lit. `match` lists other pages that light the same link (each branch page lights "Branches").
- A `comment` entry is written into the bar as an HTML comment: a way to keep a switched-off link where someone will find it.
- A page can choose its lit link itself with `data-active="branches.html"` on its own `<nav class="main-nav">`.

Below 1,180 pixels the links fold into a menu button.

## head and theme

```json
"head": { "fonts": "https://fonts.googleapis.com/css2?family=...", "stylesheets": ["styles.css"] },
"theme": { "--pc-accent": "#7b1f1f", "--gold": "#c9a227" }
```

- `head.fonts`: a stylesheet for web fonts, added to the engine's pages. Stuart's page allows that host and nothing else in its content security policy.
- `head.stylesheets`: the site's own stylesheets for the engine's pages.
- `theme`: colours and fonts for the engine's parts, written into `site-theme.css`, which loads after the engine's styles so it wins. Any of the engine's custom properties can be set:

| Properties | What they colour |
| --- | --- |
| `--gold`, `--gold-dark`, `--cream`, `--ink`, `--font-display`, `--font-body`, `--font-accent` | Shared: the navigation bar, and the defaults for the rest |
| `--pc-bg`, `--pc-paper`, `--pc-ink`, `--pc-muted`, `--pc-accent`, `--pc-accent-deep`, `--pc-accent-light`, `--pc-accent-rgb`, `--pc-title`, `--pc-gold`, `--pc-rule`, `--pc-line`, `--pc-line-direct`, `--pc-focus`, and the rest at the top of `engine/tree-canvas.css` (badges for living people, tooltips, hovers, the confidence badges, the document viewer) | The family tree. The Belfiore & Circelli site's `theme` turns the whole tree green this way |
| `--fm-bg`, `--fm-paper`, `--fm-ink`, `--fm-muted`, `--fm-accent`, `--fm-accent-deep`, `--fm-gold`, `--fm-rule`, `--fm-assoc`, `--fm-assoc-bg` | The family map |
| `--st-ink`, `--st-paper`, `--st-cream`, `--st-wine`, `--st-gold`, `--st-sepia`, `--st-line`, `--st-display`, `--st-text` | Stuart |

## data

`data.dir` is the folder that holds `people.json`, `sources.json` and `places.json` (default `data`).

## tree

The family tree. Any key here also overrides the same key in `people.json` meta, which is where older data kept them.

| Setting | What it does |
| --- | --- |
| `rootPersonId` | Whose tree it is: the default viewpoint for "how are they related" |
| `familyLabel`, `directLineLabel` | Names used in the tree's headings and key ("Daniel's direct line") |
| `generations` | Names for the rows: `{ "generation": 2, "label": "III", "title": "Arthur and Margot", "range": "1902 to 1905" }` |
| `rootOrder` | The oldest people across the top, left to right |
| `sides` | `{ "left": "arthur-hartley", "right": "marguerite-moreau", "leftLabel": "...", "rightLabel": "..." }`: one partner's family on the left and the other's on the right, so their lines never cross. Their children are drawn on the right |
| `hiddenRegions` | Regions (from each person's `region`) that are not drawn on the tree or the map, and that Stuart does not know. The people stay in the data |
| `showConfidence` | `true` shows the confidence badges in a person's panel: "Overall", the Confidence column of the facts table, and the note on uncertain timeline entries. Default `false`: they are not drawn, and the data keeps them. The cards' dotted outline for unproven people and the key are not affected |
| `suspectedRelatives` | `{ "pierre-moreau": "jean-baptiste-moreau" }`: someone kept from a hidden region and drawn beside another person, with no proven link |
| `regions`, `regionKicker` | Framed groups on the tree whose link to the family is unproven |
| `kinAnchor`, `kinLabel` | The kin box: relatives whose exact link is not known, drawn beside this person |
| `initialView` | Where the tree opens: `{ "ids": [...], "fromGen": 16, "toGen": 19 }` |
| `cardPhotos` | `set` (default): a card shows the person's `photo` only. `best`: a card with no `photo` uses the best picture in their media |
| `coupleBlocks` | `explicit` (default): a couple who both have parents on the tree are drawn together only where the data says so (`layoutJoin`). `auto`: always, in the family of the partner on the direct line, else the husband |
| `legendNote` | A sentence added to the tree's key, in the site's own words; HTML allowed |
| `noscript` | What the tree page says to visitors without JavaScript, in the site's own words; HTML allowed. The default points to the home page |

## map

| Setting | What it does |
| --- | --- |
| `home` | The region the map frames first: `{ "name": "England", "bounds": [[-6.4, 49.85], [1.9, 55.9]] }` (west, south, east, north). Places outside it are listed as "Beyond England" |
| `historicMaps` | `uk-os` for the National Library of Scotland's Ordnance Survey maps of Great Britain (needs `maptilerKey`), or `null` for no "Then" style |
| `maptilerKey`, `googleEmbedKey` | Browser keys for the satellite and historic maps and for Street View inside the page. Both are optional. Restrict each to the site's address; see [map keys](map-keys.md) |
| `branches` | Groups of places for the map's branch filter: `{ "id": "moreau", "label": "The Moreaus", "pages": ["moreau.html"], "people": [...], "regions": [...] }`. One has `"default": true` |
| `kinAnchors` | People the timeline relates others to ("Margot's father"): `[{ "id": "marguerite-moreau", "name": "Margot" }]` |
| `families` | The Family filter's choices: `{ "id": "margot", "label": "Margot's family", "option": "Margot's family (Moreau)", "roots": ["marguerite-moreau"] }`. Without any, the filter is hidden |
| `associates` | People who are not family but belong to the story, such as a business partner: `{ "label": "Business associate", "note": "Not family", "people": { "edwin-pratt": "arthur-hartley" } }`. Each associate is in a hidden region (`tree.hiddenRegions`), so the tree leaves them off; the map draws their places in slate green with a "Business associate. Not family" badge, never as "no proven link". The second id is the family member they are tied to, so a Family filter that includes that person keeps the associate's places |
| `noscript` | Extra words for visitors without JavaScript; HTML allowed |

## stuart

Stuart answers from the data and from the story pages listed here. See [Stuart](stuart.md).

| Setting | What it does |
| --- | --- |
| `anchors` | The couple at the heart of the site, left-hand side first: `[{ "key": "arthur", "id": "arthur-hartley", "title": "Grandpa Arthur", "short": "Arthur" }, ...]`. Stuart describes people by them ("Grandma Margot and Grandpa Arthur's grandson") |
| `homeCountry` | The country that counts as home, for "who was born abroad?" |
| `pages` | The story pages Stuart reads, in reading order. Give their headings `id`s so answers can link to them |
| `generalPages` | Pages about many people (the home page, an index of branches), which are not taken to be about one person |
| `examples` | Starter questions: `{ "kind": "genealogy", "q": "...", "needs": ["person-id"] }`. A question whose `needs` are not on the tree is dropped |
| `helpExample` | The example in Stuart's help text |
| `overviewSections`, `overviewFallback`, `overviewFollowups` | What "Tell me about this family" answers from: page sections (`pg:index#h-start`), a sentence when there are none, and follow-up questions |
| `warFollowups` | Follow-up questions after a question about war service |
| `stories` | `{ "page": "index.html", "anchors": [...] }`: sections of one page that hold the family's stories |
| `photos` | The answer to "where are the photographs?": `{ "text": "...", "links": [{ "title": "...", "url": "..." }] }` |
| `wordlikeNames` | Surnames that are also everyday words (Field, Cousins), which are only read as names when they look like one |
| `familyNames` | Plural family names for "who were the Moreaus?" |
| `nicknames` | Short forms of given names, added to the engine's own list (Reg for Reginald, Bob for Robert): `{ "margaret": ["Peggy", "Meg"] }` |
| `synonyms` | The site's own words for things, added to the words Stuart treats as alike when searching: `{ "earl": ["orkney"] }` |
| `skipClasses` | Classes of page furniture Stuart should not read |

## widget

Stuart's button on the site's own pages (the engine's pages place it themselves):

```json
"widget": { "enabled": true, "exclude": ["family-tree-classic.html"], "pages": { "gallery.html": { "compact": true, "avoid": ".gallery-controls" } } }
```

`compact` shows only Stuart's seal; `avoid` lists controls the button must keep clear of. There is no button when the site has no Stuart page.

## timeline

Optional. The Discovery Timeline: a page of what the family has newly learned, newest first. Off unless turned on; a site that leaves it off builds exactly as before. See [the Discovery Timeline](discovery-timeline.md) for how it works, what a site has to do to turn it on, and what it keeps.

| Setting | Default | |
| --- | --- | --- |
| `enabled` | `false` | Make the page and its "Discoveries" navigation entry, and keep the history of finds between publications. `pages.discoveries`, when it is there, decides instead |
| `file` | `discoveries.html` | The page's file name |

```json
"timeline": { "enabled": true }
```

Other settings, all optional:

| Key | Meaning |
| --- | --- |
| `showRegions` | Hidden regions (`tree.hiddenRegions`) whose deceased people may be finds on the page, with no link to the tree or the map. Living people stay withheld. Default none. See [the Discovery Timeline](discovery-timeline.md#showing-some-hidden-regions-on-the-timeline) |
| `showConfidence` | `true` shows each find's confidence label (Confirmed, Probable, Family tradition, Unverified). Default `false`: the data keeps it, the page does not draw it |
The same switch is `"pages": { "discoveries": true }`, which is the one the [settings page](admin.md) changes; `timeline.enabled` is still read when `pages.discoveries` is missing. `timeline.file` still sets the page's file name.

A site that turns it on needs an engine release that has the timeline, `build-site.yml` from the same release in its `deploy.yml` and `check.yml`, and `pages: write` for the deploy job. The site must not already have a `discoveries.html` or a `discoveries/` folder (the build stops if it does).

## access

Optional. A family password in front of the whole site. Off unless turned on; a site that leaves it off builds exactly as before. It needs a private repository and Cloudflare Pages instead of GitHub Pages, and the password is the `SITE_PASSWORD` secret, never a setting. See [private access](access.md) for what it needs and what it does not protect against.

| Setting | Default | |
| --- | --- | --- |
| `enabled` | `false` | Make the gate (`_worker.js`) and publish to Cloudflare Pages |
| `project` | none (required) | The Cloudflare Pages project name: lower case letters, digits and hyphens |
| `kicker` | `A private family archive` | The line above the name on the entrance page |
| `wordmark` | `site.name` | The name shown on the entrance page |
| `prompt` | `Family password` | The label of the password field |
| `button` | `Enter` | The label of the button |
| `hint` | none | A line under the field, such as who to ask. Everyone can read it, so never put the password in it |
| `cookieDays` | `90` | How long a device stays let in (1 to 365) |
| `entranceImage` | none | A picture inside the site, shown to everyone before the password. Use only a picture that is fine to make public |

```json
"access": { "enabled": true, "project": "smith-family-archive", "hint": "Ask Grandma for it." }
```

A key called `password`, `secret`, `token` or the like is an error, and so is any setting that is not in the table (a misspelt `enabled` would quietly leave the site open).

## visitor

Optional. "Who are you?": the visitor says who they are, the device remembers it, and the family tree opens from their place. A preference kept in the browser, never a login. Off unless turned on; a site that leaves it off builds exactly as before. See [visitor identity](visitor.md).

| Setting | Default | |
| --- | --- | --- |
| `enabled` | `false` | Ask visitors who they are, once |
| `question` | `Who are you?` | The question |
| `lead` | `Find yourself in the family, and the tree will open from where you sit in it.` | The line under the question |
| `skipLabel` | `Continue without choosing` | The quiet way to carry on without saying |
| `welcome` | `true` | Show the short welcome after a choice. Skipped anyway for visitors who ask their device for reduced motion |
| `livingPhotos` | `false` | Show a living person's photograph beside their name in the list |
| `scope` | `living` | `living`: people marked `isLiving`. `all`: everyone on the tree. Placeholders and hidden regions are never offered |

```json
"visitor": { "enabled": true }
```

## language

```json
"language": { "default": "en", "available": ["en", "de"] }
```

Optional. Without it the site is English only and builds exactly as before.

- `default`: the language of the site until a visitor chooses another: `en` (the default) or `de`.
- `available`: the languages a visitor can choose from (default: only `default`). With more than one, the navigation bar shows an `EN | DE` switcher; the choice is kept in the visitor's browser and sets `<html lang>`.

Words a site writes itself take a language ending (`label_de`, `title_de`, `name_de`) and so does research text in the data (`story_de`); the original is used where the German is missing. See [languages](languages.md) for what is translated, what stays English and how to add a language.

## publish and process

- `publish.exclude`: files and folders not to publish (globs from the site folder: `"drafts/"`, `"*.psd"`). `.git`, `.github`, `node_modules`, `_site` and `site.config.json` are never published.
- `process.exclude`: pages the build copies exactly as they are, without the engine's bar, files or button.

## What the build does to the site's own pages

For every `.html` file at the top of the site folder, unless it is in `process.exclude`:

- the `<nav class="main-nav">` block is replaced by the bar from `nav`;
- references to engine files the page may still carry from before the engine (`nav.css`, `stuart.js`, `tree-canvas.js`, `config.js` and so on) are removed, and `records.css` and `records.js` are pointed at the engine's copies;
- Stuart's stylesheet, the theme and `nav.css` are added at the end of the head (so nothing overrides the bar), and the site settings, the menu script and Stuart's button at the end of the body.

Everything else on the page is left exactly as the site wrote it.
