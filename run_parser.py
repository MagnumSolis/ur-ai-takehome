#!/usr/bin/env python3
"""CLI: parse a balance-sheet page into canonical JSON + CSV + HTML + validation report."""
import argparse
import json
import os
import sys

from parser.pipeline import parse_document
from parser.render import to_csv, to_html


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf")
    ap.add_argument("-o", "--outdir", default="output")
    ap.add_argument("-p", "--page", type=int, default=0)
    args = ap.parse_args()

    model = parse_document(args.pdf, page_index=args.page)
    os.makedirs(args.outdir, exist_ok=True)

    canonical_path = os.path.join(args.outdir, "canonical.json")
    with open(canonical_path, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    to_csv(model, os.path.join(args.outdir, "balance_sheet.csv"))
    to_html(model, os.path.join(args.outdir, "balance_sheet.html"))
    with open(os.path.join(args.outdir, "validation_report.json"), "w", encoding="utf-8") as f:
        json.dump(model["validation"], f, ensure_ascii=False, indent=2)

    v = model["validation"]
    print(f"rows: {len(model['rows'])}  columns: {[c['key'] for c in model['columns']]}")
    print(f"validation: {json.dumps(v['summary'])}")
    print(f"identity: {v['balance_identity']['status']} missing={v['balance_identity']['missing_sections']}")
    print(f"wrote: {canonical_path}, {args.outdir}/balance_sheet.csv, "
          f"{args.outdir}/balance_sheet.html, {args.outdir}/validation_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
