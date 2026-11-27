# Releases

How a change to the engine reaches the sites, a few at a time, and how to take it back.

## Versions

The engine's version is in `VERSION`, and each release is a tag `vX.Y.Z` on this repository.

- **Patch** (1.0.1): a fix. Nothing a site has to change.
- **Minor** (1.1.0): something new that sites can use, or a change in behaviour that no site has to act on. Existing settings and data keep working.
- **Major** (2.0.0): a site has to change something (a setting renamed, a page structure changed, a new data format with no reading of the old one). Each major version says in `CHANGELOG.md` exactly what a site must do.

The data format has its own version (`schemaVersion`, see [the data format](data-format.md)). A new data format arrives with a migration step and is read alongside the old one for at least one release, so it can come in a minor release.

## Channels

`channels.json` says which version each channel builds with:

```json
{ "channels": { "canary": "1.1.0", "beta": "1.0.3", "stable": "1.0.3" } }
```

Each site follows one channel (`engine.channel` in its `site.config.json`). A release goes to `canary` first, then `beta`, then `stable`, and only moves on once the sites on the earlier channel built, passed their own checks and look right. A site with the most thorough checks makes the best canary: if a release breaks something, its checks fail before it is published, and its live site stays as it was.

## Making a release

A release happens by itself when a pull request is merged to `main`. Nobody tags, publishes or moves a channel by hand.

1. Make the change on a branch, with checks, and open a pull request. The **Checks** workflow runs on it.
2. Put a label on the pull request if the release is bigger than a fix: `minor` for something new, `major` for a change a site has to act on. No label means a patch. `no-release` means this merge changes nothing a site builds (a typo in the docs, say) and makes no release. Do not edit `VERSION`, `CHANGELOG.md` or `channels.json` in the pull request; the release does it.
3. Merge. The **Release** workflow (`auto-release.yml`) then does this, in order, and stops at the first failure:
   1. Runs the full checks (`ci.yml`) and a test build of every site in `sites.json` (a site that keeps its files in a sub-folder is found by itself; add `"dir": "Folder"` to its entry in `sites.json` only if there is more than one `site.config.json`). If anything fails, nothing is released and nothing changes.
   2. Works out the new version from the labels of every pull request merged since the last release (the biggest label wins), raises `VERSION`, adds the merged pull requests to `CHANGELOG.md`, tags `vX.Y.Z` and creates the GitHub release with the same notes.
   3. Moves `canary`, `beta` and `stable` in `channels.json` to the new version. A major release is the exception: it is published, but the channels stay where they are and the workflow opens an issue, because a site has to change something first. Move the channels yourself once the sites are ready.
   4. Sends every site in `sites.json` the `engine-release` rebuild request.
   5. Waits for each site's build to finish, then asks each site's live address for its home page. A site that built and answers `200` is fine.
4. If any site failed to build or does not answer `200`, the workflow puts `canary`, `beta` and `stable` back to the previous versions, sends the rebuild request again so every site goes back to what it had, and opens an issue that lists each failing site with a link to its run. The failed release stays published and is never deleted or re-tagged; the fix is the next pull request, which makes the next release.

The workflow's own commits (the version, the changelog and the channels) start with `[auto-release]` and end with `[skip ci]`, and are skipped by the workflow and by **Checks**, so it cannot start itself. Only a message that starts with `[auto-release]` counts, so a pull request can mention it. Do not write `[skip ci]` (or `[no ci]`, `[ci skip]`, `[skip actions]`) in a commit message, PR title or PR description of your own: GitHub then runs no workflows for that commit, and a squash merge copies it into the commit on `main`, which would skip the release. It also ignores a push that only changes `VERSION`, `CHANGELOG.md` or `channels.json`. Two merges in a row make two runs that queue one after the other; the second release includes every pull request merged since the last tag, so none is lost.

A release can still be made by hand, as before: tag `vX.Y.Z` on `main` and publish it, and **Release** (`release.yml`) checks the tag against `VERSION` and fills in the notes. Moving a channel by hand in `channels.json` still sends the rebuild request through **Tell the sites** (`notify-sites.yml`).

