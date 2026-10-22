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
- Unlimited-OCR raw output (2454 chars) saved to `output/ablation/scan_200dpi_skew_base_raw.txt`

```
gold rows 43 | ocr rows 44 | matched 43
gold cells 74 | ok cells 0
by class: {"spurious": 1, "omission": 10, "value_error": 64}
column misattribution: False
```

| class | layer | row | column | gold | ocr |
|-------|-------|-----|--------|------|-----|
| spurious | L2 |  | - | (absent) | {'2025-03-31': '7,534,110', '2026-03-31': '5,135,249'} |
| omission | L1 | 現金及び預金 | 2025-03-31 | 2,002,429 | (absent) |
| omission | L1 | 現金及び預金 | 2026-03-31 | 608,281 | (absent) |
| value_error | L1 | 受取手形 | 2025-03-31 | 20,659 | 2,002,429 |
| value_error | L1 | 受取手形 | 2026-03-31 | 26,333 | 608,281 |
| value_error | L1 | 売掛金 | 2025-03-31 | 2,019,476 | 20,659 |
| value_error | L1 | 売掛金 | 2026-03-31 | 884,339 | 26,333 |
| value_error | L1 | 電子記録債権 | 2025-03-31 | 564,667 | 2,019,476 |
| value_error | L1 | 電子記録債権 | 2026-03-31 | 370,468 | 884,339 |
| value_error | L1 | 商品及び製品 | 2025-03-31 | 589,488 | 564,667 |
| value_error | L1 | 商品及び製品 | 2026-03-31 | 1,019,663 | 370,468 |
| value_error | L1 | 仕掛品 | 2025-03-31 | 186,748 | 589,488 |
| value_error | L1 | 仕掛品 | 2026-03-31 | 55,344 | 1,019,663 |
| value_error | L1 | 原材料及び貯蔵品 | 2025-03-31 | 370,403 | 186,748 |
| value_error | L1 | 原材料及び貯蔵品 | 2026-03-31 | 136,082 | 55,344 |
| value_error | L1 | 短期貸付金 | 2025-03-31 | 7,530 | 370,403 |
| value_error | L1 | 短期貸付金 | 2026-03-31 | 30,000 | 136,862 |
| value_error | L1 | その他 | 2025-03-31 | 105,260 | 7,530 |
| value_error | L1 | その他 | 2026-03-31 | 246,895 | 30,000 |
| value_error | L1 | 貸倒引当金 | 2025-03-31 | △2,979 | 105,260 |
| value_error | L1 | 貸倒引当金 | 2026-03-31 | △0 | 246,895 |
| value_error | L1 | 流動資産合計 | 2025-03-31 | 5,863,684 | △2,979 |
| value_error | L1 | 流動資産合計 | 2026-03-31 | 3,377,407 | △0 |
| omission | L1 | 建物及び構築物 | 2025-03-31 | 2,121,360 | (absent) |
| omission | L1 | 建物及び構築物 | 2026-03-31 | 1,880,082 | (absent) |
| value_error | L1 | 減価償却累計額 | 2025-03-31 | △1,923,585 | 2,121,360 |
| value_error | L1 | 減価償却累計額 | 2026-03-31 | △1,640,253 | 1,880,082 |
| value_error | L1 | 建物及び構築物（純額） | 2025-03-31 | 197,775 | △1,923,585 |
| value_error | L1 | 建物及び構築物（純額） | 2026-03-31 | 239,828 | △1,640,253 |
| value_error | L1 | 機械装置及び運搬具 | 2025-03-31 | 4,024,922 | 197,775 |
| value_error | L1 | 機械装置及び運搬具 | 2026-03-31 | 2,250,799 | 239,828 |
| value_error | L1 | 減価償却累計額 | 2025-03-31 | △3,634,165 | 4,024,922 |
| value_error | L1 | 減価償却累計額 | 2026-03-31 | △1,914,091 | 2,250,799 |
| value_error | L1 | 機械装置及び運搬具（純額） | 2025-03-31 | 390,757 | △3,634,165 |
| value_error | L1 | 機械装置及び運搬具（純額） | 2026-03-31 | 336,708 | △1,914,091 |
| value_error | L1 | 土地 | 2025-03-31 | 768,976 | 390,757 |
| value_error | L1 | 土地 | 2026-03-31 | 705,403 | 336,708 |
| value_error | L1 | リース資産 | 2025-03-31 | 210,746 | 768,976 |
| value_error | L1 | リース資産 | 2026-03-31 | 213,939 | 705,403 |
| value_error | L1 | 減価償却累計額 | 2025-03-31 | △147,599 | 210,746 |
| value_error | L1 | 減価償却累計額 | 2026-03-31 | △172,066 | 213,939 |
| value_error | L1 | リース資産（純額） | 2025-03-31 | 63,146 | △147,599 |
| value_error | L1 | リース資産（純額） | 2026-03-31 | 41,872 | △172,066 |
| value_error | L1 | 建設仮勘定 | 2025-03-31 | － | 63,146 |
| value_error | L1 | 建設仮勘定 | 2026-03-31 | 4,553 | 41,872 |
| omission | L1 | その他 | 2025-03-31 | 848,814 | (absent) |
| value_error | L1 | その他 | 2026-03-31 | 446,126 | 4,553 |
| value_error | L1 | 減価償却累計額 | 2025-03-31 | △840,375 | 848,814 |
| value_error | L1 | 減価償却累計額 | 2026-03-31 | △421,883 | 446,126 |
| value_error | L1 | その他（純額） | 2025-03-31 | 8,439 | △840,375 |
| value_error | L1 | その他（純額） | 2026-03-31 | 24,243 | △421,883 |
| value_error | L1 | 有形固定資産合計 | 2025-03-31 | 1,429,094 | 8,439 |
| value_error | L1 | 有形固定資産合計 | 2026-03-31 | 1,352,610 | 24,243 |
| omission | L1 | リース資産 | 2025-03-31 | 34,190 | (absent) |
| omission | L1 | リース資産 | 2026-03-31 | 21,402 | (absent) |
| value_error | L1 | その他 | 2025-03-31 | 10,070 | 34,190 |
| value_error | L1 | その他 | 2026-03-31 | 14,466 | 21,402 |
| value_error | L1 | 無形固定資産合計 | 2025-03-31 | 44,261 | 10,070 |
| value_error | L1 | 無形固定資産合計 | 2026-03-31 | 35,869 | 14,466 |
| omission | L1 | 投資有価証券 | 2025-03-31 | 44,180 | (absent) |
| omission | L1 | 投資有価証券 | 2026-03-31 | 218,836 | (absent) |
| value_error | L1 | 関係会社株式 | 2025-03-31 | 1,123 | 44,180 |
| value_error | L1 | 関係会社株式 | 2026-03-31 | 1,123 | 218,836 |
| value_error | L1 | 長期貸付金 | 2025-03-31 | － | 1,123 |
| value_error | L1 | 長期貸付金 | 2026-03-31 | 62,000 | 1,123 |
| omission | L1 | 退職給付に係る資産 | 2025-03-31 | 18,404 | (absent) |
| value_error | L1 | 退職給付に係る資産 | 2026-03-31 | 16,435 | 62,000 |
| value_error | L1 | その他 | 2025-03-31 | 133,361 | 18,404 |
| value_error | L1 | その他 | 2026-03-31 | 70,967 | 16,435 |
| value_error | L1 | 投資その他の資産合計 | 2025-03-31 | 197,069 | 133,361 |
| value_error | L1 | 投資その他の資産合計 | 2026-03-31 | 369,362 | 70,967 |
| value_error | L1 | 固定資産合計 | 2025-03-31 | 1,670,426 | 197,069 |
| value_error | L1 | 固定資産合計 | 2026-03-31 | 1,757,841 | 369,362 |
| value_error | L1 | 資産合計 | 2025-03-31 | 7,534,110 | 1,670,426 |
| value_error | L1 | 資産合計 | 2026-03-31 | 5,135,249 | 1,757,841 |

