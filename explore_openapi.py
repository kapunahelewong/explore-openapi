"""
explore_openapi.py

A small script that walks GitHub's real OpenAPI spec, lists all
endpoints tagged "issues", and resolves a $ref pointer to show
the full schema behind an API response.

Run it with: python3 explore_openapi.py
"""

import json

SPEC_PATH = "api.github.com.json"


def load_spec(path):
    """Load an OpenAPI JSON file into a Python dict."""
    with open(path) as f:
        return json.load(f)


def find_endpoints_by_tag(spec, tag):
    """
    Walk every path + HTTP method in the spec and return the ones
    matching a given tag (e.g. 'issues').

    Returns a list of (METHOD, path, summary) tuples.
    """
    http_methods = ("get", "post", "put", "patch", "delete")
    results = []

    for path, methods in spec["paths"].items():
        for http_method, details in methods.items():
            if http_method not in http_methods:
                continue
            if tag in details.get("tags", []):
                results.append(
                    (http_method.upper(), path, details.get("summary", ""))
                )

    return results


def resolve_ref(spec, ref):
    """
    Resolve an OpenAPI $ref string like '#/components/schemas/issue'
    into the actual dict it points to.
    """
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node[part]
    return node


def main():
    spec = load_spec(SPEC_PATH)

    # 1. List all "issues" endpoints
    endpoints = find_endpoints_by_tag(spec, "issues")
    print(f"Found {len(endpoints)} endpoints tagged 'issues':\n")
    for method, path, summary in endpoints:
        print(f"  {method:6} {path:45} {summary}")

    # 2. Resolve the $ref for the Issue schema used in the
    #    "List repository issues" response
    print("\n--- Resolving a $ref ---\n")
    ref = (
        spec["paths"]["/repos/{owner}/{repo}/issues"]["get"]
        ["responses"]["200"]["content"]["application/json"]
        ["schema"]["items"]["$ref"]
    )
    print(f"Ref string: {ref}")

    issue_schema = resolve_ref(spec, ref)
    props = list(issue_schema["properties"].keys())
    print(f"Resolved 'issue' schema has {len(props)} properties.")
    print(f"First 10: {props[:10]}")


if __name__ == "__main__":
    main()