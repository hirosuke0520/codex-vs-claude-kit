"""receipt2csv.read_receipt と同じ前処理（EXIF補正→RGB→幅1600未満なら拡大）をした PNG を書き出す。
使い方: python3 -B review/preprocess_like_tool.py <入力画像> <出力PNG>"""
import sys
from PIL import Image, ImageOps
with Image.open(sys.argv[1]) as image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    if image.width < 1600:
        scale = 1600 / image.width
        image = image.resize((1600, round(image.height * scale)), Image.Resampling.LANCZOS)
    image.save(sys.argv[2])
    print(sys.argv[2], image.size)
