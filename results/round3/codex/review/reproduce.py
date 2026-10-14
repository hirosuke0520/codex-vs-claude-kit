"""レビューの最小入力で実CLIを動かす。ネット接続・targetの変更は行わない。"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "review"


def run_case(name, case):
    env = os.environ.copy()
    for key, directory in (
        ("TMPDIR", REVIEW / "tmp"),
        ("SWIFT_MODULECACHE_PATH", REVIEW / "cache"),
        ("CLANG_MODULE_CACHE_PATH", REVIEW / "cache"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-B", str(ROOT / "target/receipt2csv.py"),
               str(REVIEW / "cases" / name)]
    proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=600)
    evidence = REVIEW / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{name}.stdout.txt").write_bytes(proc.stdout)
    (evidence / f"{name}.stderr.txt").write_bytes(proc.stderr)
    rows = list(csv.DictReader(io.StringIO(proc.stdout.decode("utf-8"))))
    matches = len(rows) == 1 and all(rows[0][f] == v for f, v in case["expected"].items())
    result = {"case": name, "command": command, "exit_code": proc.returncode,
              "expected": case["expected"], "actual": rows, "matches_spec": matches}
    (evidence / f"{name}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return proc, result


def main():
    cases = json.loads((REVIEW / "cases.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=["--all", *cases], nargs="?")
    parser.add_argument("--all", action="store_true", help="全ケースを実行してログを保存")
    args = parser.parse_args()
    if not args.case and not args.all:
        parser.error("ケース名または --all が必要です")
    names = list(cases) if args.all else [args.case]
    results = []
    for name in names:
        proc, result = run_case(name, cases[name])
        results.append(result)
        if args.all:
            print(f"{name}: exit={proc.returncode}, matches_spec={result['matches_spec']}", flush=True)
        else:
            sys.stdout.buffer.write(proc.stdout)
            sys.stderr.buffer.write(proc.stderr)
            return proc.returncode
    (REVIEW / "evidence/verification.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
