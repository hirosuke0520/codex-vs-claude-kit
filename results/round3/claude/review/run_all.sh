#!/bin/sh
# REVIEW.md の再現手順をまとめて実行し、結果を review/results.txt に保存する。
# 使い方（リポジトリ直下で）: sh review/run_all.sh
# target/ は書き換えない。CLI 自身が target/ 内に作る一時フォルダ（.receipt2csv-*）は実行終了時に CLI が消す。
cd "$(dirname "$0")/.." || exit 1
PY=$(command -v python3)
OUT=review/results.txt
export PYTHONDONTWRITEBYTECODE=1

"$PY" -B review/make_cases.py >/dev/null || exit 1
{
  echo "# 実行環境"
  sw_vers 2>/dev/null | tr '\n' ' '; echo
  "$PY" -c 'import sys, fitz, PIL; print("Python", sys.version.split()[0], "/ PyMuPDF", fitz.VersionBind, "/ Pillow", PIL.__version__)'
  swiftc --version 2>&1 | head -1
  echo

  for c in amount_compound_total ocr_tilt store_addressee ocr_row_merge ocr_row_merge_more \
           amount_english_subtotal amount_unmarked_first_number amount_space_concat \
           date_first_wins store_first_line amount_label_vocabulary \
           image_transparent_png broken_symlink date_reiwa_variants \
           ok_image_16bit_png ok_encrypted_pdf ok_pdf_columns note_refund_and_appledouble; do
    echo "## $ python3 target/receipt2csv.py review/cases/$c"
    "$PY" target/receipt2csv.py "review/cases/$c" 2>&1
    echo "(exit=$?)"
    echo
  done

  echo "## Shift_JIS ロケール: LC_ALL=ja_JP.SJIS python3 target/receipt2csv.py target/samples"
  echo "（CSV は UTF-8、標準エラーはロケールどおり Shift_JIS で出るので UTF-8 に変換して表示）"
  ERR=$(mktemp review/.stderr.XXXXXX)
  LANG=ja_JP.SJIS LC_ALL=ja_JP.SJIS "$PY" target/receipt2csv.py target/samples 2>"$ERR"
  echo "(exit=$?)"
  iconv -f SHIFT_JIS -t UTF-8 "$ERR"
  rm -f "$ERR"
  echo

  echo "## OCR が使えない環境（swiftc が PATH に無い）: env PATH=/var/empty \"\$(command -v python3)\" target/receipt2csv.py review/cases/pdf_blank_second_page"
  env PATH=/var/empty "$PY" target/receipt2csv.py review/cases/pdf_blank_second_page 2>&1
  echo "(exit=$?)"
  echo

  echo "## 細い画像: /usr/bin/time -l python3 target/receipt2csv.py review/cases/image_narrow"
  ls -l review/cases/image_narrow/narrow_16x2000.png | awk '{print "入力サイズ:", $5, "bytes"}'
  /usr/bin/time -l "$PY" target/receipt2csv.py review/cases/image_narrow 2>&1 \
    | grep -E "^file,|narrow|警告|real|maximum resident set size"
  echo
} > "$OUT" 2>&1
echo "結果: $OUT"
git status --short --ignored target/ | sed 's/^/target の変更: /'
