#!/usr/bin/env python3
"""Per-layer error attribution: Unlimited-OCR output vs frozen gold.

Compares each stress case's OCR output (HTML table emitted by the Space) against
gold/gold_balance_sheet_page4.json, row-by-row in document order with fuzzy
label matching, and classifies every discrepancy:

  omission        gold row or cell has content that is absent from OCR output
  disassociation  OCR misreads a label, so its value no longer keys to the
                  correct row identity (row still matchable by order+similarity)
  misattribution  content present but keyed to the wrong column (period);
                  raised when the OCR header dates cannot be parsed
  value_error     right row and column, wrong digits (extra class, reported
                  separately rather than shoehorned into the three above)

Usage: python3 eval/ocr_attribution.py <ocr_raw_txt> <case_name>
Prints a delta table and a per-case summary; writes nothing itself
(the aggregate log is built by eval/ablation_report.py).
"""
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser.normalize import label_key, parse_value
from parser.rows import parse_date

GOLD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "gold", "gold_balance_sheet_page4.json",
)
FACTOR = 1000  # 千円
LABEL_MATCH_THRESHOLD = 0.6


def parse_ocr_table(text: str) -> dict:
    """Parse the OCR HTML table into {columns, rows}.

    Returns:
      columns: list of column keys (dates) in x order
      rows: list of {label, is_header, cells: {col_key: raw}}
    """
    m = re.search(r"<table>(.*?)</table>", text, re.S)
    if not m:
        raise ValueError("no <table> found in OCR output")
    trs = re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S)
    rows = []
    columns = None
    for tr in trs:
        tds = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        is_header = bool(tds and 'colspan="3"' in tds[0][0])
        cells_raw = [td[1].strip() for td in tds]
        if columns is None:
            # header row: first cell empty, then per-column period labels
            dates = [parse_date(c) for c in cells_raw[1:]]
            if any(d is None for d in dates):
                columns = {"parse_failed": True, "dates": dates}
            else:
                columns = dates
            continue
        row = {"label": cells_raw[0], "is_header": is_header, "cells": {}}
        if not is_header and isinstance(columns, list):
            for key, raw in zip(columns, cells_raw[1:]):
                row["cells"][key] = raw
        rows.append(row)
    return {"columns": columns, "rows": rows}


def match_rows(gold_rows, ocr_rows):
    """Order-preserving alignment of gold rows to OCR rows (two-pointer)."""
    matches = []  # (gold_idx, ocr_idx, similarity)
    gi, oi = 0, 0
    while gi < len(gold_rows) and oi < len(ocr_rows):
        g, o = gold_rows[gi], ocr_rows[oi]
        sim = difflib.SequenceMatcher(
            None, g["label_key"], label_key(o["label"])
        ).ratio()
        if sim >= LABEL_MATCH_THRESHOLD:
            matches.append((gi, oi, sim))
            gi += 1
            oi += 1
        else:
            # decide which side to advance: try skipping one OCR row
            if oi + 1 < len(ocr_rows):
                sim_next = difflib.SequenceMatcher(
                    None, g["label_key"], label_key(ocr_rows[oi + 1]["label"])
                ).ratio()
                if sim_next >= LABEL_MATCH_THRESHOLD:
                    matches.append((gi, oi + 1, sim_next))
                    gi += 1
                    oi += 2
                    continue
            # default: gold row missing from OCR
            gi += 1
    return matches


