"""Hierarchy inference: depth from indent, row typing, subtotal closure, derived rows.

Structural rules (deterministic, corroborated by arithmetic):
  depth    -- indent level of the label's x0 (clustered)
  subtotal at depth L closes the innermost still-open group at depth L-1
             (Japanese BS convention: subtotals align with the group's items)
  triplet  -- item X, followed by 減価償却累計額 (L+1), followed by `X（純額）` (L+1):
             the net row is the value that participates in the parent subtotal;
             gross and depreciation rows do not.
"""
import math
import re

from .normalize import label_key

SUBTOTAL_RE = re.compile(r"(合計|小計|計)$")
DEPRECIATION_RE = re.compile(r"(償却累計額|償却累計額)$")
NET_RE = re.compile(r"[（(]\s*純額\s*[)）]$")


def assign_depths(table_rows: list[dict]) -> None:
    xs = sorted({round(r["label_x0"], 1) for r in table_rows})
    levels: list[list[float]] = []
    for x in xs:
        if levels and x - levels[-1][-1] <= 2.5:
            levels[-1].append(x)
        else:
            levels.append([x])
    x2depth = {x: i for i, lv in enumerate(levels) for x in lv}
    for r in table_rows:
        r["depth"] = x2depth[round(r["label_x0"], 1)]


def type_rows(table_rows: list[dict]) -> None:
    for r in table_rows:
        key = label_key(r["label"])
        has_values = any(v is not None for v in r["values"].values())
        if key.endswith("の部") and not has_values:
            r["row_type"] = "section_header"
        elif SUBTOTAL_RE.search(key) and has_values:
            r["row_type"] = "subtotal"
        elif not has_values:
            r["row_type"] = "group_header"
        else:
            r["row_type"] = "line_item"


def build_tree(table_rows: list[dict]) -> list[str]:
    """Assign parent paths, subtotal closures, and derived triplets.

    Returns a list of structural issues (empty when clean).
    """
    issues: list[str] = []

    # 1. parent = nearest preceding row at smaller depth
    stack: list[dict] = []
    for r in table_rows:
        while stack and stack[-1]["depth"] >= r["depth"]:
            stack.pop()
        r["parent_key"] = "/".join(stack[-1]["path"]) if stack else None
        stack.append(r)
        r["path"] = (stack[-2]["path"] if len(stack) > 1 else []) + [label_key(r["label"])]

    # 2. derived triplets: gross / 減価償却累計額 / （純額）
    for i, r in enumerate(table_rows):
        if r["row_type"] != "line_item":
            continue
        if i + 2 >= len(table_rows):
            continue
        dep, net = table_rows[i + 1], table_rows[i + 2]
        if (
            dep["row_type"] == "line_item"
            and DEPRECIATION_RE.search(label_key(dep["label"]))
            and dep["depth"] == r["depth"] + 1
            and net["depth"] == r["depth"] + 1
            and NET_RE.search(net["label"])
        ):
            gross_key = label_key(r["label"])
            if label_key(net["label"]).startswith(gross_key):
                r["row_type"] = "gross_item"
                dep["row_type"] = "depreciation"
                net["row_type"] = "derived_net"
                net["derived_from"] = ["/".join(r["path"]), "/".join(dep["path"])]
                r["participates_via"] = "/".join(net["path"])

    # 3. subtotal closure: subtotal at depth L closes innermost open group at L-1
    open_groups: list[dict] = []
    for r in table_rows:
        if r["row_type"] in ("section_header", "group_header"):
            for g in list(open_groups):
                if g["depth"] >= r["depth"]:
                    issues.append(f"missing_subtotal:{g['label']}")
                    open_groups.remove(g)
            open_groups.append(r)
        elif r["row_type"] == "subtotal":
            target = None
            for g in reversed(open_groups):
                if g["depth"] == r["depth"] - 1:
                    target = g
                    break
            if target is None:
                issues.append(f"orphan_subtotal:{r['label']}")
                continue
            r["subtotal_of"] = "/".join(target["path"])
            open_groups.remove(target)
    for g in open_groups:
        issues.append(f"missing_subtotal:{g['label']}")
    return issues


def summands_for(subtotal: dict, table_rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Rows whose values must add up to the subtotal, in document order.

    Children of the closed group participate, except that a gross item with a
    derived net row is represented by that net row. Group-header children
    participate through their own closing subtotals.
    """
    group_path = subtotal["subtotal_of"]
    issues: list[str] = []
    group = next(r for r in table_rows if "/".join(r["path"]) == group_path)
    end = table_rows.index(subtotal)
    start = table_rows.index(group)
    children = [
        r
        for r in table_rows[start + 1 : end]
        if r["depth"] == group["depth"] + 1 and r is not subtotal
    ]
    out: list[dict] = []
    for c in children:
        if c["row_type"] in ("group_header", "section_header"):
            closing = [
                r
                for r in table_rows[table_rows.index(c) + 1 : end]
                if r.get("subtotal_of") == "/".join(c["path"])
            ]
            if closing:
                out.append(closing[0])
            else:
                issues.append(f"group_not_closed:{c['label']}")
        elif c["row_type"] == "gross_item" and "participates_via" in c:
            out.append(next(r for r in table_rows if "/".join(r["path"]) == c["participates_via"]))
        elif c["row_type"] == "line_item":
            out.append(c)
        elif c["row_type"] == "subtotal":
            out.append(c)
    return out, issues


def rounding_tolerance(n_summands: int) -> int:
    """Display-unit tolerance for a sum of n independently rounded values."""
    return max(1, math.ceil(n_summands / 2))
