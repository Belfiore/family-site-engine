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

1. Make the change on a branch, with checks, and open a pull request. The **Checks** workflow runs the build checks and the sample site in a browser.
2. Add the change to `CHANGELOG.md` under the new version, and set `VERSION` to it. Merge.
3. Tag the merge and push the tag:

   ```sh
   git tag v1.1.0 && git push origin v1.1.0
   ```

   The **Release** workflow runs every check again, makes sure the tag and `VERSION` agree, and publishes a GitHub release with the notes from `CHANGELOG.md`. No site changes yet.
4. Move `canary` to the new version in `channels.json` on `main`. The **Tell the sites** workflow sends every site in `sites.json` a rebuild request; the canary sites build with the new version, the rest rebuild with the version they already had.
5. Check the canary sites: their **Actions** runs passed, and the pages look right.
6. Move `beta`, check, then `stable`, the same way.

### The workflow tag

Sites call the build workflow as `build-site.yml@v1`, so changes to that file reach every site at once, whatever its channel. Keep that file small and its changes rare and backward compatible. After changing it, move the `v1` tag to the release that has the change, once the canary sites have run it:

```sh
git tag -f v1 v1.1.0 && git push -f origin v1
```

A change to the workflow that sites have to act on is a new major tag (`v2`), which sites move to in their own `deploy.yml`.

### The token that tells the sites

Sending a rebuild request to another repository needs a token. Create a fine-grained personal access token on GitHub (**Settings > Developer settings > Fine-grained tokens**) with:

- **Repository access**: only the site repositories in `sites.json`;
- **Permissions**: Contents, read and write (that is what GitHub asks for to send a `repository_dispatch`); nothing else;
- an expiry date, with a reminder to renew it.

Save it in this repository under **Settings > Secrets and variables > Actions** as `SITES_DISPATCH_TOKEN`. Without it nothing breaks: the workflow says it could not tell the sites, and each site can be rebuilt from its own **Actions** tab (**Build and publish the site > Run workflow**).

## Rolling back

- **One site, now**: in that site's **Actions** tab, run **Build and publish the site** with **engine-version** set to the last good version. It builds and publishes with that version this once. The next push or release goes back to the channel.
- **One site, until further notice**: set `engine.version` in its `site.config.json` to the last good version. Remove it once the fix is out.
- **Every site on a channel**: set that channel back to the last good version in `channels.json`. The sites are told and rebuild with it.

A release is never deleted or re-tagged: a fix is a new release.

## Before a release, check

- [ ] `python3 tests/test_build.py` and `node tests/check-sample.js` pass
- [ ] `CHANGELOG.md` says what changed and, for a major version, what each site must do
- [ ] `VERSION` and the tag agree
- [ ] a site with real data was built with the change (`python3 build/build_site.py --site path/to/site`) and its own checks pass
