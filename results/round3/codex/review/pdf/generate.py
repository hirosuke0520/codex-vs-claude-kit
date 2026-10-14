"""PDF / OCR review fixtures; run from the workspace root with python3 -B."""
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent
for folder in ("control_text", "page_limit", "control_scan", "ocr_limit", "small_image", "small_image_control", "scanner_date"):
    (ROOT / folder).mkdir(exist_ok=True)


def receipt_page(doc):
    page = doc.new_page(width=400, height=220)
    for y, text in ((55, "Maple Cafe"), (105, "2026-10-01"), (155, "TOTAL JPY 1280")):
        page.insert_text((35, y), text, fontsize=24)
    return page


doc = fitz.open()
receipt_page(doc)
doc.save(ROOT / "control_text" / "receipt.pdf")
png = doc[0].get_pixmap(matrix=fitz.Matrix(4, 4)).tobytes("png")

long_doc = fitz.open()
for _ in range(20):
    long_doc.new_page(width=120, height=80)
receipt_page(long_doc)
long_doc.save(ROOT / "page_limit" / "receipt.pdf")

scan_doc = fitz.open()
page = scan_doc.new_page(width=400, height=220)
page.insert_image(page.rect, stream=png)
scan_doc.save(ROOT / "control_scan" / "receipt.pdf")

limited_scan = fitz.open()
for _ in range(5):
    limited_scan.new_page(width=120, height=80)
page = limited_scan.new_page(width=400, height=220)
page.insert_image(page.rect, stream=png)
limited_scan.save(ROOT / "ocr_limit" / "receipt.pdf")

for folder, watermark in (("small_image", True), ("small_image_control", False)):
    mixed = fitz.open()
    page = mixed.new_page(width=1000, height=1000)
    # 400 * 220 / (1000 * 1000) = 8.8% of the page; receipt is clearly legible.
    page.insert_image(fitz.Rect(100, 100, 500, 320), stream=png)
    if watermark:
        page.insert_text((50, 800), "Scanned", fontsize=12)
    mixed.save(ROOT / folder / "receipt.pdf")

annotated = fitz.open()
page = annotated.new_page(width=400, height=320)
page.insert_image(fitz.Rect(0, 0, 400, 220), stream=png)
page.insert_text((15, 260), "Scanned with local document management software", fontsize=10)
page.insert_text((15, 285), "Scan date: 2026-10-02", fontsize=10)
annotated.save(ROOT / "scanner_date" / "receipt.pdf")
