# ✅ TODO / ロードマップ

## 🎯 目標: このプロジェクトを Android アプリ化する

現状は「単一 HTML + ローカル JS + localStorage」の純クライアントサイド静的アプリ。
Android アプリ化の王道は **①PWA として整える → ②Android ラッパーで包む** の2段階。

### Phase 1: PWA 化（Android 化の前提・単体でも価値あり）
- [ ] `manifest.webmanifest` を追加（name / short_name / start_url / display:standalone / theme_color / background_color / icons）
- [ ] アプリアイコンを用意（192px / 512px / maskable）
- [ ] `<meta name="theme-color">` と manifest リンクを `index.html` に追加
- [ ] Service Worker を追加し、`index.html` / `anime-data.js`（約4.9MB）/ ポスター画像をキャッシュ → **オフライン起動**対応
- [ ] iOS 用 `apple-touch-icon` も一応用意（任意）
- [ ] Lighthouse の PWA 監査をパスさせる（installable 要件）

### Phase 2: Android ラッパー（どちらか選択）
- [ ] **案A: TWA（Trusted Web Activity）** — Bubblewrap で GitHub Pages の PWA をそのまま包む。
      Play ストア配布が容易。URL バーなしの全画面。Phase 1 の PWA が必須。
      `assetlinks.json`（Digital Asset Links）でドメイン検証が必要。
- [ ] **案B: Capacitor** — Web 資産（index.html / anime-data.js）を APK に同梱。
      完全オフライン・ネイティブ API 利用可。Android Studio でビルド。
      ※ 純静的アプリなら案B が手軽でオフラインも強い。ストア審査も独立。

### Phase 3: 仕上げ
- [ ] アイコン / スプラッシュスクリーン
- [ ] 署名キーストア作成、リリースビルド（`.aab` / `.apk`）
- [ ] 端末実機で localStorage 永続化・ホバー UI のタッチ対応を確認
- [ ] （任意）Google Play 内部テストトラックへ配信

> メモ: ホバー前提の情報カード・放送表はタッチ操作だと出しづらいので、
> Android 化に合わせて「タップで情報カード表示」のフォールバックを検討する。

---

## 🧩 その他の改善候補（難易度低〜中）
- [ ] `/` キーで検索ボックスにフォーカス（数行・低リスク）
- [ ] 放送カレンダーの `.ics` エクスポート
- [ ] 漫画原作の掲載誌（青年誌/少年誌 等）分類 ※AniList に情報が無く別途タグ付けが必要

---

## ✔️ 完了済み（最近）
- [x] 放送カレンダーを別ページ（オーバーレイ）で表示するボタンを追加
- [x] 「先頭へ戻る ↑」フローティングボタンを追加
