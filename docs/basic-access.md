# A basic family password (a stopgap, not protection)

Optional. A site that is still on GitHub Pages can ask for one shared family password before it shows its home page, or every page. It is off unless the site turns it on, and a site that leaves it off is built exactly as before.

**Read this first.** This is not security, and it is not private access. GitHub Pages cannot check a password before it serves a file, so the page, the data and the pictures are still public. The password screen is drawn by a small script in the visitor's browser. It stops people who land on the home page and are not family. It does not stop anyone who knows the address of another page or a data file, anyone who reads the page source, anyone with JavaScript turned off, or a search engine. If the site holds anything that must not be public, use [private access](access.md) (a private repository and Cloudflare Pages) instead. The engine says this on every build.

## What a visitor sees

1. They open the home page. Instead of it they get a plain screen with the site's name and one field.
2. A wrong password gets a short message and nothing else. The right one opens the page.
3. That device is remembered for 30 days (`days`). Next time it goes straight in.

By default only the home page asks (`scope: "home"`). With `scope: "all"` every page the engine builds asks, and a device that has given the password is let in to all of them.

## Turning it on

Make the settings with the tool, which asks for the password and does not show it:

```sh
python3 tools/basic-password.py              # the home page only
python3 tools/basic-password.py --scope all  # every page
```

It prints a block like this. Paste it into `site.config.json`:

```json
"basicAccess": {
  "enabled": true,
  "scope": "home",
  "salt": "NuE0nNFEDH2m+Apr2teNsA==",
  "hash": "eMp4nqEAVkyQh74PJmjfawyjRWAMvN9c7qHX5NpqZq8=",
  "iterations": 210000,
  "days": 30
}
```

Commit it. The site rebuilds and the password screen is live. To change the password, run the tool again and replace `salt` and `hash`. Every device is asked again, because what a device remembers is tied to the hash. To turn it off, set `enabled` to `false` or remove the block.

## What is kept, and where

The password is never in the site. The settings hold a random salt and a PBKDF2-SHA256 hash of the password (210,000 rounds). The script hashes what is typed in the browser and compares. The build refuses a settings file with a key called `password`, `passphrase`, `secret`, `token` or `key`, and it refuses `enabled: true` with no valid salt and hash, because that would leave the page open.

A hash in a public file can be guessed against offline by anyone who copies it. A short or common password falls quickly. Use a long passphrase (four or five unrelated words). The hash is slow on purpose, but it is not a substitute for that.

A device remembers one value in its own browser (`localStorage`, key `fse-basic-access`): the hash and an expiry date. It is not the password and nothing is sent anywhere. The `FamilyBasicAccess.lock()` function in the page clears it.

## What it does not do

- It does not keep any file private. The home page's source, the other pages, `data/*.json`, the pictures and Stuart's index can all be fetched directly.
- It does not work with JavaScript off. The page is then shown as it is.
- It does not stop search engines from reading the page.
- It does not tell family members apart. It is one shared password. To remove one person, change the password.
- It has no lockout. A guesser can try as fast as the browser can hash, and a guesser who copies the hash does not need the page at all.
- The password screen needs a secure address (https or localhost) because it uses the browser's own cryptography. On GitHub Pages that is always so.

It cannot be turned on together with `access` (the real password on Cloudflare Pages): use one or the other. It works with the Discovery Timeline and with "Who are you?".

## Settings

| Setting | Default | |
| --- | --- | --- |
| `basicAccess.enabled` | `false` | Turn it on. |
| `basicAccess.scope` | `"home"` | `"home"`: the home page only. `"all"`: every page the engine builds. |
| `basicAccess.salt`, `basicAccess.hash` | none | Made by the tool. Required when it is on. |
| `basicAccess.iterations` | `210000` | Leave as the tool wrote it. |
| `basicAccess.days` | `30` | How long a device is remembered, 1 to 365. |

## Moving to real protection later

Remove the `basicAccess` block when the site moves to [private access](access.md). Nothing else changes.

## Checks

- `python3 tests/test_basic_access.py`: the settings are checked, the password is in no file, and a site without it builds as before.
- `node tests/check-basic-access.js`: the screen holds the page back, takes the right password and refuses a wrong one, remembers the device, forgets it when the hash changes, leaves the other pages alone when the scope is the home page, and the browser and the tool make the same hash. It also fetches an unprotected file, to show what this is not. `SHOTS=dir` saves screenshots.
