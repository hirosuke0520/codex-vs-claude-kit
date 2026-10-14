#!/usr/bin/env python3
"""Extract receipt fields locally; scanned receipts use macOS Vision."""

import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata

import fitz
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def lines(text):
    return [line.strip() for line in unicodedata.normalize("NFKC", text).splitlines()
            if line.strip()]


def extract_date(text):
    text = unicodedata.normalize("NFKC", text)
    pattern = r"(?:(令和)\s*(元|\d{1,2})|(?<!\d)(\d{4}))\s*(?:年|[./-])\s*(\d{1,2})\s*(?:月|[./-])\s*(\d{1,2})(?:日|(?!\d))"
    for match in re.finditer(pattern, text):
        era, era_year, year, month, day = match.groups()
        if era:
            if era_year != "元" and int(era_year) < 1:
                continue
            year = 2018 + (1 if era_year == "元" else int(era_year))
        try:
            date = datetime.date(int(year), int(month), int(day))
        except ValueError:
            continue
        if era and date < datetime.date(2019, 5, 1):
            continue
        return date.isoformat()
    return ""


def extract_amount(text):
    receipt_lines = lines(text)
    excluded = re.compile(r"小\s*計|税抜|税額|消費税|内税|外税|お?預[りか]?|お?釣[り]?|SUB\s*TOTAL|CHANGE|TENDER", re.I)
    labels = re.compile(
        r"お?支払(?:い)?(?:合計|金額|額)|ご?請求(?:金額|額)|総(?:合計|額)|合\s*計(?:金額)?|領収(?:金額|額)|\bTOTAL\b", re.I)
    # A currency-marked number takes precedence over incidental label digits.
    money = re.compile(r"[¥￥] *([0-9][0-9, ]*)|([0-9][0-9, ]*) *円|(?<![\d/.-])([0-9]+(?:,[0-9]{3})*)(?![\d/.-])")
    candidates = []
    for index, line in enumerate(receipt_lines):
        compact = re.sub(r"\s+", "", line)
        label = labels.search(line)
        if not label or excluded.search(line[:label.start()]):
            continue
        tail = line[label.end():]
        # Tax annotations can share the total's row, but their amount is not the total.
        tail = re.sub(r"\([^)]*(?:税|TAX)[^)]*\)", "", tail, flags=re.I)
        tail = re.split(r"内消費税|内税|消費税|税額", tail, maxsplit=1)[0]
        matches = list(money.finditer(tail))
        if not matches and index + 1 < len(receipt_lines):
            next_line = receipt_lines[index + 1]
            if re.fullmatch(r"\s*[¥￥]?\s*[0-9][0-9, ]*\s*円?\s*", next_line):
                matches = list(money.finditer(next_line))
        if not matches:
            continue
        marked = [match for match in matches if match.group(1) or match.group(2)]
        match = (marked or matches)[0]
        amount = re.sub(r"\D", "", next(group for group in match.groups() if group is not None))
        rank = 3 if re.search(r"支払|総合計", compact) else 2 if "合計" in compact or re.search(r"\bTOTAL\b", line, re.I) else 1
        candidates.append((rank, -index, amount.lstrip("0") or "0"))
    return max(candidates)[2] if candidates else ""


def extract_store(text):
    for line in lines(text):
        compact = re.sub(r"\s+", "", line)
        if re.fullmatch(r"領収(?:書|証)|レシート|RECEIPT|INVOICE", compact, re.I):
            continue
        if re.match(r"(?:店舗名|店名|販売店)\s*[:：]?\s*", line):
            store = re.sub(r"^(?:店舗名|店名|販売店)\s*[:：]?\s*", "", line)
            if store:
                return store
            continue
        if re.search(r"ありがとう|ご利用|またのご来店|THANK\s*YOU", line, re.I):
            continue
        if re.search(r"電話|登録番号|発行日|取引日|日付|住所|〒|合計|小計|請求|消費税|預り|お釣|領収|支払", compact):
            continue
        if re.search(r"\b(?:TEL|FAX)(?=\s|[:：]|\d|$)", line, re.I):
            continue
        if re.match(r"(?:TOTAL|SUBTOTAL|TAX|CHANGE|CASH|AMOUNT\s+DUE|DATE)(?:\s*[:¥$]|\s+(?:JPY\s*)?\d|$)", line, re.I):
            continue
        if re.search(r"\d{4}\s*[-/年.]|令和|\d+\s*円|[¥￥]|\d{2,4}-\d{2,4}-\d{3,4}", line):
            continue
        if re.search(r"[A-Za-z\u3040-\u30ff\u3400-\u9fff]", line):
            # shortcut: the first plausible heading is the store; complex layouts need layout-aware parsing.
            return line
    return ""


