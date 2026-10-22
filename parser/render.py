"""Renderers: CSV and HTML, both derived from the canonical JSON (single source of truth)."""
import csv
import html


def _columns(model):
    return model["columns"]


def to_csv(model: dict, path: str) -> None:
    cols = _columns(model)
    header = [
        "row_key",
        "label",
        "depth",
        "row_type",
        "parent",
        "subtotal_of",
    ]
    col_heads = [f"{c['label']}({c['key']})" for c in cols]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header + col_heads + ["flags"])
        for r in model["rows"]:
            flags = set()
            vals = []
            for c in cols:
                cell = r["values"].get(c["key"])
                vals.append("" if cell is None else cell["display"])
                flags.update(cell["flags"] if cell else [])
            w.writerow(
                [
                    r["row_key"],
                    r["label"],
                    r["depth"],
                    r["row_type"],
                    r.get("parent_key") or "",
                    r.get("subtotal_of") or "",
                    *vals,
                    ";".join(sorted(flags)),
                ]
            )


def to_html(model: dict, path: str) -> None:
    cols = _columns(model)
    doc = model["document"]
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>連結貸借対照表</title>",
        "<style>table{border-collapse:collapse;font-family:'Yu Gothic','MS Mincho',serif;}"
        "td,th{border:1px solid #999;padding:2px 8px;}td.num{text-align:right;}"
        "tr.subtotal td{font-weight:bold;background:#e8f2ff;}th.section{background:#dde8f5;}"
        "td.indent{padding-left:calc(8px + var(--d)*1.6em);}</style></head><body>",
        f"<h2>{html.escape('連結貸借対照表')}{'（訂正後）' if doc['corrected'] else ''}</h2>",
        f"<p>単位: {html.escape(doc['unit_display'])}</p>",
        "<table>",
        "<tr><th>科目</th>"
        + "".join(
            f"<th>{html.escape(c['label'])}<br>({html.escape(c['key'])})</th>" for c in cols
        )
        + "</tr>",
    ]
    for r in model["rows"]:
        cls = "subtotal" if r["row_type"] in ("subtotal", "section_header") else ""
        cells = [
            f"<td class='indent' style='--d:{r['depth']}'>{html.escape(r['label'])}</td>"
        ]
        for c in cols:
            cell = r["values"].get(c["key"])
            txt = "" if cell is None else f"{cell['display']:,}".replace("-", "△")
            if cell and "nil_dash" in cell["flags"]:
                txt = "－"
            cells.append(f"<td class='num'>{txt}</td>")
        parts.append(f"<tr class='{cls}'>{''.join(cells)}</tr>")
    parts.append("</table></body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
