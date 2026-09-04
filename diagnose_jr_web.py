#!/usr/bin/env python3
from urllib.parse import urljoin
import re
import requests
from bs4 import BeautifulSoup

BASE='https://walking.jr-central.co.jp/'
INDEX=urljoin(BASE,'course/index.html')
TARGETS=[
    INDEX,
    urljoin(BASE,'course/_javascript/script.js'),
    urljoin(BASE,'_assets/_javascript/common.js'),
    urljoin(BASE,'_assets/_config/config.js'),
    urljoin(BASE,'sitemap.xml'),
    urljoin(BASE,'robots.txt'),
]
UA='forum-calendar-auto-updater/2.0 (+GitHub Actions; jr diagnostics)'

def fetch(url):
    r=requests.get(url,headers={'User-Agent':UA},timeout=30,allow_redirects=True)
    print('\nFETCH',r.status_code,r.headers.get('Content-Type',''),r.url)
    if r.status_code!=200:
        return ''
    ctype=r.headers.get('Content-Type','').lower()
    if 'text' in ctype or 'javascript' in ctype or 'json' in ctype or 'xml' in ctype:
        r.encoding=r.apparent_encoding or r.encoding
    return r.text

for url in TARGETS:
    text=fetch(url)
    if not text:
        continue
    print('LEN',len(text))
    if url.endswith('script.js') or url.endswith('common.js') or url.endswith('config.js'):
        print('--- NETWORK/DATA HITS ---')
        for line in text.splitlines():
            if re.search(r'ajax|fetch\(|axios|\.json|\.php|/api/|course|station|article|displayData|endpoint|url\s*:',line,re.I):
                print(re.sub(r'\s+',' ',line).strip()[:3000])
        print('--- URL/PATH LITERALS ---')
        for lit in re.findall(r'["\']([^"\']{1,500})["\']',text):
            if re.search(r'course|station|search|\.json|\.php|api|ajax',lit,re.I):
                print(lit[:1000])
    elif 'sitemap' in url or 'robots' in url:
        print(text[:20000])
    else:
        soup=BeautifulSoup(text,'html.parser')
        print('DETAIL LINKS',re.findall(r'/course/detail/\d+\.html',text)[:100])
        for tag in soup.find_all('script',src=True):
            print('SCRIPT',urljoin(url,tag['src']))