class LocalOCR:
    def __init__(self):
        self.temporary = None
        self.binary = None
        self.build_error = None

    def directory(self):
        if self.temporary is None:
            self.temporary = tempfile.TemporaryDirectory(prefix=".receipt2csv-", dir=ROOT)
        return Path(self.temporary.name)

    def read(self, path):
        if self.build_error:
            raise RuntimeError(self.build_error)
        directory = self.directory()
        if self.binary is None:
            binary = directory / "vision-ocr"
            try:
                environment = os.environ.copy()
                environment["TMPDIR"] = str(directory)
                subprocess.run(
                    ["swiftc", "-module-cache-path", str(directory / "module-cache"),
                     str(ROOT / "receipt_ocr.swift"), "-o", str(binary)],
                    check=True, capture_output=True, text=True, timeout=180,
                    env=environment)
            except (OSError, subprocess.SubprocessError) as error:
                self.build_error = "Vision OCR を起動できません（macOS と Swift が必要です）"
                raise RuntimeError(self.build_error) from error
            self.binary = binary
        result = subprocess.run([str(self.binary), str(path.resolve())], check=True,
                                capture_output=True, text=True, timeout=60)
        return json.loads(result.stdout)["text"]

    def close(self):
        if self.temporary is not None:
            self.temporary.cleanup()


def read_receipt(path, ocr):
    if path.suffix.lower() == ".pdf":
        texts = []
        with fitz.open(path) as document:
            for index, page in enumerate(document):
                text = page.get_text(sort=True)
                if not text.strip():
                    image_path = ocr.directory() / f"page-{index}.png"
                    page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).save(image_path)
                    text = ocr.read(image_path)
                texts.append(text)
        return "\n".join(texts)
    with Image.open(path) as image:
        image_path = ocr.directory() / "image.png"
        image = ImageOps.exif_transpose(image).convert("RGB")
        if image.width < 1600:
            scale = 1600 / image.width
            image = image.resize((1600, round(image.height * scale)), Image.Resampling.LANCZOS)
        image.save(image_path)
    return ocr.read(image_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="領収書をローカルで読み取り UTF-8 CSV にまとめます")
    parser.add_argument("input", type=Path, help="領収書が入ったフォルダ（直下のみ）")
    parser.add_argument("-o", "--output", type=Path, help="出力CSV（省略時は標準出力）")
    args = parser.parse_args(argv)
    if not args.input.is_dir():
        parser.error(f"入力フォルダが存在しないか、フォルダではありません: {args.input}")
    try:
        paths = sorted((path for path in args.input.iterdir()
                        if path.is_file() and path.suffix.lower() in EXTENSIONS),
                       key=lambda path: path.name)
    except OSError as error:
        parser.error(f"入力フォルダを読めません: {error}")
    try:
        if args.output and any(args.output.resolve() == path.resolve() or
                               (args.output.exists() and args.output.samefile(path)) for path in paths):
            parser.error("出力先が入力の領収書と同じです。別のCSVファイルを指定してください")
    except OSError as error:
        parser.error(f"出力先を確認できません: {error}")
    ocr = LocalOCR()
    try:
        output = args.output.open("w", encoding="utf-8", newline="") if args.output else sys.stdout
        if not args.output:
            output.reconfigure(encoding="utf-8", newline="")
        try:
            writer = csv.writer(output)
            writer.writerow(["file", "date", "amount", "store"])
            for path in paths:
                try:
                    text = read_receipt(path, ocr)
                except Exception as error:
                    print(f"警告: {path.name} を読めません: {error}", file=sys.stderr)
                    text = ""
                writer.writerow([path.name, extract_date(text), extract_amount(text), extract_store(text)])
        finally:
            if args.output:
                output.close()
    except OSError as error:
        print(f"エラー: CSV を書き込めません: {error}", file=sys.stderr)
        return 1
    finally:
        ocr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
