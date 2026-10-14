"""最小のテキストPDFを作成する。追加依存は対象CLIと同じPyMuPDFのみ。"""
from pathlib import Path
import fitz

base = Path(__file__).resolve().parent
cases = {
    '01_store_label.pdf': ['店名', 'カフェ ミドリ堂', '2026/10/01', '合計 ¥100'],
    '02_invalid_date.pdf': ['テスト店', '2026年10月112日', '合計 ¥100'],
    '03_expiry_only.pdf': ['テスト店', '有効期限 2026/10/31', '合計 ¥100'],
    '04_item_no_store.pdf': ['商品名: コーヒー', '2026/10/01', '合計 ¥100'],
    '05_old_date.pdf': ['テスト店', '1988/10/01', '合計 ¥100'],
    '06_invalid_era.pdf': ['テスト店', '令和0年10月1日', '合計 ¥100'],
}
for name, lines in cases.items():
    doc = fitz.open()
    page = doc.new_page(width=300, height=40 + 24 * len(lines))
    for index, line in enumerate(lines):
        page.insert_text((20, 25 + index * 24), line, fontname='japan', fontsize=11)
    doc.save(base / 'inputs' / name)
    doc.close()
