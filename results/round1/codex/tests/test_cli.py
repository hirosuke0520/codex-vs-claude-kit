"""CLIの境界条件を実際のPDFと壊れた画像で検証する。"""
import csv
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import fitz


ROOT = Path(__file__).resolve().parent.parent


class CLI(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".receipt2csv-test-", dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def pdf(self, name, text):
        path = self.directory / name
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((40, 40), text)
            document.save(path)
        return path

    def run_cli(self, *args, **kwargs):
        return subprocess.run([sys.executable, str(ROOT / "receipt2csv.py"), *map(str, args)],
                              capture_output=True, encoding="utf-8", timeout=60, **kwargs)

    def test_uppercase_extensions_bad_images_and_only_direct_files(self):
        self.pdf("b.PDF", 'Shop, "Moon"\n2026/10/08\nTOTAL JPY 2200')
        (self.directory / "a.PnG").write_bytes(b"broken image")
        (self.directory / "c.JpEg").write_bytes(b"also broken")
        (self.directory / "ignore.txt").write_text("ignore", encoding="utf-8")
        (self.directory / "nested.pdf").mkdir()
        self.pdf("nested.pdf/ignore.pdf", "Hidden Store\nTOTAL 99")
        result = self.run_cli(self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(csv.reader(io.StringIO(result.stdout))), [
            ["file", "date", "amount", "store"],
            ["a.PnG", "", "", ""],
            ["b.PDF", "2026-10-08", "2200", 'Shop, "Moon"'],
            ["c.JpEg", "", "", ""],
        ])

    def test_missing_fields_are_individually_empty(self):
        self.pdf("a.pdf", "2026/10/08\nTOTAL 2200")
        self.pdf("b.pdf", "Moon Store")
        result = self.run_cli(self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(csv.reader(io.StringIO(result.stdout)))[1:], [
            ["a.pdf", "2026-10-08", "2200", ""],
            ["b.pdf", "", "", "Moon Store"],
        ])

    def test_output_cannot_overwrite_receipt_or_hard_link(self):
        path = self.pdf("receipt.pdf", "Moon Store\nTOTAL 2200")
        original = path.read_bytes()
        alias = self.directory / "alias.csv"
        os.link(path, alias)
        for output in (path, alias):
            with self.subTest(output=output.name):
                result = self.run_cli(self.directory, "-o", output)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), original)

    def test_file_input_fails_without_traceback(self):
        path = self.pdf("receipt.pdf", "Moon Store\nTOTAL 2200")
        result = self.run_cli(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_stdout_is_utf8_even_with_ascii_environment(self):
        self.pdf("領収書.pdf", "Moon Store\nTOTAL 2200")
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "ascii"
        result = self.run_cli(self.directory, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(csv.reader(io.StringIO(result.stdout)))[1][0], "領収書.pdf")


if __name__ == "__main__":
    unittest.main()
