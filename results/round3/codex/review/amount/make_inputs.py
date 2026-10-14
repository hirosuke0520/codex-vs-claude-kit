"""最小のテキスト PDF を作る。外部アクセス・追加パッケージ不要。"""
from pathlib import Path
import fitz

BASE = Path(__file__).resolve().parent
CASES = {
    "zero_total": ["小計 1,000円", "クーポン -1,000円", "お支払金額 0円"],
    "zero_only": ["お支払金額 0円"],
    "tendered_only": ["お預り 5,000円"],
    "subtotal_only": ["小計 1,000円"],
    "mixed_strength": ["合計 1280 (内消費税 116円)"],
    "split_payment": ["お支払金額 現金 1,000円", "お支払金額 クレジット 2,000円"],
    "two_tax_rates": ["小計 2,000円", "消費税(8%) 80円", "消費税(10%) 100円"],
    "high_amount": ["お支払金額 100,000,000円"],
    "remaining_balance": ["お支払合計 3,000円", "未払金額 2,000円"],
    "postfix_total": ["1,280円 合計", "2,000円 お預り", "720円 お釣り"],
    "cash_paid_before_change": ["お支払金額 現金 1,280円", "お預り 2,000円", "お釣り 720円"],
    "coupon_inline": ["合計 1,000円 クーポン適用後 800円"],
    "coupon_paid_label": ["合計 1,000円", "クーポン -200円", "クーポン適用後のお支払金額 800円"],
    "cash_paid_after_points": ["合計 1,000円", "ポイント利用 -200円", "現金お支払金額 800円"],
}

for name, amount_lines in CASES.items():
    folder = BASE / name
    folder.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    lines = ["テスト商店", "2026/10/01", *amount_lines]
    page = doc.new_page(width=500, height=80 + len(lines) * 28)
    for i, line in enumerate(lines):
        page.insert_text((20, 40 + i * 28), line, fontname="japan", fontsize=12)
    doc.save(folder / "receipt.pdf")
    doc.close()
