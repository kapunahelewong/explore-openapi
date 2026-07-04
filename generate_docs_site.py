"""
generate_docs_site.py

Generates a small static docs site covering every endpoint in GitHub's
REST API, grouped by tag -- the same categories ("issues", "repos",
"actions", etc.) GitHub's own docs use. One HTML page per tag, plus an
index.html linking to all of them.

The OpenAPI spec itself is fetched fresh from GitHub every run (see
SPEC_URL below) rather than read from a local file, so the generated
docs always reflect whatever GitHub has published most recently.

Run it with: python3 generate_docs_site.py
Then open docs/index.html in a browser.
"""

import json
import os
import urllib.request

# --- Config -----------------------------------------------------------
# SPEC_URL points at the same api.github.com.json GitHub itself publishes
# and keeps up to date, in its public rest-api-description repo.
SPEC_URL = (
    "https://raw.githubusercontent.com/github/rest-api-description"
    "/main/descriptions/api.github.com/api.github.com.json"
)
# All generated pages live in docs/, since that's one of the two directories
# (the other being the repo root) GitHub Pages can serve a branch from.
OUTPUT_DIR = "docs"
INDEX_FILE = "index.html"


def load_spec(url):
    """Fetch the OpenAPI spec JSON straight from GitHub and parse it."""
    with urllib.request.urlopen(url) as response:
        return json.load(response)


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


def get_all_tags(spec):
    """
    Return every tag that actually has at least one endpoint, as a sorted
    list of (name, description) tuples.

    The spec's top-level "tags" list documents every tag GitHub defines,
    each with a human-written description -- but a few of those aren't
    attached to any operation, so we cross-reference against the paths
    themselves and only keep tags find_endpoints_by_tag would find
    something for.
    """
    tag_descriptions = {t["name"]: t.get("description", "") for t in spec.get("tags", [])}

    http_methods = ("get", "post", "put", "patch", "delete")
    used_tags = set()
    for methods in spec["paths"].values():
        for http_method, details in methods.items():
            if http_method not in http_methods:
                continue
            used_tags.update(details.get("tags", []))

    return sorted((name, tag_descriptions.get(name, "")) for name in used_tags)


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
    # into one big HTML string, wrapped in a div so its corners can be
    # rounded (border-radius doesn't clip table borders on its own).
    return (
        '<div class="table-wrap"><table>'
        "<tr><th>Name</th><th>In</th><th>Required</th><th>Description</th></tr>"
        + "".join(rows)
        + "</table></div>"
    )


