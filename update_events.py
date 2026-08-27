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
ALLOWED_HOSTS = {"www.city.inazawa.aichi.jp","www.inazawa-kankou.jp","inazawa-kankou.jp"}
CITY_EVENT_LIST = "https://www.city.inazawa.aichi.jp/event2d/event_list.php?ev=2&mon={mon}&page={page}"
TOURISM_EVENTS = "https://www.inazawa-kankou.jp/archives/category/event"
PARK_NAME = "文化の丘公園"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
MAX_DOWNLOAD = 25 * 1024 * 1024
HALLS = {"大ホール", "中ホール", "小ホール"}

VENUE_CORRECTIONS = {
    "食品衛生責任者養成講習会": "小ホール",
}

# Verified event corrections. Keep this list limited to official sources
# that have been manually confirmed.
EVENT_CORRECTIONS = {
    "APF VISIONARY TRYOUT CUP 2026": {
        "title": "APF VISIONARY CUP 2026",
        "official_url": "https://apf.fitness/contest/apf%E5%90%8D%E5%8F%A4%E5%B1%8B%E5%A4%A7%E4%BC%9A/",
    },
    "APF VISIONARY CUP 2026": {
        "title": "APF VISIONARY CUP 2026",
        "official_url": "https://apf.fitness/contest/apf%E5%90%8D%E5%8F%A4%E5%B1%8B%E5%A4%A7%E4%BC%9A/",
    },
}

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def clean(s, limit=240):
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(s or ""))
    return re.sub(r"\s+", " ", s.replace("\u3000", " ")).strip()[:limit]

def get(url):
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
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
    event_fix = EVENT_CORRECTIONS.get(out["title"])
    if event_fix:
        out["title"] = clean(event_fix.get("title") or out["title"], 240)
        e = {**e}
        if event_fix.get("official_url"):
            e["official_url"] = event_fix["official_url"]

    corrected_hall = VENUE_CORRECTIONS.get(out["title"])
    if corrected_hall:
        out["hall"] = corrected_hall
        e = {**e, "venues": [corrected_hall]}
    venues=e.get("venues")
    if isinstance(venues,list):
        out["venues"]=[clean(v,40) for v in venues if clean(v,40)]
    elif out["hall"]:
        out["venues"]=[out["hall"]]
    if e.get("source"): out["source"] = clean(e.get("source"), 32)
    if e.get("official_url"):
        u = clean(e.get("official_url"), 500)
        if urlparse(u).scheme == "https": out["official_url"] = u
    if not valid_date(out["date"]) or len(out["title"]) < 2:
        return None
    return out

def key(e):
    return (e.get("date", ""), clean(e.get("title")))

def dedupe(events):
    out = {}
    for raw in events:
        e = sanitize_event(raw)
        if not e: continue
        k=key(e)
        if k not in out:
            out[k]=e
            continue
        cur=out[k]
        venues=[]
        for v in (cur.get("venues") or [cur.get("hall")]) + (e.get("venues") or [e.get("hall")]):
            if v and v not in venues: venues.append(v)
        cur["venues"]=venues
        if venues: cur["hall"]=venues[0]
        if not cur.get("time") and e.get("time"): cur["time"]=e["time"]
        if not cur.get("price") and e.get("price"): cur["price"]=e["price"]
        if e.get("official_url"): cur["official_url"]=e["official_url"]
        sources=[x for x in [cur.get("source"),e.get("source")] if x]
        if sources: cur["source"]="+".join(dict.fromkeys(sources))
    return sorted(out.values(), key=lambda x:(x["date"], x.get("time", ""), x["title"]))

def ym(e): return e.get("date", "")[:7]


def page_is_valid(url, kind):
    try:
        r=get(url)
        soup=BeautifulSoup(r.content,"html.parser")
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
            soup=BeautifulSoup(r.content,"html.parser")
            for a in soup.find_all("a", href=True):
                score=candidate_score(a.get_text(" ",strip=True), kind)
                if not score: continue
                href=urljoin(hub,a["href"])
                u=urlparse(href)
                if u.scheme!="https" or u.hostname not in ALLOWED_HOSTS: continue
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
    soup = BeautifulSoup(r.content, "html.parser")
    links=[]
    for a in soup.find_all("a", href=True):
        text=clean(a.get_text(" ", strip=True))
        href=urljoin(schedule_page, a["href"])
        u=urlparse(href)
        if u.scheme=="https" and u.hostname in ALLOWED_HOSTS and u.path.lower().endswith(".pdf") and ("催事予定表" in text or "イベント" in text):
            links.append((text, href))
    if not links: raise RuntimeError("催事予定表PDFが見つかりません")
    return links[0]

