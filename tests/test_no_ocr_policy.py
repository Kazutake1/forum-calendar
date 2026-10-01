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

    def test_wrapper_keeps_jr_web_parser_and_no_ocr_dependency(self):
        text = (ROOT / "update_events_no_ocr.py").read_text(encoding="utf-8")
        self.assertIn("from jr_walking_web import parse_jr_inazawa_walks", text)
        self.assertIn("updater.parse_jr_inazawa_walks = parse_jr_inazawa_walks", text)
        self.assertNotIn("ocr_pdf", text)
        self.assertNotIn("tesseract", text.lower())


if __name__ == "__main__":
    unittest.main()
