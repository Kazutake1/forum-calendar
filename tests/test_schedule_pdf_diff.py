"""Guard image-only schedule diff against unsafe event rewrites."""
import hashlib
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import schedule_pdf_diff as diff

ROOT=Path(__file__).resolve().parents[1]

class SchedulePdfDiffTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verified=json.loads((ROOT/"verified_schedule.json").read_text(encoding="utf-8"))
        cls.baseline=json.loads((ROOT/".github"/"schedule_pdf_baseline.json").read_text(encoding="utf-8"))

    def test_baseline_is_tied_to_approved_58_rows(self):
        self.assertEqual(len(self.verified["events"]),58)
        self.assertEqual(len(self.baseline["row_digests"]),58)
        self.assertEqual(self.baseline["source_pdf_sha256"],self.verified["source_pdf_sha256"])
        self.assertEqual(self.baseline["reference_size"],[1871,2625])

    def test_changed_cell_is_reported_but_not_written(self):
        orig=[{name:"0"*20 for name,_,_ in diff.COLUMNS} for _ in range(58)]
        changed=[dict(v) for v in orig]
        changed[41]["title"]="1"*20  # November row 14
        reference={**self.baseline,"row_digests":[diff._digest(r) for r in orig]}
        fake_pdf=b"%PDF-12345"
        old=json.dumps(self.verified,sort_keys=True,ensure_ascii=False)
        with patch("schedule_pdf_diff._fingerprints",return_value=changed):
            result=diff.compare(fake_pdf,self.verified,reference)
        self.assertEqual(result["status"],"rows_changed")
        self.assertEqual(result["changed_count"],1)
        self.assertEqual(result["changed_rows"][0]["id"],"schedule-11-14")
        self.assertEqual(result["changed_rows"][0]["fields"],["title"])
        self.assertEqual(json.dumps(self.verified,sort_keys=True,ensure_ascii=False),old)

    def test_many_rows_or_unexpected_layout_are_held(self):
        orig=[{name:"0"*20 for name,_,_ in diff.COLUMNS} for _ in range(58)]
        edited=[dict(v) for v in orig]
        for i in range(16): edited[i]["title"]="1"*20
        reference={**self.baseline,"row_digests":[diff._digest(r) for r in orig]}
        with patch("schedule_pdf_diff._fingerprints",return_value=edited):
            result=diff.compare(b"%PDF-01234",self.verified,reference)
        self.assertEqual(result["status"],"layout_review")
        self.assertEqual(result["changed_count"],16)
        self.assertEqual(result["changed_rows"],[])
        with self.assertRaises(diff.UnsafeScheduleLayout):
            diff.compare(b"%PDF-01234",self.verified,
                         {**reference,"row_digests":reference["row_digests"][:-1]})
        with patch("schedule_pdf_diff._fingerprints",side_effect=diff.UnsafeScheduleLayout("bad layout")):
            with self.assertRaises(diff.UnsafeScheduleLayout):
                diff.compare(b"%PDF-01234",self.verified,reference)

    def test_known_table_line_count_without_ocr(self):
        width,height=diff.SIZE
        sample=bytearray(b"\xff"*(width*height))
        for y in list(range(110,1010,30))+list(range(1120,2080,30)):
            sample[y*width+200:y*width+1120]=b"\x00"*920
        october,november=diff._boundaries(bytes(sample),(width,height))
        self.assertEqual(len(october),30)
        self.assertEqual(len(november),32)
