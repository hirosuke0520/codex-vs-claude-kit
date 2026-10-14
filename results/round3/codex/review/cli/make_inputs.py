from pathlib import Path
import fitz
root = Path(__file__).resolve().parent / 'malformed_number'
root.mkdir(parents=True, exist_ok=True)
with fitz.open() as doc:
    page = doc.new_page(width=1100, height=220)
    for y, text in ((35, 'テスト商店'), (65, '2026/10/01'), (95, '合計 100円')):
        page.insert_text((20, y), text, fontname='japan', fontsize=12)
    page.insert_text((20, 130), '伝票番号 ' + '9' * 4301, fontname='japan', fontsize=0.2)
    doc.save(root / 'receipt.pdf')
