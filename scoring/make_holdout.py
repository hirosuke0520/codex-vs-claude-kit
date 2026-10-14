"""渡さない追加サンプル（過学習チェック用・架空）。make_receipts の描画を流用。"""
import sys, importlib.util
from pathlib import Path
import fitz
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("mk", Path(__file__).with_name("make_receipts.py"))
# make_receipts はモジュール実行で出力するので描画関数だけ写す
from PIL import Image, ImageDraw, ImageFont
FONT="/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"; FONT_B="/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
def img(lines):
    lh=46; im=Image.new("RGB",(640,60+lh*len(lines)),"white"); d=ImageDraw.Draw(im)
    for i,t in enumerate(lines): d.text((40,30+i*lh),t,fill="black",font=ImageFont.truetype(FONT_B if i==0 else FONT,34 if i==0 else 28))
    return im
def pdf(p, lines):
    doc=fitz.open(); pg=doc.new_page(width=300,height=80+22*len(lines))
    for i,t in enumerate(lines): pg.insert_text((20,40+i*22),t,fontsize=14 if i==0 else 11,fontname="japan")
    doc.save(p)
pdf(OUT/"h1_bakery.pdf", ["パン工房 こむぎ","2026.09.30 15:02","クロワッサン ¥320","あんぱん ¥320","小計 ¥640","合 計 ¥640","お預り ¥1,000","お釣り ¥360"])
img(["ホテル架空ステイ","宿泊日 2026年10月10日","宿泊料 ¥8,800","宿泊税 ¥200","お支払合計 ¥9,000"]).save(OUT/"h2_hotel.png")
pdf(OUT/"h3_drug.pdf", ["ドラッグ ナナイロ","令和8年9月9日","目薬 ¥980","税込合計 ¥1,078","電子マネー ¥1,078"])
print("ok")
