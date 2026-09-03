#!/usr/bin/env python3
from urllib.parse import urljoin
import re
import requests
from bs4 import BeautifulSoup

BASE='https://walking.jr-central.co.jp/'
INDEX=urljoin(BASE,'course/index.html')
UA='forum-calendar-auto-updater/2.0 (+GitHub Actions; jr diagnostics)'

r=requests.get(INDEX,headers={'User-Agent':UA},timeout=30)
r.raise_for_status()
r.encoding=r.apparent_encoding or r.encoding
html=r.text
soup=BeautifulSoup(html,'html.parser')
print('index_status=',r.status_code)
print('encoding=',r.encoding)

print('\nHTML asset/data references:')
patterns=[
    r'[^\"\']+\.js(?:\?[^\"\']*)?', r'[^\"\']+\.json(?:\?[^\"\']*)?',
    r'[^\"\']+\.php(?:\?[^\"\']*)?', r'[^\"\']+/api/[^\"\']*',
    r'[^\"\']*course[^\"\']*'
]
refs=[]
for pat in patterns:
    for x in re.findall(pat,html,re.I):
        x=re.sub(r'&amp;','&',x).strip()
        if len(x)<300 and x not in refs: refs.append(x)
for x in refs[:150]: print('REF',x)

print('\nTags with app/framework/data attributes:')
for tag in soup.find_all(True):
    attrs=' '.join(f'{k}={v}' for k,v in tag.attrs.items())
    text=(tag.get_text(' ',strip=True) or '')[:100]
    blob=f'{tag.name} {attrs} {text}'
    if any(k in blob.lower() for k in ('vue','angular','react','app','course','article','data-','v-')):
        print('TAG',re.sub(r'\s+',' ',blob)[:600])

# Probe likely site asset locations; print content/API references if found.
asset_candidates=[]
for tag in soup.find_all(['script','link']):
    raw=tag.get('src') or tag.get('href')
    if raw:
        u=urljoin(INDEX,raw)
        if u.startswith(BASE) and u not in asset_candidates: asset_candidates.append(u)
# Common bundle names used by the site's templates.
for rel in ['_assets/js/common.js','_assets/js/course.js','_assets/js/index.js','_assets/js/app.js','_assets/_js/common.js','_assets/_js/course.js','_assets/_js/index.js']:
    u=urljoin(BASE,rel)
    if u not in asset_candidates: asset_candidates.append(u)

print('\nAssets:')
for u in asset_candidates[:80]:
    try:
        j=requests.get(u,headers={'User-Agent':UA},timeout=20)
        print('ASSET',j.status_code,j.headers.get('Content-Type',''),u)
        if j.status_code!=200: continue
        text=j.text
        hits=[]
        for pat in [r'[^\n;]{0,220}(?:axios|fetch\(|ajax|\.json|/api/|course/detail|article|station|search)[^\n;]{0,260}',r'https?://[^\"\'\s)]+']:
            for m in re.finditer(pat,text,re.I):
                v=re.sub(r'\s+',' ',m.group(0)).strip()
                if v not in hits: hits.append(v)
        for h in hits[:50]: print(' HIT',h[:700])
    except Exception as e:
        print('ASSETERR',u,type(e).__name__,str(e)[:160])
