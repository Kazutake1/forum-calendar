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
soup=BeautifulSoup(r.text,'html.parser')
print('index_status=',r.status_code)
print('encoding=',r.encoding)
print('scripts:')
for s in soup.find_all('script'):
    if s.get('src'):
        print('SRC',urljoin(INDEX,s['src']))
    else:
        txt=(s.string or s.get_text() or '').strip()
        if any(k in txt.lower() for k in ('course','article','axios','fetch','ajax','json','api')):
            print('INLINE',re.sub(r'\s+',' ',txt)[:1200])

# Fetch same-origin JS and print only lines that look like course data/API references.
for s in soup.find_all('script',src=True):
    u=urljoin(INDEX,s['src'])
    if not u.startswith(BASE):
        continue
    try:
        j=requests.get(u,headers={'User-Agent':UA},timeout=30)
        j.raise_for_status()
        text=j.text
        hits=[]
        for m in re.finditer(r'[^\n;]{0,180}(?:axios|fetch\(|ajax|\.json|/api/|course/detail|course[^\s\"\']*\.php|article)[^\n;]{0,220}',text,re.I):
            v=re.sub(r'\s+',' ',m.group(0)).strip()
            if v not in hits: hits.append(v)
        if hits:
            print('\nJS',u)
            for h in hits[:40]: print(' ',h[:500])
    except Exception as e:
        print('JSERR',u,type(e).__name__,str(e)[:200])
