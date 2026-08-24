#!/usr/bin/env python3
import json, re, subprocess, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
EVENTS_FILE = ROOT / "events.json"
META_FILE = ROOT / "update-meta.json"

SCHEDULE_PAGE = "https://www.city.inazawa.aichi.jp/ica/0000004875.html"
EVENT_GUIDE = "https://www.city.inazawa.aichi.jp/ica/0000002507.html"
UA = "forum-calendar-auto-updater/1.0 (+GitHub Actions)"

def get(url):
    r=requests.get(url,headers={"User-Agent":UA},timeout=30)
    r.raise_for_status()
    return r

def load_old():
    try:
        return json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def norm(s):
    return re.sub(r"\s+"," ",(s or "").replace("\u3000"," ")).strip()

def canonical_key(e):
    return (e.get("date",""), norm(e.get("title","")), e.get("hall",""))

def merge(old, new):
    out={canonical_key(e):e for e in old if e.get("date") and e.get("title")}
    for e in new:
        if e.get("date") and e.get("title"):
            out[canonical_key(e)]={**out.get(canonical_key(e),{}),**e}
    return sorted(out.values(),key=lambda x:(x.get("date","9999"),x.get("time",""),x.get("title","")))

def find_schedule_pdf():
    r=get(SCHEDULE_PAGE)
    soup=BeautifulSoup(r.text,"html.parser")
    links=[]
    for a in soup.find_all("a",href=True):
        text=norm(a.get_text(" ",strip=True))
        href=urljoin(SCHEDULE_PAGE,a["href"])
        if href.lower().endswith(".pdf") and ("催事予定表" in text or "イベント" in text):
            links.append((text,href))
    if not links:
        raise RuntimeError("催事予定表PDFが見つかりません")
    return links[0]

