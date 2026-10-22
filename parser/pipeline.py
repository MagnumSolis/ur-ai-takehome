"""Pipeline orchestration: PDF page -> canonical JSON model (+ validation)."""
import os

from .extract import detect_columns, get_graphics, text_quality_gate
from .hierarchy import assign_depths, build_tree, type_rows
from .normalize import label_key, parse_value
from .rows import UNIT_FACTORS, parse_page
from .validate import validate


def parse_document(pdf_path: str, page_index: int = 0) -> dict:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    page = doc[page_index]
    words, gate = text_quality_gate(page)
    if not gate["usable"]:
        raise ValueError(f"text layer unusable: {gate.get('reason')}")

    rules, shades = get_graphics(page)
    seps, strategy = detect_columns(page, words, rules)
    parsed = parse_page(words, seps, rules, shades)
    meta, table_rows = parsed["meta"], parsed["table_rows"]

    if not meta["unit_raw"]:
        raise ValueError("unit (単位) not found on page")
    factor = UNIT_FACTORS[meta["unit_raw"]]

    columns = []
    for slot in sorted(meta["columns"]):
        c = meta["columns"][slot]
        key = c["as_of"] or f"slot{slot}"
        columns.append(
            {
                "slot": slot,
                "label": c["label"],
                "as_of": c["as_of"],
                "key": key,
                "x_band": (seps[slot - 1] if slot - 1 < len(seps) else seps[-1],
                           seps[slot] if slot < len(seps) else page.rect.width),
            }
        )
    if len({c["key"] for c in columns}) != len(columns):
        raise ValueError("duplicate column keys")

    titles_text = " / ".join(meta["titles"])
    classification = None
    if "貸借対照表" in titles_text:
        classification = ("連結" if "連結" in titles_text else "単体") + "貸借対照表"

    # attach normalized values keyed by column key
    for r in table_rows:
        r["values"] = {}
        for c in columns:
            raw = r["numbers"].get(c["slot"], "")
            r["values"][c["key"]] = parse_value(raw, factor) if raw else None
        r["label_key"] = label_key(r["label"])

    assign_depths(table_rows)
    type_rows(table_rows)
    issues = build_tree(table_rows)
    for r in table_rows:
        r["row_key"] = "/".join(r["path"])

    model = {
        "source": {
            "file": os.path.basename(pdf_path),
            "page_index": page_index,
            "page_label": meta["page_label"],
            "text_gate": gate,
            "column_detection": {"strategy": strategy, "separators": seps},
            "n_rules": len(rules),
            "n_shaded_bands": len(shades),
            "table_bbox_y": list(parsed["table_bbox"]),
        },
        "document": {
            "classification": classification,
            "corrected": "訂正後" in titles_text,
            "title_lines": meta["titles"],
            "unit_display": meta["unit_raw"],
            "unit_factor": factor,
        },
        "columns": columns,
        "rows": table_rows,
        "structural_issues": issues,
    }
    model["validation"] = validate(model)
    return model
