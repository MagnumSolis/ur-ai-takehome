"""End-to-end lock-down tests: full pipeline on the sample PDF, compared to frozen gold.

Run: pytest tests/
Requires balance_sheet_after_correction.pdf in the repo root (gitignored).
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, "balance_sheet_after_correction.pdf")
GOLD = os.path.join(ROOT, "gold", "gold_balance_sheet_page4.json")

sys.path.insert(0, ROOT)

from parser.pipeline import parse_document  # noqa: E402
from eval.compare_to_gold import compare  # noqa: E402


@pytest.fixture(scope="module")
def model():
    if not os.path.exists(PDF):
        pytest.skip("sample PDF not present")
    return parse_document(PDF)


def test_l0_document_metadata(model):
    doc = model["document"]
    assert doc["classification"] == "連結貸借対照表"
    assert doc["corrected"] is True
    assert doc["unit_display"] == "千円"
    assert doc["unit_factor"] == 1000
    assert model["source"]["page_label"] == "4"
    cols = [(c["key"], c["label"]) for c in model["columns"]]
    assert cols == [
        ("2025-03-31", "前連結会計年度"),
        ("2026-03-31", "当連結会計年度"),
    ]
    assert model["source"]["text_gate"]["usable"] is True
    assert model["source"]["column_detection"]["strategy"] == "rule_boundaries"


def test_l2_row_set_and_structure(model):
    rows = model["rows"]
    assert len(rows) == 43
    # row keys are unique (repeated labels scoped by hierarchy path)
    keys = [r["row_key"] for r in rows]
    assert len(set(keys)) == 43
    dep_rows = [r for r in rows if r["label"] == "減価償却累計額"]
    assert len(dep_rows) == 4
    assert {r["parent_key"] for r in dep_rows} == {
        "資産の部/固定資産/有形固定資産/建物及び構築物",
        "資産の部/固定資産/有形固定資産/機械装置及び運搬具",
        "資産の部/固定資産/有形固定資産/リース資産",
        "資産の部/固定資産/有形固定資産/その他",
    }
    by_key = {r["row_key"]: r for r in rows}
    assert by_key["資産の部"]["row_type"] == "section_header"
    assert by_key["資産の部/流動資産/貸倒引当金"]["row_type"] == "line_item"
    assert by_key["資産の部/流動資産/貸倒引当金"]["depth"] == 2
    assert by_key["資産の部/流動資産/流動資産合計"]["row_type"] == "subtotal"
    assert by_key["資産の部/固定資産/有形固定資産/建物及び構築物/建物及び構築物(純額)"]["row_type"] == "derived_net"
    assert by_key["資産の部/資産合計"]["row_type"] == "subtotal"
    assert model["structural_issues"] == []


def test_l1_cells_against_gold(model):
    """Full gold comparison: order, labels, depth, row types, raw, values, flags."""
    assert compare.__module__
    out = os.path.join(os.path.dirname(__file__), "_canonical_test.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False)
    try:
        assert compare(out, GOLD) == 0
    finally:
        os.remove(out)


def test_l1_sign_and_nil_semantics(model):
    rows = {r["row_key"]: r for r in model["rows"]}
    # △0 -> value 0, flagged negative zero, NOT missing
    cell = rows["資産の部/流動資産/貸倒引当金"]["values"]["2026-03-31"]
    assert (cell["raw"], cell["display"], cell["yen"]) == ("△0", 0, 0)
    assert cell["flags"] == ["negative_zero"]
    # － -> nil (value 0 with nil_dash), distinct from printed zero
    for key in (
        "資産の部/固定資産/有形固定資産/建設仮勘定",
        "資産の部/固定資産/投資その他の資産/長期貸付金",
    ):
        cell = rows[key]["values"]["2025-03-31"]
        assert (cell["raw"], cell["display"]) == ("－", 0)
        assert cell["flags"] == ["nil_dash"]
    # plain negative
    cell = rows["資産の部/流動資産/貸倒引当金"]["values"]["2025-03-31"]
    assert (cell["raw"], cell["display"], cell["yen"]) == ("△2,979", -2979, -2979000)
    assert cell["flags"] == []


def test_l3_invariants(model):
    v = model["validation"]
    assert v["summary"] == {
        "total": 20,
        "exact": 7,
        "within_rounding_tolerance": 13,
        "fail": 0,
        "incomplete_data": 0,
    }
    assert v["balance_identity"]["status"] == "skipped_page_fragment"
    assert v["balance_identity"]["missing_sections"] == ["負債の部", "純資産の部"]
    # spot-check a real rounding deviation is classified as tolerance, not failure
    sub = next(
        c
        for c in v["checks"]
        if c["kind"] == "subtotal_sum"
        and c["subject"].endswith("流動資産合計")
        and c["column"] == "2025-03-31"
    )
    assert sub["computed_display"] == 5863681
    assert sub["printed_display"] == 5863684
    assert sub["deviation_display"] == -3
    assert sub["status"] == "within_rounding_tolerance"


def test_cli_end_to_end(tmp_path):
    outdir = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "run_parser.py"), PDF, "-o", str(outdir)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "validation: " in proc.stdout
    for name in ("canonical.json", "balance_sheet.csv", "balance_sheet.html", "validation_report.json"):
        assert (outdir / name).exists()
    canonical = json.loads((outdir / "canonical.json").read_text(encoding="utf-8"))
    assert len(canonical["rows"]) == 43
    # CSV renders every row with both columns
    csv_lines = (outdir / "balance_sheet.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(csv_lines) == 44  # header + 43 rows


def test_text_gate_rejects_image_only_page(tmp_path):
    """Simulated scan: an image-only PDF must fail the gate, not produce garbage."""
    import pymupdf

    src = pymupdf.open(PDF)
    pix = src[0].get_pixmap(dpi=100)
    img_pdf = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix)
    doc.save(img_pdf)
    with pytest.raises(ValueError, match="text layer unusable"):
        parse_document(str(img_pdf))
