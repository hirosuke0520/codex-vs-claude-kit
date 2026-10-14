"""receipt2csv.py の追加テスト（受け入れテストとは別に、ルールと異常系を細かく確かめる）。

実行: python3 -m unittest discover -s tests -v
OCR を使うテストは macOS の Vision（swift）とヒラギノフォントがある環境でだけ動く。
"""
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import warnings
from pathlib import Path

with warnings.catch_warnings():  # PyMuPDF（SWIG）が Python 3.14 で import 時に出す DeprecationWarning を抑える
    warnings.simplefilter("ignore", DeprecationWarning)
    import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import receipt2csv as r  # noqa: E402

CLI = [sys.executable, str(ROOT / "receipt2csv.py")]
FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
HAS_OCR = sys.platform == "darwin" and shutil.which("swift") is not None and os.path.exists(FONT_BOLD)


def fields(*lines):
    return r.extract_fields([r.Row(r.norm_text(line), 11.0) for line in lines])


def run_cli(*args):
    return subprocess.run(CLI + [str(a) for a in args], capture_output=True, text=True, timeout=600)


def read_csv(text):
    return list(csv.reader(io.StringIO(text)))


def norm(s):
    return "".join(unicodedata.normalize("NFKC", s).split())


def make_pdf(path, lines, rotate=0, title_size=14, extra_pages=()):
    """PyMuPDF の内蔵日本語フォントでテキスト PDF を作る。("lr", 左, 右) は右寄せの金額。"""
    doc = fitz.open()
    page = doc.new_page(width=300, height=60 + 22 * len(lines))
    y = 40
    for i, line in enumerate(lines):
        if isinstance(line, tuple):
            _, left, right = line
            page.insert_text((20, y), left, fontname="japan", fontsize=11)
            w = fitz.get_text_length(right, fontname="japan", fontsize=11)
            page.insert_text((280 - w, y), right, fontname="japan", fontsize=11)
        else:
            page.insert_text((20, y), line, fontname="japan", fontsize=title_size if i == 0 else 11)
        y += 22
    if rotate:
        page.set_rotation(rotate)
    for extra in extra_pages:
        p = doc.new_page(width=300, height=200)
        for j, line in enumerate(extra):
            p.insert_text((20, 40 + 22 * j), line, fontname="japan", fontsize=11)
    doc.save(str(path))


def draw_receipt(lines, width=640, size=26):
    """1 行目を太字の店名にした領収書画像を作る。("lr", 左, 右) は右寄せの金額。"""
    from PIL import Image, ImageDraw, ImageFont
    body, title = ImageFont.truetype(FONT, size), ImageFont.truetype(FONT_BOLD, int(size * 1.25))
    im = Image.new("RGB", (width, 80 + int(size * 1.7) * len(lines)), "white")
    d = ImageDraw.Draw(im)
    y = 40
    for i, line in enumerate(lines):
        font = title if i == 0 else body
        if isinstance(line, tuple):
            _, left, right = line
            d.text((40, y), left, font=font, fill="black")
            d.text((width - 40 - d.textlength(right, font=font), y), right, font=font, fill="black")
        else:
            d.text((40, y), line, font=font, fill="black")
        y += int(size * 1.7)
    return im


