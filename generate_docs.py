"""
generate_docs.py

Takes one endpoint from GitHub's OpenAPI spec and generates a small
HTML documentation page from it -- a miniature version of what tools
like Scalar, Swagger UI, or Redoc do at scale.

Run it with: python3 generate_docs.py
Then open output.html in a browser.
"""

import json

SPEC_PATH = "api.github.com.json"
PATH_TO_DOCUMENT = "/repos/{owner}/{repo}/issue-types"
METHOD_TO_DOCUMENT = "get"
OUTPUT_FILE = "output.html"


def load_spec(path):
    with open(path) as f:
        return json.load(f)


def resolve_ref(spec, ref):
    """Follow a '#/a/b/c' style $ref string to the dict it points to."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node[part]
    return node


def resolve_if_ref(spec, item):
    """Parameters can be inline dicts OR $ref pointers. Normalize both."""
    if "$ref" in item:
        return resolve_ref(spec, item["$ref"])
    return item


def render_parameters_table(spec, parameters):
    """Build an HTML table listing each parameter."""
    rows = []
    for raw_param in parameters:
        param = resolve_if_ref(spec, raw_param)
        name = param["name"]
        location = param.get("in", "")
        required = "yes" if param.get("required") else "no"
        description = param.get("description", "").split("\n")[0]  # first line only
        rows.append(
            f"<tr><td><code>{name}</code></td><td>{location}</td>"
            f"<td>{required}</td><td>{description}</td></tr>"
        )

    return (
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Name</th><th>In</th><th>Required</th><th>Description</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def render_endpoint_html(spec, path, method):
    endpoint = spec["paths"][path][method]

    summary = endpoint.get("summary", "")
    description = endpoint.get("description", "").split("\n")[0]
    parameters_html = render_parameters_table(spec, endpoint.get("parameters", []))

    return f"""
    <html>
    <head><title>{summary}</title></head>
    <body style="font-family: sans-serif; max-width: 800px; margin: 40px auto;">
        <h1>{summary}</h1>
        <p><code style="background:#eee; padding:4px;">{method.upper()} {path}</code></p>
        <p>{description}</p>
        <h2>Parameters</h2>
        {parameters_html}
    </body>
    </html>
    """


def main():
    spec = load_spec(SPEC_PATH)
    html = render_endpoint_html(spec, PATH_TO_DOCUMENT, METHOD_TO_DOCUMENT)

    with open(OUTPUT_FILE, "w") as f:
        f.write(html)

    print(f"Wrote {OUTPUT_FILE} — open it in a browser to see the result.")


if __name__ == "__main__":
    main()