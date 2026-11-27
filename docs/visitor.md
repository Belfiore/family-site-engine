# Visitor identity: "Who are you?"

Optional. A site can ask each visitor who they are, once, and use the answer to start the family tree from their own place in the family. It is off unless the site turns it on, and a site that leaves it off builds and behaves exactly as before.

It is a **preference, not a login**. It proves nothing and unlocks nothing. Anyone can pick anyone. Who may see the site at all is a separate thing: [private access](access.md).

## What a visitor sees

1. On the first visit, before anything else on the page: a full screen with the question "Who are you?" and a field. A quiet "Continue without choosing" is under it.
2. They start typing. Matches appear as they type, each with a line that tells similar people apart: "Peter and Janet's son" and "Susan's son, lives in Leeds, born 1991". A photograph is shown only where the site allows it.
3. They pick one. "Is this you?" shows the person once more, and "Yes, that is me" confirms. Nothing is remembered until they confirm.
4. A short welcome (about two seconds, any key or tap skips it), then the page. On the family tree the view glides to their card, which is marked "YOU", and "how are we related" starts from them.
5. Next time, nothing is asked: the page opens straight on them.

A small control in the navigation bar shows their first name. It opens a menu: who is being shown, "Not you? Choose someone else", "Forget me on this device", and (on a protected site) "Lock this device". It says in plain words that it is only a preference, kept on the device, never sent anywhere.

A visitor who is not in the tree, or does not want to say, chooses "Continue without choosing". The site then looks exactly as it always did. That choice is remembered too, so they are not asked on every page, and the control stays as a quiet "Who are you?" in case they change their mind.

Matching is forgiving. It ignores capitals and accents ("zoe" finds Zoë), copes with a letter missing, extra or swapped ("Danial", "hartly"), accepts a half-typed name ("Zoë hart"), and searches every name the data holds for a person: given names, surname, `knownAs`, and each of `nameVariants` (so a maiden name finds the person and says "Kate Marsh (maiden name)"). An empty field lists nobody, so the list cannot be used to browse the family.

## What is stored, and where

One record in the browser's `localStorage`, under the key `fs.visitor.v1:<path of the site>` (the path is part of the key because several sites can share one address):

```json
{ "v": 1, "id": "kate-hartley", "skipped": false, "at": "2026-11-27" }
```

A person's id, a flag for "chose not to say", a date and a version. No name, no detail, no password. It is never sent anywhere: no request carries it, there is no cookie for it and no analytics (the tests check this). "Forget me on this device" removes it. If the person is later removed from the data, the visitor is quietly asked again.

## Who can be chosen

The list is built in the browser from `data/people.json`, the same file the tree reads, so it shows nothing the tree does not already show. It leaves out:

- placeholders and unidentified people;
- people in a hidden region (`tree.hiddenRegions`), unless `tree.suspectedRelatives` brings them back onto the tree;
- by default, everyone not marked `isLiving: true` (`visitor.scope: "living"`). Set `visitor.scope` to `"all"` to offer everyone on the tree, for a site whose living flags are incomplete.

A living person's photograph is not shown in the list unless the site sets `visitor.livingPhotos` to `true`. The picker adds no field, no count and no filter beyond what the tree shows.

## Where it is used

- **The family tree** opens centred on the visitor and uses them as the viewpoint (instead of `tree.rootPersonId` and any earlier choice in the viewpoint list). Everything is still on the page and free to move around; a link to a person (`#/person/id`) still opens that person. A visitor who chose nobody gets the tree as it was.
- **Stuart** uses the same choice, so "my grandfather" means theirs. Choosing in Stuart sets it for the site, and forgetting clears Stuart's too.

## For features that come later

When `visitor.enabled` is true, every page has `window.FamilyVisitor` (and nothing when it is off, so test for it):

```js
if (window.FamilyVisitor) {
  FamilyVisitor.status();      // "identified", "skipped" (chose not to say) or "none" (not asked yet)
  FamilyVisitor.id();          // the person's id in data/people.json, or null
  FamilyVisitor.ready.then(function (person) { /* the person's record from people.json, or null */ });
  FamilyVisitor.set(id);       // remember this person
  FamilyVisitor.skip();        // remember that the visitor chose not to say
  FamilyVisitor.clear();       // forget; they will be asked again
  FamilyVisitor.change();      // open the picker
  FamilyVisitor.on(function (d) { /* d.id, d.status, d.reason: "set", "skip", "clear" or "gone" */ });
}
window.addEventListener('familyvisitor:change', function (e) { /* e.detail is the same */ });
```

Rules for anything that uses it:

- Treat it as a preference. Never use it to decide who may see something. If a feature must restrict, that is access (the gate), not identity.
- Do not send it anywhere, put it in a URL, or log it.
- Check the person is on your page's data before using the id (`FamilyVisitor.id()` can be an id your page does not show).
- Anything that puts a name, a link, a count or a picture of a person on a page goes through the same privacy rules as the rest of the engine: living people and hidden regions are the site's own decision, so use the same data the page already reads.
- A site that has it off has no `FamilyVisitor`; the feature must work without it.

## Settings

See [site settings](site-config.md#visitor). `enabled`, `question`, `lead`, `skipLabel`, `welcome`, `livingPhotos`, `scope`.

## Testing

```sh
node tests/check-visitor.js           # in a browser: typeahead, similar names, maiden names, remembered, changed, cleared, tree, phone, reduced motion, privacy
SHOTS=/tmp/shots node tests/check-visitor.js    # also saves screenshots
```
