# explore-openapi

A small script that turns GitHub's [REST API OpenAPI spec](https://github.com/github/rest-api-description)
into a static, browsable reference site that includes every endpoint, grouped by tag.

**Live site:** https://kapunahelewong.github.io/explore-openapi/

## What it does

[`generate_docs_site.py`](generate_docs_site.py) fetches GitHub's published
`api.github.com.json` OpenAPI spec, groups all ~1,200 endpoints by tag
(`issues`, `repos`, `actions`, etc. for 47 tags in total), and renders one
HTML page per tag into [`docs/`](docs/). Each doc features each endpoint's method, path,
description, parameters, and possible responses, plus a linked table of
contents. `docs/index.html` lists every tag with a description and endpoint
count, linking out to its page. GitHub Pages serves the site from
the `docs/` folder.

It's a small-scale version of what tools like Scalar, Redoc, or Swagger UI
do at a much larger scale. I created this to play around.

## Running it locally

```
python3 generate_docs_site.py
```

This regenerates `docs/index.html` plus one `docs/{tag}.html` file per tag,
from whatever spec GitHub has published at the time you run it — no local
copy of the spec is stored or required.

## Keeping the site fresh

[`.github/workflows/refresh-docs.yml`](.github/workflows/refresh-docs.yml)
runs weekly (and can be triggered manually from the Actions tab), regenerates
every page from the latest spec, and commits only if something actually
changed. GitHub Pages then redeploys automatically from `main`.

## A smaller, single-tag version

[`examples/single-tag-version/`](examples/single-tag-version/) keeps an
earlier version of `generate_docs_site.py`, from before it grew to cover
every tag — it documents just one tag (`issues`) into a single `index.html`.
If the full multi-page generator feels like a lot, start there. This file has
 lots of comments to clarify what the Python is doing under the hood. 
