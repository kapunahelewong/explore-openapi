# single-tag-version

This is an earlier, scaled-down version of `generate_docs_site.py` — before
the main script grew to cover every tag in GitHub's API. It documents just
one tag (`issues`, via `TAG_TO_DOCUMENT`) into a single `index.html`.

Kept here as a simpler starting point for anyone who wants to see how the
one-page version worked before it grew into a full multi-page site.

Run it the same way as the main script, from inside this directory:

```
python3 generate_docs_site.py
```

That writes `index.html` right here — open it in a browser.