def attribute(case_name: str, ocr_text: str) -> dict:
    gold = json.load(open(GOLD, encoding="utf-8"))
    gold_rows = []
    for r in gold["rows"]:
        gold_rows.append({
            "row_key": "/".join([s for s in r["values"] and [r["label"]]]),
            "label": r["label"],
            "label_key": label_key(r["label"]),
            "row_type": r["row_type"],
            "is_header": r["row_type"] in ("section_header", "group_header"),
            "values": {
                k: (parse_value(v["raw"], FACTOR) if v.get("raw") else None)
                for k, v in r["values"].items()
            },
            "raws": {k: v.get("raw") for k, v in r["values"].items()},
        })
    # rebuild gold row keys from labels + gold order is identity; keys not needed here
    parsed = parse_ocr_table(ocr_text)
    columns = parsed["columns"]
    ocr_rows = parsed["rows"]

    issues = []
    col_misattribution = not isinstance(columns, list)
    if col_misattribution:
        issues.append({
            "class": "misattribution", "layer": "L0",
            "row": "-", "column": "-",
            "gold": "header dates parse to 2025-03-31 / 2026-03-31",
            "ocr": f"header dates unparseable: {columns}",
        })

    matches = match_rows(gold_rows, ocr_rows)
    matched_gold = {m[0] for m in matches}
    matched_ocr = {m[1] for m in matches}

    # omissions: gold rows with no OCR match
    for gi, g in enumerate(gold_rows):
        if gi in matched_gold:
            continue
        cls = "omission"
        issues.append({
            "class": cls, "layer": "L2" if g["is_header"] else "L1",
            "row": g["label"], "column": "-",
            "gold": g["raws"] or "header row", "ocr": "(absent)",
        })

    # spurious OCR rows
    for oi, o in enumerate(ocr_rows):
        if oi not in matched_ocr:
            issues.append({
                "class": "spurious", "layer": "L2", "row": o["label"],
                "column": "-", "gold": "(absent)", "ocr": o["cells"] or "header row",
            })

    # matched rows: label fidelity + cell comparison
    for gi, oi, sim in matches:
        g, o = gold_rows[gi], ocr_rows[oi]
        if sim < 0.999 and not g["is_header"]:
            issues.append({
                "class": "disassociation", "layer": "L1",
                "row": g["label"], "column": "-",
                "gold": g["label"], "ocr": o["label"],
                "note": f"label misread (similarity {sim:.2f}); value present but "
                        "not keyable by label",
            })
        if g["is_header"] and sim < 0.999:
            issues.append({
                "class": "disassociation", "layer": "L2",
                "row": g["label"], "column": "-",
                "gold": g["label"], "ocr": o["label"],
            })
        for col, gcell in g["values"].items():
            oraw = o["cells"].get(col) if not col_misattribution else None
            ocell = parse_value(oraw, FACTOR) if oraw else None
            if gcell is None and ocell is None:
                continue
            if gcell is None and ocell is not None:
                issues.append({"class": "spurious", "layer": "L1",
                               "row": g["label"], "column": col,
                               "gold": "(empty)", "ocr": oraw})
                continue
            if gcell is not None and ocell is None:
                issues.append({"class": "omission", "layer": "L1",
                               "row": g["label"], "column": col,
                               "gold": g["raws"][col], "ocr": "(absent)"})
                continue
            if gcell["display"] != ocell["display"]:
                issues.append({"class": "value_error", "layer": "L1",
                               "row": g["label"], "column": col,
                               "gold": g["raws"][col], "ocr": oraw})
            else:
                # same number: nil vs zero semantics preserved?
                gflags = set(gcell["flags"])
                oflags = set(ocell["flags"])
                if gflags != oflags:
                    issues.append({"class": "flag_error", "layer": "L1",
                                   "row": g["label"], "column": col,
                                   "gold": f"{g['raws'][col]} {sorted(gflags)}",
                                   "ocr": f"{oraw} {sorted(oflags)}"})

    # counts
    n_cells = sum(1 for g in gold_rows for v in g["values"].values() if v is not None)
    by_class = {}
    for i in issues:
        by_class[i["class"]] = by_class.get(i["class"], 0) + 1
    ok_cells = n_cells - sum(
        1
        for i in issues
        if i["class"] in ("omission", "value_error") and i["layer"] == "L1" and i["column"] != "-"
    )
    return {
        "case": case_name,
        "gold_rows": len(gold_rows),
        "ocr_rows": len(ocr_rows),
        "matched_rows": len(matches),
        "gold_cells": n_cells,
        "ok_cells": ok_cells,
        "by_class": by_class,
        "column_misattribution": col_misattribution,
        "issues": issues,
    }


def main() -> int:
    ocr_txt_path, case_name = sys.argv[1], sys.argv[2]
    text = open(ocr_txt_path, encoding="utf-8").read()
    r = attribute(case_name, text)
    print(f"### {r['case']}")
    print(
        f"gold rows {r['gold_rows']} | ocr rows {r['ocr_rows']} | matched {r['matched_rows']}"
    )
    print(f"gold cells {r['gold_cells']} | ok cells {r['ok_cells']}")
    print(f"by class: {json.dumps(r['by_class'], ensure_ascii=False)}")
    print(f"column misattribution: {r['column_misattribution']}")
    print()
    print("| class | layer | row | column | gold | ocr |")
    print("|-------|-------|-----|--------|------|-----|")
    for i in r["issues"]:
        print(
            f"| {i['class']} | {i['layer']} | {i['row']} | {i['column']} "
            f"| {i['gold']} | {i['ocr']} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
