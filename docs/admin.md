# The settings page

Each site can have a settings page at `/admin/`. It is a static page: there is no server, so it talks to GitHub from the browser. A person with write access to the site's repository switches pages on and off, changes the site's title, tagline and engine channel, and saves. Saving commits `site.config.json` to the repository, and that commit rebuilds the site by itself.

It is off unless the site turns it on:

```json
"admin": { "enabled": true }
```

The build then makes `admin/index.html`. The page is not in the navigation bar, not in Stuart's index, has no Stuart button, carries `noindex, nofollow, noarchive` so search engines leave it out, and is taken out of a `sitemap.xml` the site keeps itself. Anyone who knows the address can open it, and they will see the settings read only.

## What the page does

1. **Reads** the settings from the repository through the GitHub API (public repositories can be read without signing in).
2. **Signs in** with a GitHub token pasted into the page. The page then asks GitHub whether that person can write to the repository. If not, or if there is no token, everything is shown as **Read only** and nothing can be saved.
3. **Shows the switches**: Home (always on and locked), Stories, Family Tree, Family Map, Records and Research, Discoveries, then the site title, the tagline, the language, the site style and the engine channel.
4. **Shows what will change** before anything is saved: each switch that moved, and each setting that changed, from the old value to the new.
5. **Commits** the change. The file is edited line by line, not written out again, so the commit shows only what the person changed and the file keeps its layout. Before sending, the page reads the result back and checks that every setting it does not own is exactly as it was.
6. **Links to the build** that the commit started, and to the commit.

If the file changed on GitHub while the page was open, or the branch does not allow the commit, nothing is overwritten: the page says so and asks for a reload.

## Signing in

GitHub's device flow cannot be used from a page like this (GitHub does not allow the requests from a browser), so the page uses a fine-grained token:

1. On GitHub, **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token**.
2. **Repository access**: only this site's repository.
3. **Permissions**: **Contents**, read and write. Nothing else.
4. Give it an expiry date, copy it, and paste it into the page.

The token is kept in that browser tab only (`sessionStorage`) and is gone when the tab is closed or when **Sign out** is pressed. It is sent only to `api.github.com`, in the `Authorization` header. It is never written to the page, the repository, the address bar or the console, and the page's content security policy allows requests to no other site. Do not paste a token into a page you did not expect.

The branch can be protected. If it only accepts changes through a pull request, the commit is refused and the page says so; give the person's account permission to bypass the rule, or change the setting in the repository by hand.

## What it changes

| Setting | Where it is saved |
| --- | --- |
| Stories, Records and Research, Discoveries | `pages.stories`, `pages.records`, `pages.discoveries` as `true` or `false` |
| Family Tree, Family Map | `pages.tree`, `pages.map`: `true` or `false`; an object gets `enabled` inside it so its file and title are kept; a file name becomes `{"file": "...", "enabled": false}` |
| Site title | `site.name` |
| Tagline | `site.description` |
| Default language, languages visitors can choose | `language.default`, `language.available` (see [languages](languages.md)). Writing only what changed |
| Site style | `style.heritage` (`classic` for the Classic Archive) and, for a style with a texture, `style.options.texture`. See [heritage styles](themes.md) |
| Engine channel | `engine.channel` (a pinned `engine.version` still wins, and the page says so) |

The tagline is `site.description`. The engine itself does not print it on any page; a site shows it if its own pages or theme do.

Turning **Discoveries** on needs the site's workflows to use `build-site.yml` from engine 1.2.0 or newer (see [releases](releasing.md#the-build-workflow)). A long dash in the title or tagline is refused.

## Language and site style

Both sections are on the same page and are separate: one never changes the other.

**Language** picks the default language and the languages a visitor can switch between. The default is always one of them.

**Site style** shows the heritage styles as cards, marks the one the family's own data suggests, and lets you try any of them on the real site without saving. **Apply this style** goes through the same review and commit as every other change; **Cancel** goes back to what is saved. Anyone can try a style; only someone who can write to the repository can apply one. The page's content security policy allows its own files (the style sheets and fonts) and `api.github.com`. See [heritage styles](themes.md).

## Settings

| Setting | Default | |
| --- | --- | --- |
| `admin.enabled` | `false` | Make the page |
| `admin.repo` | the repository the build runs in | `owner/name`. If the build cannot tell, the page reads it from a `github.io` address, or asks. |
| `admin.branch` | the repository's default branch | Where the commit goes |
| `admin.configPath` | `site.config.json` | For a site that lives in a sub-folder of its repository |

## Turning it on for a site

1. Add `"admin": { "enabled": true }` to the site's `site.config.json`. The site's `deploy.yml` calls `build-site.yml`, which passes the repository to the build; nothing else changes.
2. Check that the site's `deploy.yml` runs on a push to the branch the page saves to, so the commit rebuilds the site (the sites already do).
3. Make sure the site has no `admin/index.html` of its own (the build stops if it does).
