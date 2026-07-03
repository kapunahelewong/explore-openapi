"""
generate_docs_site.py

Generates one combined HTML page documenting every endpoint tagged
with a given tag (e.g. "issues") -- a small-scale version of what a
generated docs site (Scalar, Redoc, docs-platform) does across a
whole API.

Run it with: python3 generate_docs_site.py
Then open site.html in a browser.
"""

import json

# --- Config -----------------------------------------------------------
# These three constants are the "knobs" for this script. Change TAG_TO_DOCUMENT
# to generate docs for a different slice of the API (e.g. "pulls", "repos").
SPEC_PATH = "api.github.com.json"
TAG_TO_DOCUMENT = "issues"
OUTPUT_FILE = "index.html"


def load_spec(path):
    """Read the OpenAPI spec JSON file off disk and parse it into a dict."""
    with open(path) as f:
        return json.load(f)


def resolve_ref(spec, ref):
    """
    Follow an OpenAPI '$ref' pointer to the object it points at.

    OpenAPI specs reuse shared pieces (parameters, response schemas, etc.)
    instead of repeating them everywhere. Instead of inlining the object,
    the spec just says {"$ref": "#/components/parameters/per_page"}.

    The ref string is a path into the spec itself, e.g.
    "#/components/parameters/per_page" splits into
    ["components", "parameters", "per_page"], and we walk the spec dict
    one key at a time until we land on the real object.
    """
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node[part]
    return node


def resolve_if_ref(spec, item):
    """
    Parameters/responses can be given either inline (a plain dict) or as
    a $ref pointer to a shared definition. Callers don't want to care which
    one they got, so this function normalizes both cases: if it's a $ref,
    resolve it; otherwise just hand back the dict as-is.
    """
    if "$ref" in item:
        return resolve_ref(spec, item["$ref"])
    return item


def find_endpoints_by_tag(spec, tag):
    """Return a list of (method, path, endpoint_dict) tuples matching a tag."""
    http_methods = ("get", "post", "put", "patch", "delete")
    results = []

    # spec["paths"] looks like: {"/repos/{owner}/{repo}/issues": {"get": {...}, "post": {...}}, ...}
    # so we need a nested loop: one path can have multiple HTTP methods defined on it.
    for path, methods in spec["paths"].items():
        for http_method, details in methods.items():
            # Paths objects can also contain non-method keys (like "parameters"
            # shared across all methods on that path), so skip anything that
            # isn't actually an HTTP verb.
            if http_method not in http_methods:
                continue
            # Every endpoint can list multiple tags (categories); we only want
            # the ones tagged with the one we're documenting right now.
            if tag in details.get("tags", []):
                results.append((http_method, path, details))

    return results


def slugify(method, path):
    """Turn 'get /repos/{owner}/{repo}/issues' into a safe HTML id."""
    raw = f"{method}-{path}"
    # HTML ids can't contain "/" or "{"/"}", so strip those out to get
    # something like "get-repos-owner-repo-issues" that's safe to use
    # as an anchor (id="...") and in a URL fragment (href="#...").
    return raw.replace("/", "-").replace("{", "").replace("}", "").strip("-")


