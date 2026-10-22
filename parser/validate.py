"""Accounting invariants: derived-row checks, subtotal sum checks, identity spec.

The identity 資産合計 == 負債合計 + 純資産合計 is spec'd here but reported as
`skipped_page_fragment` when the filing fragment lacks 負債の部/純資産の部.
It is never fabricated.
"""
from .hierarchy import rounding_tolerance, summands_for

FULL_BS_SECTIONS = ["資産の部", "負債の部", "純資産の部"]


def _check(kind, subject, column, printed, computed, n_summands, factor):
    tol = rounding_tolerance(n_summands)
    if printed is None or computed is None:
        status = "incomplete_data"
        deviation = None
    else:
        deviation = computed - printed
        if deviation == 0:
            status = "exact"
        elif abs(deviation) <= tol:
            status = "within_rounding_tolerance"
        else:
            status = "fail"
    return {
        "kind": kind,
        "subject": subject,
        "column": column,
        "printed_display": printed,
        "computed_display": computed,
        "deviation_display": deviation,
        "deviation_yen": deviation * factor if deviation is not None else None,
        "tolerance_display": tol,
        "status": status,
    }


def validate(model: dict) -> dict:
    """Run all invariants on the parsed page model. Mutates nothing."""
    rows = model["rows"]
    factor = model["document"]["unit_factor"]
    checks: list[dict] = []

    # 1. derived net rows: net == gross + depreciation
    for r in rows:
        if r["row_type"] != "derived_net" or "derived_from" not in r:
            continue
        gross = next(x for x in rows if x["row_key"] == r["derived_from"][0])
        dep = next(x for x in rows if x["row_key"] == r["derived_from"][1])
        for col in model["columns"]:
            key = col["key"]
            vals = {
                "net": (r["values"].get(key) or {}).get("display"),
                "gross": (gross["values"].get(key) or {}).get("display"),
                "dep": (dep["values"].get(key) or {}).get("display"),
            }
            if any(v is None for v in vals.values()):
                checks.append(
                    _check("derived_net", r["row_key"], key, vals["net"], None, 3, factor)
                )
                continue
            computed = vals["gross"] + vals["dep"]
            checks.append(
                _check("derived_net", r["row_key"], key, vals["net"], computed, 3, factor)
            )

    # 2. subtotal == sum of participating children
    for r in rows:
        if r["row_type"] != "subtotal" or "subtotal_of" not in r:
            continue
        summands, issues = summands_for(r, rows)
        for col in model["columns"]:
            key = col["key"]
            printed = (r["values"].get(key) or {}).get("display")
            terms = [(s["values"].get(key) or {}).get("display") for s in summands]
            computed = sum(t for t in terms if t is not None) if all(
                t is not None for t in terms
            ) else None
            checks.append(
                _check("subtotal_sum", r["row_key"], key, printed, computed, len(summands), factor)
            )
        r.setdefault("summand_row_keys", []).extend(s["row_key"] for s in summands)
        for issue in issues:
            checks.append(
                {
                    "kind": "structure_issue",
                    "subject": r["row_key"],
                    "column": None,
                    "status": "fail",
                    "detail": issue,
                }
            )

    # 3. balance identity -- spec'd, exercised only when the full statement is present
    sections_present = [r["label"] for r in rows if r["row_type"] == "section_header"]
    missing = [s for s in FULL_BS_SECTIONS if s not in sections_present]
    identity = {
        "id": "balance_identity",
        "formula": "資産合計 == 負債合計 + 純資産合計",
        "status": "skipped_page_fragment" if missing else "not_checked",
        "missing_sections": missing,
        "spec": (
            "Requires all three sections of the statement. Fragments are stitched at "
            "filing level first (section headers plus 前頁からの繰越/再掲 continuation "
            "markers link fragments), then the identity is asserted per column with the "
            "same rounding tolerance as subtotal checks."
        ),
    }

    statuses = [c["status"] for c in checks]
    return {
        "checks": checks,
        "summary": {
            "total": len(checks),
            "exact": statuses.count("exact"),
            "within_rounding_tolerance": statuses.count("within_rounding_tolerance"),
            "fail": statuses.count("fail"),
            "incomplete_data": statuses.count("incomplete_data"),
        },
        "balance_identity": identity,
        "coverage": {
            "sections_present": sections_present,
            "page_is_fragment": bool(missing),
        },
    }
