# 日付・店名レビュー（実CLIで確認済み）

全6ケースは `review/date_store/make_inputs.py` で生成した最小のテキストPDFです。PDFは1ページ、画像・OCRなし。再生成と確認は作業フォルダをカレントにして以下で行えます。

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/review/tmp" python3 -B review/date_store/make_inputs.py
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/review/tmp" SWIFT_MODULECACHE_PATH="$PWD/review/cache" CLANG_MODULE_CACHE_PATH="$PWD/review/cache" python3 -B target/receipt2csv.py review/date_store/inputs --debug
```

確認済みの標準出力は `review/date_store/outputs/actual.csv`、標準エラーは `review/date_store/outputs/stderr.txt` に保存済み。終了コードは0。対象の `target/` は変更していません。

## 中: 独立した「店名」見出しを店名として出す

最小入力 `01_store_label.pdf` は次の4行です。

```text
店名
カフェ ミドリ堂
2026/10/01
合計 ¥100
```

実際のCSV行:

```csv
01_store_label.pdf,2026-10-01,100,店名
```

期待値は `store=カフェ ミドリ堂`。見出しと値が別行という普通のレイアウトで実名を落とし、見出し文字列に入れ替わります。警告なし。

原因: `target/receipt2csv.py:444-446` の `STORE_LABEL_RE` は値と同じ行の見出しだけ認識し、値のない「店名」は認識されません。`looks_like_store`（`target/receipt2csv.py:485-496`）の除外対象に店名見出しがなく、`find_store` の先頭優先加点（`target/receipt2csv.py:511-522`）で「店名」は3+2=5点、次行の実店名は2+2=4点になり、見出しを選びます。

注意: 見出しを「店名:」に変えると本ケースでは再現しません。再現入力はコロンのない「店名」です。「店舗名」や「加盟店名」だと短い代替パターンへのバックトラックで値を「名」と誤解する同根の挙動も関数呼出しで確認（これらは実CLIで未確認）。

## 中: 3桁の日を切り詰め、存在しない日付を別の正しい日付にして出す

最小入力 `02_invalid_date.pdf`:

```text
テスト店
2026年10月112日
合計 ¥100
```

実際のCSV行:

```csv
02_invalid_date.pdf,2026-10-11,100,テスト店
```

期待値は `date` 空欄と日付未取得の警告。OCRの余分な数字・壊れた入力を、11日と断定して黙って出します。

原因: `target/receipt2csv.py:160` の日パターンには数字の後方境界がなく、`target/receipt2csv.py:167-175` は末尾の `日` を任意にしているため、`2026年10月112日` のうち `2026年10月11` だけが正規表現に一致します。その切り詰めた候補は `target/receipt2csv.py:215-224` の暦日検証を通ってしまいます。和暦の `令和8年10月112日` も同根です（関数で確認、実CLIは西暦ケースを確認）。

## 中: 取引日のない領収書から有効期限を日付として出す

最小入力 `03_expiry_only.pdf`:

```text
テスト店
有効期限 2026/10/31
合計 ¥100
```

実際のCSV行:

```csv
03_expiry_only.pdf,2026-10-31,100,テスト店
```

取引・領収日のない入力なので `date` は空欄であるべきですが、有効期限を出します。警告なし。領収書にポイント/クーポンの有効期限だけが残っている入力が該当します。

原因: `DATE_BAD` は `target/receipt2csv.py:189-191` で有効期限を把握していますが、`target/receipt2csv.py:254-255` は6点を減らすだけです。`target/receipt2csv.py:262-265` は最低点や除外条件なしで必ず候補の最大値を採用するため、唯一の有効期限が出力されます。

## 中: 店名欠落時、明示された商品名を店名として出す

最小入力 `04_item_no_store.pdf`:

```text
商品名: コーヒー
2026/10/01
合計 ¥100
```

実際のCSV行:

```csv
04_item_no_store.pdf,2026-10-01,100,商品名: コーヒー
```

期待値は `store` 空欄と店名未取得の警告です。これは推測の曖昧な裸の商品名ではなく、「商品名:」と種類を明記した入力です。実店名は一切ありません。警告なし。

原因: `target/receipt2csv.py:447-464` は「商品名」「品名」等の明示見出しを候補から除外せず、`target/receipt2csv.py:485-496` は一般の文字列を店名候補にします。`target/receipt2csv.py:511-522` は店名を示す語やラベルなしでも選択するため、商品名の行が出ます。「取れなかった項目は空」という仕様に反します。

## 低: 1989年より前の有効な西暦日付をすべて落とす

最小入力 `05_old_date.pdf`:

```text
テスト店
1988/10/01
合計 ¥100
```

実際のCSV行:

```csv
05_old_date.pdf,,100,テスト店
```

実際の標準エラー（debug行を除く）:

```text
警告: 05_old_date.pdf: 日付を取得できませんでした
```

期待値は `date=1988-10-01`。仕様には処理対象年の下限がなく、入力に有効な西暦が明記されています。古い領収書を処理した場合に項目を落とします。

原因: `target/receipt2csv.py:222-223` の仕様にない1989年下限で除外します。`TODAY.year + 10` を超える年も同じ条件で除外します。

## 低: 和暦0年を西暦に変換して出す

最小入力 `06_invalid_era.pdf`:

```text
テスト店
令和0年10月1日
合計 ¥100
```

実際のCSV行:

```csv
06_invalid_era.pdf,2018-10-01,100,テスト店
```

期待値は `date` 空欄と日付未取得の警告。令和0年は存在しません。OCR誤認等で入った0を2018年と断定します。警告なし。

原因: `target/receipt2csv.py:167-171` は0を許し、`target/receipt2csv.py:201-203` は年数を検証せず基準年に加算します。`target/receipt2csv.py:215-224` は変換後の西暦暦日しか検証しないため、2018年10月1日として通ります。