def ocr_pdf(pdf_bytes):
    with tempfile.TemporaryDirectory() as td:
        pdf=Path(td)/"schedule.pdf"; pdf.write_bytes(pdf_bytes)
        prefix=Path(td)/"page"
        subprocess.run(["pdftoppm","-png","-r","240",str(pdf),str(prefix)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        texts=[]
        for img in sorted(Path(td).glob("page-*.png")):
            p=subprocess.run(["tesseract",str(img),"stdout","-l","jpn+eng","--psm","6"],capture_output=True,text=True,check=True)
            texts.append(p.stdout)
        return "\n".join(texts)

def infer_year_months(label, pdf_url):
    # e.g. 令和8年8月・9月 / 202608-09.pdf
    m=re.search(r"令和\s*(\d+)年\s*(\d+)月.*?(\d+)月",label)
    if m:
        return 2018+int(m.group(1)), [int(m.group(2)),int(m.group(3))]
    m=re.search(r"(20\d{2})(\d{2})-(\d{2})",pdf_url)
    if m:
        return int(m.group(1)),[int(m.group(2)),int(m.group(3))]
    now=datetime.now()
    return now.year,[now.month]

def parse_schedule_ocr(text, year, months):
    # OCR fallback parser. It intentionally only accepts rows with recognizable
    # date + hall and enough title text. This avoids corrupting events.json.
    events=[]
    current_month=months[0]
    for raw in text.splitlines():
        line=norm(raw)
        if not line: continue
        mm=re.search(r"(\d{1,2})\s*月",line)
        if mm and int(mm.group(1)) in months:
            current_month=int(mm.group(1))
        hall=""
        if "大ホール" in line: hall="大ホール"
        elif "中ホール" in line: hall="中ホール"
        elif "小ホール" in line: hall="小ホール"
        if not hall: continue
        dm=re.search(r"(?:^|\s)(\d{1,2})(?:日|\s)",line)
        if not dm: continue
        day=int(dm.group(1))
        try:
            date=f"{year:04d}-{current_month:02d}-{day:02d}"
        except Exception:
            continue
        # Strip common columns
        title=line
        title=re.sub(rf"(^|\s){day}(日)?(\s|$)"," ",title,count=1)
        title=title.replace(hall," ")
        title=re.sub(r"\b\d{1,2}:\d{2}\b.*$","",title)
        title=re.sub(r"\b(無料|関係者|要整理券|会員制)\b.*$","",title)
        title=norm(title)
        if len(title)<4: continue
        time=""
        tm=re.search(r"(\d{1,2}:\d{2})(?:\s*[〜～~-]\s*(\d{1,2}:\d{2}))?",line)
        if tm:
            time=tm.group(1)+(f"〜{tm.group(2)}" if tm.group(2) else "〜")
        price=""
        if "無料" in line: price="無料"
        elif "関係者" in line: price="関係者"
        elif "要整理券" in line: price="要整理券"
        events.append({"date":date,"hall":hall,"time":time,"title":title,"price":price,"source":"schedule_ocr"})
    # Deduplicate OCR repeats
    uniq={}
    for e in events: uniq[canonical_key(e)]=e
    return list(uniq.values())

def parse_event_guide():
    r=get(EVENT_GUIDE)
    soup=BeautifulSoup(r.text,"html.parser")
    text=norm(soup.get_text("\n",strip=True))
    # The page is rich and changes over time. We safely extract event-like
    # headings and dates when both are explicit.
    events=[]
    headings=soup.find_all(["h2","h3","h4"])
    for h in headings:
        title=norm(h.get_text(" ",strip=True))
        if not title or any(x in title for x in ["開催日","チケット","お問い合わせ","料金","会場"]):
            continue
        # scan a limited number of following siblings for explicit date/hall
        chunk=[]
        cur=h
        for _ in range(12):
            cur=cur.find_next()
            if not cur: break
            if cur.name in ["h2","h3","h4"] and cur is not h: break
            t=norm(cur.get_text(" ",strip=True))
            if t: chunk.append(t)
        ctx=" ".join(chunk)
        dm=re.search(r"令和\s*(\d+)年\s*(\d+)月\s*(\d+)日",ctx)
        if not dm:
            dm2=re.search(r"(20\d{2})年\s*(\d+)月\s*(\d+)日",ctx)
            if dm2: year,month,day=map(int,dm2.groups())
            else: continue
        else:
            year=2018+int(dm.group(1)); month=int(dm.group(2)); day=int(dm.group(3))
        hall="その他"
        for hh in ["大ホール","中ホール","小ホール"]:
            if hh in ctx: hall=hh; break
        tm=re.search(r"(\d{1,2})時(\d{2})分",ctx)
        time=f"{int(tm.group(1))}:{tm.group(2)}〜" if tm else ""
        cleaned=re.sub(r"^[〖【].*?[〗】]\s*","",title)
        if len(cleaned)>=4:
            events.append({"date":f"{year:04d}-{month:02d}-{day:02d}","hall":hall,"time":time,"title":cleaned,"price":"","source":"event_guide","official_url":EVENT_GUIDE})
    return events

def main():
    old=load_old()
    added=[]
    notes=[]
    status="ok"

    # Official event guide (HTML)
    try:
        guide=parse_event_guide()
        if guide:
            added.extend(guide)
            notes.append(f"公式イベント案内 {len(guide)}件")
        else:
            notes.append("公式イベント案内: 新規構造化データなし")
    except Exception as e:
        notes.append(f"公式イベント案内取得失敗: {e}")

    # Monthly schedule PDF (OCR)
    try:
        label,pdf_url=find_schedule_pdf()
        pdf=get(pdf_url).content
        year,months=infer_year_months(label,pdf_url)
        text=ocr_pdf(pdf)
        parsed=parse_schedule_ocr(text,year,months)
        # Safety threshold: do not merge a suspiciously small OCR result.
        if len(parsed)>=8:
            added.extend(parsed)
            notes.append(f"催事予定表OCR {len(parsed)}件 / {pdf_url}")
        else:
            notes.append(f"催事予定表OCRは信頼度不足({len(parsed)}件)のため既存データを維持")
    except Exception as e:
        notes.append(f"催事予定表OCR失敗: {e}")

    merged=merge(old,added)
    if not merged:
        merged=old
        status="fallback"

    EVENTS_FILE.write_text(json.dumps(merged,ensure_ascii=False,indent=2),encoding="utf-8")
    jst=timezone(timedelta(hours=9))
    META_FILE.write_text(json.dumps({
        "status":status,
        "updated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "updated_at_jst":datetime.now(jst).strftime("%Y/%m/%d %H:%M"),
        "event_count":len(merged),
        "notes":notes,
        "sources":[SCHEDULE_PAGE,EVENT_GUIDE]
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print("\n".join(notes))
    print(f"events: {len(old)} -> {len(merged)}")

if __name__=="__main__":
    main()
