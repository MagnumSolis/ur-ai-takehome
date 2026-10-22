"""Geometry-layer extraction: word boxes, vector rulings, shaded bands, column detection.

Never trusts content-stream order. All downstream structure comes from coordinates
and vector graphics, with a whitespace-alignment fallback for unruled pages.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def text_quality_gate(page) -> tuple[list[Word], dict]:
    """L0 pre-check: is the text layer present AND usable (not CID-junk)?"""
    words = [Word(*w[:5]) for w in page.get_text("words")]
    report = {"n_words": len(words)}
    if len(words) < 8:
        report.update(usable=False, reason="too_few_words")
        return words, report
    junk = 0
    total = 0
    for w in words:
        for ch in nfkc(w.text):
            total += 1
            if ch == "\ufffd" or 0xE000 <= ord(ch) <= 0xF8FF:
                junk += 1
    ratio = junk / max(total, 1)
    report["replacement_or_pua_char_ratio"] = round(ratio, 4)
    report["usable"] = ratio < 0.05
    if not report["usable"]:
        report["reason"] = "cid_junk"
    return words, report


def get_graphics(page) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float, float]]]:
    """Split vector fills into horizontal rule segments and shaded row bands.

    Returns (rules, shades):
      rules  -- (y0, x0, x1) thin dark fills (horizontal rulings)
      shades -- (y0, y1, x0, x1) taller light fills (background bands, e.g. subtotals)
    """
    rules: list[tuple[float, float, float]] = []
    shades: list[tuple[float, float, float, float]] = []
    for d in page.get_drawings():
        if d["type"] not in ("f", "fs"):
            continue
        r = d["rect"]
        fill = d.get("fill")
        if fill is None:
            continue
        dark = all(c < 0.5 for c in fill)
        if r.height <= 4.0 and r.width >= 15.0 and dark:
            rules.append((r.y0, r.x0, r.x1))
        elif not dark and r.height > 5.0 and r.width >= 15.0:
            shades.append((r.y0, r.y1, r.x0, r.x1))
    rules.sort()
    shades.sort()
    return rules, shades


def detect_columns_from_rules(rules, words: Optional[list[Word]] = None) -> Optional[list[float]]:
    """Column separators from horizontal rulings, by boundary voting.

    Producers draw rulings as per-column segments, so segment starts/ends cluster
    at column boundaries. A boundary is a real separator only if words sit on both
    sides of it (a table-frame edge has words on one side only). Works both for
    full-width rules and for rules spanning only the numeric columns.
    """
    if len(rules) < 3:
        return None
    from collections import Counter

    by_y: dict[float, list[tuple[float, float]]] = {}
    for y, x0, x1 in rules:
        by_y.setdefault(round(y, 1), []).append((x0, x1))
    votes: Counter[float] = Counter()
    for segs in by_y.values():
        for x0, x1 in segs:
            votes[round(x0)] += 1
            votes[round(x1)] += 1
    n_rows = len(by_y)
    keys = sorted(votes)
    clusters: list[list[float]] = []
    for k in keys:
        if clusters and k - clusters[-1][-1] <= 3.0:
            clusters[-1].append(k)
        else:
            clusters.append([k])
    centers = [
        sum(k * votes[k] for k in cl) / sum(votes[k] for k in cl) for cl in clusters
    ]
    counts = [sum(votes[k] for k in cl) for cl in clusters]
    cands = [c for c, n in zip(centers, counts) if n >= 0.5 * n_rows]
    if len(cands) < 2:
        return None
    if words is None:
        return cands
    y_lo, y_hi = min(y for y, _, _ in rules), max(y for y, _, _ in rules)
    region = [w for w in words if y_lo <= w.cy <= y_hi]
    seps = [
        b
        for b in cands
        if any(w.x1 < b - 2 for w in region) and any(w.x0 > b + 2 for w in region)
    ]
    return seps or None


_PURE_NUM_RE = re.compile(r"^[△Δ]?[\d０-９][\d０-９,，]*$")
_DASHES = {"-", "‐", "−", "―", "–", "ー", "－"}


def is_numberish(folded: str) -> bool:
    s = folded.strip()
    if s in _DASHES:
        return True  # nil dash occupying a numeric column
    return bool(_PURE_NUM_RE.match(s))


def detect_columns_from_words(
    words: list[Word], y_range: Optional[tuple[float, float]] = None
) -> Optional[list[float]]:
    """Fallback for unruled tables: cluster right edges of pure numeric words.

    Numeric columns are right-aligned, so x1 clusters tightly per column. Only
    pure numbers and nil dashes vote -- not dates, labels, or footers -- and the
    label-band boundary is derived from label words' right edge.
    """
    region = [w for w in words if y_range[0] <= w.cy <= y_range[1]] if y_range else words
    nums = [w for w in region if is_numberish(nfkc(w.text))]
    if len(nums) < 4:
        return None
    ordered = sorted(nums, key=lambda w: w.x1)
    clusters: list[list[Word]] = [[ordered[0]]]
    for w in ordered[1:]:
        if w.x1 - clusters[-1][-1].x1 <= 3.0:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    clusters = [c for c in clusters if len(c) >= 4]
    if len(clusters) < 2:
        return None
    num_ids = {id(w) for w in nums}
    labels = [w for w in region if id(w) not in num_ids]
    seps: list[float] = []
    for i, cl in enumerate(clusters):
        left_edge = max((w.x1 for w in labels), default=None) if i == 0 else max(
            w.x1 for w in clusters[i - 1]
        )
        right_edge = min(w.x0 for w in cl)
        if left_edge is None or right_edge <= left_edge:
            return None
        seps.append(round((left_edge + right_edge) / 2, 1))
    return seps


def detect_columns(page, words: list[Word], rules) -> tuple[list[float], str]:
    seps = detect_columns_from_rules(rules)
    if seps:
        return seps, "rule_boundaries"
    y_range = (min(y for y, _, _ in rules), max(y for y, _, _ in rules)) if rules else None
    seps = detect_columns_from_words(words, y_range)
    if seps:
        return seps, "right_edge_clusters"
    raise ValueError("no column separators detectable (neither rulings nor number alignment)")