class DateTest(unittest.TestCase):
    def test_formats(self):
        cases = {
            "2026年9月3日 10:42": "2026-09-03",
            "2026/09/14": "2026-09-14",
            "発行日 2026-10-01": "2026-10-01",
            "2026.10.05": "2026-10-05",
            "２０２６年１０月７日（水）": "2026-10-07",
            "乗車日 令和8年8月20日": "2026-08-20",
            "乗車日 和8年8月20日": "2026-08-20",  # OCR で「令」が欠けた形
            "令和元年5月1日": "2019-05-01",
            "平成31年4月30日": "2019-04-30",
            "R8.9.12 18:03": "2026-09-12",
            "R08/10/05": "2026-10-05",
            "2026年(令和8年)10月1日": "2026-10-01",
            "令 和 8 年 1 0 月 1 日": "2026-10-01",
            "ご利用日 26/09/09": "2026-09-09",
            "Date: Oct 3, 2026": "2026-10-03",
            "2026 年 9 月 3 日": "2026-09-03",
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(fields(line)["date"], expected)

    def test_stay_period_start_and_scanner_stamp_are_not_issue_dates(self):
        self.assertEqual(fields("ご宿泊 2026年10月10日~10月11日 (1泊)", "ご請求額 ¥41,880", "2026年10月11日",
                                "旅館 みさき荘")["date"], "2026-10-11")
        self.assertEqual(fields("クリーニング しろくま", "受付日 2026年10月1日", "合計 ¥1,980",
                                "Scanned 2026/10/12 18:03 FakeScan Pro")["date"], "2026-10-01")

    def test_label_decides_between_dates(self):
        self.assertEqual(fields("入庫 2026/10/04 22:10", "出庫 2026/10/05 08:40")["date"], "2026-10-05")
        self.assertEqual(fields("有効期限 2027/10/31", "発行日 2026/10/01")["date"], "2026-10-01")
        self.assertEqual(fields("チェックイン 2026/09/01", "チェックアウト 2026/09/03")["date"], "2026-09-03")

    def test_not_dates(self):
        for line in ("TEL 00-0000-0001", "登録番号 T0000000000001", "13:40", "2026/13/45", "Summary 12 2026"):
            with self.subTest(line=line):
                self.assertEqual(fields(line)["date"], "")


class AmountTest(unittest.TestCase):
    def check(self, lines, expected):
        self.assertEqual(fields(*lines)["amount"], expected, lines)

    def test_total_not_subtotal_tendered_change_tax(self):
        self.check(["小計 ¥1,280", "(内消費税 ¥116)", "合計 ¥1,280", "お預り ¥2,000", "お釣り ¥720"], "1280")
        self.check(["小計 ¥1,430", "消費税 ¥143", "合計 ¥1,573", "クレジット ¥1,573"], "1573")
        self.check(["お預り ¥10,000", "合計 ¥6,820-", "お釣り ¥3,180"], "6820")

    def test_keywords_and_formats(self):
        self.check(["ご請求額 ￥12,100（税込）"], "12100")
        self.check(["迎車料金 ¥300", "運賃 ¥2,860", "合計金額 3,160円"], "3160")
        self.check(["合　計 ¥260", "お　釣 ¥9,740"], "260")
        self.check(["合計 \\1,280", "お預り \\2,000"], "1280")
        self.check(["TOTAL JPY 1,280"], "1280")
        self.check(["Subtotal ¥2,400", "Tax ¥240", "Total ¥2,640", "Cash ¥3,000", "Change ¥360"], "2640")
        self.check(["Amount paid ¥2,640"], "2640")
        self.check(["Taxi fare ¥3,160", "Tolls ¥700", "Total ¥3,860"], "3860")  # Taxi の tax を税と読まない
        self.check(["合計-----¥1,280", "お預り-----¥2,000"], "1280")
        self.check(["合計 Y1,280", "お預り Y2,000"], "1280")  # OCR が ¥ を Y と読んだ形

    def test_purchase_total_before_coupon_is_not_paid_amount(self):
        self.check(["お買上計 ¥1,460", "クーポン値引 -¥100", "合計 ¥1,360", "(内消費税等 ¥100)", "お預り ¥2,000",
                    "お釣り ¥640"], "1360")

    def test_paid_amount_after_discount(self):
        self.check(["合計 ¥2,160", "ポイント利用 -¥160", "お支払金額 ¥2,000"], "2000")
        self.check(["合計 ¥2,000", "クーポン -¥500", "お支払い合計 ¥1,500"], "1500")

    def test_label_and_amount_on_separate_lines(self):
        self.check(["目薬 ¥880", "合計", "¥880", "ご来店ありがとうございました"], "880")
        self.check(["お支払方法 クレジットカード", "¥1,573"], "1573")

    def test_counts_are_not_amounts(self):
        self.check(["日替わり定食 1点 ¥980", "合計 ¥980", "現金 ¥1,000", "お釣り ¥20"], "980")
        self.check(["お買上点数 3点 合計 ¥1,280"], "1280")
        self.check(["合計(10点) ¥1,280"], "1280")
        self.check(["10%対象 合計 ¥1,000", "合計 ¥1,280"], "1280")

    def test_fallbacks_without_total_line(self):
        self.check(["小計 ¥980", "現金 ¥1,000", "お釣り ¥20"], "980")    # お預り - お釣り
        self.check(["小計 ¥1,430", "消費税等(10%) ¥143"], "1573")        # 小計 + 外税
        self.check(["料金 ¥4,280"], "4280")
        self.check(["領収書", "山田 太郎 様", "¥15,400-", "上記正に領収いたしました"], "15400")
        self.check(["メモ", "日付だけ 2026/01/01"], "")


class StoreTest(unittest.TestCase):
    def check(self, lines, expected):
        self.assertEqual(norm(fields(*lines)["store"]), norm(expected), lines)

    def test_first_line_store(self):
        self.check(["カフェ ミドリ堂", "東京都架空区みどり1-2-3", "TEL 00-0000-0001", "合計 ¥1,280"], "カフェ ミドリ堂")
        self.check(["Tokyo Byte Parking", "入庫 2026/10/05 09:10", "合計 ¥1,200"], "Tokyo Byte Parking")
        self.check(["ｶﾌｪ ﾏﾙｲ", "合計 ¥480"], "カフェ マルイ")

    def test_skips_titles_customers_and_boilerplate(self):
        self.check(["領収書", "No. 000123", "上様", "ギャラリー 青葉", "お支払い ¥1,200"], "ギャラリー 青葉")
        self.check(["いらっしゃいませ", "【カフェ ミドリ堂】", "合計 ¥100"], "カフェ ミドリ堂")

    def test_issuer_at_bottom_of_receipt_form(self):
        self.check(["領収書", "山田 太郎 様", "¥15,400-", "但し 会議費として", "上記正に領収いたしました",
                    "2026年9月30日", "株式会社 ひだまり商事", "東京都架空区ひだまり4-5-6"], "株式会社 ひだまり商事")
        self.check(["領収書", "株式会社テスト 御中", "金額 ¥55,000-", "2026年9月30日", "デザイン事務所 ルーペ"],
                   "デザイン事務所 ルーペ")

    def test_labels_and_same_line_contacts(self):
        self.check(["クレジットカード売上票", "加盟店名: レストラン ソラ", "ご利用金額 ¥7,700"], "レストラン ソラ")
        self.check(["クリーニング ハヤテ TEL 03-0000-1111", "合計 ¥1,320"], "クリーニング ハヤテ")

    def test_store_names_that_look_like_keywords(self):
        self.check(["100円ショップ ダイソン", "合計 ¥110"], "100円ショップ ダイソン")
        self.check(["レジャーランド ゆうえん", "合計 ¥100"], "レジャーランド ゆうえん")
        self.check(["(株)ミドリ(本店)", "合計 ¥100"], "(株)ミドリ(本店)")
        self.check(["ファミリーマート 港区芝5丁目店", "東京都港区芝5-1-2", "合計 ¥100"], "ファミリーマート 港区芝5丁目店")

    def test_address_lines_are_not_stores(self):
        self.check(["神奈川県横浜市架空町1番2号", "カフェ ミドリ堂", "合計 ¥100"], "カフェ ミドリ堂")
        self.check(["架空区みどり1-2-3", "カフェ ミドリ堂", "合計 ¥100"], "カフェ ミドリ堂")

    def test_english_words_containing_keywords(self):
        # HOTEL / PASTEL の中の tel、Timely の time を電話・時刻の見出しと取り違えない
        self.check(["HOTEL SUNRISE OSAKA", "大阪府架空市なみはや町1-2-3", "TEL 06-0000-0101", "領収書",
                    "ご請求金額 ¥26,800"], "HOTEL SUNRISE OSAKA")
        self.check(["PASTEL COFFEE STAND", "Tel 03-0000-0505", "Total ¥1,598"], "PASTEL COFFEE STAND")
        self.check(["Timely Parking 架空駅前", "領収書", "出庫 2026/10/05 07:45", "駐車時間 10時間15分",
                    "お支払 ¥1,500"], "Timely Parking 架空駅前")
        self.check(["Time Cafe", "Date: 2026/10/05", "Total ¥700"], "Time Cafe")
        self.check(["CASHEW CAFE", "Total ¥1,200"], "CASHEW CAFE")
        self.check(["TAXI KING", "運賃 ¥2,000", "合計 ¥2,000"], "TAXI KING")

    def test_prefecture_word_in_store_name(self):
        self.check(["北海道らーめん こがね亭", "架空市みなと町2-5-8", "合計 ¥2,290"], "北海道らーめん こがね亭")

    def test_document_titles_and_brackets(self):
        self.check(["御 計 算 書", "山田 太郎 様", "ご請求額 ¥41,880", "2026年10月11日", "旅館 みさき荘",
                    "静岡県架空郡みさき町9-9"], "旅館 みさき荘")
        self.check(["ベーカリー こむぎ畑(TEL 03-0000-0404)", "合計 ¥1,360"], "ベーカリー こむぎ畑")

    def test_company_form_on_its_own_line(self):
        self.check(["株式会社", "ミドリ商事", "合計 ¥100"], "株式会社 ミドリ商事")


class LayoutTest(unittest.TestCase):
    def test_rotated_segments_are_read_in_order(self):
        # 90 度回転した画像の OCR 結果（文字は下から上へ進む）でも、上から順の行になる
        def seg(text, x, y0, y1):
            return r.Segment(text, [(x, y1), (x, y0), (x + 30, y0), (x + 30, y1)])
        segs = [seg("合計 ¥980", 200, 100, 400), seg("店名テスト", 10, 100, 400), seg("2026/10/07", 100, 100, 400)]
        self.assertEqual([row.text for row in r.build_rows(segs)], ["店名テスト", "2026/10/07", "合計 ¥980"])

    def test_label_and_amount_on_same_baseline_join(self):
        segs = [r.Segment("¥1,280", [(200, 100), (260, 100), (260, 112), (200, 112)]),
                r.Segment("合計", [(20, 101), (50, 101), (50, 113), (20, 113)])]
        self.assertEqual([row.text for row in r.build_rows(segs)], ["合計 ¥1,280"])

    def test_vote(self):
        got = r.vote([{"date": "2026-08-28", "amount": "3160", "store": "ヒカリ交通"},
                      {"date": "2026-08-20", "amount": "3160", "store": "ヒカリ 交通"},
                      {"date": "2026-08-20", "amount": "", "store": "ヒカリ交通"}])
        self.assertEqual(got["date"], "2026-08-20")
        self.assertEqual(got["amount"], "3160")
        self.assertEqual(norm(got["store"]), "ヒカリ交通")


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_text_pdfs_and_file_selection(self):
        d = self.tmp / "in"
        d.mkdir()
        make_pdf(d / "b_reiwa.PDF", ["喫茶 こもれび", "令和8年10月1日", "合計 ¥500", "お預り ¥1,000", "お釣り ¥500"])
        make_pdf(d / "a_rotated.pdf", ["文具店 えんぴつ", "2026/07/07", "合計 ¥330"], rotate=90)
        make_pdf(d / "c,multi.pdf", ["ホテル つばさ", "宿泊日 2026/09/20", "合計 ¥9,800"],
                 extra_pages=[["ご利用規約", "有効期限 2027/03/31"]])
        make_pdf(d / "d_spaced.pdf", ["ベーカリー こむぎ", "2026.10.05", ("lr", "合　計", "¥260"),
                                      ("lr", "お預り", "¥10,000"), ("lr", "お　釣", "¥9,740")])
        (d / "notes.txt").write_text("合計 ¥99,999 2026/01/01", encoding="utf-8")
        (d / "sub.pdf").mkdir()  # フォルダは対象外
        p = run_cli(d)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(read_csv(p.stdout), [
            ["file", "date", "amount", "store"],
            ["a_rotated.pdf", "2026-07-07", "330", "文具店 えんぴつ"],
            ["b_reiwa.PDF", "2026-10-01", "500", "喫茶 こもれび"],
            ["c,multi.pdf", "2026-09-20", "9800", "ホテル つばさ"],
            ["d_spaced.pdf", "2026-10-05", "260", "ベーカリー こむぎ"],
        ])

    def test_unreadable_files_get_empty_rows(self):
        d = self.tmp / "in"
        d.mkdir()
        (d / "a.png").write_bytes(b"not an image")
        (d / "b.jpeg").write_bytes(b"")
        doc = fitz.open()
        doc.new_page().insert_text((20, 40), "合計 ¥100", fontname="japan")
        doc.save(str(d / "c_locked.pdf"), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="owner")
        p = run_cli(d)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(read_csv(p.stdout)[1:], [["a.png", "", "", ""], ["b.jpeg", "", "", ""],
                                                  ["c_locked.pdf", "", "", ""]])
        self.assertNotIn("Traceback", p.stderr)

    def test_output_file_is_utf8_and_stdout_is_empty(self):
        d = self.tmp / "in"
        d.mkdir()
        make_pdf(d / "領収書.pdf", ["まちの電気屋さん", "発行日：2026年10月10日", "合計 1,980円（税込）"])
        out = self.tmp / "out.csv"
        p = run_cli(d, "-o", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "")
        self.assertEqual(read_csv(out.read_bytes().decode("utf-8")),
                         [["file", "date", "amount", "store"], ["領収書.pdf", "2026-10-10", "1980", "まちの電気屋さん"]])

    def test_bad_arguments_fail_without_traceback(self):
        a_file = self.tmp / "file.pdf"
        a_file.write_bytes(b"x")
        for args in ([self.tmp / "missing"], [a_file], [self.tmp, "-o", self.tmp / "no_dir" / "out.csv"], []):
            with self.subTest(args=args):
                p = run_cli(*args)
                self.assertNotEqual(p.returncode, 0)
                self.assertNotIn("Traceback", p.stderr)
                self.assertTrue(p.stderr.strip())


@unittest.skipUnless(HAS_OCR, "macOS の Vision（swift）とヒラギノフォントが必要")
class OcrTest(unittest.TestCase):
    """画像を作って OCR まで通す。回転・透過・EXIF・スキャン PDF・宛名つき領収書など。"""

    @classmethod
    def setUpClass(cls):
        from PIL import Image, ImageFilter
        cls.tmp = Path(tempfile.mkdtemp())
        d = cls.tmp / "in"
        d.mkdir()
        cls.expected = {}

        def add(name, date, amount, store):
            cls.expected[name] = [date, amount, store]

        draw_receipt(["そば処 やまびこ", "2026年9月21日(月)", ("lr", "ざるそば", "¥900"), ("lr", "合　計", "¥1,500"),
                      ("lr", "お預り", "¥2,000"), ("lr", "お釣り", "¥500")]).save(d / "01_right_aligned.png")
        add("01_right_aligned.png", "2026-09-21", "1500", "そば処 やまびこ")

        draw_receipt(["みなと交通", "乗車日 令和8年7月4日", "運賃 ¥1,940", "高速代 ¥700", "合計 ¥2,640"]) \
            .rotate(90, expand=True, fillcolor="white").save(d / "02_rot90.jpg", quality=90)
        add("02_rot90.jpg", "2026-07-04", "2640", "みなと交通")

        rgba = draw_receipt(["ネイルサロン ルミエ", "2026/10/08", "ハンドケア ¥4,400", "合計 ¥4,400"]).convert("L")
        clear = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        clear.putalpha(rgba.point(lambda v: 255 - v))  # 黒文字・透明背景
        clear.save(d / "03_transparent.PNG")
        add("03_transparent.PNG", "2026-10-08", "4400", "ネイルサロン ルミエ")

        exif = Image.Exif()
        exif[0x0112] = 6  # 画素は横倒し、向き情報で正しく表示される写真
        draw_receipt(["花屋 フルール", "2026年10月9日", "花束 ¥3,300", "合計 ¥3,300"]).rotate(90, expand=True) \
            .save(d / "04_exif.jpg", quality=90, exif=exif)
        add("04_exif.jpg", "2026-10-09", "3300", "花屋 フルール")

        draw_receipt(["領収書", "鈴木 一郎 様", "金額 ¥8,800-", "但し 研修費として", "上記正に領収いたしました",
                      "令和8年9月1日", "セミナールーム あかり"]).save(d / "05_form.png")
        add("05_form.png", "2026-09-01", "8800", "セミナールーム あかり")

        draw_receipt(["焼肉 ほむら", "2026年9月25日", "カルビ ¥1,280", "小計 ¥1,280", "合計 ¥1,280", "お預り ¥3,000",
                      "お釣り ¥1,720"]).rotate(4, expand=True, fillcolor="white", resample=Image.BICUBIC) \
            .filter(ImageFilter.GaussianBlur(1)).save(d / "06_skew_blur.jpg", quality=50)
        add("06_skew_blur.jpg", "2026-09-25", "1280", "焼肉 ほむら")

        scan = draw_receipt(["カメラのキタノ", "2026年9月19日", "SDカード ¥2,980", "合計 ¥2,980"]).rotate(180)
        buf = io.BytesIO()
        scan.save(buf, "PNG")
        doc = fitz.open()
        doc.new_page(width=595, height=842).insert_image(fitz.Rect(300, 40, 560, 40 + 260 * scan.height / scan.width),
                                                        stream=buf.getvalue())
        doc.save(str(d / "07_scan_upside_down.pdf"))
        add("07_scan_upside_down.pdf", "2026-09-19", "2980", "カメラのキタノ")

        # テキスト層がスキャナーの透かしだけのスキャン PDF（透かしの日付ではなく領収書の日付を採る）
        scan = draw_receipt(["クリーニング しろくま", "受付日 2026年10月1日", "スーツ上下 ¥1,320", "合計 ¥1,320"])
        buf = io.BytesIO()
        scan.save(buf, "PNG")
        doc = fitz.open()
        page = doc.new_page(width=420, height=595)
        page.insert_image(fitz.Rect(20, 20, 400, 20 + 380 * scan.height / scan.width), stream=buf.getvalue())
        page.insert_text((20, 580), "Scanned 2026/10/12 18:03 FakeScan Pro", fontname="helv", fontsize=8)
        doc.save(str(d / "08_scan_with_footer.pdf"))
        add("08_scan_with_footer.pdf", "2026-10-01", "1320", "クリーニング しろくま")

        cls.proc = run_cli(d)
        cls.rows = read_csv(cls.proc.stdout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_exit_code(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_values(self):
        got = {row[0]: row[1:] for row in self.rows[1:]}
        self.assertEqual(sorted(got), sorted(self.expected))
        for name, (date, amount, store) in self.expected.items():
            with self.subTest(file=name):
                self.assertEqual(got[name][0], date)
                self.assertEqual(got[name][1], amount)
                self.assertEqual(norm(got[name][2]), norm(store))


if __name__ == "__main__":
    unittest.main()
