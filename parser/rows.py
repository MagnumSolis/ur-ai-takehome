"""Row clustering and page-region parsing: title, unit, column headers, footer, table rows."""
import bisect
import re

from .extract import Word, nfkc

DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
UNIT_RE = re.compile(r"単位[:：]\s*(円|千円|百万円)")
FOOTER_RE = re.compile(r"^-\s*(\d+)\s*-$")
UNIT_FACTORS = {"円": 1, "千円": 1_000, "百万円": 1_000_000}


def parse_date(s: str) -> str | None:
    m = DATE_RE.search(nfkc(s))
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{y:04d}-{mo:02d}-{d:02d}"


def cluster_rows(words: list[Word], tol: float = 4.0) -> list[list[Word]]:
    """Group words into visual rows by vertical center proximity."""
    rows: list[list[Word]] = []
    anchor: list[Word] = []
    for w in sorted(words, key=lambda w: (w.cy, w.x0)):
        if not rows or abs(w.cy - rows[-1][0].cy) > tol:
            rows.append([w])
        else:
            rows[-1].append(w)
    for r in rows:
        r.sort(key=lambda w: w.x0)
    return rows


def slot_of(word: Word, seps: list[float]) -> int:
    """0 = label band; 1..n = numeric columns left of each separator."""
    return bisect.bisect_left(seps, word.cx)


def parse_page(words: list[Word], seps: list[float], rules, shades) -> dict:
    """Split page into regions and parse each. Returns intermediate page model."""
    table_top = min(y for y, _, _ in rules)
    table_bottom = max(y for y, _, _ in rules)
    meta: dict = {"titles": [], "unit_raw": None, "page_label": None, "columns": {}}
    table_rows: list[dict] = []
    col_label_parts: dict[int, str] = {}
    col_date_parts: dict[int, str] = {}

    for row in cluster_rows(words):
        cy = row[0].cy
        folded_all = nfkc("".join(w.text for w in row)).strip()
        is_header = ("連結会計年度" in folded_all) or DATE_RE.search(folded_all)

        if FOOTER_RE.match(folded_all):
            meta["page_label"] = FOOTER_RE.match(folded_all).group(1)
        elif "単位" in folded_all and UNIT_RE.search(folded_all):
            meta["unit_raw"] = UNIT_RE.search(folded_all).group(1)
        elif cy < table_top or not is_header and cy > table_bottom + 8:
            if folded_all:
                meta["titles"].append(folded_all)
        elif is_header:
            per_slot: dict[int, list[str]] = {}
            for w in row:
                s = slot_of(w, seps)
                if s > 0:
                    per_slot.setdefault(s, []).append(w.text)
            for s, parts in per_slot.items():
                joined = nfkc("".join(parts))
                if DATE_RE.search(joined):
                    col_date_parts[s] = col_date_parts.get(s, "") + joined
                else:
                    col_label_parts[s] = col_label_parts.get(s, "") + joined
        else:
            label_words = [w for w in row if slot_of(w, seps) == 0]
            if not label_words:
                continue  # decorative or stray row
            numbers: dict[int, str] = {}
            for w in row:
                s = slot_of(w, seps)
                if s == 0:
                    continue
                numbers.setdefault(s, "")
                numbers[s] += w.text
            table_rows.append(
                {
                    "label": "".join(w.text for w in label_words),
                    "label_x0": min(w.x0 for w in label_words),
                    "y": cy,
                    "numbers": numbers,
                    "shaded": any(y0 <= cy <= y1 for y0, y1, _, _ in shades),
                }
            )

    for s in sorted(set(col_label_parts) | set(col_date_parts)):
        meta["columns"][s] = {
            "slot": s,
            "label": col_label_parts.get(s, "").strip(),
            "as_of": parse_date(col_date_parts.get(s, "")),
        }
    return {"meta": meta, "table_rows": table_rows, "table_bbox": (table_top, table_bottom)}