def ocr_pdf(pdf_bytes):
    """Extract schedule text with a text-layer-first, multi-pass OCR fallback."""
    with tempfile.TemporaryDirectory() as td:
        pdf=Path(td)/"schedule.pdf"; pdf.write_bytes(pdf_bytes)

        candidates=[]

        # Text layer is normally more accurate than OCR and preserves table spacing.
        try:
            p=subprocess.run(
                ["pdftotext","-layout",str(pdf),"-"],
                capture_output=True,text=True,check=True,timeout=60
            )
            t=p.stdout or ""
            if len(clean(t, 20000)) >= 80:
                candidates.append(t)
        except Exception:
            pass

        prefix=Path(td)/"page"
        subprocess.run(
            ["pdftoppm","-png","-r","300",str(pdf),str(prefix)],
            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120
        )

        for psm in ("4","6"):
            pages=[]
            try:
                for img in sorted(Path(td).glob("page-*.png")):
                    p=subprocess.run(
                        ["tesseract",str(img),"stdout","-l","jpn+eng","--psm",psm],
                        capture_output=True,text=True,check=True,timeout=120
                    )
                    pages.append(p.stdout)
                candidates.append("\n".join(pages))
            except Exception:
                continue

        if not candidates:
            raise RuntimeError("PDFから文字を抽出できません")

        # Prefer output containing more recognizable schedule structure.
        def score(t):
            # Prefer text preserving complete table rows:
            # day + weekday + hall marker (大/中/小) on the same line.
            row_hits=len(re.findall(
                r"(?m)^\s*\d{1,2}\s*日?\s+(?:月|火|水|木|金|土|日)(?:[・･]\s*祝)?\s+(?:[大小中])(?:\s|$)",
                t
            ))
            hall_hits=sum(t.count(h) for h in HALLS)
            date_hits=len(re.findall(r"(?:^|\s)\d{1,2}\s*日(?:\s|$)",t,re.M))
            return row_hits*1000 + hall_hits*100 + date_hits*10 + min(len(t),10000)/1000
        return max(candidates,key=score)


def debug_schedule_text(text, max_lines=180):
    """Print extracted schedule text safely for one diagnostic run."""
    print("=== SCHEDULE RAW DEBUG START ===")
    lines=str(text or "").splitlines()
    shown=0
    for i,raw in enumerate(lines, start=1):
        # Keep column spacing visible in logs.
        line=raw.rstrip("\n\r")
        if not line.strip():
            continue
        print(f"RAW {i:03d}: {line[:500]}")
        shown += 1
        if shown >= max_lines:
            print(f"... truncated after {max_lines} non-empty lines ...")
            break
    print("=== SCHEDULE RAW DEBUG END ===")

def infer_year_months(label, pdf_url):
    m=re.search(r"令和\s*(\d+)年\s*(\d+)月.*?(\d+)月",label)
    if m: return 2018+int(m.group(1)), [int(m.group(2)),int(m.group(3))]
    m=re.search(r"(20\d{2})(\d{2})-(\d{2})",pdf_url)
    if m: return int(m.group(1)),[int(m.group(2)),int(m.group(3))]
    n=datetime.now(); return n.year,[n.month]

def normalize_schedule_ocr(s):
    """Normalize text while preserving the PDF's column spacing."""
    s=str(s or "").replace("\u3000"," ")
    s=re.sub(r"大\s*ホ\s*ー?\s*ル", "大ホール", s)
    s=re.sub(r"中\s*ホ\s*ー?\s*ル", "中ホール", s)
    s=re.sub(r"小\s*ホ\s*ー?\s*ル", "小ホール", s)
    s=s.replace("～","〜").replace("−","-").replace("―","-")
    return s

def _weekday_field(s):
    return bool(re.fullmatch(r"(?:月|火|水|木|金|土|日)(?:[・･]\s*祝)?", clean(s,20)))

