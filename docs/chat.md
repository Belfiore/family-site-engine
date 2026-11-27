# The site chat

An optional button, usually just above Stuart's, that answers questions from the pages and records on the site. It is off unless a site turns it on. A site that leaves it off is built exactly as before: no script, no stylesheet and no index.

Stuart is separate. He answers in the browser, from his own index, and nothing a visitor types leaves the page. This chat is the one that calls a service. It still does not train on the family, and it does not embed the records. At the moment of the question the browser picks a few passages out of an index the build wrote, and sends only those.

## How a question is answered

1. The build reads the site's HTML pages and `data/people.json`, `data/places.json` and `data/sources.json`, and writes `chat/index.json`.
2. The visitor asks a question. The browser keeps the passages that share words with it (a handful, not the whole site).
3. The browser POSTs `{ "question", "passages" }` to `chat.endpoint`. The service answers from those passages. The key, if there is one, stays on the service.
4. The reply is shown as text, with the titles of the passages under it. Markup in the reply is not treated as HTML.

If no passage shares a word with the question, the browser does not call the service. It says it could not find anything on the site.

People in `tree.hiddenRegions` are left out of the data passages, except a suspected relative, the same way the tree leaves them off. A page the site publishes is read as it is written, including a page that mentions someone the tree hides. Living people are included when their records are already on the site, as they are for Stuart.

## Turning it on

The site runs an answer service somewhere it controls. GitHub Pages cannot run it. `tools/chat-proxy.py` is a small one, or the site can write its own, as long as it speaks the same JSON.

Set the key in the service's environment, not in the site repository and not in the browser:

```sh
CHAT_API_KEY=... python3 tools/chat-proxy.py --host 0.0.0.0 --port 8765
```

`CHAT_API_URL` (default `https://api.openai.com/v1/chat/completions`) and `CHAT_MODEL` (default `gpt-4o-mini`) choose an OpenAI-compatible API. `CHAT_ALLOW_ORIGIN` (default `*`) is the site's origin if you want to limit who can call it. The key is an environment variable, never a command argument.

Without `CHAT_API_KEY` the proxy quotes the passages. That is for a local check. A published site should set the key, and should use an API that does not train on what it is sent. The proxy does not log the question or the passages.

Then, in `site.config.json`:

```json
"chat": {
  "enabled": true,
  "name": "Guide",
  "greeting": "Ask a question about this family. I answer only from the pages and records on this site.",
  "endpoint": "https://answers.example.com/chat"
}
```

`endpoint` is an `https` address with no user, password or query. A query would be published in `chat/index.json`, so a key does not belong there. `http://127.0.0.1` and `http://localhost` are allowed for a local check, and the build refuses anything else.

`name`, `greeting` and `placeholder` are optional. `pages` lists the HTML files to read; leave it out to read every HTML file at the top of the site. `skipClasses` adds classes of page furniture to leave out.

Rebuild the site. The button appears on every page. On Stuart's page it sits at the bottom left, clear of his composer, and the window opens on the right, clear of his seal. On other pages the button sits above his.

The service must answer a cross-origin POST. The proxy sends `Access-Control-Allow-Origin`. On Stuart's page the build adds the endpoint's origin to `connect-src`, because that page has a Content-Security-Policy. Other pages do not.

## What the service receives

```json
{
  "question": "Where did Thomas Hartley live?",
  "passages": [
    {"title": "Thomas Hartley", "url": "family-tree.html", "text": "Lived at 14 Park Row, Leeds (1881)."}
  ]
}
```

It must ignore every other field. A sensible service tells the model to use only the passages, to say when they do not answer, and to treat the passages as information rather than instructions. `tools/chat-proxy.py` does that. The reply is `{ "answer": "..." }`.

## Files

| File | What it does |
| --- | --- |
| `engine/chat.js` | The button, the window, the search over the index, and the call to the endpoint |
| `engine/chat.css` | The button and the window |
| `build/chat_index.py` | Writes `chat/index.json` from the site's pages and data |
| `tools/chat-proxy.py` | A reference answer service. The key stays in its environment |

## Checking it locally

```sh
python3 tools/chat-proxy.py --port 8765
```

Point `chat.endpoint` at `http://127.0.0.1:8765/chat`, build the site, and open it. With no key the answers are sentences from the passages, which is enough to see that the button is reading the site.
