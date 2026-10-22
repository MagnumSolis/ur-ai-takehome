#!/usr/bin/env python3
"""Convert Unlimited-OCR raw output into a canonical-shaped artifact.

Uses ONLY structure visible in the OCR output itself -- no gold data:
  - colspan=3 rows are group/section headers; they build the path stack
  - a header directly after another header APPENDS to the stack; a header
    after plain rows REPLACES the last stack entry (block-closure heuristic)
  - plain rows become items under the current stack, with values normalized
    by the same parser.normalize contract as the deterministic pipeline
  - the unit is parsed from the OCR text's 単位 line when present

The known limitation is deliberate and measured by the probe: the OCR output
does not encode indent depth, so gross / 減価償却累計額 / （純額） rows all land
directly under their subcategory -- their parent-item scoping is lost.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from eval.ocr_attribution import parse_ocr_table  # noqa: E402
from parser.normalize import label_key, parse_value  # noqa: E402
from parser.rows import UNIT_FACTORS  # noqa: E402


def build_artifact(raw_text: str, case: str) -> dict:
    parsed = parse_ocr_table(raw_text)
    columns = parsed["columns"]
    if not isinstance(columns, list):
        raise ValueError("OCR header dates unparseable; artifact would be unkeyable")

    m = re.search(r"単位[:：]\s*(円|千円|百万円)", raw_text)
    unit = m.group(1) if m else "千円"
    factor = UNIT_FACTORS[unit]

    stack: list[str] = []  # open header blocks (folded labels)
    closed_by_subtotal = False
    plain_since_header = False
    rows: list[dict] = []

    for r in parsed["rows"]:
        if r["is_header"]:
            key = label_key(r["label"])
            if stack and not closed_by_subtotal and plain_since_header:
                stack[-1] = key  # sibling of a still-open block
            else:
                stack.append(key)  # child of the deepest open block
            plain_since_header = False
            closed_by_subtotal = False
            continue

        plain_since_header = True
        key = label_key(r["label"])
        path = stack + [key]
        values = {}
        for col, raw in r["cells"].items():
            if raw:
                cell = parse_value(raw, factor)
                if cell is not None:
                    values[col] = cell
        rows.append(
            {
                "row_key": "/".join(path),
                "label": r["label"],
                "row_type": "subtotal" if key.endswith(("合計", "計")) and values else "line_item",
                "values": values,
            }
        )
        # subtotal closure: `<deepest header>合計` pops that header (OCR-visible
        # convention, same rule as the deterministic parser's subtotal closure)
        if stack and key.endswith(("合計", "計")) and key[: -len("合計")] == stack[-1]:
            stack.pop()
            closed_by_subtotal = True
    return {
        "source": {"kind": "unlimited_ocr", "case": case, "unit_display": unit, "unit_factor": factor},
        "columns": [{"slot": i + 1, "key": k, "label": "", "as_of": k} for i, k in enumerate(columns)],
        "rows": rows,
    }


def main() -> int:
    raw_path, case, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    text = open(raw_path, encoding="utf-8").read()
    art = build_artifact(text, case)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(art, f, ensure_ascii=False, indent=2)
    print(f"[artifact] {case}: {len(art['rows'])} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
