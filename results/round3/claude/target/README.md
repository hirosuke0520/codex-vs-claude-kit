# receipt2csv

領収書のPDF・PNG・JPG・JPEGを、1ファイル1行のUTF-8 CSVにまとめます。

```sh
python3 receipt2csv.py samples
python3 receipt2csv.py samples -o receipts.csv
python3 -m unittest discover -s tests -v
```

列は `file,date,amount,store`。入力フォルダ直下のみをファイル名順に処理し、
読めないファイルも行を残します。取得できない項目は空欄、警告は標準エラーへ出します。
令和の日付を西暦に変換し、合計・支払金額・請求額から金額を選びます。
小計・預り・釣り・税額だけの場合は合計を推測しません。

PDFの文字はPyMuPDF、画像と文字のないPDFページはmacOS Visionで読み取ります。
ネット通信・外部API・追加インストールは使いません。既存のPython 3、PyMuPDF、
Pillow、Swiftが必要です。`receipt_ocr.swift` は `receipt2csv.py` と同じ場所に置いてください。
初回OCR時にSwiftをコンパイルします。コンパイルと画像変換の一時ファイルは
このフォルダ内に作成し、実行終了時に削除するため、書き込み権限が必要です。

OCRには誤読があります。店名は先頭付近の見出しから推定するため、
複雑なレイアウトでは誤る場合があります。日付は西暦と令和、金額は円の整数に対応します。
文字とスキャン画像が同じPDFページに混在する場合、文字部分だけを読みます。
出力内容は利用前に原本と確認してください。