def _hall_time_field(s):
    s=clean(s,100)
    m=re.match(r"^([大小中])(?:\s+|$)(.*)$",s)
    if not m:
        return None
    return {"大":"大ホール","中":"中ホール","小":"小ホール"}[m.group(1)], m.group(2).strip()

def _extract_time(s):
    m=re.search(r"(\d{1,2}:\d{2})(?:\s*[〜~-]\s*(\d{1,2}:\d{2}))?",s or "")
    if not m:
        if re.search(r"\b未定\b", s or ""):
            return ""
        return ""
    return m.group(1)+(f"〜{m.group(2)}" if m.group(2) else "〜")

def _price_from_text(s):
    s=s or ""
    if "無料" in s: return "無料"
    if "関係者" in s: return "関係者"
    if "要事前申込" in s or "要事前申請" in s: return "要事前申込"
    if "要整理券" in s: return "要整理券"
    # Preserve simple highest-price strings when clearly present.
    m=re.search(r"([0-9,]+円(?:ほか)?)",s)
    return m.group(1) if m else ""

def _plausible_title(s):
    t=clean(s,240).strip("|｜ +-・･")
    if len(t)<4:
        return ""
    compact=re.sub(r"\s","",t)
    if compact in {"催事名","催事予定表","入場方法","開演時間","場所・上演時間","主催者・問合先"}:
        return ""
    if re.fullmatch(r"[年月火水木金土日祝大小中0-9:+〜~\\-]+", compact):
        return ""
    return t

def _parse_layout_row(raw, year, month):
    """Parse one pdftotext -layout row using the PDF's visible columns."""
    # Keep multiple spaces; they represent column boundaries.
    line=raw.rstrip()
    if not line.strip():
        return None

    # Split only on 2+ spaces so spaces inside event names survive.
    cols=[c.strip() for c in re.split(r"\s{2,}",line.strip()) if c.strip()]
    if len(cols)<3:
        return None

    # Find date and weekday in the first few columns.
    day=None; day_i=None; weekday_i=None
    for i,c in enumerate(cols[:4]):
        m=re.fullmatch(r"(\d{1,2})\s*日?",c)
        if m:
            day=int(m.group(1)); day_i=i
            break
        m=re.match(r"^(\d{1,2})\s*日?\s+(月|火|水|木|金|土|日)(?:[・･]\s*祝)?$",c)
        if m:
            day=int(m.group(1)); day_i=i; weekday_i=i
            break
    if day is None or not 1<=day<=31:
        return None

    if weekday_i is None:
        for i in range(day_i+1,min(day_i+3,len(cols))):
            if _weekday_field(cols[i]):
                weekday_i=i
                break
    if weekday_i is None:
        return None

    # Hall+time is normally the next column after weekday.
    hall=None; hall_i=None; hall_tail=""
    for i in range(weekday_i+1,min(weekday_i+4,len(cols))):
        ht=_hall_time_field(cols[i])
        if ht:
            hall,hall_tail=ht; hall_i=i
            break
    if hall_i is None:
        return None

    # The event title is the next real column.
    title=""
    title_i=None
    for i in range(hall_i+1,len(cols)):
        cand=_plausible_title(cols[i])
        if cand and not re.fullmatch(r"(無料|関係者|要整理券|要事前申込|要事前申請|見学可|[0-9,]+円(?:ほか)?)",cand):
            title=cand; title_i=i
            break
    if not title:
        return None

    try:
        date=datetime(year,month,day).strftime("%Y-%m-%d")
    except ValueError:
        return None

    rest=" ".join(cols[title_i+1:]) if title_i is not None else ""
    return {
        "date":date,
        "hall":hall,
        "time":_extract_time(hall_tail),
        "title":title,
        "price":_price_from_text(rest),
        "source":"schedule_ocr",
    }

