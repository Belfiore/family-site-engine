# The data format

Every site keeps its family in three files in its `data/` folder:

| File | What it holds | Needed |
| --- | --- | --- |
| `people.json` | Everyone on the tree: names, family links, life events, homes, work, voyages, pictures, stories | always |
| `sources.json` | The records the site relies on; everything else cites them by id | always |
| `places.json` | The places on the map and what happened at each | when the site has a map |

The format is written down as a JSON Schema in `schema/family-data.schema.json`, which is the reference; this page explains it. The build checks every file against the schema and against itself before it builds anything (see [Checking](#checking)), and a site whose data has an error is not published.

The examples below come from the made-up family in `sample/data/`.

## Ids

People, sources, places and place events each have an `id`: lower-case letters, digits and hyphens (`arthur-hartley`, `census-1881-leeds`). An id is how everything else points at a record, and pages link to people by it (`family-tree.html#/person/arthur-hartley`), so never reuse an id for someone else and never rename one once the site is live. Two people with the same name get different ids (`eli-hartley-1850`, `eli-hartley-1874`).

## Dates

A date is held twice: once for the computer and once for people.

```json
"birth": { "date": "1848", "display": "about 1848", "dateQualifier": "about", "place": "Leeds, Yorkshire", "placeId": "leeds", "confidence": "probable", "sourceIds": ["census-1881-leeds"] }
```

- `date` is as much as is known, in the form `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, or empty when nothing is known. The engine never shows more precision than this: a year stays a year in every age and timeline.
- `display` is how the site words it: "about 1848", "spring 1901 (registered)", "baptised 19 June 1873".
- `dateQualifier` (optional) says how exact it is: `exact`, `about`, `before`, `after`, `uncertain`, `year`, `baptised`.
- `alternates` lists other dates the records give for the same event, each with its own `display`, `note` and `sourceIds`. The tree shows them ("1882/83") and Stuart mentions them.

## How sure: the confidence scale

Every claim can carry a `confidence`, from this list and nothing else:

| Value | Meaning |
| --- | --- |
| `confirmed` | A record says it. |
| `probable` | The records point to it, but a certificate or register entry would make it firmer. |
| `family tradition` | The family says it; no record has been found. |
| `unverified` | Not yet checked, or the evidence is thin. |

Probable and unverified parent links are drawn dashed on the tree, and Stuart says when a link in a chain is not confirmed.

## Sources and citations

Each entry in `sources.json` has an `id`, a `title` and a `type` (census, parish register, newspaper, photograph, family testimony and so on), and optionally `repository`, `date`, `url`, `file` and `note`. Anything that relies on a source names it in `sourceIds`; a story cites it in the text as `[^source-id]`:

```json
"story": "Thomas Hartley traded wool in Leeds for forty years.[^census-1881-leeds]"
```

## People

A person needs `id`, `displayName`, `sex` (`M`, `F` or `U`) and the three family lists (`parents`, `children`, `spouses`), which may be empty. Everything else is optional.

### Family links

Links go both ways and must agree: if Arthur lists William among his `parents`, William lists Arthur among his `children`; partners list each other in `spouses`. The checker stops the build when a link points at someone who is not in the file, and warns when the two sides do not agree.

```json
"spouses": [{ "id": "marguerite-moreau", "order": 1, "marriageDate": "1930-06-07", "marriageDisplay": "7 June 1930",
              "place": "Soho, London", "placeId": "soho", "confidence": "confirmed", "sourceIds": ["marriage-hartley-moreau"] }]
```

`relation: "partner"` marks partners who did not marry. `order` numbers a person's marriages.

### Living people

`isLiving: true` marks someone who is, or may be, alive. The tree marks them as living, and Stuart talks about them in the present tense ("is living", and their age today when the record has a birth date). Nothing else is held back: whatever the record holds (dates, places, pictures, stories) is shown on the tree, the map and by Stuart, exactly as for anyone else. What to put in a living person's record is the site's own decision.

### Layout hints

The tree lays itself out from the family links. A few optional fields steer it:

- `generation`: the row, 0 for the oldest generation shown. A parent's generation must be lower than their child's.
- `order`: order among brothers and sisters, oldest first.
- `layoutJoin`: when both partners have parents on the tree, the id of the partner whose family the couple is drawn in. With `tree.coupleBlocks: "auto"` in the settings the engine works this out itself.
- `uncertainBeside`: draw this person beside someone else, joined by a dashed line, with no proven link.
- `region`: a named group (`"legend"`), which the settings can hide (`tree.hiddenRegions`) or frame (`tree.regions`).
- `placeholder`: a stand-in for someone not yet identified ("Woman in a studio portrait"); `kin`: a relative whose exact link is not known.

### Pictures

`media` lists a person's photographs and documents. Each item needs `type` (`photo`, `portrait`, `document`, `gravestone`, ...) and `file`, and should have `thumb`, `caption`, `alt` and the `sourceId` it comes from. Documents can carry `pdf`, `transcription` and `translation`. `photo` is the picture on the card; with `tree.cardPhotos: "best"` a card with no `photo` uses the best picture in `media` (a photo or portrait first, then a gravestone, then anything else).

### The rest of a life

| Field | Each item has |
| --- | --- |
| `nameVariants` | `name` (required), `note`, `confidence`, `sourceIds` |
| `residences` | `place`, `placeId`, `address`, `years`, `confidence`, `note`, `sourceIds` |
| `occupations` | `title`, `employer`, `place`, `placeId`, `years`, `note`, `confidence`, `sourceIds` |
| `immigration` (one object) | `date`, `port`, `ship`, `age`, `note`, `confidence`, `sourceIds` |
| `voyages` | `id`, `ship`, `from`, `to`, `fromPlaceId`, `toPlaceId`, `departureDate`, `arrivalDate`, `display`, `recordCrops`, `confidence`, `note`, `sourceIds` |
| `facts` | `label` (required), `value`, `confidence`, `sourceIds` |
| `timeline` | `date`, `label`, `event`, `kind` (`life` or `context`), `placeId`, `mapEvent`, `confidence`, `sourceIds` |
| `openQuestions` | `question` (required), `record` (the record that would answer it) |
| `relatedPages` | `url` (required), `title` |

## Places

`places.json` is only needed by sites with a map. Each place has an `id`, a `name`, coordinates (`lat`, `lng`), how exact they are (`precision`, `uncertaintyMetres`) and how to draw it (`drawAs`):

- `pin`: a known address or building;
- `halo`: a place known only roughly, drawn as a dashed pin with a circle of uncertainty;
- `area`: a district, parish, county or country.

`inHomeRegion` says whether the place is inside the site's home region (`map.home` in the settings); the map frames the home region first and lists the rest as "Beyond". `country` lets Stuart answer "who went to France?".

### Place events

`events` lists what happened at the place: `type` (born, baptised, lived, married, worked, served, sailed, civil case, photographed, celebrated, died, buried), `personIds`, dates (`dateStart`, `dateEnd`, `datePrecision`) and `sourceIds`. An event that mirrors a fact in `people.json` names it in `factRef` (`"arthur-hartley.birth"`), and the map then takes its date and wording from `people.json`, so the map never says more than the tree. A fact in `people.json` with a `placeId` but no place event is added to the map by itself. Voyage ends carry `voyageId` and `voyageEnd` (`departure` or `arrival`).

## Field reference

Generated from the schema. A field the schema does not list is kept and passed through, with a warning, so a tool that adds a new kind of information does not break a site.

### person

| Field | Type | Required | What it is |
| --- | --- | --- | --- |
| `id` | string | yes | A stable id: lower-case letters, digits and hyphens. Never reuse or rename one; pages link to it. |
| `displayName` | string | yes | The name shown on the card and in headings. |
| `givenNames` | string or null |  |  |
| `knownAs` | string |  | Optional (engine 1.1.0). The name the person went by when it is not the first given name, e.g. "Bruno" for Max Bruno. Map pin labels, cards and sentences use it; otherwise they use the first given name. |
| `surname` | string or null |  | Surname at birth, or the surname the site uses. |
| `disambiguator` | string or null |  | A short line that tells this person apart: "Reg, Pat's father" or "nee Bennett, Pat's mother". Shown under the name. |
| `nameVariants` | list of object |  | Other spellings and names the records use. |
| `nameUncertain` | boolean |  | The name itself is not certain. |
| `sex` | `M`, `F`, `U` | yes | M, F or U (unknown). Used for relationship words and couple order. |
| `isLiving` | boolean |  | The person is, or may be, alive. The engine shows "Living" and uses the present tense; it shows whatever else this record holds. |
| `placeholder` | boolean |  | A stand-in for someone not yet identified ("Woman and girl, Camden Town"). |
| `kin` | boolean |  | A relative whose exact link is not known; drawn in the kin box. |
| `isDirectLine` | boolean |  | On the root person's direct line of ancestry. |
| `generation` | integer |  | Row on the tree, 0 for the oldest generation shown. |
| `order` | number or null |  | Layout hint: order among brothers and sisters, oldest first. |
| `layoutJoin` | string or null |  | Layout hint: id of the partner whose family this person is drawn in, when both have parents on the tree. |
| `uncertainBeside` | string or null |  | Layout hint: id of the person this one is drawn beside, joined by a dashed line, with no proven link. |
| `uncertainLink` | boolean |  | The link to the parents is not proven; the card is drawn dashed. |
| `region` | string or null |  | A named group on the tree ("orkney"), used by tree.hiddenRegions and the framed regions in tree.regions. |
| `confidence` | `confirmed`, `probable`, `family tradition`, `unverified` |  | How sure the site is of this claim. confirmed: a record says it. probable: the records point to it but a certificate would make it firmer. family tradition: the family says it and no record has been found. unverified: not yet checked. |
| `parentLinkConfidence` | `confirmed`, `probable`, `family tradition`, `unverified` or null |  | How sure the link to the parents is; probable and unverified links are drawn dashed. |
| `parents` | list of person id | yes |  |
| `children` | list of person id | yes |  |
| `spouses` | list of object | yes |  |
| `birth` | event or null |  |  |
| `death` | event or null |  |  |
| `burial` | event or null |  |  |
| `residences` | list of object |  |  |
| `occupations` | list of object |  |  |
| `immigration` | object or null |  |  |
| `voyages` | list of object |  |  |
| `facts` | list of object |  |  |
| `timeline` | list of object |  |  |
| `media` | list of object |  |  |
| `photo` | string or null |  | Picture for the card. With tree.cardPhotos "best", a card with no photo uses the best picture in media. |
| `portrait` | string or null |  | A larger portrait for the profile. |
| `cardPlace` | string or null |  | The short place line on the card. |
| `summary` | string or null |  | One or two sentences: who this person was. |
| `story` | string or null |  | Markdown. Cite sources as [^source-id]; the id must be in sources.json. |
| `openQuestions` | list of object |  |  |
| `relatedPages` | list of object |  |  |
| `layout` | object |  | Reserved for layout hints in later versions. |

### event

| Field | Type | Required | What it is |
| --- | --- | --- | --- |
| `date` | string or null |  | The date as far as it is known: YYYY, YYYY-MM or YYYY-MM-DD; empty or null when not known. Use display for how the site words it. |
| `display` | string or null |  | How the site writes the date, e.g. "about 1866" or "spring 1901 (registered)". |
| `dateQualifier` | `exact`, `about`, `before`, `after`, `uncertain`, `year`, `baptised`, `baptism` or null |  | Optional: how exact the date is. |
| `place` | string or null |  |  |
| `placeId` | string or null |  | Id of a place in places.json (sites with a map). |
| `confidence` | `confirmed`, `probable`, `family tradition`, `unverified` |  | How sure the site is of this claim. confirmed: a record says it. probable: the records point to it but a certificate would make it firmer. family tradition: the family says it and no record has been found. unverified: not yet checked. |
| `note` | string or null |  |  |
| `sourceIds` | list of string |  | Ids of entries in sources.json that support this claim. |
| `alternates` | list of object |  | Other dates the records give for the same event. |
| `age` | integer or string or null |  |  |

### source

| Field | Type | Required | What it is |
| --- | --- | --- | --- |
| `id` | string | yes | A stable id: lower-case letters, digits and hyphens. Never reuse or rename one; pages link to it. |
| `title` | string | yes |  |
| `type` | string | yes | census, parish register, newspaper, photograph, family testimony, web ... |
| `repository` | string or null |  |  |
| `date` | string or null |  |  |
| `url` | string or null |  |  |
| `file` | string or null |  |  |
| `note` | string or null |  |  |
| `earlierNote` | string or null |  |  |

### place

| Field | Type | Required | What it is |
| --- | --- | --- | --- |
| `id` | string | yes | A stable id: lower-case letters, digits and hyphens. Never reuse or rename one; pages link to it. |
| `name` | string | yes |  |
| `historicName` | string or null |  |  |
| `variants` | list of string |  |  |
| `kind` | string |  | home, church, town, port, workplace, cemetery, registration district ... |
| `address` | string or null |  |  |
| `modernAddress` | string or null |  |  |
| `precision` | string |  | How exact the point is: address, building, street, parish, town, registration district, county, country. |
| `lat` | number or null |  |  |
| `lng` | number or null |  |  |
| `uncertaintyMetres` | integer or number or null |  |  |
| `coordinateMethod` | string or null |  |  |
| `coordinatePrecision` | string or null |  |  |
| `coordinateSourceIds` | list of string |  | Ids of entries in sources.json that support this claim. |
| `drawAs` | `pin`, `halo`, `area` |  |  |
| `inHomeRegion` | boolean or null |  | Inside the site's home region (map.home). Older data says inEngland. |
| `inEngland` | boolean or null |  | Older name for inHomeRegion; read when inHomeRegion is absent. |
| `country` | string or null |  | Optional: the country, for questions such as "who went to Italy?". |
| `noProvenLink` | boolean |  |  |
| `standsToday` | string or null |  |  |
| `standsTodaySource` | string or null |  |  |
| `todayNote` | string or null |  |  |
| `status` | string or null |  |  |
| `significance` | string or null |  |  |
| `blurb` | string or null |  |  |
| `blurbSourceIds` | list of string |  | Ids of entries in sources.json that support this claim. |
| `title` | string or null |  |  |
| `boundary` | any |  |  |
| `historicMap` | any |  |  |
| `images` | array |  |  |
| `streetView` | object or null |  |  |
| `streetViewReason` | string or null |  |  |
| `events` | list of place event | yes |  |

### placeEvent

| Field | Type | Required | What it is |
| --- | --- | --- | --- |
| `id` | string | yes |  |
| `type` | `born`, `baptised`, `lived`, `married`, `worked`, `served`, `sailed`, `civil case`, `photographed`, `celebrated`, `died`, `buried` | yes |  |
| `personIds` | list of person id | yes |  |
| `date` | string or null |  |  |
| `dateStart` | string or null |  | The date as far as it is known: YYYY, YYYY-MM or YYYY-MM-DD; empty or null when not known. Use display for how the site words it. |
| `dateEnd` | string or null |  | The date as far as it is known: YYYY, YYYY-MM or YYYY-MM-DD; empty or null when not known. Use display for how the site words it. |
| `datePrecision` | string or null |  |  |
| `approximate` | boolean |  |  |
| `factRef` | string or null |  | Which people.json fact this event mirrors ("person-id.birth"); empty when places.json is the only source. |
| `alsoFactRefs` | list of string |  |  |
| `pages` | list of string |  |  |
| `recordCrops` | list of string |  |  |
| `sourceIds` | list of string |  | Ids of entries in sources.json that support this claim. |
| `confidence` | `confirmed`, `probable`, `family tradition`, `unverified` |  | How sure the site is of this claim. confirmed: a record says it. probable: the records point to it but a certificate would make it firmer. family tradition: the family says it and no record has been found. unverified: not yet checked. |
| `familyStatement` | boolean |  |  |
| `summary` | string or null |  |  |
| `note` | string or null |  |  |
| `voyageId` | string or null |  |  |
| `voyageEnd` | `departure`, `arrival` or null |  |  |

## Notes for the Discovery Timeline

Every record below can carry an optional `discovery` object, in which a researcher says in their own words what was found, when, by whom and from what. The engine writes a plain headline from the data when there is no note. The notes are only read when the site turns on the [Discovery Timeline](discovery-timeline.md); otherwise they are ignored.

| Field | Meaning |
| --- | --- |
| `found` | Date it was found, `YYYY-MM-DD` |
| `headline` | A plain-English sentence, replacing the engine's wording |
| `findType` | `person`, `record`, `photo`, `correction`, `place` or `connection` |
| `foundBy` | Who found it |
| `source` | A string, or `{ "text", "url" }` |
| `confidence` | One of the confidence levels above |
| `image`, `imageAlt` | A picture of the find (a path in the site) and what it shows |
| `changeNote` | One sentence on what changed |

`discovery` is allowed on a person, an event, a place, a placeEvent, and on a person's `spouses`, `residences`, `occupations`, `voyages`, `facts`, `timeline` items and `media`. A note on a living person is ignored with a warning.

Notes can also go in one file, `data/discoveries.json`: `{ "discoveries": [ { "id", "covers", "personIds", "placeIds", ...the fields above } ] }`. `covers` lists the claim keys a note is about, so that when the engine finds the same thing the note's wording is used and only one find is written. The file is read by the build and is not published.

## Checking

`python3 build/validate.py --site path/to/site` runs the same checks as the build. Errors stop the build; warnings are printed and the build carries on.

Errors:

- a file is missing or is not valid JSON;
- a required field is missing, or a field has the wrong type or a value outside its list (a confidence of "certain", a date of `1880-13`);
- an id is used twice;
- a family link, `layoutJoin` or `uncertainBeside` names someone who is not in `people.json`;
- a place event names someone who is not in `people.json`;
- the settings name someone who is not in `people.json` (`tree.sides`, `stuart.anchors`, `map.families` and so on), or the navigation bar links to a page the site does not have.

Warnings:

- a field the schema does not know;
- a link that only goes one way (a parent who does not list the child);
- a parent in the same or a later generation than their child;
- a cited source, place, picture or file that is not there;
- a story footnote `[^id]` that is not in `sources.json`;
- a page named in the settings that the site does not have.

## Versions of the format

`people.json` says which version of the format it follows in `meta.schemaVersion`. The current version is 1.

- Adding an optional field is not a new version: older data stays valid.
- Renaming, removing or changing the meaning of a field is a new version, and comes with a step in `build/migrate.py` that brings older data up to date. The engine keeps reading the previous version for at least one release, so sites can move in their own time.

To bring a site's data up to date:

```sh
python3 path/to/engine/build/migrate.py --site .           # shows what would change
python3 path/to/engine/build/migrate.py --site . --write   # changes the files
```

Version 0 to 1 moved the tree's look (`familyLabel`, `rootPersonId`, `directLineLabel`, `generations`, `rootOrder`, `kinAnchor`, `kinLabel`, `regions`, `regionKicker`, `initialView`, `sides`) from `people.json` meta into `site.config.json`, folded the duplicate `living` flag into `isLiving`, and renamed `inEngland` to `inHomeRegion`. Data without a `schemaVersion` is read as version 0, with a warning.
