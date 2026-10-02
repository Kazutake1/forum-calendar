# 文化フォーラム カレンダー PWA

名古屋文理大学文化フォーラム（稲沢市民会館）を中心とした公開イベントを、カレンダー／一覧で確認するPWAです。

現在の画面バージョンは **Ver.9.3.7** です。

## データ構成

イベントデータは役割ごとに分離しています。

- `events.json` — 自動取得したイベント。自動イベントの唯一の正本。
- `manual_events.json` — 人が確認して追加した手動イベント。
- `verified_schedule.json` — 稲沢市の催事予定表を目視照合した確定データ。
- `update-meta.json` — 自動更新日時、件数、取得状況などのメタ情報。
- `event-policy.json` — Python／JavaScript共通の出典優先順位、許可する出典種別、対象フィールド。

画面表示時に自動イベント、手動イベント、照合済み催事予定表を安全に統合します。

## 出典と優先順位

項目単位で確認済みの出典を評価します。

1. イベント公式・主催者公式などの個別公式情報
2. 稲沢市公式情報（催事予定表、会館公式イベント案内など）
3. Xの投稿

URLが存在するだけでは「確認済み」と扱いません。情報が食い違う場合は、安全に統合できる根拠がなければ自動上書きしません。

稲沢市の出典は、`city_schedule`（催事予定表）、`city_event_guide`（会館公式イベント案内）、`city_event_calendar`（市イベントカレンダー）、`city_official`（その他の市公式個別情報）を区別しています。手動登録でこれらを使用する場合は、稲沢市公式ドメインのHTTPS URLと `source_verified=true` の両方が必須です。旧 `event_guide` は既存自動データ互換用で、手動登録には使用しません。

## 自動更新

本番更新の入口は **`update_events_no_ocr.py`** です。

- OCRは無効です。
- `update_events.py` の直接実行は無効です。
- 催事予定表の未照合月をOCRで置き換えません。
- JR東海さわやかウォーキングはJR東海公式Web/APIを使用し、稲沢駅スタートのみ対象にします。
- 既存の `events.json` が欠落・破損・空の場合は安全のため更新を停止します。
- 同日同名でも、別時刻の公演を安易に統合しません。
- 募集案内は通常の開催イベントとして登録しません。

GitHub Actionsの `Update Forum Events` が本番更新を実行します。

## 手動イベント

手動イベントは `manual_events.json` に保存し、`events.json` とは分離しています。

`manage_manual_events.py` と `Monthly Manual Event Housekeeping` により、開催日から90日を過ぎた手動イベントを年別アーカイブへ移動し、重複候補レポートを更新します。

自動更新と月次整理は共通の `forum-calendar-main-write` concurrencyグループを使用し、mainへの同時書き込みを防止します。

## オフライン動作

Service Worker（`sw.js`）が正常取得済みのデータを保存します。

- `events.json`
- `manual_events.json`
- `verified_schedule.json`
- `event-policy.json`

通信障害時は検証済みの保存データへ切り替え、画面に保存済みデータ使用中であることを表示します。不正な空データで正常な保存データを上書きしません。

## テスト

`Calendar Integrity Tests` で以下を継続確認します。

- Pythonのデータ・公演同一性・アーカイブ回帰テスト
- 手動イベント統合のJavaScript回帰テスト
- 照合済み催事予定表の回帰／オフラインテスト
- 自動イベントのオフラインキャッシュテスト
- no-OCRポリシー
- `event-policy.json` の出典ランク契約
- Python／JavaScript／JSONの構文
- 公開イベントJSONの妥当性

## 主なファイル

| ファイル | 役割 |
| --- | --- |
| `index.html` | PWA画面・カレンダー・一覧 |
| `sw.js` | Service Worker／オフライン保存 |
| `manifest.json` | PWAマニフェスト |
| `events.json` | 自動イベント |
| `manual_events.json` | 手動イベント |
| `verified_schedule.json` | 目視照合済み催事予定表 |
| `event-policy.json` | 共通出典ポリシー |
| `update_events.py` | 自動取得・統合の本体モジュール |
| `update_events_no_ocr.py` | 本番更新の唯一のCLI入口 |
| `event_integrity.py` | 公演同一性・出典優先順位・統合ルール |
| `manual-events.js` | 手動イベントのブラウザ統合 |
| `verified-schedule.js` | 照合済み予定表のブラウザ統合 |
| `manage_manual_events.py` | 手動イベントの月次整理 |
| `tests/` | 回帰テスト |
| `.github/workflows/` | 自動更新・月次整理・CI |

## 開発時の基本ルール

- 作業前にGitHubの最新 `main` を取得する。
- 指定外のデータ・UI・機能を変更しない。
- イベント情報の食い違いを推測で解決しない。
- 稲沢市公式サイト／催事予定表を優先し、Xは公式情報にない補足として扱う。
- 変更後は関連回帰テストと差分を確認してから `main` へ反映する。

更新履歴の詳細は [CHANGELOG.md](CHANGELOG.md) を参照してください。