def _parse_compact_row(raw, year, month):
    """Fallback for OCR output where table columns collapse to single spaces."""
    line=clean(raw,1000)
    if not line:
        return None

    # Require date + weekday + row-local hall marker in this order.
    m=re.match(
        r"^\s*(\d{1,2})\s*日?\s+(月|火|水|木|金|土|日)(?:[・･]\s*祝)?\s+([大小中])\s+(.*)$",
        line
    )
    if not m:
        return None
    day=int(m.group(1))
    if not 1<=day<=31:
        return None
    hall={"大":"大ホール","中":"中ホール","小":"小ホール"}[m.group(3)]
    tail=m.group(4).strip()

    # Remove leading time/unset marker from the venue/time column.
    tm=re.match(r"^(未定|\d{1,2}:\d{2}(?:\s*[〜~-]\s*\d{1,2}:\d{2})?)\s+(.*)$",tail)
    if tm:
        time=_extract_time(tm.group(1))
        body=tm.group(2)
    else:
        time=""
        body=tail

    # Admission/organizer columns are usually separated by 2+ spaces in OCR too.
    pieces=[p.strip() for p in re.split(r"\s{2,}",body) if p.strip()]
    title=_plausible_title(pieces[0] if pieces else body)
    if not title:
        return None

    try:
        date=datetime(year,month,day).strftime("%Y-%m-%d")
    except ValueError:
        return None
    rest=" ".join(pieces[1:])
    return {
        "date":date,"hall":hall,"time":time,"title":title,
        "price":_price_from_text(rest),"source":"schedule_ocr"
    }

def parse_schedule_ocr(text, year, months):
    """Hybrid table parser.

    Strategy:
    1. Preserve pdftotext -layout columns and parse by column boundaries.
    2. Fall back to a strict OCR row parser.
    3. Never infer the date from arbitrary numbers inside an event name/time.
    4. Never inherit a hall from the previous row.
    """
    events=[]
    current_month=months[0]
    raw_text=normalize_schedule_ocr(text)

    for raw in raw_text.splitlines():
        # Month headers in this PDF are explicit ("8月", "9月").
        mm=re.search(r"(?<!\d)(\d{1,2})\s*月",raw)
        if mm and int(mm.group(1)) in months:
            current_month=int(mm.group(1))

        e=_parse_layout_row(raw,year,current_month)
        if e is None:
            e=_parse_compact_row(raw,year,current_month)
        if e:
            events.append(e)

    return dedupe(events)

def parse_event_guide(event_guide):
    r=get(event_guide); soup=BeautifulSoup(r.content,"html.parser"); events=[]
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


def month_add(dt, n):
    y=dt.year+(dt.month-1+n)//12
    m=(dt.month-1+n)%12+1
    return y,m

