#!/usr/bin/env python3

import json
import os
import re
import sys
from typing import Dict, List

import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance, ImageFilter

SUPPORTED_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
SUPPORTED_PDF_TYPES = {".pdf"}


def _configured_poppler_path() -> str | None:
    poppler_path = os.environ.get("POPPLER_PATH", "").strip()
    return poppler_path or None


def _configure_tesseract() -> None:
    tesseract_cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def _normalize_number(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9\.-]", "", value)


def _images_from_file(file_path: str) -> List[Image.Image]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext in SUPPORTED_PDF_TYPES:
        poppler_path = _configured_poppler_path()
        pages = convert_from_path(file_path, dpi=220, poppler_path=poppler_path)
        return pages

    if ext in SUPPORTED_IMAGE_TYPES:
        return [Image.open(file_path)]

    raise ValueError(f"Unsupported file type: {ext}")


def _ocr_image(image: Image.Image) -> str:
    gray = image.convert("L").filter(ImageFilter.SHARPEN)
    enhanced = ImageEnhance.Contrast(gray).enhance(1.8)
    return pytesseract.image_to_string(enhanced, config="--oem 3 --psm 6")


def _extract_field(patterns: List[str], text: str) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def extract_invoice_data(file_path: str) -> Dict[str, str]:
    # 1. Detect if PDF or image
    # 2. If PDF -> convert to images (poppler)
    # 3. Run OCR (tesseract)
    # 4. Extract fields using regex
    # 5. Return structured data
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    _configure_tesseract()

    pages = _images_from_file(file_path)
    text_parts = [_ocr_image(page) for page in pages]
    text = "\n".join(text_parts)

    invoice_number = _extract_field(
        [
            r"Invoice\s*(?:Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]*)",
            r"Inv\.?\s*(?:No\.?|Number)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]*)",
        ],
        text,
    )

    invoice_date = _extract_field(
        [
            r"(?:Invoice\s*)?Date\s*[:\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
            r"(?:Invoice\s*)?Date\s*[:\-]?\s*([0-9]{4}[/-][0-9]{1,2}[/-][0-9]{1,2})",
        ],
        text,
    )

    tpin = _extract_field([r"(?:Customer|Supplier)?\s*TPIN\s*[:\-]?\s*([0-9]{5,15})"], text)
    customer_name = _extract_field(
        [
            r"Customer\s*Name\s*[:\-]?\s*(.+?)\s*(?=Address|TPIN|Invoice|$)",
            r"Name\s*of\s*(?:Purchaser|Supplier)\s*[:\-]?\s*(.+?)\s*(?=Address|TPIN|Invoice|$)",
            r"Bill\s*To\s*[:\-]?\s*(.+?)\s*(?=Address|TPIN|Invoice|$)",
        ],
        text,
    )

    amount_before_tax = _extract_field(
        [
            r"(?:Sub[\s\-]?Total|Amount\s*Before\s*(?:VAT|Tax)|Amount\s*Excl(?:uding)?\s*VAT)\s*[:\-]?\s*([0-9,]+(?:\.[0-9]{2,}))",
        ],
        text,
    )
    local_excise_duty = _extract_field(
        [r"Local\s*Excise\s*Duty\s*[:\-]?\s*([0-9,]+(?:\.[0-9]{2,}))"], text
    )
    total = _extract_field(
        [r"(?:Total\s*Amount|Total)\s*[:\-]?\s*([0-9,]+(?:\.[0-9]{2,}))"],
        text,
    )
    vat = _extract_field(
        [r"VAT\s*(?:@\s*\d+%?)?\s*[:\-]?\s*([0-9,]+(?:\.[0-9]{2,}))"],
        text,
    )

    description = _extract_field(
        [r"Item\s*Description\s*[:\-]?\s*(.+?)\s*(?=Total|VAT|Excise|Tax|$)"],
        text,
    )

    return {
        "filePath": file_path,
        "invoiceNumber": invoice_number,
        "invoiceDate": invoice_date,
        "tpin": re.sub(r"\D", "", tpin),
        "name": re.sub(r"\s+", " ", customer_name).strip().upper(),
        "descriptionOfGoodsServices": re.sub(r"\s+", " ", description).strip(),
        "amountBeforeTax": _normalize_number(amount_before_tax),
        "localExciseDuty": _normalize_number(local_excise_duty),
        "total": _normalize_number(total),
        "vat": _normalize_number(vat),
        "rawText": text,
    }


def _main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python main.py <invoice.pdf|image>")
        return 1

    file_path = sys.argv[1]
    data = extract_invoice_data(file_path)
    print(json.dumps(data, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
