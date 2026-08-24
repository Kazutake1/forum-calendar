文化フォーラム カレンダー Ver.9.1

名古屋文理大学文化フォーラム（稲沢市民会館）のイベント情報を、
スマートフォン・iPadから見やすく確認するためのWebアプリです。

【主な機能】
・月間カレンダーでイベントを表示
・大ホール／中ホール／小ホール／その他で絞り込み
・イベント名検索
・日付を選択するとイベント詳細を表示
・イベント名からGoogle検索
・公式イベント案内／ホール催事予定表へのリンク
・会館への電話
・今日の日付と選択中の日付を別の色で表示
・ライトモード／ダークモード／端末設定に合わせる自動モード
・iPhoneのホーム画面に追加してWebアプリとして使用可能
・iPad横向きでは「月間カレンダー＋選択日の詳細」の2カラム表示

【自動更新】
・毎日 05:20（日本時間）にGitHub Actionsが公式情報を確認
・公式イベント案内HTMLを自動解析
・月間ホール催事予定表PDFをOCRで自動解析
・events.jsonを自動更新
・アプリに最終自動更新日時とイベント件数を表示
・公式情報の正常取得が48時間以上ない場合は警告を表示
・取得やOCRに失敗した場合は既存イベントデータを維持
・十分な精度で催事予定表を取得できた場合は、削除・中止された催事にも追従

【公式URLの自動追従】
公式イベント案内またはホール催事予定表のURLが変更された場合、
現在のURLが利用できるか確認したうえで、新しいページを自動探索します。

探索先:
1. 名古屋文理大学文化フォーラム公式トップページ
2. 稲沢市公式サイトマップ

新しいURL候補はページ内容を確認してから採用し、
update-meta.jsonに保存して次回以降も利用します。
アプリ内の公式ページへのリンクも新しいURLへ自動的に変更されます。

【セキュリティ・安定性対策】
・events.json由来の文字列をHTMLエスケープしてXSSを防止
・自動取得先を稲沢市公式HTTPSホストに制限
・取得ファイルのサイズ上限を設定
・Service Workerによる不要なJSONキャッシュの蓄積を防止
・Service Worker更新時に古いキャッシュを削除
・自動取得失敗時に既存データを破壊しないフェイルセーフ設計
・公式情報の最終正常取得日時を記録

【通常のルートに置くファイル】
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

【GitHub Actions用】
.github/workflows/update-events.yml

GitHub Actionsのワークフローファイルは必ず
.github/workflows/update-events.yml
に配置してください。

【更新の流れ】
稲沢市公式情報
↓
GitHub Actions
↓
update_events.py
↓
events.json / update-meta.json
↓
GitHub Pages
↓
文化フォーラム カレンダー

【現在のバージョン】
Ver.9.1
・Ver.9: 公式ページURL自動追従機能を追加
・Ver.9.1: iPad横向き専用2カラムレイアウトを追加
