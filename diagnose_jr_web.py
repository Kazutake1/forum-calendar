#!/usr/bin/env python3
import re
import requests

URL='https://walking.jr-central.co.jp/course/_javascript/script.js'
UA='forum-calendar-auto-updater/2.0 (+GitHub Actions; jr diagnostics)'
r=requests.get(URL,headers={'User-Agent':UA},timeout=30)
print('FETCH',r.status_code,r.headers.get('Content-Type',''),r.url)
r.raise_for_status()
r.encoding=r.apparent_encoding or r.encoding
text=r.text
print('LEN',len(text))

for needle in ['searchCond:', 'courseList:', 'loadCond', 'loadList', 'X7=', 'V7(', 'course_data']:
    print('\n===',needle,'===')
    start=0
    found=0
    while True:
        i=text.find(needle,start)
        if i<0 or found>=8:
            break
        print(text[max(0,i-1000):min(len(text),i+1800)])
        start=i+len(needle)
        found+=1

print('\n=== LIKELY ENDPOINT LITERALS ===')
for lit in re.findall(r'["\']([^"\']{1,500})["\']',text):
    if any(x in lit.lower() for x in ['.json','.php','api/','course_data','course-list','search-cond','searchcond','courselist']):
        print(lit)
