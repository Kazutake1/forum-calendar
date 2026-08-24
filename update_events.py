#!/usr/bin/env python3
import json, re, subprocess, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
EVENTS_FILE = ROOT / "events.json"
META_FILE = ROOT / "update-meta.json"
DEFAULT_SCHEDULE_PAGE = "https://www.city.inazawa.aichi.jp/ica/0000004875.html"
DEFAULT_EVENT_GUIDE = "https://www.city.inazawa.aichi.jp/ica/0000002507.html"
ICA_HOME = "https://www.city.inazawa.aichi.jp/ica/index.html"
SITE_MAP = "https://www.city.inazawa.aichi.jp/sitemap.html"
ALLOWED_HOST = "www.city.inazawa.aichi.jp"
UA = "forum-calendar-auto-updater/2.0 (+GitHub Actions)"
MAX_DOWNLOAD = 25 * 1024 * 1024
HALLS = {"大ホール", "中ホール", "小ホール"}

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def clean(s, limit=240):
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(s or ""))
    return re.sub(r"\s+", " ", s.replace("\u3000", " ")).strip()[:limit]

def get(url):
    u = urlparse(url)
    if u.scheme != "https" or u.hostname != ALLOWED_HOST:
        raise RuntimeError(f"許可されていない取得先: {url}")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30, stream=True)
    r.raise_for_status()
    data = bytearray()
    for chunk in r.iter_content(65536):
        if chunk:
            data.extend(chunk)
            if len(data) > MAX_DOWNLOAD:
                raise RuntimeError("取得ファイルが大きすぎます")
    r._content = bytes(data)
    r._content_consumed = True
    return r

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def valid_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except Exception:
        return False

def sanitize_event(e):
    out = {
        "date": clean(e.get("date"), 10),
        "hall": clean(e.get("hall"), 24),
        "time": clean(e.get("time"), 40),
        "title": clean(e.get("title"), 240),
        "price": clean(e.get("price"), 100),
    }
    if e.get("source"): out["source"] = clean(e.get("source"), 32)
    if e.get("official_url"):
        u = clean(e.get("official_url"), 500)
        if urlparse(u).scheme == "https": out["official_url"] = u
    if not valid_date(out["date"]) or len(out["title"]) < 2:
        return None
    return out

def key(e):
    return (e.get("date", ""), clean(e.get("title")), e.get("hall", ""))

def dedupe(events):
    out = {}
    for raw in events:
        e = sanitize_event(raw)
        if e: out[key(e)] = e
    return sorted(out.values(), key=lambda x:(x["date"], x.get("time", ""), x["title"]))

def ym(e): return e.get("date", "")[:7]


def page_is_valid(url, kind):
    try:
        r=get(url)
        soup=BeautifulSoup(r.text,"html.parser")
        h1=clean(soup.find("h1").get_text(" ",strip=True) if soup.find("h1") else "", 200)
        title=clean(soup.title.get_text(" ",strip=True) if soup.title else "", 200)
        text=f"{h1} {title}"
        if kind=="schedule":
            return "ホール催事予定表" in text
        if kind=="events":
            if ("コンサート" in text and "イベント" in text):
                return True
            # Structural fallback: consolidated event guide contains multiple event sections.
            return len(soup.find_all(["h2","h3"], string=re.compile("財団|開催日"))) >= 2
    except Exception:
        return False
    return False

def candidate_score(text, kind):
    t=clean(text,200)
    if kind=="schedule":
        if t=="ホール催事予定表": return 100
        if "ホール催事予定表" in t: return 80
        return 0
    # Prefer the consolidated event-list link, not individual event links.
    if "イベント一覧を見る" in t: return 100
    if "コンサート" in t and "イベント" in t: return 95
    if t in {"イベント","イベント案内"}: return 50
    return 0

def discover_page(kind, preferred):
    # 1) Existing URL first, so ordinary runs remain fast.
    if preferred and page_is_valid(preferred, kind):
        return preferred, "fixed"

    candidates={}
    for hub in (ICA_HOME, SITE_MAP):
        try:
            r=get(hub)
            soup=BeautifulSoup(r.text,"html.parser")
            for a in soup.find_all("a", href=True):
                score=candidate_score(a.get_text(" ",strip=True), kind)
                if not score: continue
                href=urljoin(hub,a["href"])
                u=urlparse(href)
                if u.scheme!="https" or u.hostname!=ALLOWED_HOST: continue
                # Prefer pages inside the culture-forum area.
                if "/ica/" in u.path: score+=10
                candidates[href]=max(score,candidates.get(href,0))
        except Exception:
            continue

    for url,_score in sorted(candidates.items(), key=lambda x:x[1], reverse=True):
        if page_is_valid(url, kind):
            return url, "discovered"

    raise RuntimeError(f"{kind}ページの自動探索に失敗しました")

