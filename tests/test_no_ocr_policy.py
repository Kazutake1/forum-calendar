"""Regression guard for the repository's no-OCR production policy."""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class NoOcrPolicyTests(unittest.TestCase):
    def test_base_updater_contains_no_ocr_implementation(self):
        text = (ROOT / "update_events.py").read_text(encoding="utf-8")
        self.assertNotIn("tesseract", text.lower())
        self.assertNotIn("def ocr_pdf", text)
        self.assertNotIn("def parse_schedule_ocr", text)
        self.assertIn("催事予定表OCRは無効です", text)

    def test_direct_base_updater_execution_is_blocked(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "update_events.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("update_events_no_ocr.py", output)

    def test_production_workflow_uses_only_canonical_entrypoint(self):
        production = (WORKFLOWS / "update-events.yml").read_text(encoding="utf-8")
        self.assertIn("python update_events_no_ocr.py", production)
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("tesseract", text.lower(), path.name)
            for line in text.splitlines():
                command = line.strip()
                self.assertFalse(
                    command.startswith("python update_events.py"),
                    f"Direct OCR-capable updater command is forbidden: {path.name}: {command}",
                )

    def test_jr_web_parser_is_the_only_jr_implementation(self):
        base = (ROOT / "update_events.py").read_text(encoding="utf-8")
        wrapper = (ROOT / "update_events_no_ocr.py").read_text(encoding="utf-8")
        self.assertIn("from jr_walking_web import parse_jr_inazawa_walks", base)
        self.assertNotIn("def parse_jr_inazawa_walks", base)
        self.assertNotIn("_jr_pdf_text", base)
        self.assertNotIn("_jr_brochure_url", base)
        self.assertNotIn("_jr_year", base)
        self.assertNotIn("_jr_clean_title", base)
        self.assertNotIn("pdftotext", base.lower())
        self.assertNotIn("subprocess", base)
        self.assertNotIn("tempfile", base)
        self.assertNotIn('"walking.jr-central.co.jp"}', base)
        self.assertIn("from update_events import main", wrapper)
        self.assertNotIn("updater.parse_jr_inazawa_walks", wrapper)
        self.assertNotIn("ocr_pdf", wrapper)
        self.assertNotIn("tesseract", wrapper.lower())


if __name__ == "__main__":
    unittest.main()