def status_badge_class(status_code):
    """
    Map a response status code to a CSS class so 2xx/3xx/4xx/5xx each get
    a distinct badge color -- a glance down the column shows which rows
    are the happy path vs. error cases.
    """
    first_digit = status_code[:1]
    return {
        "2": "status-2xx",
        "3": "status-3xx",
        "4": "status-4xx",
        "5": "status-5xx",
    }.get(first_digit, "status-other")


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

        badge_class = status_badge_class(status_code)
        rows.append(
            f'<tr><td><span class="status-badge {badge_class}">{status_code}</span></td>'
            f"<td>{description}</td><td>{has_schema}</td></tr>"
        )

    return (
        '<div class="table-wrap"><table>'
        "<tr><th>Status</th><th>Description</th><th>Has JSON body</th></tr>"
        + "".join(rows)
        + "</table></div>"
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

    return '<ul id="endpoint-list">' + "".join(items) + "</ul>"


def render_search_script(input_id, item_selector, no_results_id):
    """
    Shared client-side filter: hides every element matching item_selector
    whose text doesn't contain what's typed into input_id. Used for both
    the tag index's search box and each tag page's endpoint search box, so
    the filtering logic only has to be written once.
    """
    return f"""
    <script>
        (function () {{
            var input = document.getElementById("{input_id}");
            var items = Array.prototype.slice.call(document.querySelectorAll("{item_selector}"));
            var noResults = document.getElementById("{no_results_id}");

            input.addEventListener("input", function () {{
                var query = input.value.trim().toLowerCase();
                var visibleCount = 0;

                items.forEach(function (item) {{
                    var matches = item.textContent.toLowerCase().includes(query);
                    item.classList.toggle("hidden", !matches);
                    if (matches) visibleCount += 1;
                }});

                noResults.style.display = visibleCount === 0 ? "block" : "none";
            }});
        }})();
    </script>
    """


# --- Styling ------------------------------------------------------------
# One big CSS string, injected into every page's <style> tag. Keeping it as
# a plain triple-quoted string (rather than a separate .css file) keeps
# everything in one script that's easy to run standalone.
STYLE = """
    /* CSS custom properties (variables) so colors/shadows are defined once
       and reused everywhere below via var(--name), instead of repeating
       hex codes in a dozen places. */
    :root {
        --page-bg: #eef1f6;
        --surface: #ffffff;
        --text: #1a1d24;
        --muted: #667085;
        --border: #e3e6ea;
        --accent: #4f46e5;
        --accent-soft: #eef0fe;
        --code-bg: #f6f7fb;
        --radius: 14px;
        --shadow-sm: 0 1px 2px rgba(16, 24, 40, 0.05);
        --shadow-md: 0 10px 30px rgba(16, 24, 40, 0.08);
    }
    /* Makes width/padding math predictable: an element's declared width
       includes its padding and border, instead of adding on top of it. */
    * { box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        color: var(--text);
        background: var(--page-bg);
        margin: 0;
        padding: 40px 20px;
        line-height: 1.6;
    }
    /* Everything sits inside one elevated "page" card floating on the
       muted background -- the main thing that makes this feel like a
       real docs site instead of an unstyled HTML dump. */
    .page {
        max-width: 1200px;
        margin: 0 auto;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow-md);
        padding: 40px 48px;
    }
    h1 { font-size: 2.1rem; font-weight: 800; letter-spacing: -0.02em; margin: 0 0 0.3rem; }
    h2 { font-size: 1.3rem; font-weight: 700; margin-top: 0; }
    /* h3 is used for the "PARAMETERS" / "RESPONSES" sub-headings -- styled
       small and uppercase so it reads as a label rather than a heading. */
    h3 { font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; margin: 1.4em 0 0.6em; }
    .intro {
        color: var(--muted);
        border-bottom: 1px solid var(--border);
        padding-bottom: 20px;
        margin-bottom: 24px;
    }
    .intro p { margin: 0.4em 0; }
    .back-link {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: var(--accent);
        text-decoration: none;
        font-size: 0.85rem;
        font-weight: 600;
        padding: 6px 14px;
        border-radius: 999px;
        background: var(--code-bg);
        margin-bottom: 20px;
        transition: background 0.15s ease;
    }
    .back-link:hover { background: var(--accent-soft); }
    /* Search inputs (tag index + per-tag endpoint list) share this look:
       a soft pill with a search glyph baked into the placeholder text
       rather than a separate icon element. */
    input[type="search"] {
        display: block;
        width: 100%;
        max-width: 340px;
        padding: 10px 14px;
        margin-bottom: 18px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: var(--code-bg);
        font-size: 0.95rem;
        font-family: inherit;
        color: var(--text);
    }
    input[type="search"]:focus {
        outline: none;
        border-color: var(--accent);
        background: var(--surface);
        box-shadow: 0 0 0 3px var(--accent-soft);
    }
    .hidden { display: none; }
    .no-results { display: none; color: var(--muted); font-size: 0.9rem; }
    /* The table-of-contents box: a shaded, scrollable panel so a long
       endpoint list doesn't push all the content down. */
    nav {
        background: var(--code-bg);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 30px;
        max-height: 360px;
        overflow-y: auto;
    }
    /* "columns: 2" splits the <ul> into two side-by-side newspaper-style
       columns; "break-inside: avoid" stops a single <li> from being split
       across the column break. */
    nav ul { list-style: none; margin: 0; padding: 0; columns: 2; column-gap: 20px; }
    nav li { break-inside: avoid; }
    nav a {
        display: flex;
        align-items: center;
        text-decoration: none;
        color: var(--text);
        font-size: 0.92rem;
        padding: 6px 8px;
        margin: 1px 0;
        border-radius: 8px;
        transition: background 0.12s ease;
    }
    nav a:hover { background: var(--surface); color: var(--accent); }
    .endpoint {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 26px 30px;
        margin-bottom: 24px;
        box-shadow: var(--shadow-sm);
        scroll-margin-top: 20px;
    }
    /* Briefly rings the endpoint you jumped to from the nav, so it's
       obvious the page actually moved. */
    .endpoint:target { box-shadow: 0 0 0 3px var(--accent-soft), var(--shadow-sm); }
    code.route {
        background: var(--code-bg);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 0.95rem;
    }
    /* Base look shared by every method badge; the specific background
       color for each HTTP verb is set by the .method-{verb} rules below. */
    .method {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 52px;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        padding: 3px 8px;
        border-radius: 999px;
        margin-right: 8px;
        color: #fff;
    }
    .method-get { background: #16a34a; }
    .method-post { background: #2563eb; }
    .method-put { background: #d97706; }
    .method-patch { background: #7c3aed; }
    .method-delete { background: #dc2626; }
    .table-wrap {
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
        margin: 8px 0 20px;
    }
    table { border-collapse: collapse; width: 100%; font-size: 0.92rem; }
    th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
    tr:last-child td { border-bottom: none; }
    th {
        background: var(--code-bg);
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--muted);
    }
    /* Zebra-striping: shades every other data row so wide tables are
       easier to scan across. */
    tr:nth-child(even) td { background: #fafbfd; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    /* Response status codes get the same color-coded-pill treatment as
       method badges: green for success, red for error, etc. -- a glance
       at the column tells you which rows are the "happy path". */
    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.8rem;
    }
    .status-2xx { background: #dcfce7; color: #15803d; }
    .status-3xx { background: #e0e7ff; color: #4338ca; }
    .status-4xx { background: #fef3c7; color: #b45309; }
    .status-5xx { background: #fee2e2; color: #b91c1c; }
    .status-other { background: var(--code-bg); color: var(--muted); }
    /* Index page: a responsive card grid, one card per tag. auto-fill +
       minmax means the browser fits as many ~260px cards per row as
       will fit, wrapping as needed -- no media queries required. */
    .tag-list {
        list-style: none;
        margin: 0;
        padding: 0;
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 16px;
    }
    .tag-card {
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px 18px;
        background: var(--surface);
        box-shadow: var(--shadow-sm);
        transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }
    .tag-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-md);
        border-color: var(--accent);
    }
    .tag-card a { text-decoration: none; color: var(--accent); font-size: 1.05rem; font-weight: 700; }
    .tag-count { display: block; color: var(--muted); font-size: 0.78rem; margin: 4px 0; }
    .tag-card p { margin: 6px 0 0; font-size: 0.88rem; }
"""


def render_tag_page(tag, description, endpoints, sections_html):
    """
    Build the full HTML page for one tag: a link back to the tag index, an
    intro naming the tag and how many endpoints it has, a searchable table
    of contents, then every endpoint's section back to back.
    """
    nav_html = render_nav(endpoints)
    search_script = render_search_script("endpoint-search", "#endpoint-list li", "no-endpoint-results")

    return f"""
    <html>
    <head>
        <title>{tag.title()} API Reference</title>
        <meta charset="utf-8">
        <style>{STYLE}</style>
    </head>
    <body>
    <div class="page">
        <a class="back-link" href="index.html">&larr; All tags</a>
        <h1>{tag.title()} API Reference</h1>
        <div class="intro">
            <p>{description}</p>
            <p>{len(endpoints)} endpoints tagged <code>{tag}</code>, each listing its
            parameters and possible responses. Search or scroll the index below to
            jump to a specific endpoint.</p>
        </div>
        <input type="search" id="endpoint-search" placeholder="🔍 Search endpoints…" aria-label="Search endpoints" autocomplete="off">
        <nav>{nav_html}</nav>
        <p id="no-endpoint-results" class="no-results">No endpoints match your search.</p>
        {sections_html}
    </div>
    {search_script}
    </body>
    </html>
    """


def render_index_page(tags_with_counts):
    """
    Build the top-level index.html: a search box, then one card per tag
    linking to "{tag}.html", showing its description and endpoint count.
    """
    total_endpoints = sum(count for _, _, count in tags_with_counts)

    cards = []
    for name, description, count in tags_with_counts:
        cards.append(f"""
        <li class="tag-card">
            <a href="{name}.html"><strong>{name}</strong></a>
            <span class="tag-count">{count} endpoints</span>
            <p>{description}</p>
        </li>
        """)
    tags_html = '<ul class="tag-list" id="tag-list">' + "".join(cards) + "</ul>"
    search_script = render_search_script("tag-search", "#tag-list .tag-card", "no-results")

    return f"""
    <html>
    <head>
        <title>GitHub REST API Reference</title>
        <meta charset="utf-8">
        <style>{STYLE}</style>
    </head>
    <body>
    <div class="page">
        <h1>GitHub REST API Reference</h1>
        <div class="intro">
            <p>Every endpoint in GitHub's REST API, grouped by tag, generated from the published
            OpenAPI spec.</p>
            <p>{total_endpoints} endpoints across {len(tags_with_counts)} tags. Pick one below.</p>
        </div>
        <input type="search" id="tag-search" placeholder="🔍 Search tags…" aria-label="Search tags" autocomplete="off">
        {tags_html}
        <p id="no-results" class="no-results">No tags match your search.</p>
    </div>
    {search_script}
    </body>
    </html>
    """


def main():
    # 1. Fetch the raw OpenAPI spec straight from GitHub (once -- everything
    #    after this is just slicing up the same in-memory spec dict).
    spec = load_spec(SPEC_URL)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 2. Render one page per tag, keeping a running (name, description, count)
    #    list so the index page can link to each one with a live endpoint count.
    tags_with_counts = []
    for name, description in get_all_tags(spec):
        endpoints = find_endpoints_by_tag(spec, name)
        sections_html = "".join(
            render_endpoint_section(spec, method, path, endpoint)
            for method, path, endpoint in endpoints
        )
        html = render_tag_page(name, description, endpoints, sections_html)

        with open(os.path.join(OUTPUT_DIR, f"{name}.html"), "w") as f:
            f.write(html)

        tags_with_counts.append((name, description, len(endpoints)))

    # 3. Render the index page linking out to every tag page just written.
    index_html = render_index_page(tags_with_counts)
    with open(os.path.join(OUTPUT_DIR, INDEX_FILE), "w") as f:
        f.write(index_html)

    total_endpoints = sum(count for _, _, count in tags_with_counts)
    print(
        f"Wrote {OUTPUT_DIR}/{INDEX_FILE} and {len(tags_with_counts)} tag pages "
        f"({total_endpoints} endpoints total) — open {OUTPUT_DIR}/{INDEX_FILE} in a browser."
    )


if __name__ == "__main__":
    main()
