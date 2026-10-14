"""target/receipt2csv.py の read_receipt / extract_* をそのまま呼び、抽出前の生テキストと抽出結果を表示する。
使い方: python3 -B review/dump_text.py <ファイル>...
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "target"))
import receipt2csv as r  # noqa: E402

ocr = r.LocalOCR()
try:
    for name in sys.argv[1:]:
        path = Path(name)
        text = r.read_receipt(path, ocr)
        print(f"===== {path.name} =====")
        for i, line in enumerate(r.lines(text)):
            print(f"{i:3d}| {line}")
        print(f"--> date={r.extract_date(text)!r} amount={r.extract_amount(text)!r} store={r.extract_store(text)!r}")
finally:
    ocr.close()
