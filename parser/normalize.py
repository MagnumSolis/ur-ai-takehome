"""Semantic normalization: sign conventions, nil dashes, unit binding, label keys.

Contract: every cell value becomes a signed integer in 円 (the stated display unit
is folded in), with flags preserving what the raw glyphs encoded:
  negative_zero -- printed as e.g. `△0`; value 0, sign was explicit
  nil_dash      -- printed as `－`/`-`/`—` meaning zero, not a missing cell
  paren_negative-- printed in parentheses (negative in some formats)
"""
import unicodedata

from .extract import nfkc

_DASHES = {"-", "‐", "−", "―", "–", "ー", "－"}
_MINUS_MARKS = {"△", "Δ", "▲"}


def parse_value(raw: str, factor: int) -> dict | None:
    """Parse a raw cell string into {yen, display, flags}. None if not a number."""
    s = nfkc(raw).strip().replace(" ", "")
    if not s:
        return None
    if s in _DASHES:
        return {"raw": raw, "yen": 0, "display": 0, "flags": ["nil_dash"]}
    negative = False
    flags: list[str] = []
    if s[0] in _MINUS_MARKS:
        negative = True
        s = s[1:]
    if s.startswith("(") and s.endswith(")"):
        negative = not negative
        flags.append("paren_negative")
        s = s[1:-1]
    s = s.replace(",", "")
    if not s.isdigit():
        return None
    v = int(s)
    if v == 0 and negative:
        flags.append("negative_zero")
    if negative:
        v = -v
    return {"raw": raw, "yen": v * factor, "display": v, "flags": flags}


def label_key(label: str) -> str:
    """Canonical key: NFKC-folded, whitespace-collapsed."""
    folded = nfkc(label)
    folded = " ".join(folded.split())
    return folded


def fold_width(s: str) -> str:
    return nfkc(s)
