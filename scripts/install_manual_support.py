#!/usr/bin/env python3
"""Idempotently attach the separate manual-events overlay to the existing PWA."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / 'index.html'
SW = ROOT / 'sw.js'

def change_once(text, old, new, label):
    if new in text:
        return text
    if text.count(old) != 1:
        raise RuntimeError(f'{label}: expected exactly one original anchor; found {text.count(old)}')
    return text.replace(old, new, 1)

def main():
    index = INDEX.read_text(encoding='utf-8')
    sw = SW.read_text(encoding='utf-8')
    assert (ROOT / 'manual-events.js').is_file()
    assert (ROOT / 'manual_events.json').is_file()

    index = change_once(index, 'loadAutoData();', '''loadAutoData().then(() => {
  const script = document.createElement('script');
  script.src = './manual-events.js?v=932';
  script.onload = () => window.loadManualForumEvents();
  script.onerror = () => {
    const status = document.querySelector('#autoUpdated');
    if (status) {
      status.classList.add('stale');
      status.textContent += ' ・ 手動登録機能の読み込みに失敗';
    }
  };
  document.body.appendChild(script);
});''', 'async manual integration')
    index = change_once(index, "navigator.serviceWorker.register('./sw.js?v=931'", "navigator.serviceWorker.register('./sw.js?v=932'", 'service worker version')
    if 'Ver.9.3.2' not in index:
        if index.count('Ver.9.3.1') != 2:
            raise RuntimeError('PWA version: unexpected current version')
        index = index.replace('Ver.9.3.1', 'Ver.9.3.2')
    sw = change_once(sw, "const CACHE='forum-calendar-v9-2-3';", "const CACHE='forum-calendar-v9-3-2';", 'cache version')
    sw = change_once(sw, "'./icon-512.png'];", "'./icon-512.png','./manual-events.js'];", 'static cache')
    sw = change_once(sw, "'/events.json','/update-meta.json'];", "'/events.json','/update-meta.json','/manual_events.json'];", 'network-only manual data')
    # Write only after all anchor checks pass, so a mismatch does not partially install.
    INDEX.write_text(index, encoding='utf-8')
    SW.write_text(sw, encoding='utf-8')
    print('Installed manual-data overlay (or already current).')

if __name__ == '__main__':
    main()
