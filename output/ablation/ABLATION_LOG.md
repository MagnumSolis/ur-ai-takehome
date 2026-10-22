# Ablation log: deterministic text-layer pipeline vs Unlimited-OCR

- Sample: `balance_sheet_after_correction.pdf` (資産の部, 連結貸借対照表（訂正後）, unit 千円,
  columns 2025-03-31 / 2026-03-31). Gold: `gold/gold_balance_sheet_page4.json` (43 rows, 74 cells).
- Deterministic path: PyMuPDF geometry pipeline (`parser/`).
- OCR path: baidu/Unlimited-OCR Hugging Face Space, mode `base`, prompt `document parsing.`,
  driven via its public Gradio API (`eval/run_ocr_space.py`). No local GPU.
- Error classes: **omission** (gold content absent), **disassociation** (label misread so the
  value no longer keys to its row), **misattribution** (wrong column/period), **value_error**
  (right row+column, wrong digits), **spurious** (content not in gold).

## Deterministic baseline (true text-layer PDF)

```
rows: 43  cells: 74
validation: {"total": 20, "exact": 7, "within_rounding_tolerance": 13, "fail": 0, "incomplete_data": 0}
$ python3 eval/compare_to_gold.py output/canonical.json gold/gold_balance_sheet_page4.json
rows compared: 43   cells compared: 74
gold match: all L0/L1/L2 comparisons clean
```

## Per-case results

### scan_200dpi

- Deterministic pipeline on simulated scan: `usable=False reason=too_few_words words=0`
  → routed away from the text-layer path by design; 0 cells extracted.
- Unlimited-OCR raw output (2425 chars) saved to `output/ablation/scan_200dpi_base_raw.txt`

```
gold rows 43 | ocr rows 43 | matched 43
gold cells 74 | ok cells 73
by class: {"disassociation": 4, "omission": 1}
column misattribution: False
```

| class | layer | row | column | gold | ocr |
|-------|-------|-----|--------|------|-----|
| disassociation | L1 | 短期貸付金 | - | 短期貸付金 | 短則貸付金 |
| disassociation | L1 | 減価償却累計額 | - | 減価償却累計額 | 減価額却累计額 |
| disassociation | L1 | 機械装置及び運搬具 | - | 機械装置及び運搬具 | 機械装置及び連鎖具 |
| disassociation | L1 | 機械装置及び運搬具（純額） | - | 機械装置及び運搬具（純額） | 機械装置及び連鎖具(純額) |
| omission | L1 | 建設仮勘定 | 2025-03-31 | － | (absent) |

### scan_120dpi

- Deterministic pipeline on simulated scan: `usable=False reason=too_few_words words=0`
  → routed away from the text-layer path by design; 0 cells extracted.
- Unlimited-OCR raw output (2425 chars) saved to `output/ablation/scan_120dpi_base_raw.txt`

```
gold rows 43 | ocr rows 43 | matched 43
gold cells 74 | ok cells 73
by class: {"disassociation": 1, "omission": 1}
column misattribution: False
```

| class | layer | row | column | gold | ocr |
|-------|-------|-----|--------|------|-----|
| disassociation | L1 | 短期貸付金 | - | 短期貸付金 | 短期的貨金 |
| omission | L1 | 建設仮勘定 | 2025-03-31 | － | (absent) |

### scan_200dpi_skew

- Deterministic pipeline on simulated scan: `usable=False reason=too_few_words words=0`
  → routed away from the text-layer path by design; 0 cells extracted.
- Unlimited-OCR: **not run** (no raw output at /home/visionary-solis/ur-ai-takehome/output/ablation/scan_200dpi_skew_base_raw.txt)

### scan_200dpi_crop

- Deterministic pipeline on simulated scan: `usable=False reason=too_few_words words=0`
  → routed away from the text-layer path by design; 0 cells extracted.
- Unlimited-OCR: **not run** (no raw output at /home/visionary-solis/ur-ai-takehome/output/ablation/scan_200dpi_crop_base_raw.txt)

## Cross-case comparison

| case | deterministic text-layer pipeline | Unlimited-OCR (base) |
|------|-----------------------------------|----------------------|
| true PDF (text layer) | 74/74 cells, 0 issues, 20/20 invariants pass | not applicable |
| scan_200dpi (simulated scan) | 0 cells (text gate: unusable; routed to OCR path) | 73/74 cells ok, 5 issues |
| scan_120dpi (simulated scan) | 0 cells (text gate: unusable; routed to OCR path) | 73/74 cells ok, 2 issues |
| scan_200dpi_skew (simulated scan) | 0 cells (text gate: unusable; routed to OCR path) | not run |
| scan_200dpi_crop (simulated scan) | 0 cells (text gate: unusable; routed to OCR path) | not run |

## Observations

- The deterministic pipeline extracts 74/74 cells with zero issues on the text-layer
  page; on simulated scans it extracts nothing by design (the gate is the router).
- Unlimited-OCR is digit-perfect on every numeric cell it emits in both completed cases
  (200 dpi and 120 dpi), including `△0` and `△` negatives; its failures concentrate in
  *association* (misread kanji labels: 短則貸付金 / 減価額却累计額 / 機械装置及び連鎖具)
  and one *omission* (the `－` nil cell of 建設仮勘定, lost in both cases).
- 120 dpi was cleaner than 200 dpi on labels (1 disassociation vs 4): per-case OCR error
  patterns are not monotone in resolution.
- OCR row structure (colspan headers) recovers group/section headers, but indent depth
  (gross / 減価償却累計額 / （純額） scoping) is not encoded in the OCR output; the
  order+pattern matching used here would not generalize to reordered tables.
- Simulated scans that alter page geometry (skew, crop) could not complete in this
  session: the Space's anonymous ZeroGPU quota was exhausted (`90 s requested vs 0 s
  left`), and no HF token was available to raise it. Recorded as an operational
  constraint of the free demo, not a model verdict. To complete these cases, set
  `HF_TOKEN` in the environment and re-run `eval/run_ocr_space.py` for the two
  remaining images (the runner now sends the token when present).
- Extra-table observation: on the 120 dpi case the OCR also misread the title line
  (連結貸借対照表 -> 連結資倍対照表); title text is outside the `<table>` element and is
  not counted in the cell attribution above. The page footer `- 4 -` was preserved