def find_schedule_pdf(schedule_page):
    r = get(schedule_page)
    soup = BeautifulSoup(r.text, "html.parser")
    links=[]
    for a in soup.find_all("a", href=True):
        text=clean(a.get_text(" ", strip=True))
        href=urljoin(schedule_page, a["href"])
        u=urlparse(href)
        if u.scheme=="https" and u.hostname==ALLOWED_HOST and u.path.lower().endswith(".pdf") and ("催事予定表" in text or "イベント" in text):
            links.append((text, href))
    if not links: raise RuntimeError("催事予定表PDFが見つかりません")
    return links[0]

def ocr_pdf(pdf_bytes):
    with tempfile.TemporaryDirectory() as td:
        pdf=Path(td)/"schedule.pdf"; pdf.write_bytes(pdf_bytes)
        prefix=Path(td)/"page"
        subprocess.run(["pdftoppm","-png","-r","240",str(pdf),str(prefix)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
        texts=[]
        for img in sorted(Path(td).glob("page-*.png")):
            p=subprocess.run(["tesseract",str(img),"stdout","-l","jpn+eng","--psm","6"],capture_output=True,text=True,check=True,timeout=90)
            texts.append(p.stdout)
        return "\n".join(texts)

def infer_year_months(label, pdf_url):
    m=re.search(r"令和\s*(\d+)年\s*(\d+)月.*?(\d+)月",label)
    if m: return 2018+int(m.group(1)), [int(m.group(2)),int(m.group(3))]
    m=re.search(r"(20\d{2})(\d{2})-(\d{2})",pdf_url)
    if m: return int(m.group(1)),[int(m.group(2)),int(m.group(3))]
    n=datetime.now(); return n.year,[n.month]

def parse_schedule_ocr(text, year, months):
    events=[]; current_month=months[0]
    for raw in text.splitlines():
        line=clean(raw, 600)
        if not line: continue
        mm=re.search(r"(\d{1,2})\s*月",line)
        if mm and int(mm.group(1)) in months: current_month=int(mm.group(1))
        hall=next((h for h in HALLS if h in line), "")
        if not hall: continue
        dm=re.search(r"(?:^|\s)(\d{1,2})(?:日|\s)",line)
        if not dm: continue
        day=int(dm.group(1))
        try:
            d=datetime(year,current_month,day).strftime("%Y-%m-%d")
        except ValueError:
            continue
        title=re.sub(rf"(^|\s){day}(日)?(\s|$)"," ",line,count=1).replace(hall," ")
        title=re.sub(r"\b\d{1,2}:\d{2}\b.*$","",title)
        title=re.sub(r"\b(無料|関係者|要整理券|会員制)\b.*$","",title)
        title=clean(title)
        if len(title)<4: continue
        tm=re.search(r"(\d{1,2}:\d{2})(?:\s*[〜～~-]\s*(\d{1,2}:\d{2}))?",line)
        time=tm.group(1)+(f"〜{tm.group(2)}" if tm and tm.group(2) else "〜") if tm else ""
        price="無料" if "無料" in line else "関係者" if "関係者" in line else "要整理券" if "要整理券" in line else ""
        events.append({"date":d,"hall":hall,"time":time,"title":title,"price":price,"source":"schedule_ocr"})
    return dedupe(events)

def parse_event_guide(event_guide):
    r=get(event_guide); soup=BeautifulSoup(r.text,"html.parser"); events=[]
    for h in soup.find_all(["h2","h3","h4"]):
        title=clean(h.get_text(" ",strip=True))
        if not title or any(x in title for x in ["開催日","チケット","お問い合わせ","料金","会場"]): continue
        chunk=[]; cur=h
        for _ in range(12):
            cur=cur.find_next()
            if not cur: break
            if cur.name in ["h2","h3","h4"] and cur is not h: break
            t=clean(cur.get_text(" ",strip=True))
            if t: chunk.append(t)
        ctx=" ".join(chunk)
        dm=re.search(r"令和\s*(\d+)年\s*(\d+)月\s*(\d+)日",ctx)
        if dm: year,month,day=2018+int(dm.group(1)),int(dm.group(2)),int(dm.group(3))
        else:
            dm=re.search(r"(20\d{2})年\s*(\d+)月\s*(\d+)日",ctx)
            if not dm: continue
            year,month,day=map(int,dm.groups())
        hall=next((hh for hh in HALLS if hh in ctx),"その他")
        tm=re.search(r"(\d{1,2})時(\d{2})分",ctx)
        time=f"{int(tm.group(1))}:{tm.group(2)}〜" if tm else ""
        cleaned=re.sub(r"^[〖【].*?[〗】]\s*","",title)
        events.append({"date":f"{year:04d}-{month:02d}-{day:02d}","hall":hall,"time":time,"title":cleaned,"price":"","source":"event_guide","official_url":event_guide})
    return dedupe(events)

def main():
    old=dedupe(load_json(EVENTS_FILE, []))
    old_meta=load_json(META_FILE, {})
    run_at=now_iso(); notes=[]
    guide=[]; schedule=[]; schedule_trusted=False; target_yms=set(); source_success=False

    previous_urls=old_meta.get("resolved_urls") or {}
    event_guide_pref=previous_urls.get("events") or DEFAULT_EVENT_GUIDE
    schedule_page_pref=previous_urls.get("schedule") or DEFAULT_SCHEDULE_PAGE
    event_guide=event_guide_pref
    schedule_page=schedule_page_pref

    try:
        event_guide,mode=discover_page("events", event_guide_pref)
        notes.append(f"イベント案内URL: {mode} {event_guide}")
    except Exception as e:
        notes.append(f"イベント案内URL探索失敗: {clean(e,180)}")

    try:
        schedule_page,mode=discover_page("schedule", schedule_page_pref)
        notes.append(f"催事予定表URL: {mode} {schedule_page}")
    except Exception as e:
        notes.append(f"催事予定表URL探索失敗: {clean(e,180)}")

    try:
        guide=parse_event_guide(event_guide)
        if guide:
            source_success=True; notes.append(f"公式イベント案内 {len(guide)}件")
        else: notes.append("公式イベント案内: 構造化イベント0件")
    except Exception as e:
        notes.append(f"公式イベント案内取得失敗: {clean(e,180)}")

    try:
        label,pdf_url=find_schedule_pdf(schedule_page); pdf=get(pdf_url).content
        year,months=infer_year_months(label,pdf_url); target_yms={f"{year:04d}-{m:02d}" for m in months}
        parsed=parse_schedule_ocr(ocr_pdf(pdf),year,months)
        old_target=sum(1 for e in old if ym(e) in target_yms and e.get("hall") in HALLS)
        threshold=max(8, int(old_target*0.60)) if old_target else 8
        if len(parsed)>=threshold:
            schedule=parsed; schedule_trusted=True; source_success=True
            notes.append(f"催事予定表OCR 信頼済み {len(parsed)}件 / しきい値{threshold}")
        else:
            notes.append(f"催事予定表OCR 信頼度不足 {len(parsed)}件 / しきい値{threshold} のため既存月データ維持")
    except Exception as e:
        notes.append(f"催事予定表OCR失敗: {clean(e,180)}")

    base=old
    if schedule_trusted:
        # Official schedule becomes authoritative for its hall/month scope, so removed/cancelled entries can disappear.
        base=[e for e in old if not (ym(e) in target_yms and e.get("hall") in HALLS)]
        base.extend(schedule)
    base.extend(guide)
    merged=dedupe(base)
    if not merged: merged=old

    last_success=run_at if source_success else old_meta.get("last_successful_source_at") or old_meta.get("updated_at") or ""
    status="ok" if source_success else "fallback"
    EVENTS_FILE.write_text(json.dumps(merged,ensure_ascii=False,indent=2),encoding="utf-8")
    jst=timezone(timedelta(hours=9))
    META_FILE.write_text(json.dumps({
        "status":status,
        "updated_at":run_at,
        "updated_at_jst":datetime.now(jst).strftime("%Y/%m/%d %H:%M"),
        "last_successful_source_at":last_success,
        "event_count":len(merged),
        "schedule_replaced":schedule_trusted,
        "notes":notes,
        "resolved_urls":{"events":event_guide,"schedule":schedule_page},
        "sources":[schedule_page,event_guide]
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print("\n".join(notes)); print(f"events: {len(old)} -> {len(merged)}; status={status}")

if __name__=="__main__": main()
