# 更新履歴

## Ver.9.3.2 — 手動イベントの表示基盤
- 自動更新データ `events.json` はそのまま維持し、手動登録は別ファイル `manual_events.json` に保存する。
- 手動イベントを表示時に統合し、日時・名称・会場を用いて重複を照合する。名称・日時の不一致は明示的な `match` による確認を必要とする。
- 出典URL付きで稲沢市公式サイト確認済みの情報を優先する。出典不明の自動イベントは既存情報を保持し、Xの内容で無断上書きしない。
- 手動登録データの取得・検証に失敗した場合は画面に警告を表示する。
- 取り込み画面は設けず、イベント一覧は登録内容を確認した後にGitHub連携で更新する。

### 手動イベントの必須フィールド
`id`, `date` (YYYY-MM-DD), `title`, `hall`, `source_type` (`x` / `city_official` / `other`), `source_url` (HTTPS URL)。任意: `time`, `price`, `venues`, `source_verified`, `match` (`date`, `title`, 必要なら `hall`, `time`)。`source_type=city_official` は稲沢市公式ドメインのURLと `source_verified=true` の両方が必要。

**注意:** 曖昧な重複候補や情報の食い違いは、登録前に人が確認する。公式サイトへの一般的なリンクがあるだけでは個別イベントを「公式確認済み」と扱わない。
