#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generic PDF OCR extractor.

Features:
- Single PDF or folder batch mode.
- Extracts PDF metadata (page count, title, author, etc.).
- Extracts native PDF text and OCR text (RapidOCR) page-by-page.
- Saves JSON and TXT outputs.
- Optional recursive folder scan.

Dependencies:
    pip install pymupdf numpy rapidocr_onnxruntime

Examples:
    python pdf_ocr_extractor.py --input "D:\\docs\\a.pdf"
    python pdf_ocr_extractor.py --input "D:\\docs" --recursive
    python pdf_ocr_extractor.py --input "D:\\docs\\a.pdf" --dpi-scale 2.5 --skip-native-text
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # pymupdf
import numpy as np
from rapidocr_onnxruntime import RapidOCR


@dataclass
class PageExtraction:
    page_index: int
    native_text: str
    ocr_text: str
    combined_text: str
    ocr_line_count: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "page_index": self.page_index,
            "native_text": self.native_text,
            "ocr_text": self.ocr_text,
            "combined_text": self.combined_text,
            "ocr_line_count": self.ocr_line_count,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract information from PDF files using native text + OCR."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a PDF file or directory containing PDF files.",
    )
    parser.add_argument(
        "--output-dir",
        default="ocr_output",
        help="Output directory for extracted files (default: ocr_output).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="If input is a folder, scan recursively for PDFs.",
    )
    parser.add_argument(
        "--dpi-scale",
        type=float,
        default=2.0,
        help="Render scale for OCR image quality, e.g. 2.0/2.5/3.0.",
    )
    parser.add_argument(
        "--skip-native-text",
        action="store_true",
        help="Skip built-in PDF text extraction and use OCR only.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Limit processed pages per PDF; 0 means all pages.",
    )
    return parser.parse_args()


def list_pdf_files(input_path: Path, recursive: bool) -> List[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file is not a PDF: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise ValueError(f"Input path does not exist: {input_path}")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    files = sorted(p for p in input_path.glob(pattern) if p.is_file())
    return files


def safe_filename(name: str) -> str:
    # Windows-safe + generic filename sanitization
    return re.sub(r'[\\/:*?"<>|]+', "_", name)


def read_native_text(page: fitz.Page) -> str:
    try:
        return page.get_text("text") or ""
    except Exception:
        return ""


def read_ocr_text(page: fitz.Page, engine: RapidOCR, scale: float) -> Tuple[str, int]:
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        result, _ = engine(img)
        lines = [str(item[1]) for item in (result or []) if len(item) >= 2]
        return "\n".join(lines), len(lines)
    except Exception:
        return "", 0


def extract_pdf(
    pdf_path: Path,
    engine: RapidOCR,
    dpi_scale: float,
    skip_native_text: bool,
    max_pages: int,
) -> Dict[str, object]:
    started_at = datetime.now()
    doc = fitz.open(pdf_path)
    metadata = doc.metadata or {}
    total_pages = len(doc)
    pages_to_process = total_pages if max_pages <= 0 else min(total_pages, max_pages)

    extracted_pages: List[PageExtraction] = []
    for page_index in range(pages_to_process):
        page = doc[page_index]
        native_text = "" if skip_native_text else read_native_text(page)
        ocr_text, ocr_line_count = read_ocr_text(page, engine, dpi_scale)
        combined = native_text.strip()
        if ocr_text.strip():
            combined = (combined + "\n" + ocr_text.strip()).strip() if combined else ocr_text.strip()

        extracted_pages.append(
            PageExtraction(
                page_index=page_index + 1,
                native_text=native_text.strip(),
                ocr_text=ocr_text.strip(),
                combined_text=combined,
                ocr_line_count=ocr_line_count,
            )
        )

    doc.close()
    ended_at = datetime.now()

    return {
        "file_path": str(pdf_path),
        "file_name": pdf_path.name,
        "file_stem": pdf_path.stem,
        "file_size_bytes": pdf_path.stat().st_size,
        "metadata": metadata,
        "total_pages": total_pages,
        "processed_pages": pages_to_process,
        "started_at": started_at.isoformat(timespec="seconds"),
        "ended_at": ended_at.isoformat(timespec="seconds"),
        "duration_seconds": round((ended_at - started_at).total_seconds(), 3),
        "pages": [p.to_dict() for p in extracted_pages],
    }


def save_outputs(result: Dict[str, object], output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_filename(str(result["file_stem"]))
    json_path = output_dir / f"{stem}_ocr.json"
    txt_path = output_dir / f"{stem}_ocr.txt"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    lines: List[str] = []
    lines.append(f"FILE: {result['file_path']}")
    lines.append(f"PAGES: {result['processed_pages']}/{result['total_pages']}")
    lines.append(f"SIZE_BYTES: {result['file_size_bytes']}")
    lines.append(f"START: {result['started_at']}")
    lines.append(f"END: {result['ended_at']}")
    lines.append(f"DURATION_SECONDS: {result['duration_seconds']}")
    lines.append("")

    for page in result["pages"]:
        lines.append(f"===== PAGE {page['page_index']} =====")
        lines.append(page.get("combined_text", ""))
        lines.append("")

    with txt_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return json_path, txt_path


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_root = Path(args.output_dir)

    try:
        pdf_files = list_pdf_files(input_path, args.recursive)
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1

    if not pdf_files:
        print("[ERROR] No PDF files found.")
        return 1

    print(f"[INFO] Found {len(pdf_files)} PDF file(s). Initializing OCR engine...")
    engine = RapidOCR()
    success_count = 0
    failed_count = 0

    for idx, pdf in enumerate(pdf_files, start=1):
        print(f"[INFO] ({idx}/{len(pdf_files)}) Processing: {pdf}")
        try:
            result = extract_pdf(
                pdf_path=pdf,
                engine=engine,
                dpi_scale=args.dpi_scale,
                skip_native_text=args.skip_native_text,
                max_pages=args.max_pages,
            )

            if input_path.is_dir():
                rel = pdf.parent.relative_to(input_path)
                out_dir = output_root / rel
            else:
                out_dir = output_root

            json_path, txt_path = save_outputs(result, out_dir)
            print(f"[OK] JSON: {json_path}")
            print(f"[OK] TXT : {txt_path}")
            success_count += 1
        except Exception as e:
            print(f"[FAIL] {pdf}: {e}")
            failed_count += 1

    print(
        f"[DONE] Success={success_count}, Failed={failed_count}, Total={len(pdf_files)}"
    )
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
