#!/usr/bin/env python3
from urllib.parse import urljoin
import re
import requests
from bs4 import BeautifulSoup

BASE='https://walking.jr-central.co.jp/'
INDEX=urljoin(BASE,'course/index.html')
UA='forum-calendar-auto-updater/2.0 (+GitHub Actions; jr diagnostics)'

def fetch(url):
    r=requests.get(url,headers={'User-Agent':UA},timeout=30)
    print('FETCH',r.status_code,r.headers.get('Content-Type',''),url)
    if r.status_code!=200: return ''
    if 'text' in r.headers.get('Content-Type','') or 'javascript' in r.headers.get('Content-Type',''):
        r.encoding=r.apparent_encoding or r.encoding
    return r.text

html=fetch(INDEX)
soup=BeautifulSoup(html,'html.parser')
assets=[]
for tag in soup.find_all(['script','link']):
    raw=tag.get('src') or tag.get('href')
    if raw:
        u=urljoin(INDEX,raw)
        if u.startswith(BASE) and u not in assets: assets.append(u)
print('ASSETS',*assets,sep='\n')

# Recursively inspect same-site JS references. The course page uses Vue templates,
# so the data endpoint may be declared in a module loaded by another module.
queue=[u for u in assets if '.js' in u]
seen=set()
for _ in range(40):
    if not queue: break
    u=queue.pop(0)
    if u in seen: continue
    seen.add(u)
    text=fetch(u)
    if not text: continue
    print('\n--- JS',u,'---')
    # Print compact lines around network/data keywords.
    for line in text.splitlines():
        if re.search(r'ajax|fetch\(|axios|\.json|\.php|/api/|course|station|article|endpoint|url\s*:',line,re.I):
            print('HIT',re.sub(r'\s+',' ',line).strip()[:1600])
    # Discover nested same-site JS references, including relative paths.
    for m in re.findall(r'["\']([^"\']+\.js(?:\?[^"\']*)?)["\']',text,re.I):
        nu=urljoin(u,m)
        if nu.startswith(BASE) and nu not in seen and nu not in queue: queue.append(nu)
    # Print URL/path literals likely to be course data endpoints.
    literals=re.findall(r'["\']([^"\']{1,300})["\']',text)
    for lit in literals:
        if re.search(r'course|station|search|\.json|\.php|api',lit,re.I):
            print('LITERAL',lit[:500])

# Also probe the station query form directly. Search-engine rendering shows query
# parameters can produce server/rendered course results, which may be a simpler
# stable source than an undocumented API.
for param in ['station=稲沢','station=%E7%A8%B2%E6%B2%A2','keyword=稲沢','q=稲沢']:
    u=INDEX+'?'+param
    text=fetch(u)
    plain=BeautifulSoup(text,'html.parser').get_text(' ',strip=True)
    print('QUERY',param,'contains_inazawa=',('稲沢' in plain),'detail_links=',re.findall(r'/course/detail/\d+\.html',text)[:20])
