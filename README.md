# Consolidated Balance-Sheet Parser (連結貸借対照表)

Take-home project: parse a page of a real Japanese company filing (a consolidated
balance sheet, 資産の部, unit 千円, FY columns 2025-03-31 / 2026-03-31) into a
canonical, unit-bound table with explicit hierarchy, under a measurable
definition of correctness.

## Verified extraction

The sample page (`balance_sheet_after_correction.pdf`, kept out of the repo) was
extracted **three independent ways, all in agreement across 43 rows and 74 value
cells**, including the `△0` negative-zero cell and both `－` nil cells:

1. the deterministic PyMuPDF geometry pipeline in `parser/`;
2. a poppler `pdftotext -layout` transcription (independent extraction code path),
   frozen as `gold/gold_balance_sheet_page4.json`;
3. an independent manual extraction performed before this session and
   cross-checked row-by-row by the project owner.

`eval/compare_to_gold.py` asserts (1) == (2) at every layer; the owner's
pre-session extraction (3) confirms both. `output/validation_report.json`
additionally corroborates via accounting invariants: 20 checks, 7 exact,
13 within rounding tolerance (±⌈n/2⌉ display units, a property of rounding to
千円, not of extraction), 0 fail. The balance identity
`資産合計 == 負債合計 + 純資産合計` is spec'd but reported
`skipped_page_fragment`: the page contains 資産の部 only.

## Usage

```bash
pip install -r requirements.txt        # pymupdf
python3 run_parser.py balance_sheet_after_correction.pdf -o output
pytest tests/                          # end-to-end lock-down
python3 stress_cases/make_cases.py      # renders simulated-scan variants
```

Artifacts in `output/`: `canonical.json` (source of truth: hierarchy paths,
unit-bound 円 values, per-cell flags), `balance_sheet.csv`, `balance_sheet.html`,
`validation_report.json`.

## Correctness layers

| Layer | Question | Metric |
|-------|----------|--------|
| L0 | right page, metadata (unit, periods, classification) | field exact match |
| L1 | right number in the right cell | cell precision/recall vs gold |
| L2 | right row set and hierarchy tree | row F1, tree edit distance |
| L3 | accounting invariants | subtotal = Σ children within rounding tolerance |
| L4 | tie-out (prior filing / XBRL) | not exercised (no continuation page; EDINET hunt deliberately out of scope) |

## Design notes

- Geometry-first: structure comes from word bounding boxes and vector rulings,
  never from content-stream order; `pdftotext -layout` is only used as an
  independent gold source.
- Column separators are voted from ruling-segment boundaries (verified by word
  content on both sides), with a right-edge-clustering fallback for unruled
  pages; period mapping is date-driven, not positional (prior FY is the LEFT
  column on this page, the reverse of many filers).
- Sign/nil contract: `△` prefix = negative; `△0` = value 0 with `negative_zero`
  flag; `－` = nil with `nil_dash` flag (kept distinct from printed zero);
  values are stored in 円 with the 千円 unit folded in.
- Subtotals indent at item level and close the group one level up; `（純額）`
  rows are derived (gross + 減価償却累計額) and are what parent subtotals sum.
- Repeated labels (`減価償却累計額` ×4, `その他` ×3, `リース資産` ×2) are
  scoped by full hierarchy path, which serves as the row key.

## Ablation (scanned variants vs deterministic path)

`stress_cases/` renders the page as simulated scans (~200 dpi, low-dpi, skew,
crop). Each is wrapped in an image-only PDF so the text-quality gate correctly
routes them away from the text-layer path, and they are run through the
Unlimited-OCR Hugging Face Space. `eval/ocr_attribution.py` scores the OCR
output against the frozen gold with per-layer error attribution
(omission / disassociation / misattribution); see `output/ablation/`.
