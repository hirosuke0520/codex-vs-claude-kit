"""判定用の意地悪セット（どちらにも見せていない・架空）。期待値は expected.csv"""
import sys, io, csv
from pathlib import Path
import fitz
from PIL import Image, ImageDraw, ImageFont, ImageFilter
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
F="/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"; FB="/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
def img(lines, rot=0, blur=False):
    lh=46; im=Image.new("RGB",(680,60+lh*len(lines)),"white"); d=ImageDraw.Draw(im)
    for i,t in enumerate(lines): d.text((40,30+i*lh),t,fill="black",font=ImageFont.truetype(FB if i==0 else F,34 if i==0 else 28))
    if rot: im=im.rotate(rot,expand=True,fillcolor="white")
    if blur: im=im.filter(ImageFilter.GaussianBlur(0.7))
    return im
def pdf(p, lines):
    doc=fitz.open(); pg=doc.new_page(width=320,height=80+22*len(lines))
    for i,t in enumerate(lines): pg.insert_text((20,40+i*22),t,fontsize=14 if i==0 else 11,fontname="japan")
    doc.save(p)
def scan(p, lines, rot=0):
    b=io.BytesIO(); img(lines,rot).save(b,format="PNG"); doc=fitz.open(); pg=doc.new_page(width=420,height=595)
    pg.insert_image(fitz.Rect(20,20,400,560),stream=b.getvalue(),keep_proportion=True); doc.save(p)
E=[]
def add(name,d,a,s): E.append([name,d,a,s])
pdf(OUT/"x01_hotel.pdf",["HOTEL PASTEL 架空","TEL 00-0000-0002","2026年10月2日","宿泊料 ¥7,700","合計 ¥7,700"]); add("x01_hotel.pdf","2026-10-02","7700","HOTEL PASTEL 架空")
pdf(OUT/"x02_zenkaku.pdf",["そば処 たけ","２０２６年１０月３日","もりそば ￥１，１００","合計 ￥２，２００"]); add("x02_zenkaku.pdf","2026-10-03","2200","そば処 たけ")
img(["カレーの店 ハル","2026/09/22 12:31","カレー ¥1,050","合計 ¥1,050","お預り ¥10,000","お釣り ¥8,950"]).save(OUT/"x03_UPPER.PNG"); add("x03_UPPER.PNG","2026-09-22","1050","カレーの店 ハル")
pdf(OUT/"x04_gannen.pdf",["古書 しおり堂","令和元年5月1日","古書 ¥3,000","合計 ¥3,000"]); add("x04_gannen.pdf","2019-05-01","3000","古書 しおり堂")
pdf(OUT/"x05_spaces.pdf",["青空ベーカリー","2026-09-05","合計　　 12,345 円"]); add("x05_spaces.pdf","2026-09-05","12345","青空ベーカリー")
pdf(OUT/"x06_timefirst.pdf",["コインランドリー架空","10:42 2026/09/01","洗濯 ¥500","合計 ¥500"]); add("x06_timefirst.pdf","2026-09-01","500","コインランドリー架空")
pdf(OUT/"x07_multidate.pdf",["セミナー架空協会","領収書","発行日 2026年9月20日","受講料 ¥22,000","合計 ¥22,000","有効期限 2026年12月31日"]); add("x07_multidate.pdf","2026-09-20","22000","セミナー架空協会")
pdf(OUT/"x08_oshiharai.pdf",["花屋 ミモザ","2026/09/18","小計 ¥4,000","消費税 ¥400","お支払金額 ¥4,400"]); add("x08_oshiharai.pdf","2026-09-18","4400","花屋 ミモザ")
scan(OUT/"x09_scan_tilt.pdf",["ガソリン架空スタンド","2026年9月12日","レギュラー 30L ¥5,190","合計 ¥5,190"],rot=3); add("x09_scan_tilt.pdf","2026-09-12","5190","ガソリン架空スタンド")
img(["喫茶 こもれび","2026年8月8日","アイスコーヒー ¥600","合計 ¥600"],rot=-4,blur=True).save(OUT/"x10_tilt_blur.jpeg"); add("x10_tilt_blur.jpeg","2026-08-08","600","喫茶 こもれび")
pdf(OUT/"x11_total_before_tax.pdf",["架空マート","2026.10.11","合計 ¥1,650","(10%対象 ¥1,500 消費税 ¥150)","クレジット ¥1,650"]); add("x11_total_before_tax.pdf","2026-10-11","1650","架空マート")
pdf(OUT/"x12_reiwa_short.pdf",["整体院 ゆるり","R8.9.27","施術料 ¥6,000","合計 ¥6,000"]); add("x12_reiwa_short.pdf","2026-09-27","6000","整体院 ゆるり")
with open(OUT.parent/"expected.csv","w",newline="",encoding="utf-8") as f: csv.writer(f).writerows([["file","date","amount","store"]]+E)
print(len(E))
