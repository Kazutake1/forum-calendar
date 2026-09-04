#!/usr/bin/env python3
import re
import requests
from urllib.parse import quote_from_bytes

BASE='https://walking.jr-central.co.jp'
UA='forum-calendar-auto-updater/2.0 (+GitHub Actions; jr diagnostics)'

def get(path):
    url=BASE+path
    r=requests.get(url,headers={'User-Agent':UA},timeout=30)
    print('\nFETCH',r.status_code,r.headers.get('Content-Type',''),url)
    r.raise_for_status()
    r.encoding=r.apparent_encoding or r.encoding
    print('LEN',len(r.text))
    print(r.text[:5000])
    return r.text

get('/common/_api/search_cond.json')
course_list=get('/common/_api/course_list.json')
print('\nINAZAWA IN COURSE LIST?', '稲沢' in course_list)
for m in re.finditer('稲沢',course_list):
    print(course_list[max(0,m.start()-500):m.start()+1000])

sjis=quote_from_bytes('稲沢'.encode('shift_jis'))
search=get('/common/_api/course_search?stname='+sjis)
print('\nSEARCH PARAM',sjis)
print('INAZAWA IN SEARCH?', '稲沢' in search)
