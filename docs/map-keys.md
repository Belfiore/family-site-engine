# Map keys

The family map works without any key. Two optional browser keys add to it:

| Key | Setting | What it adds |
| --- | --- | --- |
| MapTiler | `map.maptilerKey` | The satellite map and the historic maps ("Then") |
| Google Maps Embed API | `map.googleEmbedKey` | Street View inside the page, instead of a link to Google Maps |

Both go in `site.config.json`, so they end up in the published pages, where anyone can read them. That is normal for browser keys and is safe only when each key is restricted to the site's own address in its provider's console. Never leave a browser key unrestricted, and never put any other kind of key in the settings.

Create the accounts and keys yourself: they are agreements between you and the provider.

## MapTiler

1. Create a MapTiler account and sign in (the free plan is for non-commercial use).
2. Open **API keys** and click **New key**.
3. Under **Allowed HTTP origins**, enter the site's domain on its own line, with no `https://` and no path: for a GitHub Pages site, `yourname.github.io`.
4. Do not add `localhost` to the key the live site uses: a localhost rule matches any machine.
5. Save, and copy the key into `map.maptilerKey`.

## Google Maps Embed API

1. In the Google Cloud console, open **APIs & Services > Library**, find **Maps Embed API** and enable it. Google asks for a billing account, though the Embed API itself is free.
2. Open **Google Maps Platform > Keys & Credentials** and create an API key.
3. Restrict it to the **Maps Embed API** only.
4. Under **Application restrictions**, choose **Websites** and add the site with its scheme and a star: `https://yourname.github.io/*`.
5. Save, and copy the key into `map.googleEmbedKey`.

## The build-time Street View key

`tools/streetview-viewpoints.mjs` asks Google where the nearest panorama to each place is. It needs a third key, used only on your own machine:

1. In the same Google Cloud project, enable the **Street View Static API**.
2. Create another API key, restricted to the **Street View Static API** only, with no website restriction (the command does not send one).
3. Never put it in `site.config.json` or any other file. Pass it in the environment for one run:

   ```sh
   GOOGLE_STREETVIEW_KEY=your-key node path/to/engine/tools/streetview-viewpoints.mjs --site .
   ```
