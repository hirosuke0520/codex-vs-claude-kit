"""再現用の入力ファイルを review/cases/<ケース名>/ に作る。

使い方: python3 -B review/make_cases.py
PDF は PyMuPDF（サンプルと同じ内蔵 japan フォント）、画像は Pillow＋ヒラギノで描く。
どちらも依頼条件で使ってよいとされているライブラリだけを使う。
"""
from pathlib import Path
import os
import shutil

import fitz
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"
FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"


def pdf(path, lines):
    """1行ずつ insert_text したテキストPDF（サンプル 01〜03 と同じ作り）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as document:
        page = document.new_page(width=300, height=40 + 16 * len(lines))
        for index, line in enumerate(lines):
            page.insert_text((20, 30 + 16 * index), line, fontname="japan", fontsize=11)
        document.save(path)


def receipt_image(rows, *, width=650, pitch=50, top=40, size=30, price_x=430):
    """左にラベル・右に金額を置いた白地のレシート画像（サンプル 06 と同じ作り）。"""
    font = ImageFont.truetype(FONT, size)
    image = Image.new("RGB", (width, top * 2 + pitch * len(rows)), "white")
    draw = ImageDraw.Draw(image)
    for index, row in enumerate(rows):
        label, price = row if isinstance(row, tuple) else (row, None)
        y = top + pitch * index
        draw.text((40, y), label, font=font, fill="black")
        if price:
            draw.text((price_x, y), price, font=font, fill="black")
    return image


def on_desk(receipt):
    """レシートが高さの45%を占めるよう、余白（机）ごと縦長に撮った写真を模す。"""
    photo = Image.new("RGB", (receipt.width * 2, round(receipt.height / 0.45)), (235, 235, 235))
    photo.paste(receipt, ((photo.width - receipt.width) // 2, (photo.height - receipt.height) // 2))
    return photo


def reset(name):
    directory = CASES / name
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    return directory


def main():
    CASES.mkdir(exist_ok=True)

    # --- 金額: 「合計」を含む別項目の行が先にあると、その行の金額が出る
    d = reset("amount_compound_total")
    pdf(d / "a_discount.pdf", ["スーパーみどり", "2026/10/10", "食品 ¥1,500", "小計 ¥1,500",
                                "値引合計 -¥200", "合計 ¥1,300", "お預り ¥2,000", "お釣り ¥700"])
    pdf(d / "b_tax_rate.pdf", ["スーパーみどり", "2026/10/10", "8%対象合計 ¥540",
                                "10%対象合計 ¥1,100", "合計 ¥1,640"])
    pdf(d / "c_item_count.pdf", ["スーパーみどり", "2026/10/10", "合計点数 3点", "合計 ¥1,280"])

    # --- 金額: 英語レシートの小計・税額行が合計として採用される
    d = reset("amount_english_subtotal")
    pdf(d / "a_sub_total.pdf", ["Blue Bottle Cafe", "2026/10/10", "SUB TOTAL ¥300", "TAX ¥30", "TOTAL ¥330"])
    pdf(d / "b_sub-total.pdf", ["Blue Bottle Cafe", "2026/10/10", "Sub-Total ¥300", "Tax ¥30", "Total ¥330"])
    pdf(d / "c_total_tax.pdf", ["Blue Bottle Cafe", "2026/10/10", "SUBTOTAL ¥1,000", "TOTAL TAX ¥100",
                                "TOTAL ¥1,100"])

    # --- 金額: 通貨記号が無い（円記号が \ で入っている等）と行内の最初の数字（点数）が出る
    d = reset("amount_unmarked_first_number")
    pdf(d / "a_backslash_yen.pdf", ["スーパーみどり", "2026/10/10", "小計 3点 \\1,280", "合計 3点 \\1,280"])
    pdf(d / "b_items.pdf", ["Blue Bottle Cafe", "2026/10/10", "TOTAL (2 items) 1,500"])
    pdf(d / "c_count_then_next_line.pdf", ["スーパーみどり", "2026/10/10", "合計 3点", "¥1,280"])

    # --- 金額: ¥の後ろの空白＋数字、数字＋空白＋「円」が連結される
    d = reset("amount_space_concat")
    pdf(d / "a_persons.pdf", ["居酒屋 はなび", "2026/10/10", "合計 ¥3,300 2名様"])
    pdf(d / "b_count_before_yen.pdf", ["居酒屋 はなび", "2026/10/10", "合計 2 1,280円"])

    # --- 店名: 宛名（〜様・〜御中）が店名として出る／正式な領収書は金額も空
    d = reset("store_addressee")
    pdf(d / "a_formal_sama.pdf", ["領収書", "山田 太郎 様", "¥12,100-", "但し 書籍代として",
                                   "2026年10月1日", "上記正に領収いたしました", "まるいち書店",
                                   "東京都架空区1-2-3"])
    pdf(d / "b_onchu.pdf", ["領収書", "株式会社テスト 御中", "2026/10/01", "合計 ¥1,100",
                             "まるいち書店"])

    # --- 店名: 店名より前にある「No.」「お客様控え」などが店名として出る
    d = reset("store_first_line")
    pdf(d / "a_number.pdf", ["No. 000123", "まるいち書店", "2026/10/01", "合計 ¥1,100"])
    pdf(d / "b_copy.pdf", ["お客様控え", "まるいち書店", "2026/10/01", "合計 ¥1,100"])
    pdf(d / "c_100yen_shop.pdf", ["100円ショップ ダイソー", "2026/10/01", "コップ 110", "合計 ¥110"])
    # 店名がロゴ画像で、テキストは住所から始まる電子レシートPDF
    pdf(d / "d_address_first.pdf", ["東京都架空区みどり1-2-3", "TEL 03-0000-0001", "2026/10/01", "合計 ¥1,100"])

    # --- 日付: 日付が複数あると先頭（入庫日・乗車日など）が出る
    d = reset("date_first_wins")
    pdf(d / "a_parking.pdf", ["Tokyo Byte Parking", "入庫 2026/10/04 22:10", "出庫 2026/10/05 08:30",
                               "駐車料金 ¥2,400", "合計 ¥2,400"])
    pdf(d / "b_hotel.pdf", ["ホテル みなと", "チェックイン 2026/10/04", "チェックアウト 2026/10/05",
                             "宿泊料金 ¥9,800", "合計 ¥9,800"])

    # --- 日付: 令和の略記・併記は空になる
    d = reset("date_reiwa_variants")
    pdf(d / "a_r_abbrev.pdf", ["ヒカリ交通", "R8.10.07", "合計 ¥1,200"])
    pdf(d / "b_reiwa_with_seireki.pdf", ["ヒカリ交通", "令和8年(2026年)10月7日", "合計 ¥1,200"])
    pdf(d / "c_seireki_with_reiwa.pdf", ["ヒカリ交通", "2026年(令和8年)10月7日", "合計 ¥1,200"])

    # --- 金額: ラベルの語彙が狭く空になる（お会計・総計・ご利用金額・金額）
    d = reset("amount_label_vocabulary")
    pdf(d / "a_okaikei.pdf", ["居酒屋 はなび", "2026/10/10", "お会計 ¥3,300"])
    pdf(d / "b_soukei.pdf", ["居酒屋 はなび", "2026/10/10", "総計 ¥3,300"])
    pdf(d / "c_goriyou.pdf", ["ヒカリ交通", "2026/10/10", "ご利用金額 ¥3,300"])
    pdf(d / "d_kingaku.pdf", ["領収書", "金額 ¥3,300-", "2026/10/10", "上記正に領収いたしました", "居酒屋 はなび"])

    # --- OCR: 行間が画像の高さの 1.2% 未満だと隣の行と1行に結合される。
    # 37行のレシートを、余白のある写真（机に置いて縦長に撮影）として置いたものと、ぴったり切り抜いたものを比べる。
    d = reset("ocr_row_merge")
    rows = ["スーパーみどり 中央店", "東京都架空区1-2-3", "2026年10月10日 18:32"]
    total = 0
    for i in range(1, 31):
        price = 100 + (i * 37) % 400
        total += price
        rows.append((f"商品{i:02d}", f"¥{price:,}"))
    rows += [("小計", f"¥{total:,}"), ("合計", f"¥{total:,}"), ("お預り", "¥20,000"),
             ("お釣り", f"¥{20000 - total:,}")]
    receipt = receipt_image(rows, pitch=40, size=26)
    photo = on_desk(receipt)
    photo.save(d / "a_on_desk.png")
    receipt.save(d / "b_cropped.png")
    print(f"ocr_row_merge: 合計 = {total}, 行数 = {len(rows)}, 写真 {photo.size}, 切り抜き {receipt.size}")
    # 同じ条件で品目数だけ変えたもの（偶然の1枚ではないことの確認用）
    d = reset("ocr_row_merge_more")
    for count in (27, 28, 29, 31, 32):
        rows = ["スーパーみどり 中央店", "東京都架空区1-2-3", "2026年10月10日 18:32"]
        total = 0
        for i in range(1, count + 1):
            price = 100 + (i * 37) % 400
            total += price
            rows.append((f"商品{i:02d}", f"¥{price:,}"))
        rows += [("小計", f"¥{total:,}"), ("合計", f"¥{total:,}"), ("お預り", "¥20,000"),
                 ("お釣り", f"¥{20000 - total:,}")]
        on_desk(receipt_image(rows, pitch=40, size=26)).save(d / f"items{count}_total{total}.png")

    # --- OCR: わずかに傾いた写真で、合計ラベルの次の行に別の行の金額が来る
    d = reset("ocr_tilt")
    lunch = ["定食処 あおば", "2026年10月7日(水)", ("日替わり定食1点", "¥980"), ("小計", "¥980"),
             ("合計", "¥980"), ("現金", "¥1,000"), ("お釣り", "¥20")]
    upright = receipt_image(lunch)
    upright.save(d / "a_upright.png")
    for angle in (1, 1.5, 2, 3, -1, -2, -3):
        tilted = upright.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
        tilted.save(d / f"b_rotate_{angle:+.1f}.png")

    # --- 画像: 背景が透明なPNG（文字は黒）
    d = reset("image_transparent_png")
    rgba = upright.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, _ = pixels[x, y]
            darkness = 255 - (r + g + b) // 3
            pixels[x, y] = (0, 0, 0, darkness)  # 白地を透明に、文字は黒（アンチエイリアスは半透明）
    rgba.save(d / "a_transparent.png")
    flattened = Image.new("RGB", rgba.size, "white")
    flattened.paste(rgba, mask=rgba.getchannel("A"))
    flattened.save(d / "b_same_on_white.png")

    # --- 画像: 幅が極端に小さい画像（1.3KB）。上限なしで幅1600pxへ拡大される
    d = reset("image_narrow")
    Image.new("RGB", (16, 2000), "white").save(d / "narrow_16x2000.png")

    # --- 一覧に出ない: 壊れたシンボリックリンク
    d = reset("broken_symlink")
    pdf(d / "a_ok.pdf", ["まるいち書店", "2026/10/01", "合計 ¥1,100"])
    os.symlink("does_not_exist.pdf", d / "b_link_to_missing.pdf")

    # --- 2ページ目が白紙のテキストPDF（OCRが使えない環境で1ページ目の内容まで消える）
    d = reset("pdf_blank_second_page")
    pdf(d / "a_one_page.pdf", ["まるいち書店", "2026/10/01", "合計 ¥1,100"])
    with fitz.open() as document:
        page = document.new_page(width=300, height=120)
        for index, line in enumerate(["まるいち書店", "2026/10/01", "合計 ¥1,100"]):
            page.insert_text((20, 30 + 16 * index), line, fontname="japan", fontsize=11)
        document.new_page(width=300, height=120)  # 裏面などの白紙ページ
        document.save(d / "b_two_pages.pdf")

    # --- 以下は「問題なし」を確かめた対照ケース
    d = reset("ok_image_16bit_png")  # 16bit グレースケールPNG（スキャナ出力でありうる形式）
    gray = upright.convert("L")
    gray16 = Image.new("I;16", gray.size)
    gray16.putdata([v * 257 for v in gray.tobytes()])
    gray16.save(d / "a_gray16.png")

    d = reset("ok_encrypted_pdf")  # パスワード付きPDF → 警告を出して空行で継続できるか
    with fitz.open() as document:
        page = document.new_page(width=300, height=120)
        page.insert_text((20, 30), "まるいち書店\n2026/10/01\n合計 ¥1,100", fontname="japan", fontsize=11)
        document.save(d / "locked.pdf", encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")

    # --- 補足（不具合とは断定しないが仕様判断が要るもの）: 返品レシート、外付けドライブで macOS が作る ._ ファイル
    d = reset("note_refund_and_appledouble")
    pdf(d / "a_refund.pdf", ["スーパーみどり", "2026/10/10", "返品", "合計 -¥1,280"])
    (d / "._a_refund.pdf").write_bytes(b"\x00\x05\x16\x07AppleDouble")

    d = reset("ok_pdf_columns")  # ラベル列・金額列を別々に描いた表形式PDF → 行が正しく揃うか
    with fitz.open() as document:
        page = document.new_page(width=300, height=160)
        page.insert_text((30, 30), "まるいち書店\n2026/10/01", fontname="japan", fontsize=11)
        page.insert_text((30, 70), "小計\n消費税\n合計\nお預り", fontname="japan", fontsize=11)
        page.insert_text((200, 70), "¥1,164\n¥93\n¥1,257\n¥2,000", fontname="japan", fontsize=11)
        document.save(d / "columns.pdf")


if __name__ == "__main__":
    main()
