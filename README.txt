文化フォーラム カレンダー Ver.5（自動更新版）

追加機能
・毎日 05:20（日本時間）にGitHub Actionsが公式サイトを確認
・公式イベント案内HTMLを自動解析
・月間ホール催事予定表PDFをOCRで自動解析
・events.json を自動更新
・アプリに最終自動更新日時と件数を表示
・OCR失敗/構造変更時は既存データを壊さず維持
・Google検索、公式ページ、会館電話、Ver.4アイコンは維持

重要
GitHub Actionsのワークフローだけは
.github/workflows/update-events.yml
という場所に置く必要があります。

通常のルートに置くファイル:
index.html
manifest.json
sw.js
icon-180.png
icon-192.png
icon-512.png
events.json
update-meta.json
update_events.py
requirements.txt
README.txt

GitHub Actions用:
.github/workflows/update-events.yml
