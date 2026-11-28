# Source preview

One component (`engine/source-preview.js` and `source-preview.css`, `window.FamilySourcePreview`) for showing a source: a clear title that links to the document, a preview card on hover or keyboard focus, and a drawer that shows the document without leaving the page. The map uses it now.

## What a source offers

A source is an entry of `data/sources.json`. The component uses only what the entry holds and never makes anything up:

| Field | Used for |
| --- | --- |
| `title` | The link text, the card title, the drawer heading |
| `file` | The document. An image (`.jpg`, `.png`, `.webp` and so on) is its own thumbnail and shows inline. A `.pdf` shows inline and gets an icon on the card (the engine has no PDF renderer, so there is no thumbnail). Anything else gets a card with an "Open in new tab" button |
| `url` | A web page (`http` or `https` only). The card shows the page's address and its icon (`/favicon.ico` of that site, or a plain globe if it does not load). The page's own title cannot be read from another site, so the card uses `title` |
| `repository`, `date` | The publisher line |
| `note` | The one-line summary |

If both `file` and `url` are given, the file is the document. A source with neither is plain text: no link, no card, no drawer.

## How it behaves

- **Card.** Hover for about 300 ms, or keyboard focus at once. It fades in over 150 ms (ease-out), stays open while the pointer is over it, and closes when the pointer leaves, on blur, on scroll, or on Escape. It is not used on a touch screen.
- **Drawer.** Click or Enter. It slides in from the right over 220 ms (`cubic-bezier(0.2, 0.8, 0.2, 1)`, `translateX(100%)` to 0) and back out the same way. It has a close button and an "Open in new tab" button, closes on Escape or a click outside, keeps Tab inside it, and returns focus to the link that opened it. Nothing on the page behind it moves. With `prefers-reduced-motion` it does not animate. On a screen 700 px wide or less it is a full-height sheet from the bottom.
- **Web pages** are shown in a sandboxed frame (`allow-scripts allow-same-origin allow-popups`, no top navigation, no referrer), with a line under it: "Page not showing? Open in new tab". A page from `http` on an `https` site is never framed (browsers refuse it), and a page that has not loaded after 9 seconds is replaced by a card with the same button. A browser does not tell a page when a site refused to be framed, so for that case the line under the frame is the way out.
- **Without the script** a title link is an ordinary link that opens the document in a new tab.

## Using it

```js
FamilySourcePreview.resolver(function (id) { return sourcesById[id] || null; });   // once
html += FamilySourcePreview.titleHTML(source);      // the link, or plain text if the source has nothing to open
```

Load `source-preview.css` and `source-preview.js` (the build lists them for the map page). The card and the drawer work on every `.sp-link` in the page, whenever it was drawn. Add `source-preview.js` and `.css` to the page's list in `build/pages.py` (and its words group `sp` is already in the dictionaries).

## Where else it could go (not changed)

- The tree page's Sources list on a person's profile and in the drawer (`tree.open` and `tree.viewFile` links in `tree-canvas.js`).
- The Research and Records pages (`records.js`), where a source is cited next to a record.
- Stuart's answers, where a source is named in a reply (`stuart.js`).
- The Discoveries page, which cites a source for each find.