def render_parameters_table(spec, parameters):
    """Build an HTML <table> listing every parameter for one endpoint."""
    if not parameters:
        return "<p><em>No parameters.</em></p>"

    rows = []
    for raw_param in parameters:
        # raw_param might be a $ref, so resolve it to the real parameter object first.
        param = resolve_if_ref(spec, raw_param)
        name = param["name"]
        location = param.get("in", "")  # e.g. "path", "query", "header"
        required = "yes" if param.get("required") else "no"
        # Descriptions can be multiple lines/paragraphs; we only show the
        # first line here to keep the table compact.
        description = param.get("description", "").split("\n")[0]
        rows.append(
            f"<tr><td><code>{name}</code></td><td>{location}</td>"
            f"<td>{required}</td><td>{description}</td></tr>"
        )

    # Build the table by gluing the header row and all the data rows together
    # into one big HTML string.
    return (
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Name</th><th>In</th><th>Required</th><th>Description</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def render_responses_table(spec, responses):
    """
    Build an HTML table listing each status code for an endpoint.
    Responses can be inline dicts OR $ref pointers, just like parameters,
    so we resolve each one the same way.
    """
    if not responses:
        return "<p><em>No responses documented.</em></p>"

    rows = []
    # responses is a dict keyed by status code, e.g. {"200": {...}, "404": {...}}
    for status_code, raw_response in responses.items():
        response = resolve_if_ref(spec, raw_response)
        description = response.get("description", "")

        # not every response has a JSON body (e.g. a 204 No Content)
        content = response.get("content", {})
        has_schema = "yes" if "application/json" in content else "no"

        rows.append(
            f"<tr><td><code>{status_code}</code></td><td>{description}</td>"
            f"<td>{has_schema}</td></tr>"
        )

    return (
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Status</th><th>Description</th><th>Has JSON body</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def render_endpoint_section(spec, method, path, endpoint):
    """
    Build the full HTML <section> for one endpoint: a heading with its
    summary, the method + path, a description, and its parameters/responses
    tables. This is the "detail" block that the nav links jump down to.
    """
    slug = slugify(method, path)  # used as this section's HTML id, matched by nav links
    summary = endpoint.get("summary", "")
    description = endpoint.get("description", "").split("\n")[0]
    parameters_html = render_parameters_table(spec, endpoint.get("parameters", []))
    responses_html = render_responses_table(spec, endpoint.get("responses", {}))

    # The <span class="method method-{method}"> gives each row a colored
    # badge (green GET, blue POST, etc.) -- the actual colors live in STYLE below.
    return f"""
    <section id="{slug}" class="endpoint">
        <h2>{summary}</h2>
        <p><code class="route"><span class="method method-{method}">{method.upper()}</span> {path}</code></p>
        <p>{description}</p>
        <h3>Parameters</h3>
        {parameters_html}
        <h3>Responses</h3>
        {responses_html}
    </section>
    """


def render_nav(endpoints):
    """
    Build a table-of-contents linking to each section by its anchor id.
    Each entry mirrors the method badge used in the endpoint section itself,
    so the nav and the detail page look visually consistent.
    """
    items = []
    for method, path, endpoint in endpoints:
        slug = slugify(method, path)
        summary = endpoint.get("summary", "")
        items.append(
            f'<li><a href="#{slug}"><span class="method method-{method}">{method.upper()}</span> {summary}</a></li>'
        )

    return "<ul>" + "".join(items) + "</ul>"


# --- Styling ------------------------------------------------------------
# One big CSS string, injected into the page's <style> tag in render_site().
# Keeping it as a plain triple-quoted string (rather than a separate .css
# file) keeps everything in one script that's easy to run standalone.
STYLE = """
    /* CSS custom properties (variables) so colors are defined once and
       reused everywhere below via var(--name), instead of repeating hex
       codes in a dozen places. */
    :root {
        --bg: #ffffff;
        --text: #1b1f23;
        --muted: #57606a;
        --border: #d8dee4;
        --accent: #0969da;
        --code-bg: #f6f8fa;
    }
    /* Makes width/padding math predictable: an element's declared width
       includes its padding and border, instead of adding on top of it. */
    * { box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        color: var(--text);
        background: var(--bg);
        max-width: 1200px;
        margin: 40px auto;
        padding: 0 20px;
        line-height: 1.5;
    }
    h1 { font-size: 2rem; margin-bottom: 0.25rem; }
    h2 { font-size: 1.35rem; margin-top: 0; }
    /* h3 is used for the "PARAMETERS" / "RESPONSES" sub-headings -- styled
       small and uppercase so it reads as a label rather than a heading. */
    h3 { font-size: 1rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
    .intro {
        color: var(--muted);
        border-bottom: 1px solid var(--border);
        padding-bottom: 20px;
        margin-bottom: 20px;
    }
    .intro p { margin: 0.4em 0; }
    /* The table-of-contents box: a shaded, scrollable panel so a long
       endpoint list (55+ for "issues") doesn't push all the content down. */
    nav {
        background: var(--code-bg);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 12px 20px;
        margin-bottom: 30px;
        max-height: 320px;
        overflow-y: auto;
    }
    /* "columns: 2" splits the <ul> into two side-by-side newspaper-style
       columns; "break-inside: avoid" stops a single <li> from being split
       across the column break. */
    nav ul { list-style: none; margin: 0; padding: 0; columns: 2; column-gap: 24px; }
    nav li { break-inside: avoid; margin: 4px 0; }
    nav a { text-decoration: none; color: var(--accent); font-size: 1rem; }
    nav a:hover { text-decoration: underline; }
    .endpoint {
        margin-bottom: 40px;
        border-bottom: 1px solid var(--border);
        padding-bottom: 24px;
    }
    code.route {
        background: var(--code-bg);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 1rem;
    }
    /* Base look shared by every method badge; the specific background
       color for each HTTP verb is set by the .method-{verb} rules below. */
    .method {
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 2px 6px;
        border-radius: 4px;
        margin-right: 6px;
        color: #fff;
    }
    .method-get { background: #2da44e; }
    .method-post { background: #0969da; }
    .method-put { background: #9a6700; }
    .method-patch { background: #8250df; }
    .method-delete { background: #cf222e; }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 12px 0 20px;
        font-size: 1rem;
    }
    th, td {
        border: 1px solid var(--border);
        padding: 6px 10px;
        text-align: left;
    }
    th { background: var(--code-bg); }
    /* Zebra-striping: shades every other data row so wide tables are
       easier to scan across. */
    tr:nth-child(even) { background: #fafbfc; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
"""


def render_site(spec, tag):
    """
    Assemble the full HTML document: header/intro, the nav table-of-contents,
    then every endpoint section back to back. This is the top-level "page
    builder" that calls all the smaller render_* helpers above.
    """
    endpoints = find_endpoints_by_tag(spec, tag)

    nav_html = render_nav(endpoints)
    # Build one big HTML section per endpoint, then glue them all together
    # into a single string with "".join(...).
    sections_html = "".join(
        render_endpoint_section(spec, method, path, endpoint)
        for method, path, endpoint in endpoints
    )

    return f"""
    <html>
    <head>
        <title>{tag.title()} API Reference</title>
        <meta charset="utf-8">
        <style>{STYLE}</style>
    </head>
    <body>
        <h1>{tag.title()} API Reference</h1>
        <div class="intro">
            <p>Reference docs for every endpoint tagged <code>{tag}</code> in GitHub's REST API,
            generated from its OpenAPI spec.</p>
            <p>Includes {len(endpoints)} endpoints, with each listing its parameters and possible
            responses. Use the index to jump to a specific endpoint.</p>
        </div>
        <nav>{nav_html}</nav>
        <hr>
        {sections_html}
    </body>
    </html>
    """


def main():
    # 1. Load the raw OpenAPI spec from disk.
    spec = load_spec(SPEC_PATH)
    # 2. Turn it into one big HTML string for the tag we care about.
    html = render_site(spec, TAG_TO_DOCUMENT)

    # 3. Write that HTML string out to a file we can open in a browser.
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)

    print(f"Wrote {OUTPUT_FILE} — open it in a browser to see the result.")


if __name__ == "__main__":
    main()
