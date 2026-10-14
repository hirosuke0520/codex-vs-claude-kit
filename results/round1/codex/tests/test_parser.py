"""サンプル以外の文字列で領収書の抽出ルールを検証する。"""
import unittest

from receipt2csv import extract_amount, extract_date, extract_store


class Parser(unittest.TestCase):
    def test_dates_and_full_width_characters(self):
        cases = (
            ("購入日 ２０２５年１１月４日", "2025-11-04"),
            ("領収日 令和元年５月１日", "2019-05-01"),
            ("発行日 令和8年2月15日", "2026-02-15"),
            ("購入日 2024/02/29", "2024-02-29"),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(extract_date(text), expected)

    def test_invalid_or_missing_date_is_empty(self):
        for text in ("2025-02-29", "2026/13/01", "2026年4月31日", "日付なし"):
            with self.subTest(text=text):
                self.assertEqual(extract_date(text), "")

    def test_total_wins_over_other_amounts(self):
        text = "\n".join((
            "雑貨 2点 ￥2,800",
            "小計 ￥2,800",
            "消費税 ￥280",
            "合計 ￥3,080",
            "内税 ￥280",
            "お預り ￥5,000",
            "お釣り ￥1,920",
        ))
        self.assertEqual(extract_amount(text), "3080")

    def test_total_labels_and_separate_value_line(self):
        cases = (
            ("ご請求額 ￥8,640（税込）", "8640"),
            ("お支払金額 2,350円", "2350"),
            ("SUBTOTAL 300\nTAX 30\nTOTAL JPY 330", "330"),
            ("小計 ￥3,845\n合計\n￥４，２３０\nお預り ￥5,000", "4230"),
            ("合計 ￥1,100（内消費税 ￥100）", "1100"),
            ("合計（税込）￥1,100", "1100"),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(extract_amount(text), expected)

    def test_non_total_amounts_are_not_guessed(self):
        text = "小計 ￥1,500\n消費税 ￥150\nお預り ￥2,000\nお釣り ￥350"
        self.assertEqual(extract_amount(text), "")
        self.assertEqual(extract_amount("金額記載なし"), "")

    def test_store_after_receipt_header(self):
        cases = (
            ("領収書\n喫茶 星の庭\n東京都架空区4-2-1\nTEL 00-0000-0123\n2025/11/04", "喫茶 星の庭"),
            ("HOTEL MOON\nTOTAL 12000", "HOTEL MOON"),
            ("領収書\n店名\n喫茶 月あかり\n2025/11/04\n合計 ￥1,100", "喫茶 月あかり"),
            ("領収書\n2025/11/04\n合計 ￥1,100\nありがとうございました", ""),
            ("", ""),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(extract_store(text), expected)


if __name__ == "__main__":
    unittest.main()
