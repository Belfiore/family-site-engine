# The Discovery Timeline

A page that lists what a family has newly learned, newest first, so a relative who comes back to the site can see what is new since their last visit. It is off unless a site turns it on. A site that leaves it off builds exactly as it did before.

```json
"timeline": { "enabled": true }
```

The page is `discoveries.html` (set another name with `timeline.file`), with a "Discoveries" entry in the navigation bar. It works without JavaScript: the build writes the whole page. JavaScript adds the "new since your last visit" banner, the filters and the folding of busy days.

## What counts as a discovery

The engine compares the **meaning** of the site's data with the data it published last time. It does not compare files or text, so reordering a file, reformatting it or renaming an id's wording is not a discovery. It uses no network and no model: the same two versions of the data always give the same finds and the same headlines.

Each publication, the data is reduced to **claims** (the build's word is "atoms"): one small, normalised statement each. A person, a parent link, a marriage, a birth, a death, a burial, a residence, an occupation, a voyage, an immigration record, a fact, an item in a person's timeline, a photograph or document, a place, an event at a place, and a source. Each claim has a key that stays the same whatever file it sits in, in whatever order. Two lists are compared, last time's and this time's:

| Change | Is it a find? | Shown as |
| --- | --- | --- |
| A claim that was not there before | Yes | New person, New record, New photo, New connection or New place, by what it is |
| A claim whose value changed (a date, a place) | Yes | Correction, with the previous and the updated value both kept |
| A date made more exact (1876 became 10 June 1876) | Yes | Record ("Found the exact date of ...") |
| Confidence raised | Yes | New connection or New record |
| Confidence lowered | Yes | Correction |
| A source that now backs a claim that already existed | Yes | Record |
| A claim removed | **No.** It is not a discovery. If a find was published about that claim, the find says "This find has since been withdrawn." (or "Part of this find has since been withdrawn.") instead of staying up as fact | |
| A picture file renamed or moved | No. Pictures are known by their content, not their file name | |
| Story text, summaries and other prose edited | No. The engine reads facts, not paragraphs | |
| Capital letters, punctuation, accents or a one-letter spelling variant changed | No. Digits are never ignored: a changed year is a change | |

### Grouping and headlines

A person added with their parents, birth, home and a census record is **one** find, not twelve. Changes that come from the same source are grouped into one find; people who were each given exactly the same new detail (a couple at one address) share one find; a publication that puts more than three new places on the map at once is one find.

Within a find the headline is written from the data and a short fixed set of connecting words, in English, for example:

- "Found Thomas Hartley and Mary Ann Hartley in the 1891 census, 3 Kirkgate, Leeds: recorded as a wool broker, with their daughter Hannah."
- "Corrected William Hartley's birth date from 1876 to 10 June 1876 after finding ..."
- "New evidence confirms Ruth Hartley as the daughter of James Hartley."

Headlines never use long dashes and never contain markup.

## Where the history lives

The engine keeps no database and the build is stateless. The memory of what was published is **inside the published site**, in two files that every publication writes:

| File | What it holds | Who reads it |
| --- | --- | --- |
| `discoveries/state.json` | The claims of the last publication, the finds so far (with the claims each is made of), hashed marks for withheld people, and the date the timeline began | The next build |
| `discoveries/history.json` | The finds as the page shows them: nothing the page does not already show | Anyone; the page's own data |

Before each build, `build-site.yml` reads the **live** `state.json` from the site's GitHub Pages address (`build/previous_site.py`) and passes it to the build as `--previous`. So "the previous version" always means "what is live", and a failed build, which publishes nothing, cannot move it.

What follows from that:

- **First activation.** The live site has no `state.json` yet. The first build records the current data as the baseline and lists nothing from it: turning the timeline on does not flood the page with the whole family. The page says when the timeline began.
- **A failed build or check changes nothing.** The site stays as it was and the next build compares with the same baseline.
- **A rebuild of the same data finds nothing new,** and a build that is rerun gives the same entries with the same ids and dates. No find is listed twice.
- **Each site is independent.** Every site keeps its own history inside its own published files.
- **Missing history is an error, not a reset.** If the live site once had the timeline (its `engine-build.json` has a `timeline` entry) but `state.json` cannot be read, the build stops rather than start the history again. A server error, a page that is not JSON, or a history from a different format version also stop the build. A build that is not given `--previous` at all stops too.
- **A new way of reading the data** (a change to how claims are derived, `ATOM_SCHEMA`) rebuilds the baseline silently: the finds already listed stay, and nothing new is listed for that publication.

### Dates

A find has two dates. **Published** is when the build that first listed it ran. **Found** is the date shown on the page: by default the same day, or the day a researcher gives in a `discovery` note (see below). "New since your last visit" always uses the published date, so a find a researcher dates last month still counts as new to a visitor who last came a week ago.

## Privacy

Living people are never part of the timeline. The engine has one definition of a living person (`isLiving`, or the older `living` flag), and people in `tree.hiddenRegions` are treated the same way. For all of them:

- they never become claims, so nothing about them is a find and nothing is counted;
- they never appear in a headline, a link, a filter, a picture, a source line, `state.json` or `history.json`;
- their ids are stored only as one-way hashes, so the file does not name them, and a person who stops being living (or is added already deceased) joins the timeline without flooding it;
- **every build checks the kept finds again.** If someone is marked living after a find about them was published, that find disappears from the page and from both files on the next build. So does any find whose personIds, or whose words, include a withheld person's full name. A find about a deceased person that says "a daughter of James Hartley" goes too if James is now living;
- a researcher's note on a living person's record is ignored, with a warning;
- a find is never linked to a place that only withheld people were at.

### Showing some hidden regions on the timeline

A hidden region can hold people the site wants to talk about without drawing them on the tree: a lead that is not yet proven, a business associate. `timeline.showRegions` names the hidden regions whose **deceased** people may be finds on the page:

```json
"tree": { "hiddenRegions": ["legend", "associates"] },
"timeline": { "enabled": true, "showRegions": ["associates"] }
```

- Only the named regions change. Any other hidden region stays withheld exactly as above.
- A living person is withheld in every region, named or not.
- The tree, the map and Stuart are untouched. The setting does not bring anyone back onto them.
- A find about a person in a shown region has no "See it in the tree" or "Show on the map" link, because there is nothing for it to open. Its picture, source and words are shown like any other find.
- Turning a region on does not flood the page. The people already in the data become the baseline, as when someone stops being living. Finds made after that appear as usual. Taking the setting off again withholds them and removes their finds on the next build.
- **This publishes names, headlines and sources of those people** on the page and in `state.json` and `history.json`. Name a region only when the site is happy for that to be public. `build/validate.py` warns if a named region is not in `tree.hiddenRegions` or has nobody in it.

The page links to the family tree and the map only for a person or place that is public. It does not load pictures of withheld people, because their claims never exist.

The engine publishes `people.json` as it always has (the tree and the map read it). The timeline neither changes that nor makes it worse; see "Limits" below.

## The page

- **Days, newest first.** Each day has a header (`Thursday, 26 November 2026`) and a computed summary (`4 new finds across The Hartleys and The Moreaus.`, or `4 new finds.` on a site with one family line). The summary is written again for what is showing when a filter is on.
- **Cards.** Each find has a type label and icon (New person, New record, New photo, Correction, New place, New connection), the headline, who found it and the source and confidence when they are known, and a thumbnail only if the find has a picture. A correction shows both the previous and the updated value. A find that was later corrected or withdrawn says so ("This find has since been corrected.").
- **The headline is never a link.** A card has at most one link into the site, to one specific person or place: "See it in the tree" or "Show on the map". A find about someone in a shown region (see Privacy) has none.
- **Sources and pictures.** A web address in a find's source is a link that opens in a new tab (`target="_blank"`, `rel="noopener"`). If the note gives a `source.url`, the whole source text links to it; otherwise each `http` or `https` address inside the text does, without trailing punctuation. Anything else stays plain text. A thumbnail opens the full-size image in the engine's lightbox (Escape or a click closes it; a modified click opens the file in its own tab). Where the record has a separate full-size file, that is what opens.
- **Confidence is not shown.** The Confirmed, Probable, Family tradition and Unverified labels are kept in `history.json` but not drawn. Set `timeline.showConfidence` to `true` to show them.
- **Busy days fold.** A day with more than 6 finds shows the first 5 with "Show all N finds". The banner's jump button and a link to one find (`#find-<id>`) open a folded day.
- **Filters** by family line (the site's `map.branches`, assigned the way the map assigns people) and by type, in a collapsed bar that says when one is on.
- **Since your last visit.** The browser remembers the last visit in `localStorage` (no cookie, nothing is sent anywhere). A returning visitor sees "7 new finds since your last visit on 12 Nov." with a button that jumps to the first one; new finds are marked "New" and stay marked for the whole visit, including a reload. A first-time visitor sees no banner. Blocking `localStorage` just turns the banner off.
- **On a phone** the date headers stay under the navigation bar while their day scrolls, and every button is at least 40 pixels tall.
- The look comes from the site's own theme (`--var` tokens); the page needs no theme of its own.

## Writing your own notes

The engine writes a plain headline from the data. A researcher can say it better, and say who found it, where, and how sure. Every field is optional. Put a `discovery` object on the record it is about, or list notes in `data/discoveries.json`.

| Field | Meaning |
| --- | --- |
| `found` | The date it was found, `YYYY-MM-DD`. Without it, the day it was first published |
| `headline` | A plain-English sentence. Replaces the engine's wording |
| `findType` | `person`, `record`, `photo`, `correction`, `place` or `connection` |
| `foundBy` | Who found it, in the site's own words ("Sebastian", "Stuart - Italian") |
| `source` | The citation: a string, or `{ "text": "...", "url": "..." }` |
| `confidence` | `confirmed`, `probable`, `family tradition` or `unverified` |
| `image` | A picture of the find (a path in the site), with `imageAlt` to say what it shows |
| `changeNote` | One sentence on what changed ("The household was thought to have left Soho in 1885") |

```json
{
  "id": "henri-moreau",
  "residences": [{
    "place": "Soho", "placeId": "soho", "address": "22 Greek Street, Soho", "years": "1891",
    "discovery": {
      "found": "2026-11-18",
      "headline": "Henri Moreau was lodging at 22 Greek Street in Soho by 1891.",
      "foundBy": "Sebastian",
      "source": { "text": "1891 census, Soho", "url": "https://example.org/census-1891" },
      "confidence": "probable"
    }
  }]
}
```

`discovery` is allowed on a person, an event, a place, a placeEvent, and on a person's spouses, residences, occupations, voyages, facts, timeline items and media.

A note in `data/discoveries.json` is for something with no record of its own, or one note about several claims:

```json
{ "discoveries": [
  { "id": "album", "personIds": ["mary-ann-briggs"], "covers": ["person:hannah-hartley"],
    "headline": "Mary Ann Hartley appears in a family photograph album held by a cousin.",
    "findType": "photo", "foundBy": "Sebastian", "found": "2026-11-21", "source": "Family photograph album" }
] }
```

How notes combine with what the engine finds:

- A note **overrides** the engine's fields for the same find. `covers` lists the claim keys it is about (the backfill script writes them), and when the engine also finds those claims it uses the note's wording and writes one find, not two.
- A note with nothing the engine detected stands alone. **Notes show up even on the first activation:** a researcher who wrote one meant it to be listed. They are always checked for privacy.
- Taking a note away brings the engine's own wording back on the next build. The engine remembers what it wrote.
- A `found` date in the future, a missing `image`, long dashes in note text or a note on a living person is reported as a warning; a note of the wrong shape stops the build.
- `data/discoveries.json` and `discoveries.suggestions.json` are read, never published as they are.

## Starting with a history: the backfill

Turning the timeline on starts it empty. If the site's data is in git, `tools/backfill-discoveries.py` can work out what the timeline would have found over the site's past, for a researcher to read and approve.

```sh
python3 tools/backfill-discoveries.py --site path/to/site [--since 2026-11-01] [--out file] [--force]
```

It replays each commit that changed `people.json`, `sources.json` or `places.json`, one after another, with the same code as the live build, and writes `discoveries.suggestions.json` in the same shape as `data/discoveries.json`. It **never changes the data, the history or the settings**, and will not replace an existing suggestions file without `--force`.

- The first commit it reads is the starting point, not a find.
- Each suggestion is dated by the commit that added it, which is not always the day the research was done. Every suggestion carries a `review` note saying so. A commit that adds more than 25 finds is flagged as a possible bulk import.
- Living people and hidden regions are judged by the site as it stands now, whatever the old data said.
- Finds that a later commit corrected or withdrew are left out, and sources that nothing cited at the time are not suggested when a later find uses them.
- To use suggestions: delete the ones you do not want, check the dates, and move the rest into `data/discoveries.json`. The `review` notes are ignored by the build and can stay or go.

On the FitzMaurice and Andrews site's real history (23 data commits) the script suggests about 130 finds, most of them from two large days of research, which is why the review step is there.

## Publishing: what a site has to do

1. Take an engine release that has the timeline, and move `build-site.yml@vX.Y.Z` to that release in `deploy.yml` and `check.yml`.
2. The deploy workflow must give its job `pages: write` (the build reads the live site's address from the Pages API). A check-only run falls back to `https://<owner>.github.io/<repo>/`.
3. Set `"timeline": { "enabled": true }` in `site.config.json`.
4. Publish. That publication is the baseline. Optionally run the backfill and add what you approve.

A site with a custom domain is read at the address the Pages API reports. If it cannot be found on a deploy run, the build stops rather than start again.

## For local builds

```sh
python3 build/build_site.py --site path/to/site --out _site --previous none      # first publication, or a trial
python3 build/build_site.py --site path/to/site --out _next --previous _site      # the next one, against the last
```

`--previous` takes a folder (a copy of the last published site, or just its `discoveries/` folder), a `state.json` file, or `none`. `--now 2026-11-26T10:00:00Z` sets the clock, for tests. A site with the timeline on needs `--previous` every time; without it the build stops.

## Tests

- `python3 tests/test_discoveries.py` (Python only): detection, backward compatibility, privacy, history kept across publications, the page, the live-history fetch and the backfill, on `tests/timeline_fixtures.py`, a made-up family (the sample's Hartley and Moreau people) in seven successive versions.
- `node tests/check-timeline.js`: the page in a browser. `SHOTS=dir` saves screenshots; `DIST=path` checks a real site's build.

## Limits

- Only what the data says is read. A story paragraph rewritten is not a discovery.
- A find about a person who is later marked living, or one whose words name such a person, disappears. That is deliberate.
- A photograph of a living person attached to a deceased person's record cannot be recognised as such.
- Wording and dates are English.
- `people.json`, `sources.json` and `places.json` are still published raw by the engine, as they have always been, because the tree, the map and Stuart read them. A living person in those files is visible there. That is separate from, and unchanged by, the timeline.
- If a build succeeds but the deploy step fails, the history was not published, so the same finds are found again next time with a later published date.
- Two publications running at once could both read the same baseline. Each site's deploy workflow should keep a single run at a time.
- The history starts the day the timeline is turned on. Earlier research is only listed if a researcher approves backfill suggestions.
