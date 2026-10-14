"""生成済み入力を CLI で実行し、実出力と終了コードを保存する。"""
import os
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent
env = os.environ.copy()
env.update({
    "TMPDIR": str(ROOT / "review/tmp"),
    "SWIFT_MODULECACHE_PATH": str(ROOT / "review/cache"),
    "CLANG_MODULE_CACHE_PATH": str(ROOT / "review/cache"),
    "PYTHONDONTWRITEBYTECODE": "1",
})
for folder in sorted(BASE.iterdir()):
    if not folder.is_dir() or not (folder / "receipt.pdf").exists():
        continue
    command = [sys.executable, "-B", str(ROOT / "target/receipt2csv.py"), str(folder)]
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    (folder / "actual.csv").write_text(result.stdout, encoding="utf-8")
    (folder / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    (folder / "exit-code.txt").write_text(str(result.returncode) + "\n", encoding="utf-8")
    print(folder.name, "exit=" + str(result.returncode), repr(result.stdout), repr(result.stderr))
