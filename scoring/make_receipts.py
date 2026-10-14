"""架空の領収書サンプルを生成する（実在の店舗・個人情報は使わない）。"""
import sys, io
from pathlib import Path
import fitz
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
FONT_B = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"

R = {
 "01_cafe.pdf": ["カフェ ミドリ堂", "東京都架空区みどり1-2-3", "TEL 00-0000-0001", "2026年9月3日 10:42", "ブレンドコーヒー  ¥550", "チーズケーキ  ¥730", "小計  ¥1,280", "(内消費税 ¥116)", "合計  ¥1,280", "お預り  ¥2,000", "お釣り  ¥720"],
 "02_stationery.pdf": ["文具のサクラ屋", "登録番号 T0000000000001", "2026/09/14", "ノート x3  ¥990", "ボールペン x2  ¥440", "小計 ¥1,430", "消費税 ¥143", "合計 ¥1,573", "クレジット ¥1,573"],
 "03_books.pdf": ["まるいち書店", "領収書", "発行日 2026-10-01", "書籍代として", "ご請求額 ￥12,100（税込）", "上記正に領収いたしました"],
 "04_taxi.png": ["ヒカリ交通", "乗車日 令和8年8月20日", "迎車料金 ¥300", "運賃 ¥2,860", "合計金額 3,160円", "ご利用ありがとうございました"],
 "05_parking.png": ["Tokyo Byte Parking", "入庫 2026/10/05 09:10", "出庫 2026/10/05 13:40", "駐車料金 ¥1,200", "合計 ¥1,200"],
 "06_lunch.jpg": ["定食処 あおば", "2026年10月7日(水)", "日替わり定食 1点 ¥980", "小計 ¥980", "合計 ¥980", "現金 ¥1,000", "お釣り ¥20"],
 "07_scanned.pdf": ["ハナミズキ電器", "2026年7月31日", "USBケーブル ¥1,980", "電源アダプタ ¥3,480", "小計 ¥5,460", "合計 ¥5,460"],
}

def render_img(lines, w=640, rotate=0.0, blur=False):
    lh = 46; h = 60 + lh * len(lines)
    img = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 28); fb = ImageFont.truetype(FONT_B, 34)
    for i, t in enumerate(lines):
        d.text((40, 30 + i * lh), t, fill="black", font=fb if i == 0 else f)
    if rotate: img = img.rotate(rotate, expand=True, fillcolor="white")
    if blur: img = img.filter(ImageFilter.GaussianBlur(0.6))
    return img

for name, lines in R.items():
    p = OUT / name
    if name.endswith(".png"):
        render_img(lines).save(p)
    elif name.endswith(".jpg"):
        render_img(lines, rotate=1.5, blur=True).save(p, quality=70)
    elif name == "07_scanned.pdf":  # 画像だけのPDF（スキャン想定・テキスト層なし）
        buf = io.BytesIO(); render_img(lines).save(buf, format="PNG")
        doc = fitz.open(); pg = doc.new_page(width=420, height=595)
        pg.insert_image(fitz.Rect(20, 20, 400, 20 + 380 * (60 + 46*len(lines)) / 640), stream=buf.getvalue()); doc.save(p)
    else:
        doc = fitz.open(); pg = doc.new_page(width=300, height=40 + 22 * len(lines) + 40)
        for i, t in enumerate(lines):
            pg.insert_text((20, 40 + i * 22), t, fontsize=14 if i == 0 else 11, fontname="japan", )
        doc.save(p)

(OUT / "memo.txt").write_text("これは領収書ではないメモ。合計 ¥99,999 2026/01/01\n", encoding="utf-8")
print("ok", sorted(x.name for x in OUT.iterdir()))
