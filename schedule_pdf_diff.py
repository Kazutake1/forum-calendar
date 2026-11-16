"""Fail-closed, read-only image comparison of the 58 confirmed 2026-10/11 hall schedule rows.

No OCR, text guesses, or data mutation. Detect changed row/cell locations only.
Only separately verified official event data can authorize an event correction.
"""
import hashlib
import json
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent
DPI = 220
SIZE = (1871, 2625)
COLUMNS = (("date",178,247),("weekday",247,286),("hall",286,340),
           ("time",340,473),("title",473,1148),("price",1148,1264),
           ("organizer",1264,1605),("contact",1605,1767))
EXPECTED_MONTH_ROWS = (28,30)

class UnsafeScheduleLayout(ValueError):
    """A changed PDF format is not safe to assign to known event rows."""

def _render(pdf):
    if len(pdf) < 100 or len(pdf) > 25*1024*1024 or not pdf.startswith(b"%PDF-"):
        raise UnsafeScheduleLayout("PDF形式・サイズを確認できません")
    try:
        with fitz.open(stream=pdf,filetype="pdf") as document:
            if document.page_count != 1:
                raise UnsafeScheduleLayout("PDFのページ数が変更されました")
            pix=document[0].get_pixmap(matrix=fitz.Matrix(DPI/72,DPI/72),
                                        colorspace=fitz.csGRAY,alpha=False)
            return pix.samples,(pix.width,pix.height)
    except UnsafeScheduleLayout:
        raise
    except Exception as exc:
        raise UnsafeScheduleLayout("PDFの画像化に失敗しました") from exc

def _boundaries(image,size):
    width,height=size
    if size != SIZE:
        raise UnsafeScheduleLayout("PDFのページ寸法が変更されました")
    positions=[]
    for y in range(height):
        row=image[y*width+200:y*width+1120]
        if sum(pixel < 185 for pixel in row) >= 828:
            positions.append(y)
    lines=[]
    for y in positions:
        if not lines or y-lines[-1][-1] > 2: lines.append([y])
        else: lines[-1].append(y)
    lines=[group[0] for group in lines]
    if len(lines) != sum(EXPECTED_MONTH_ROWS)+4:
        raise UnsafeScheduleLayout("PDFの罫線または行数が変更されました")
    block1=lines[:30]
    block2=lines[30:]
    for block,count in ((block1,28),(block2,30)):
        if len(block) != count+2 or any(not 19 <= b-a <= 95
                                         for a,b in zip(block,block[1:])):
            raise UnsafeScheduleLayout("PDFの行幅・構造が変わりました")
    if block2[0]-block1[-1] < 15:
        raise UnsafeScheduleLayout("月別の表を分離できません")
    return block1,block2

def _fingerprints(pdf):
    image,size=_render(pdf)
    width,_=size
    rows=[]
    for block in _boundaries(image,size):
        for i in range(len(block)-2):
            y1,y2=block[i+1],block[i+2]
            fields={}
            for name,left,right in COLUMNS:
                h=hashlib.sha256()
                for y in range(y1+2,y2-2):
                    h.update(image[y*width+left+2:y*width+right-2])
                fields[name]=h.hexdigest()[:20]
            rows.append(fields)
    if len(rows) != 58:
        raise UnsafeScheduleLayout("全58行の対応が失われました")
    return rows

def _digest(cells):
    joined="".join(cells[name] for name,_,_ in COLUMNS)
    total=hashlib.sha256(joined.encode("ascii")).hexdigest()[:16]
    return total+cells["title"][:16]+cells["time"][:16]+cells["date"][:16]+cells["hall"][:16]

def _ids():
    return ([f"schedule-10-{i:02d}" for i in range(1,29)]
            +[f"schedule-11-{i:02d}" for i in range(1,31)])

def build_baseline(pdf,verified):
    """Offline authoring after visually checking a published PDF; not the daily path."""
    rows=verified.get("events") or []
    if [x.get("id") for x in rows] != _ids():
        raise UnsafeScheduleLayout("確認済みの58行が一致しません")
    pdfsha=hashlib.sha256(pdf).hexdigest()
    if pdfsha != verified.get("source_pdf_sha256"):
        raise UnsafeScheduleLayout("原本PDFのSHA-256が一致しません")
    return {"schema_version":1,"source_pdf_sha256":pdfsha,
            "reference_size":list(SIZE),"render_dpi":DPI,
            "row_digests":[_digest(c) for c in _fingerprints(pdf)]}

def compare(pdf,verified,baseline):
    """Report changed positions only. Never edits an event or infers new values."""
    rows=verified.get("events") or []
    refs=baseline.get("row_digests")
    prior=verified.get("source_pdf_sha256")
    if ([x.get("id") for x in rows] != _ids()
        or baseline.get("schema_version") != 1
        or baseline.get("source_pdf_sha256") != prior
        or baseline.get("reference_size") != list(SIZE)
        or baseline.get("render_dpi") != DPI
        or not isinstance(refs,list) or len(refs) != 58
        or any(not isinstance(x,str) or len(x)!=80
               or any(c not in "0123456789abcdef" for c in x) for x in refs)):
        raise UnsafeScheduleLayout("確認済み予定表と画像比較基準が一致しません")
    sha=hashlib.sha256(pdf).hexdigest()
    result={"status":"unchanged","baseline_sha256":prior,
            "current_sha256":sha,"changed_count":0,"changed_rows":[]}
    if sha == prior:
        return result
    changes=[]
    for row,old,cells in zip(rows,refs,_fingerprints(pdf)):
        new=_digest(cells)
        if new == old: continue
        changed=[name for name,pos in
                 (("title",16),("time",32),("date",48),("hall",64))
                 if new[pos:pos+16] != old[pos:pos+16]]
        changes.append({"id":row["id"],"date":row["date"],"hall":row["hall"],
                        "fields":changed or ["other_fields"]})
    result["changed_count"]=len(changes)
    if len(changes) > 15:
        result["status"]="layout_review"
        result["warning"]="多数の行が変更されました。個別行の照合は保留"
    elif changes:
        result["status"]="rows_changed"
        result["changed_rows"]=changes
    else:
        result["status"]="pdf_changed_no_row_changes"
    return result

def compare_against_pinned(pdf,root=ROOT):
    verified=json.loads((root/"verified_schedule.json").read_text(encoding="utf-8"))
    baseline=json.loads((root/"schedule_pdf_baseline.json").read_text(encoding="utf-8"))
    return compare(pdf,verified,baseline)
