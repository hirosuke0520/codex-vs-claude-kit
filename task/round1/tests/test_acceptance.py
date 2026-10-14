"""受け入れテスト（両エンジンに同じものを渡す）。実行: python3 -m unittest discover -s tests -v"""
import csv, io, os, subprocess, sys, tempfile, unicodedata, shutil, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLI = [sys.executable, str(ROOT / "receipt2csv.py")]
SAMPLES = ROOT / "samples"
HEADER = ["file", "date", "amount", "store"]
EXPECTED = {
    "01_cafe.pdf": ("2026-09-03", "1280", "カフェ ミドリ堂"),
    "02_stationery.pdf": ("2026-09-14", "1573", "文具のサクラ屋"),
    "03_books.pdf": ("2026-10-01", "12100", "まるいち書店"),
    "04_taxi.png": ("2026-08-20", "3160", "ヒカリ交通"),
    "05_parking.png": ("2026-10-05", "1200", "Tokyo Byte Parking"),
    "06_lunch.jpg": ("2026-10-07", "980", "定食処 あおば"),
    "07_scanned.pdf": ("2026-07-31", "5460", "ハナミズキ電器"),
}

def norm(s):
    return "".join(unicodedata.normalize("NFKC", s).split())

def run(*args):
    return subprocess.run(CLI + list(args), capture_output=True, text=True, timeout=600)

def read_csv(text):
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))

class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        out = cls.tmp / "out.csv"
        cls.proc = run(str(SAMPLES), "-o", str(out))
        cls.rows = read_csv(out.read_text(encoding="utf-8")) if out.exists() else []

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_exit_code_zero(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_header(self):
        self.assertEqual(self.rows[0], HEADER)

    def test_rows_sorted_and_only_receipts(self):
        self.assertEqual([r[0] for r in self.rows[1:]], sorted(EXPECTED))

    def test_values(self):
        got = {r[0]: r[1:] for r in self.rows[1:]}
        for name, (date, amount, store) in EXPECTED.items():
            with self.subTest(file=name):
                self.assertIn(name, got)
                d, a, s = got[name]
                self.assertEqual(d, date)
                self.assertEqual(a, amount)
                self.assertEqual(norm(s), norm(store))

    def test_stdout_when_no_output_option(self):
        p = run(str(SAMPLES))
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = read_csv(p.stdout)
        self.assertEqual(rows[0], HEADER)
        self.assertEqual(len(rows), 1 + len(EXPECTED))

    def test_empty_dir(self):
        d = self.tmp / "empty"; d.mkdir()
        p = run(str(d))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(read_csv(p.stdout), [HEADER])

    def test_missing_dir_fails(self):
        p = run(str(self.tmp / "no_such_dir"))
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("Traceback", p.stderr)

    def test_broken_file_does_not_stop_batch(self):
        d = self.tmp / "broken"; d.mkdir()
        (d / "a_broken.pdf").write_bytes(b"this is not a pdf")
        shutil.copy(SAMPLES / "01_cafe.pdf", d / "b_ok.pdf")
        p = run(str(d))
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = read_csv(p.stdout)
        self.assertEqual(rows[1], ["a_broken.pdf", "", "", ""])
        self.assertEqual(rows[2][:3], ["b_ok.pdf", "2026-09-03", "1280"])

if __name__ == "__main__":
    unittest.main()