### What the release needs set up in GitHub

- **Secret `RELEASE_TOKEN`** (this repository, **Settings > Secrets and variables > Actions**): a fine-grained personal access token that can push to `main`, create tags and releases, and tell and read the sites. Repository access: this repository and every site repository in `sites.json`. Permissions: **Contents** read and write, **Actions** read, **Issues** read and write, **Pull requests** read, **Metadata** read, **Pages** read. Give it an expiry date and a reminder to renew it. `SITES_DISPATCH_TOKEN` is used if `RELEASE_TOKEN` is not set, but it needs the same permissions to do the whole job.
- **Branch protection on `main`**: the workflow pushes two small commits straight to `main`. A token cannot do that through a rule that demands a pull request unless it is allowed to bypass it. Allow the account that owns `RELEASE_TOKEN` to bypass the pull request rule (or use a ruleset with that account as a bypass actor). The default `GITHUB_TOKEN` cannot, and a commit pushed with it would not start the site builds either, which is why a personal token is used.
- **Labels** `minor`, `major` and `no-release` on this repository.
- **Each site** keeps its `deploy.yml` listening for `repository_dispatch` of type `engine-release` (they already do).
- **Settings > Actions > General > Workflow permissions** can stay on read-only; each job asks for what it needs.

Without `RELEASE_TOKEN` the workflow stops at its first step with a message that says so, before anything is changed.

### The build workflow

Each site names the release whose build workflow it uses: `build-site.yml@v1.0.0` in its `deploy.yml` and `check.yml`. That file decides how a site is checked and published, so a change to it does not reach a site through its channel: when a release changes `build-site.yml`, update the tag in each site's two workflows by pull request, canary sites first. Keep the file small and its changes rare. Most releases leave it alone, and the version of the engine a site builds with still comes from its channel.

A release that adds a step to `build-site.yml` (the Discovery Timeline's fetch of the live site's history is one) needs the tag moved in a site's two workflows before that site can use the feature. A site that has not moved its tag, or has not turned the feature on, is built as before. A site that turns the timeline on while still on an older workflow stops with an error that says what to do, rather than publishing a page that forgets its history.

The Discovery Timeline's deploy workflow also needs `pages: write` for the job that calls `build-site.yml`, because the build asks GitHub for the site's Pages address. See [the Discovery Timeline](discovery-timeline.md#publishing-what-a-site-has-to-do).

### The token that tells the sites

Sending a rebuild request to another repository needs a token. Create a fine-grained personal access token on GitHub (**Settings > Developer settings > Fine-grained tokens**) with:

- **Repository access**: only the site repositories in `sites.json`;
- **Permissions**: Contents, read and write (that is what GitHub asks for to send a `repository_dispatch`); nothing else;
- an expiry date, with a reminder to renew it.

Save it in this repository under **Settings > Secrets and variables > Actions** as `SITES_DISPATCH_TOKEN`. Without it nothing breaks: the workflow says it could not tell the sites, and each site can be rebuilt from its own **Actions** tab (**Build and publish the site > Run workflow**).

## Rolling back

- **One site, now**: in that site's **Actions** tab, run **Build and publish the site** with **engine-version** set to the last good version. It builds and publishes with that version this once. The next push or release goes back to the channel.
- **One site, until further notice**: set `engine.version` in its `site.config.json` to the last good version. Remove it once the fix is out.
- **Every site on a channel**: set that channel back to the last good version in `channels.json`. The sites are told and rebuild with it. The automatic release does this for you when a site fails after a release (see above), and files an issue.

A release that is in use is never deleted or re-tagged: a fix is a new release.

## Before a release, check

- [ ] `python3 tests/test_build.py`, `python3 tests/test_discoveries.py`, `python3 tests/test_autorelease.py`, `node tests/check-sample.js` and `node tests/check-timeline.js` pass
- [ ] the pull request has the right label (`minor`, `major` or none), and its title reads well as a release note, because it becomes one
- [ ] for a major version, the pull request description says what each site must do (it goes into the release notes)
- [ ] a site with real data was built with the change (`python3 build/build_site.py --site path/to/site`) and its own checks pass