def expand_dates_from_text(text):
    """Extract event dates only from explicitly date-labeled context."""
    today=datetime.now().date()
    candidates=[]
    fragments=re.split(r"[。\n\r]|(?=開催日時)|(?=開催日)|(?=日時)|(?=とき)", text)
    labeled=[f for f in fragments if re.search(r"(開催日時|開催日|日時|とき)",f)]
    for frag in labeled[:12]:
        frag=re.split(r"(更新日|掲載日|申込|申し込み|募集|締切|受付期間|販売期間)",frag,maxsplit=1)[0]
        full=[]
        for y,m,d in re.findall(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日",frag):
            try: full.append(datetime(int(y),int(m),int(d)).date())
            except ValueError: pass
        for ry,m,d in re.findall(r"令和\s*(\d+)年\s*(\d{1,2})月\s*(\d{1,2})日",frag):
            try: full.append(datetime(2018+int(ry),int(m),int(d)).date())
            except ValueError: pass
        if len(full)>=2:
            a,b=full[0],full[1]
            if 0 <= (b-a).days <= 14:
                candidates.extend(a+timedelta(days=i) for i in range((b-a).days+1))
            else:
                candidates.extend(full)
        else:
            candidates.extend(full)
        base=re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日",frag)
        if base:
            y,m=int(base.group(1)),int(base.group(2))
            for d in re.findall(r"(?:・|、|,|及び|と)\s*(\d{1,2})日",frag[base.end():]):
                try: candidates.append(datetime(y,m,int(d)).date())
                except ValueError: pass
    return sorted(set(d for d in candidates if today-timedelta(days=45)<=d<=today+timedelta(days=420)))[:20]

def parse_time_from_text(text):
    m=re.search(r"(午前|午後)?\s*(\d{1,2})時(?:\s*(\d{1,2})分)?\s*[〜～\-]\s*(午前|午後)?\s*(\d{1,2})時(?:\s*(\d{1,2})分)?",text)
    if not m: return ""
    def cv(ap,h,mi):
        h=int(h); mi=int(mi or 0)
        if ap=="午後" and h<12: h+=12
        if ap=="午前" and h==12: h=0
        return f"{h:02d}:{mi:02d}"
    return f"{cv(m.group(1),m.group(2),m.group(3))}〜{cv(m.group(4),m.group(5),m.group(6))}"

def park_event_from_page(url, source):
    r=get(url); soup=BeautifulSoup(r.content,"html.parser")
    text=clean(soup.get_text(" ",strip=True),12000)
    if PARK_NAME not in text: return []
    h1=soup.find("h1")
    title=clean(h1.get_text(" ",strip=True) if h1 else (soup.title.get_text(" ",strip=True) if soup.title else ""),240)
    if not title or title in {"イベントカレンダー","イベント"}: return []
    dates=expand_dates_from_text(text)
    today=datetime.now().date()
    dates=[d for d in dates if today-timedelta(days=45) <= d <= today+timedelta(days=420)]
    time=parse_time_from_text(text)
    price=""
    if "入場無料" in text or "入場料：なし" in text or "入場料:なし" in text: price="無料"
    return [{"date":d.strftime("%Y-%m-%d"),"hall":PARK_NAME,"venues":[PARK_NAME],"time":time,
             "title":title,"price":price,"source":source,"official_url":url} for d in dates]

def parse_city_park_events():
    today=datetime.now().date()
    seen=set(); events=[]; pages_ok=0
    for offset in range(0,13):
        y,m=month_add(datetime(today.year,today.month,1),offset)
        mon=f"{y:04d}{m:02d}"
        for page in range(1,6):
            url=CITY_EVENT_LIST.format(mon=mon,page=page)
            try:
                r=get(url); pages_ok+=1
            except Exception:
                break
            soup=BeautifulSoup(r.content,"html.parser")
            links=[]
            for a in soup.find_all("a",href=True):
                href=urljoin(url,a["href"])
                u=urlparse(href)
                if u.hostname!="www.city.inazawa.aichi.jp": continue
                if not re.fullmatch(r"/0{0,6}\d+\.html",u.path): continue
                if href not in seen:
                    seen.add(href); links.append(href)
            if not links and page>1: break
            for href in links:
                try: events.extend(park_event_from_page(href,"city_event_calendar"))
                except Exception: continue
            # Usually 10/page; a short content page means last page.
            if len(links)<8: break
    return dedupe(events), pages_ok

def parse_tourism_park_events():
    # Supplementary only: the tourism site may reject GitHub's overseas runner IP.
    seen=set(); events=[]; pages_ok=0
    for page in range(1,4):
        url=TOURISM_EVENTS if page==1 else f"{TOURISM_EVENTS}/page/{page}"
        try:
            r=get(url); pages_ok+=1
        except Exception:
            break
        soup=BeautifulSoup(r.content,"html.parser")
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"]); u=urlparse(href)
            if u.hostname not in {"www.inazawa-kankou.jp","inazawa-kankou.jp"}: continue
            if not re.fullmatch(r"/archives/\d+/?",u.path): continue
            if href in seen: continue
            seen.add(href)
            try: events.extend(park_event_from_page(href,"tourism"))
            except Exception: continue
    return dedupe(events), pages_ok


def main():
    old=dedupe(load_json(EVENTS_FILE, []))
    old_meta=load_json(META_FILE, {})
    run_at=now_iso(); notes=[]
    guide=[]; schedule=[]; park=[]; schedule_trusted=False; target_yms=set(); source_success=False; forum_success=False; park_success=False; city_park_authoritative=False

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
            source_success=True; forum_success=True; notes.append(f"公式イベント案内 {len(guide)}件")
        else: notes.append("公式イベント案内: 構造化イベント0件")
    except Exception as e:
        notes.append(f"公式イベント案内取得失敗: {clean(e,180)}")

    try:
        label,pdf_url=find_schedule_pdf(schedule_page); pdf=get(pdf_url).content
        year,months=infer_year_months(label,pdf_url); target_yms={f"{year:04d}-{m:02d}" for m in months}
        extracted_text=ocr_pdf(pdf)
        debug_schedule_text(extracted_text)
        parsed=parse_schedule_ocr(extracted_text,year,months)
        old_target=sum(1 for e in old if ym(e) in target_yms and e.get("hall") in HALLS)
        threshold=max(8, int(old_target*0.60)) if old_target else 8
        hall_kinds={e.get("hall") for e in parsed if e.get("hall") in HALLS}
        junk=sum(1 for e in parsed if re.fullmatch(r"[|｜ +大小中月火水木金土日祝0-9:〜~-]+", clean(e.get("title",""))))
        quality_ok = len(parsed)>=threshold and len(hall_kinds)>=2 and junk==0
        if quality_ok:
            schedule=parsed; schedule_trusted=True; source_success=True; forum_success=True
            notes.append(f"催事予定表OCR[診断版] 信頼済み {len(parsed)}件 / しきい値{threshold} / 会場{len(hall_kinds)}種")
        else:
            notes.append(f"催事予定表OCR[診断版] 信頼度不足 {len(parsed)}件 / しきい値{threshold} / 会場{len(hall_kinds)}種 / junk{junk} のため既存月データ維持")
    except Exception as e:
        notes.append(f"催事予定表OCR失敗: {clean(e,180)}")

    # Culture-no-Oka Park events: city official calendar is primary, tourism association is supplementary.
    try:
        city_park,checked=parse_city_park_events()
        city_park_authoritative=checked>0
        park.extend(city_park)
        park_success = park_success or checked>0
        source_success = source_success or checked>0
        notes.append(f"文化の丘公園（市公式） {len(city_park)}件 / カレンダー{checked}ページ確認")
    except Exception as e:
        notes.append(f"文化の丘公園（市公式）取得失敗: {clean(e,180)}")
    try:
        tourism_park,checked=parse_tourism_park_events()
        park.extend(tourism_park)
        if checked>0: park_success=True; source_success=True
        notes.append(f"文化の丘公園（観光協会） {len(tourism_park)}件 / {checked}ページ確認")
    except Exception as e:
        notes.append(f"文化の丘公園（観光協会）取得失敗: {clean(e,180)}")
    park=dedupe(park)

    base=old
    if schedule_trusted:
        base=[e for e in base if not (ym(e) in target_yms and e.get("hall") in HALLS)]
        base.extend(schedule)

    if city_park_authoritative:
        today=datetime.now().date()
        horizon_end=today+timedelta(days=400)
        def keep_old_park(e):
            venues=e.get("venues") or [e.get("hall")]
            if PARK_NAME not in venues: return True
            try: d=datetime.strptime(e.get("date",""),"%Y-%m-%d").date()
            except Exception: return True
            if not (today <= d <= horizon_end): return True
            src=e.get("source","")
            return not any(s in src for s in ("city_event_calendar","tourism"))
        base=[e for e in base if keep_old_park(e)]

    base.extend(guide)
    base.extend(park)
    merged=dedupe(base)
    if not merged: merged=old

    last_success=run_at if source_success else old_meta.get("last_successful_source_at") or old_meta.get("updated_at") or ""
    last_forum=run_at if forum_success else old_meta.get("last_successful_forum_at") or old_meta.get("last_successful_source_at") or old_meta.get("updated_at") or ""
    last_park=run_at if park_success else old_meta.get("last_successful_park_at") or ""
    status="ok" if forum_success else ("partial" if source_success else "fallback")
    EVENTS_FILE.write_text(json.dumps(merged,ensure_ascii=False,indent=2),encoding="utf-8")
    jst=timezone(timedelta(hours=9))
    META_FILE.write_text(json.dumps({
        "status":status,
        "updated_at":run_at,
        "updated_at_jst":datetime.now(jst).strftime("%Y/%m/%d %H:%M"),
        "last_successful_source_at":last_success,
        "last_successful_forum_at":last_forum,
        "last_successful_park_at":last_park,
        "event_count":len(merged),
        "schedule_replaced":schedule_trusted,
        "notes":notes,
        "resolved_urls":{"events":event_guide,"schedule":schedule_page},
        "sources":[schedule_page,event_guide,"https://www.city.inazawa.aichi.jp/event2d/event_list.php?ev=2","https://www.inazawa-kankou.jp/archives/category/event"]
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print("\n".join(notes)); print(f"events: {len(old)} -> {len(merged)}; status={status}")

if __name__=="__main__": main()
