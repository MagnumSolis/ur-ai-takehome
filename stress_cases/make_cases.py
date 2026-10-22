#!/usr/bin/env python3
"""Render simulated-scan stress cases from the sample PDF.

Cases (all content-preserving; none removes table content):
  scan_200dpi.png        ~200 dpi plain render (the primary scanned case)
  scan_120dpi.png        120 dpi -- low-resolution fax-grade scan
  scan_200dpi_skew.png   200 dpi rendered with a 2.0 degree rotation (deskew needed)
  scan_200dpi_crop.png   200 dpi with 20pt cropped page edges (over-cropped scan)

Each PNG is also wrapped in an image-only PDF so the text-quality gate
demonstrates correct routing (text layer absent -> not the text-layer path).
Writes stress_cases/manifest.json.
"""
import json
import os
import sys

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, "balance_sheet_after_correction.pdf")
OUT = os.path.join(ROOT, "stress_cases")

CASES = [
    {"name": "scan_200dpi", "dpi": 200, "transform": "plain"},
    {"name": "scan_120dpi", "dpi": 120, "transform": "plain"},
    {"name": "scan_200dpi_skew", "dpi": 200, "transform": "rotate_2deg"},
    {"name": "scan_200dpi_crop", "dpi": 200, "transform": "crop_20pt"},
]


def render(page, case):
    zoom = case["dpi"] / 72.0
    if case["transform"] == "rotate_2deg":
        mat = pymupdf.Matrix(zoom, zoom).prerotate(2.0)
        return page.get_pixmap(matrix=mat, alpha=False)
    if case["transform"] == "crop_20pt":
        clip = pymupdf.Rect(20, 20, page.rect.width - 20, page.rect.height - 20)
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)


def wrap_as_image_pdf(png_path, pdf_path):
    """Image-only PDF: the text-quality gate must reject it."""
    import pymupdf as pm

    pix_info = pm.Pixmap(png_path)
    w, h = pix_info.width, pix_info.height
    doc = pm.open()
    page = doc.new_page(width=w * 72.0 / 200, height=h * 72.0 / 200)
    page.insert_image(page.rect, filename=png_path)
    doc.save(pdf_path)
    pix_info = None
    return w, h


def main():
    if not os.path.exists(PDF):
        sys.exit("sample PDF not present")
    os.makedirs(OUT, exist_ok=True)
    src = pymupdf.open(PDF)
    page = src[0]
    manifest = []
    for case in CASES:
        png = os.path.join(OUT, case["name"] + ".png")
        pix = render(page, case)
        pix.save(png)
        pdf = os.path.join(OUT, case["name"] + ".pdf")
        wrap_as_image_pdf(png, pdf)
        entry = {
            "name": case["name"],
            "dpi": case["dpi"],
            "transform": case["transform"],
            "png": os.path.basename(png),
            "png_bytes": os.path.getsize(png),
            "pixels": [pix.width, pix.height],
            "image_only_pdf": os.path.basename(pdf),
        }
        manifest.append(entry)
        print(
            f"{case['name']}: {pix.width}x{pix.height}px "
            f"{os.path.getsize(png)//1024} KiB  ->  {os.path.basename(pdf)}"
        )
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    # gate check: every image-only PDF must fail the text gate
    from parser.extract import text_quality_gate

    for entry in manifest:
        d = pymupdf.open(os.path.join(OUT, entry["image_only_pdf"]))
        _, rep = text_quality_gate(d[0])
        assert not rep["usable"], entry["name"]
        print(f"gate check {entry['name']}: usable={rep['usable']} reason={rep.get('reason')}")


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    main()
