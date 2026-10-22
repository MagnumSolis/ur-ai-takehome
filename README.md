# 連結貸借対照表 Parser — take-home solution

Parse a page of a real Japanese company filing (資産の部 of a 連結貸借対照表, unit 千円, FY
2025-03-31 / 2026-03-31) into a canonical, unit-bound table with explicit hierarchy —
under a measurable definition of correctness — for both text-layer PDFs and scans.

## Problem statement

A 連結貸借対照表 page is easy to read and hard to parse: hierarchy is encoded only in
full-width-space indentation; subtotals close groups by convention; `（純額）` rows are
derived (gross + 減価償却累計額); labels repeat under different parents (`減価償却累計額`
×4, `その他` ×3, `リース資産` ×2); sign/nil conventions are hostile (`△` negatives,
`△0` negative zero, `－` = nil, not zero); the unit is stated once in a floating header;
and column→period order varies by filer. Content-stream order is not reading order, and
scans have no text layer at all.

## Correctness = answerability (RCRR framing)

Following Ur AI's RCRR benchmark (reading-comprehension recovery; technical report:
ur-ai.net/blog/rcrr-technical-report — 14 systems on 99 Japanese IR pages, 1,410 verified
questions), correctness is **the share of answerable meaning that survives conversion**,
not character accuracy. CER/TEDS would score a digit-perfect table whose values are
severed from their row identities as nearly perfect; RCRR scores it as broken meaning.
This repo operationalizes that with a deterministic probe (below) — no model self-grading.

**Normalization contract** (what "equal" means): every cell =
`{row_key = hierarchy path, column_key = period date, value = signed integer in 円 (unit
folded in), flags}`. `△`→negative, `△0`→0 + `negative_zero`, `－`→0 + `nil_dash`
(distinct from printed zero), period keys parsed from header dates, never column position.

| Layer | Question | Metric |
|-------|----------|--------|
| L0 | Right page, right metadata? | field exact match |
| L1 | Right number in the right cell? | cell precision & recall vs gold |
| L2 | Right rows, right tree? | row F1, hierarchy-path equality |
| L3 | Internally coherent? | subtotal = Σ children (±⌈n/2⌉ display units) |
| L4 | Matches the outside world? | prior-filing / XBRL tie-out (future) |

L3 is **zero-label supervision**: the accounting identity
(`資産合計 = 負債合計 + 純資産合計`) and subtotal sums verify most cells with no gold
labels, and a failing subtree localizes the suspect cell.

## Architecture

```
PDF → text-quality gate ─ usable ─► word boxes + vector rulings ─┐
            └─ unusable (scan) ─► OCR engine (baidu/Unlimited-OCR)┤
                                                                 ▼
            cell grid → structural parser (rows, date-driven columns, indent
            depth, subtotal closure at item level, 純額 triplets) → semantic
            normalizer (contract rules) → accounting validator (invariants,
            per-cell confidence) → canonical JSON → CSV/HTML + report
```

Geometry first (never content-stream order); one mid-representation for both front-ends;
deterministic core with the VLM OCR as the scan-path engine; ambiguity is refused, not
guessed. Files: `parser/` (gate/extract/rows/normalize/hierarchy/validate/render/pipeline),
`run_parser.py`.

## Validation on the true PDF

74/74 cells, 43/43 rows exact vs gold; **20/20 invariants pass** (7 exact, 13 within
rounding tolerance, 0 fail). The ±⌈n/2⌉ display-unit tolerance is not leniency: values are
rounded to 千円 independently, so Σ children can legitimately differ from a printed
subtotal by up to n/2 units — observed deviations are 1–3 千円 (e.g. 流動資産合計 FY2025:
Σ 5,863,681 vs printed 5,863,684). An exact-match-only definition would misreport a
correct parse as wrong. `pytest tests/` locks all of this down (7 tests).

**Triangulation**: the extraction was produced three independent ways — the PyMuPDF
geometry pipeline, a poppler `pdftotext -layout` transcription (frozen as gold), and the
project owner's pre-session manual extraction — all agreeing on 43 rows / 74 cells,
including the `△0` and `－` cells.

