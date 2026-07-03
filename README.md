# explore-openapi

A small script that turns GitHub's own [REST API OpenAPI spec](https://github.com/github/rest-api-description)
into a static, browsable reference page.

**Live site:** https://kapunahelewong.github.io/explore-openapi/

## What it does

[`generate_docs_site.py`](generate_docs_site.py) fetches GitHub's published
`api.github.com.json` OpenAPI spec, pulls out every endpoint tagged `issues`
(configurable via `TAG_TO_DOCUMENT`), and renders them into one
self-contained `index.html` — each endpoint's method, path, description,
parameters, and possible responses, plus a linked table of contents.

It's a small-scale version of what tools like Scalar, Redoc, or Swagger UI
do at a much larger scale.

## Running it locally

```
python3 generate_docs_site.py
```

This regenerates `index.html` from whatever spec GitHub has published at
the time you run it — no local copy of the spec is stored or required.

## Keeping the site fresh

[`.github/workflows/refresh-docs.yml`](.github/workflows/refresh-docs.yml)
runs weekly (and can be triggered manually from the Actions tab), regenerates
`index.html` from the latest spec, and commits it only if something actually
changed. GitHub Pages then redeploys automatically from `main`.