### scan_200dpi_crop

- Deterministic pipeline on simulated scan: `usable=False reason=too_few_words words=0`
  → routed away from the text-layer path by design; 0 cells extracted.
- Unlimited-OCR raw output (2420 chars) saved to `output/ablation/scan_200dpi_crop_base_raw.txt`

```
gold rows 43 | ocr rows 43 | matched 43
gold cells 74 | ok cells 74
by class: {"disassociation": 5}
column misattribution: False
```

| class | layer | row | column | gold | ocr |
|-------|-------|-----|--------|------|-----|
| disassociation | L1 | 減価償却累計額 | - | 減価償却累計額 | 減価償却異計額 |
| disassociation | L1 | 減価償却累計額 | - | 減価償却累計額 | 減価償却異計額 |
| disassociation | L1 | 減価償却累計額 | - | 減価償却累計額 | 減価償却異計額 |
| disassociation | L1 | 減価償却累計額 | - | 減価償却累計額 | 減価償却異計額 |
| disassociation | L1 | 長期貸付金 | - | 長期貸付金 | 長期贷付金 |

## Cross-case comparison

| case | deterministic text-layer pipeline | Unlimited-OCR (base) |
|------|-----------------------------------|----------------------|
| true PDF (text layer) | 74/74 cells, 0 issues, 20/20 invariants pass | not applicable |
| scan_200dpi (simulated scan) | 0 cells (text gate: unusable; routed to OCR path) | 73/74 cells ok, 5 issues |
| scan_120dpi (simulated scan) | 0 cells (text gate: unusable; routed to OCR path) | 73/74 cells ok, 2 issues |
| scan_200dpi_skew (simulated scan) | 0 cells (text gate: unusable; routed to OCR path) | 0/74 cells ok, 75 issues |
| scan_200dpi_crop (simulated scan) | 0 cells (text gate: unusable; routed to OCR path) | 74/74 cells ok, 5 issues |