## Ablation: deterministic pipeline vs Unlimited-OCR (baidu/Unlimited-OCR Space, mode `base`)

Simulated scans (`stress_cases/`, generated from the PDF): 200 dpi, 120 dpi, 2° skew,
20 pt crop; all correctly rejected by the text gate (gate = router).

| condition | deterministic | Unlimited-OCR |
|-----------|---------------|---------------|
| true PDF | 74/74 cells, 20/20 invariants | n/a |
| scan_200dpi | 0 cells (gate rejects) | 73/74 cells ok; 4 label disassociations, 1 nil omission |
| scan_120dpi | 0 cells (gate rejects) | 73/74 cells ok; 1 label disassociation, 1 nil omission |
| skew / crop | 0 cells (gate rejects) | quota-blocked (see below) |

Per-layer attribution (`eval/ocr_attribution.py`, full log `output/ablation/ABLATION_LOG.md`):
OCR values are **digit-perfect on every emitted cell** including `△0`; failures are
**disassociation** (misread kanji labels: 短則貸付金, 減価額却累计額, 機械装置及び連鎖具)
and one consistent **omission** (the `－` nil cell). Error counts are non-monotone in
resolution (120 dpi cleaner than 200 dpi). Skew/crop runs were blocked by the Space's
anonymous ZeroGPU quota exhaustion — an operational constraint of the free demo, not a
model verdict; finish them with: `HF_TOKEN=... python3 eval/run_ocr_space.py
stress_cases/scan_200dpi_skew.png base output/ablation/scan_200dpi_skew_base_raw.txt`.

## Answerability probe (`eval/probe_questions.json`, `eval/probe_runner.py`)

10 authored questions answered by strict path lookup (no model), scored 0/1/2 (2 =
correct + exact path citation; 1 = correct value, degraded provenance; 0 =
wrong/absent/refused-when-answerable). Duplicated labels are refused as ambiguous —
refusal, not guessing. OCR artifacts are built from OCR output alone
(`eval/ocr_to_artifact.py`), so the probe is non-circular.

| question class | deterministic | OCR 200dpi | OCR 120dpi |
|----------------|---------------|------------|------------|
| dup label under specific parent (×3) | 6/6 | 2/6 (2 refused as ambiguous) | 2/6 |
| nil cell | 2 | 0 (omission) | 0 |
| △0 | 2 | 2 | 2 |
| YoY changes (×2) | 4 | 4 | 4 |
| derived 純額 | 2 | 1 (value right, provenance degraded) | 1 |
| subtotal | 2 | 2 | 2 |
| not-on-page liabilities | 2 (refused) | 2 (refused) | 2 (refused) |
| **total** | **20/20** | **13/20** | **13/20** |

Every value the OCR artifacts could produce was correct; they lose exactly the
parent-item scoping and the nil cell. Authoring caught one real spec bug before freeze
(an ambiguous YoY direction convention; fixed with an explicit per-question `direction`
field) — the kind of ambiguity probes exist to surface.

## Limitations

- **Single-page fragment**: only 資産の部 exists. The balance identity is spec'd and
  reported `skipped_page_fragment` — designed, never assumed or faked.
- **Synthetic stress cases**: geometric variants of one page; no other filers, unruled
  layouts, wrapped labels, or true paper scans yet.
- The `misattribution` failure class is implemented but never fired in these runs (both
  OCR headers carried parseable dates).

## Roadmap

Multi-page stitching (前頁からの繰越/再掲 markers, filing-level table identity check);
EDINET XBRL tie-out as free L4 gold; chart parsing (per RCRR, where OCR products lose
~5/6 of meaning); vertical text (縦書き) pages.

## Run

```bash
pip install -r requirements.txt
python3 run_parser.py balance_sheet_after_correction.pdf -o output
pytest tests/                # 7 end-to-end tests
python3 stress_cases/make_cases.py          # regenerate simulated scans
python3 eval/ablation_report.py              # regenerate ABLATION_LOG.md
python3 eval/probe_runner.py output/canonical.json eval/probe_questions.json
```
