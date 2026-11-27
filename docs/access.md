# Private access: a family password

Optional. A site can ask every visitor for one shared family password before it shows anything: no page, no picture, no data file, no Stuart index. It is off unless the site turns it on, and a site that leaves it off builds and behaves exactly as before.

This is real protection, and it needs a different host. Read [What it needs](#what-it-needs) before turning it on.

## What a visitor sees

1. They open any address on the site. Instead of the page they get a quiet entrance: the site's name, a small family tree that draws itself, and one field for the family password. Nothing of the family is on that page.
2. They type the password. A wrong one gets a plain message and nothing else. The right one opens the page they asked for, deep links included.
3. That device is remembered for 90 days (`access.cookieDays`). Next time they go straight in.
4. If the family also turns on [visitor identity](visitor.md), "Who are you?" comes next, once.

The entrance animation takes about two seconds, any key or tap skips it, it is skipped for visitors who ask their device for reduced motion, and it is skipped on later visits in the same browser tab. It uses the site's own colours and type. It shows no picture unless the site names one (`access.entranceImage`), and then that picture is public.

## How it works

```
 visitor ──► Cloudflare Pages ──► _worker.js (the gate) ──► the site's files
                                      │
              no valid cookie? ◄──────┘  the files are never read, and never sent
              entrance page (401)
```

The build writes `_worker.js` into the built site. On Cloudflare Pages that file is not a page; it is code that runs in front of every request, including requests for pictures and data files. For each request it checks a cookie. No valid cookie, no file.

- **The password** is the `SITE_PASSWORD` secret. It is held by GitHub (a repository secret) and by the Cloudflare Pages project (a Pages secret, set by the deploy workflow). It is not in `site.config.json`, not in the repository, not in the built files, not in the browser's JavaScript and not in the entrance page. The build refuses a settings file that has a key called `password`, `secret`, `token` or the like.
- **The cookie** is called `__Host-fs_access`. It holds an expiry time and a signature (HMAC-SHA256). It is `HttpOnly` (no script can read it), `Secure`, `SameSite=Lax`, with no `Domain`. It does not contain the password.
- **The signing key** is made from the password. So changing the password makes every cookie ever issued fail the check, at once, with no list of sessions to keep.
- **Wrong passwords** are compared in constant time, answered after a short delay, and give no cookie. The password field accepts 256 characters at most.
- **It fails closed.** With no `SITE_PASSWORD` set, the worker answers 503 to everything and serves nothing.
- **Search engines** are told no three ways: `robots.txt` disallows everything, every response carries `X-Robots-Tag: noindex, nofollow, noarchive`, and the entrance page has a robots meta tag.
- Only two things are public: `/robots.txt`, and the entrance picture if the site names one.

Access, identity and what a record shows are three separate things. The password decides who can reach the site. Visitor identity only decides where the tree starts. Which people are drawn (living people, hidden regions) is the site's own decision in its data and settings, as before. None of them feeds another.

## Security guarantees, and their limits

What it gives, tested in `tests/check-gate.js` and `tests/check-access.js` against the real worker:

- Without the cookie, every address returns 401 and no family content: pages, data, pictures, scripts, Stuart's index, `engine-build.json`, with or without a trailing slash, different capitals, `..` segments, encoded slashes, query strings, other methods.
- A tampered, truncated, expired or other-password cookie is refused.
- A new password invalidates all earlier access, including cookies that are still unexpired.
- The password is in no built file, no cookie, no response and no browser storage.

What it does not give. Be plain with the family about these:

- **One shared secret.** Anyone who has the password can give it to someone else, and you cannot tell who did. There are no accounts and no way to remove one person. To remove someone, change the password, which logs out everyone.
- **A guessable password is a weak lock.** There is a delay after each wrong guess but no lockout, because the free Workers plan cannot keep a counter. Use a long passphrase (four or five unrelated words). Add a Cloudflare rate limiting rule on `/__gate/login` (Security, WAF, Rate limiting rules; about five requests a minute per IP) for real protection against guessing.
- **A device that has the cookie is in** until it expires or the password changes. A stolen laptop that is already signed in stays signed in. "Lock this device" in the visitor menu clears the cookie on that device only.
- **Cloudflare can see everything.** The site's files are on Cloudflare's servers and the password is in its secret store. That is the trade for a host that can actually check a password.
- **Someone who is in can save what they see.** This keeps strangers out. It does not stop a family member copying a photograph.
- **Fonts may be fetched from a third party.** The entrance uses the site's own typography. If the site's `head.fonts` points at Google Fonts (as some sites do on every page), a visitor's browser asks Google for the fonts, so Google sees an IP address and browser, even before the password. The gate sends `Referrer-Policy: same-origin`, so the site's address is not passed on. To avoid even that, remove `head.fonts`: the engine's own bundled fonts are then used and nothing leaves the site.
- **The repository must be private.** The site's data and pictures are in its repository. If the repository is public, the "private" site's data is public on GitHub. See below.

## What it needs

GitHub Pages cannot do this. Pages serves files to anyone and cannot run code before it does, and a site on Pages whose repository is public is public. A password screen drawn in the browser over files that are still reachable is not security, and the engine does not offer one. So a protected site needs three things:

1. **A private repository.** The site's data, pictures and Stuart's index are in it. (Public sites stay on GitHub Pages with a public repository, as they are.)
2. **A Cloudflare account** (the free plan is enough) with a Pages project. The deploy workflow makes the project the first time.
3. **Three GitHub secrets** in the site's repository: `SITE_PASSWORD`, `CLOUDFLARE_API_TOKEN` (permission: Cloudflare Pages, Edit) and `CLOUDFLARE_ACCOUNT_ID`.

Why Cloudflare Pages: it runs a worker in front of every request on the free plan, takes a deploy from GitHub Actions with one command, keeps secrets out of the code, and needs no server to look after. Cloudflare Access was considered and rejected because it works by emailing a code to named addresses, which is accounts again. A page that decrypts itself in the browser was rejected because the encrypted files are still public and a short password can be guessed offline, with no delay and no limit.

## Turning it on for a site

1. Make the site's repository private (GitHub, Settings, General, Danger zone, Change visibility). Check that nothing in it has to be public.
2. In Cloudflare, make an API token with Pages edit rights, and note the account id. In the repository's Settings, Secrets and variables, Actions, add `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` and `SITE_PASSWORD` (the family password).
3. In `site.config.json` add:

   ```json
   "access": { "enabled": true, "project": "smith-family-archive", "hint": "Ask Grandma for it." }
   ```

   `project` is the Cloudflare Pages project name: lower case letters, digits and hyphens. The site will be at `https://<project>.pages.dev` (Cloudflare adds letters if the name is taken; the deploy log prints the address). A custom domain can be added in Cloudflare later.
4. In the site's `deploy.yml` pass the secrets to the workflow and move to an engine release that has this feature:

   ```yaml
   jobs:
     site:
       uses: Belfiore/family-site-engine/.github/workflows/build-site.yml@v1.3.0   # the release that has access
       secrets: inherit
       with:
         site-tests: |
           node tests/verify-canvas.js
   ```

   Do the same tag change in `check.yml` so the pull request checks use the same workflow. The job needs `contents: read` only; it no longer needs `pages: write`.
5. Merge. The workflow builds, makes the Cloudflare project if it is not there, sets the password secret, publishes, and then looks at the published address as a stranger would. If anything answers without the password, the run fails and says so.
6. Turn GitHub Pages off for the repository (Settings, Pages, Source: none), so the old public copy is not left behind. Remove the old address from wherever it was shared.
7. Tell the family the new address and the password.
8. If the site is in `sites.json`, add `"protected": true, "url": "https://<project>.pages.dev/"` to its entry so the release checks it is closed instead of expecting a 200.

The Discovery Timeline cannot be on together with access yet: it reads its history from the live site, which a password keeps closed. The build says so.

## Changing the password

Change the `SITE_PASSWORD` secret in GitHub, then run the site's deploy workflow again (Actions, the deploy workflow, Run workflow, or push any change). Cloudflare reads a secret when a deployment is made, so the new password applies from that deployment. Every device is asked for the new password and no old cookie works. Tell the family the new one.

If you only want to log everyone out and keep the password, there is no shortcut: change it to a new one.

## Remembered access, and forgetting a device

Access is remembered in the cookie, for `access.cookieDays` days (default 90, 1 to 365). The visitor menu (the small name control in the navigation bar, when visitor identity is on) has "Lock this device", which clears the cookie. Without visitor identity, a visitor can clear the site's cookies in their browser. Locking a device does not forget who the visitor said they are; that is a separate choice.

## Settings

See [site settings](site-config.md#access). `enabled`, `project`, `kicker`, `wordmark`, `prompt`, `button`, `hint`, `cookieDays`, `entranceImage`.

## Testing a protected build on your own computer

```sh
python3 tests/access_fixtures.py /tmp/fx/site                  # a made-up protected site from the sample family
python3 build/build_site.py --site /tmp/fx/site --out /tmp/fx/out
node tests/gate-server.js /tmp/fx/out "some password" 8787     # runs the real _worker.js; open http://127.0.0.1:8787
node tests/check-gate.js                                       # the security checks
node tests/check-access.js                                     # the same in a browser, plus the first visit
```

`tests/gate-server.js` is a stand-in for Cloudflare Pages that runs the built `_worker.js` in Node. It is the same code, but it is not Cloudflare: the first real deploy needs the checks in the workflow to pass, and that is where a difference between the two would show.

## If something goes wrong

- **The deploy fails with "secret is not set".** One of the three secrets is missing from the site's repository.
- **The deploy fails at "Check the gate is closed".** The published site answered without a password. Cloudflare did not use `_worker.js` (check the project is a Pages project, not a Workers one) or the secret is missing. Treat the site as open until a later run passes; delete the Pages project in Cloudflare if you need it closed now.
- **Everyone sees "This site is not set up yet" (503).** The Pages project has no `SITE_PASSWORD`. Run the deploy workflow again.
- **The password is right and the page still asks.** The browser is blocking cookies for the site, or the clock on the device is badly wrong.