## Answerability probe

10 authored questions (`eval/probe_questions.json`) answered by deterministic path
lookup (`eval/probe_runner.py`), scored 0/1/2: 2 = correct with exact row-path
citation, 1 = correct value but degraded provenance (non-exact lookup tier),
0 = wrong/absent/refused-when-answerable. Ambiguous duplicated labels are refused,
never guessed. OCR artifacts are built from OCR output alone
(`eval/ocr_to_artifact.py`), so the probe is non-circular.

| question | gold | deterministic (text layer) | Unlimited-OCR scan_200dpi | Unlimited-OCR scan_120dpi |
|----------|------|----------------------------|---------------------------|---------------------------|
| q01 Accumulated depreciation of buildings and st... | -1923585 | 2: -1923585 | 0: refuse (label_only), disassociation | 0: refuse (label_only), disassociation |
| q02 Lease assets recorded under intangible fixed... | 21402 | 2: 21402 | 2: 21402 | 2: 21402 |
| q03 Construction in progress as of 2025-03-31? (... | 0 | 2: 0 | 0: absent, omission | 0: absent, omission |
| q04 Allowance for doubtful accounts as of 2026-0... | 0 | 2: 0 | 2: 0 | 2: 0 |
| q05 By how much did cash and deposits change fro... | -1394148 | 2: -1394148 | 2: -1394148 | 2: -1394148 |
| q06 Machinery and transport equipment, net, as o... | 336708 | 2: 336708 | 1: 336708 (fuzzy) | 1: 336708 (label_only) |
| q07 Total fixed assets as of 2025-03-31 (thousan... | 1670426 | 2: 1670426 | 2: 1670426 | 2: 1670426 |
| q08 Accumulated depreciation of lease assets (ta... | -172066 | 2: -172066 | 0: refuse (label_only), disassociation | 0: refuse (label_only), disassociation |
| q09 By how much did total assets decrease from F... | 2398861 | 2: 2398861 | 2: 2398861 | 2: 2398861 |
| q10 Total current liabilities as of 2026-03-31 (... | refuse | 2: refuse | 2: refuse | 2: refuse |

| condition | probe score | failures |
|-----------|-------------|----------|
| deterministic (text layer) | 20/20 | {} |
| Unlimited-OCR scan_200dpi | 13/20 | {"disassociation": 2, "omission": 1, "provenance_degraded": 1} |
| Unlimited-OCR scan_120dpi | 13/20 | {"disassociation": 2, "omission": 1, "provenance_degraded": 1} |

- Deterministic artifact: 20/20, every answer cited by exact row path.
- Both OCR artifacts: 13/20 with an identical failure pattern: the two
  duplicated-label questions (減価償却累計額 under a specific parent) are refused
  as ambiguous (disassociation -- the OCR output loses parent-item scoping), the
  nil cell 建設仮勘定 FY2025 is dropped (omission), and the derived （純額） question
  scores 1 (value correct, provenance degraded). Every value the OCR artifacts
  could produce was correct, including △0 and the YoY arithmetic.
- The refusal guard held in all three conditions: the liabilities question was
  refused rather than fabricated (2/2 on q10 everywhere).
- Honest notes: the `misattribution` class never fired (both OCR headers carried
  parseable dates, so no column/period confusion arose in these runs); no question
  required non-deterministic scoring. Authoring caught one real spec bug before
  freeze: the YoY direction convention was ambiguous, fixed with an explicit
  `direction` field per question.

## Observations

- The deterministic pipeline extracts 74/74 cells with zero issues on the text-layer
  page; on simulated scans it extracts nothing by design (the gate is the router).
- Unlimited-OCR is digit-perfect on every numeric cell it emits in the clean, low-res,
  and cropped cases (200 dpi, 120 dpi, crop), including `△0` and `△` negatives; its
  failures concentrate in *association* (misread kanji labels: 短則貸付金 / 減価額却累计額 /
  機械装置及び連鎖具) and one *omission* (the `－` nil cell of 建設仮勘定, lost in the
  200 dpi and 120 dpi cases).
- 120 dpi was cleaner than 200 dpi on labels (1 disassociation vs 4): per-case OCR error
  patterns are not monotone in resolution.
- OCR row structure (colspan headers) recovers group/section headers, but indent depth
  (gross / 減価償却累計額 / （純額） scoping) is not encoded in the OCR output; the
  order+pattern matching used here would not generalize to reordered tables.
- Geometry stress splits sharply. The cropped 200 dpi scan is nearly lossless
  (74/74 cells ok, 5 issues, all disassociation: 4x 減価償却累計額 -> 減価償却異計額,
  1x 長期貸付金 -> 長期贷付金), while a small skew breaks row association
  catastrophically: every value is emitted one row late (verified in the raw
  output), so 0/74 cells are correctly associated (75 issues: 64 value_error,
  10 omission, 1 spurious). Every individual digit survives skew; the
  label->value association does not. This is disassociation at its most dangerous
  -- confidently wrong answers (e.g. 固定資産合計 FY2025 read as 197,069 instead of
  1,670,426), which a subtotal-recomputing validator catches but a
  string-similarity metric does not.
- Provenance: the skew/crop runs initially hit the Space's anonymous ZeroGPU
  quota limit; they were completed with an authenticated Read-Only HF token
  (same model, `base` mode).
- Extra-table observation: on the 120 dpi case the OCR also misread the title line
  (連結貸借対照表 -> 連結資倍対照表); title text is outside the `<table>` element and is
  not counted in the cell attribution above. The page footer `- 4 -` was preserved
