# Stories

A page for stories, articles and essays about the family, written as Markdown files in the site's own repository. There is no page layout to build: write the story, add the picture, commit. The site makes a list of stories, newest first, and one page for each.

## Writing a story

Put a file in `content/stories/`, named for the story (`the-crossing.md`). It starts with a block of settings between `---` lines, then the story:

```
---
title: The Crossing
date: 1923-04-02
cover: images/crossing.jpg
coverAlt: The ship at the dock in Liverpool
people: [arthur-hartley, marguerite-moreau]
summary: How Arthur left Leeds, one March morning.
---
Arthur left Leeds on a grey morning in March.

## The docks

Markdown works as you would expect: **bold**, *italic*, [links](https://example.org), lists, quotes and pictures.
```

| Setting | |
| --- | --- |
| `title` | Required. |
| `date` | Optional: `1923`, `1923-04` or `1923-04-02`. The list is newest first; a story with no date goes last. |
| `cover` | Optional: a picture in the site (`images/crossing.jpg`) or an `https` address. Shown on the list and at the top of the story. |
| `coverAlt` | A short description of the cover for people who cannot see it. |
| `people` | Optional: ids from `people.json`. Each becomes a tag that links to that person on the family tree. |
| `summary` | Optional: the line shown on the list. Without it, the start of the first paragraph is used. |
| `draft` | `true` keeps the story off the site while you write it. |

The Markdown the page understands is headings, paragraphs, bold, italic, links, pictures, lists, quotes, rules and code. A `#` heading in a story becomes a second-level heading, because the story's title is the page's main heading. Anything that looks like HTML is shown as text and never runs, and a link can only go to `http`, `https`, `mailto`, another page of the site, or a place on the same page. Pictures are paths from the top of the site (`images/crossing.jpg`).

## What the build makes

- `stories.html`: the list.
- `story-<file name>.html`: one page per story, with newer and older links. `the-crossing.md` becomes `story-the-crossing.html`.
- An entry called "Stories" at the end of the navigation bar, unless `nav` already links to `stories.html`.

The Markdown files themselves are never published; only the pages made from them. Two files that would make the same page, a missing title, a date that is not a date, or a person who is not in `people.json` stop the build with the file named. A cover or picture that is missing from the site is a warning.

## People tags and living people

A tag links to the person on the family tree, so a story never shows anyone the tree does not. People who are living, and people in a group the tree hides (`tree.hiddenRegions`), get no tag, and the build says so. If the family tree page is turned off, the names are shown as plain text.

## Turning it on and off

`pages.stories` is `true`, `false`, or an object (`file`, `title`, `description`, `heading`, `stylesheets`). When the key is not there the page appears as soon as the site has a story, and a site with no `content/stories/` folder is built exactly as before. `false` hides the list and every story, including the ones already written. See [the pages settings](site-config.md#pages).

## Style

The page uses the site's own colours and fonts (`--ink`, `--cream`, `--gold`, `--font-display` and `--font-body`, from `tokens.css` and the theme), in `engine/content-pages.css`. Put your own stylesheet in `head.stylesheets` or the page's `stylesheets` to change it.
