#!/usr/bin/env python3
from pathlib import Path

path = Path("index.html")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        '@media(prefers-color-scheme:dark){html:not([data-theme]){--bg:#0c1017;--card:#151a22;--text:#f3f4f6;--muted:#98a2b3;--line:#2d3440;--accent:#60a5fa;--large:#3d2422;--large2:#fca5a5;--mid:#1e3049;--mid2:#93c5fd;--small:#173629;--small2:#86efac;--other:#2c2442;--other2:#c4b5fd;--park:#3b2f0b;--park2:#facc15;--jr:#3b1f3f;--jr2:#f0abfc}}\n',
        '',
    ),
    (
        '@media(prefers-color-scheme:dark){html:not([data-theme]) .dotLarge{background:#fca5a5}html:not([data-theme]) .dotMid{background:#93c5fd}html:not([data-theme]) .dotSmall{background:#86efac}html:not([data-theme]) .dotPark{background:#facc15}html:not([data-theme]) .dotJR{background:#f0abfc}html:not([data-theme]) .dotOther{background:#c4b5fd}}\n',
        '',
    ),
    (
        '<button class="themeBtn" id="themeToggle" type="button">自動</button>',
        '<button class="themeBtn" id="themeToggle" type="button">ライト</button>',
    ),
    (
        """const themeBtn=document.querySelector('#themeToggle');
let themeMode='system';
try{themeMode=localStorage.getItem('forum-theme')||'system'}catch(e){}
function applyTheme(mode){
  if(mode==='system')document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme',mode);
  if(themeBtn){
    themeBtn.dataset.mode=mode;
    themeBtn.textContent=mode==='system'?'自動':mode==='light'?'ライト':'ダーク';
  }
}
applyTheme(themeMode);
if(themeBtn)themeBtn.onclick=()=>{
  const order=['system','light','dark'];
  const cur=themeBtn.dataset.mode||'system';
  themeMode=order[(order.indexOf(cur)+1)%order.length];
  try{localStorage.setItem('forum-theme',themeMode)}catch(e){}
  applyTheme(themeMode);
};
""",
        """const themeBtn=document.querySelector('#themeToggle');
let themeMode='light';
try{themeMode=localStorage.getItem('forum-theme')==='dark'?'dark':'light'}catch(e){}
function applyTheme(mode){
  document.documentElement.setAttribute('data-theme',mode);
  if(themeBtn){
    themeBtn.dataset.mode=mode;
    themeBtn.textContent=mode==='light'?'ライト':'ダーク';
  }
}
applyTheme(themeMode);
if(themeBtn)themeBtn.onclick=()=>{
  themeMode=(themeBtn.dataset.mode||'light')==='light'?'dark':'light';
  try{localStorage.setItem('forum-theme',themeMode)}catch(e){}
  applyTheme(themeMode);
};
""",
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Removed automatic theme mode; light/dark only.")
