#!/usr/bin/env python3
"""Per-layer comparison of a canonical parse against the frozen gold JSON.

Reports L0 (document/metadata), L1 (cells: raw glyph strings, normalized values,
flags), and L2 (row set, order, depth, row_type) discrepancies. Exit code 1 on
any diff.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser.normalize import parse_value


def compare(canonical_path: str, gold_path: str) -> int:
    canon = json.load(open(canonical_path, encoding="utf-8"))
    gold = json.load(open(gold_path, encoding="utf-8"))
    diffs: list[str] = []

    # L0: document metadata
    for field in ("classification", "corrected", "unit_display"):
        if canon["document"][field] != gold["document"][field]:
            diffs.append(f"L0 document.{field}: {canon['document'][field]!r} != {gold['document'][field]!r}")
    if canon["source"]["page_label"] != gold["document"]["page_label"]:
        diffs.append(f"L0 page_label: {canon['source']['page_label']!r} != {gold['document']['page_label']!r}")
    if [c["key"] for c in canon["columns"]] != [c["key"] for c in gold["columns"]]:
        diffs.append(f"L0 columns: {[c['key'] for c in canon['columns']]} != {[c['key'] for c in gold['columns']]}")

    # L2: row set, order, structure
    cr, gr = canon["rows"], gold["rows"]
    if len(cr) != len(gr):
        diffs.append(f"L2 row count: {len(cr)} != {len(gr)}")
    for i, (c, g) in enumerate(zip(cr, gr)):
        for field in ("label", "depth", "row_type"):
            if c[field] != g[field]:
                diffs.append(f"L2 row {i} {field}: {c[field]!r} != {g[field]!r}")

    # L1: cells
    factor = canon["document"]["unit_factor"]
    cells = n_cmp = 0
    for i, (c, g) in enumerate(zip(cr, gr)):
        for col in gold["columns"]:
            key = col["key"]
            gcell = g["values"].get(key)
            ccell = c["values"].get(key)
            cells += 1
            if gcell is None and ccell is None:
                continue
            if gcell is None or ccell is None:
                diffs.append(f"L1 row {i} ({c['label']}) col {key}: presence mismatch")
                continue
            n_cmp += 1
            if ccell["raw"] != gcell["raw"]:
                diffs.append(f"L1 row {i} ({c['label']}) col {key} raw: {ccell['raw']!r} != {gcell['raw']!r}")
                continue
            expect = parse_value(gcell["raw"], factor)
            if (ccell["yen"], ccell["display"]) != (expect["yen"], expect["display"]):
                diffs.append(
                    f"L1 row {i} ({c['label']}) col {key} value: {ccell['display']} != {expect['display']}"
                )
            want_flags = set(gcell.get("flags", []))
            got_flags = set(ccell.get("flags", []))
            if want_flags != got_flags:
                diffs.append(
                    f"L1 row {i} ({c['label']}) col {key} flags: {sorted(got_flags)} != {sorted(want_flags)}"
                )

    print(f"rows compared: {len(gr)}   cells compared: {n_cmp}")
    if diffs:
        print(f"DIFFS ({len(diffs)}):")
        for d in diffs:
            print(" ", d)
        return 1
    print("gold match: all L0/L1/L2 comparisons clean")
    return 0


if __name__ == "__main__":
    sys.exit(compare(sys.argv[1], sys.argv[2]))
