# PDF / OCR レビュー結果（親レビューへ統合用）

全件、実際の `target/receipt2csv.py` を実行して確認済み。`target/` は変更していない。再現資料はすべてこのディレクトリ内。

作業フォルダのルートから、必要なら以下で入力を再生成する。

```sh
python3 -B review/pdf/generate.py
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$PWD/review/tmp"
export SWIFT_MODULECACHE_PATH="$PWD/review/cache"
export CLANG_MODULE_CACHE_PATH="$PWD/review/cache"
```

## 高: スキャナーの日時を領収書の日付として黙って確定する

入力: `scanner_date/receipt.pdf`。領収書部分は画像で、店名 Maple Cafe、日付 `2026-10-01`、支払合計 `JPY 1280`。その下にスキャナーの PDF 文字層として `Scanned with local document management software` と `Scan date: 2026-10-02` を置いている。

```sh
python3 -B target/receipt2csv.py review/pdf/scanner_date --debug
```

終了コード 0。標準出力:

```csv
file,date,amount,store
receipt.pdf,2026-10-02,1280,Maple Cate
```

標準エラーの実際の判定結果（全体は `scanner_date.stderr`）:

```text
--- receipt.pdf [テキスト None] -> {'date': '2026-10-02', 'amount': '', 'store': ''}
--- receipt.pdf [補助OCR 0] -> {'date': '2026-10-01', 'amount': '1280', 'store': 'Maple Cate'}
--- receipt.pdf [補助OCR 1] -> {'date': '2026-10-01', 'amount': '1280', 'store': 'Maple Cate'}
--- receipt.pdf [補助OCR 2] -> {'date': '2026-10-01', 'amount': '1280', 'store': 'Maple Cafe'}
```

OCR のすべての読取りで正しい領収日を取得しているが、最終行の日付はスキャン日となる。警告はない。`Maple Cate` は OCR の表記揺れで、この指摘の根拠は日付の取り違え。

原因: `target/receipt2csv.py:885`–`892` は OCR の文字数が PDF 文字層の 2 倍を超えないと OCR を主に使わない。`target/receipt2csv.py:924`–`930` は既存の date を保持し、補助 OCR では空欄だけを埋める。そのため、文字層にスキャン日しかない場合でも正しく抽出できた領収日を採用しない。

## 中: 仕様にない PDF / OCR ページ上限で読取り可能な内容を落とす

### 21 ページ目の文字入り領収書

入力: `page_limit/receipt.pdf`。最初の 20 ページは白紙。21 ページ目だけに `Maple Cafe / 2026-10-01 / TOTAL JPY 1280` を文字として置く。

```sh
python3 -B target/receipt2csv.py review/pdf/page_limit --debug
```

終了コード 0。標準出力:

```csv
file,date,amount,store
receipt.pdf,,,
```

標準エラー末尾:

```text
警告: receipt.pdf: 日付・金額・店名を取得できませんでした
```

対照: 領収書ページを先頭 1 ページのみにした入力では正しく抽出する。

```sh
python3 -B target/receipt2csv.py review/pdf/control_text --debug
```

```csv
file,date,amount,store
receipt.pdf,2026-10-01,1280,Maple Cafe
```

原因: `target/receipt2csv.py:39` の `MAX_PDF_PAGES = 20` を `target/receipt2csv.py:804` で適用し、以降のページを読む処理自体がない。

### 6 ページ目のスキャン領収書

入力: `ocr_limit/receipt.pdf`。最初の 5 ページは白紙。6 ページ目だけに同じ領収書のスキャン画像を置く。

```sh
python3 -B target/receipt2csv.py review/pdf/ocr_limit --debug
```

終了コード 0。標準出力と警告は上記 21 ページの場合と同じ。`control_scan/receipt.pdf` の 1 ページだけなら `2026-10-01,1280,Maple Cafe` が出る。

原因: `target/receipt2csv.py:40` の `MAX_OCR_PAGES = 5` と `target/receipt2csv.py:815`–`819` により、白紙も OCR 回数を消費して 6 ページ目が OCR されない。両上限とも SPEC にはない。上限に達したことも警告されず、単に項目を取得できなかったという表示になる。

## 中: 小さいスキャン画像は注記の文字層があるだけで OCR されない

入力: `small_image/receipt.pdf`。1000 × 1000 のページに 400 × 220 の領収書画像を置き、下に `Scanned` という 7 文字の注記を PDF の文字層で置く。画像はページの 8.8% で、正常な 1 ページ領収書の店名・日付・金額が見える。

```sh
python3 -B target/receipt2csv.py review/pdf/small_image --debug
```

終了コード 0。標準出力:

```csv
file,date,amount,store
receipt.pdf,,,Scanned
```

標準エラー:

```text
--- receipt.pdf [テキスト None] -> {'date': '', 'amount': '', 'store': 'Scanned'}
    Scanned  (size=12.0)
警告: receipt.pdf: 日付・金額を取得できませんでした
```

対照: 画像の位置・大きさを変えず `Scanned` の文字層だけを外した `small_image_control/receipt.pdf` では、OCR で全項目を正しく取得する。

```sh
python3 -B target/receipt2csv.py review/pdf/small_image_control --debug
```

```csv
file,date,amount,store
receipt.pdf,2026-10-01,1280,Maple Cafe
```

原因: `target/receipt2csv.py:786`–`790` は英数字が 6 文字以上なら文字層を有効とみなす。`target/receipt2csv.py:809`–`815` は画像面積がページの 10% 未満で文字層が有効だと OCR を起動しない。抽出結果が不完全でも再度 OCR されないため、画像で読める領収書を取り落とし、注記を店名として出力する。
