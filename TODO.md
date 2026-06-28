# ✅ TODO / ロードマップ

## 🎯 目標: このプロジェクトを Android アプリ化する

現状は「単一 HTML + ローカル JS + localStorage」の純クライアントサイド静的アプリ。
Android アプリ化の王道は **①PWA として整える → ②Android ラッパーで包む** の2段階。

### Phase 1: PWA 化（Android 化の前提・単体でも価値あり） ✅ 完了
- [x] `manifest.webmanifest` を追加（name / short_name / start_url / display:standalone / theme_color / background_color / icons）
- [x] アプリアイコンを用意（192px / 512px / maskable）→ `icons/`
- [x] `<meta name="theme-color">` と manifest リンクを `index.html` に追加
- [x] Service Worker を追加し、`index.html` / `anime-data.js`（約4.9MB）/ ポスター画像をキャッシュ → **オフライン起動**対応（`sw.js`）
- [x] iOS 用 `apple-touch-icon` も用意
- [x] installable 要件をブラウザ実機（Chromium）で確認 — SW active / manifest parse / standalone OK
      ※ 正式な Lighthouse スコア計測は未実施（任意）

### Phase 2: Android ラッパー → **案A: TWA を採用**
- [x] TWA 設定一式をリポジトリに用意（`android/twa-manifest.json`・`android/assetlinks.json`）
- [x] ビルド手順書を作成（`docs/android-twa.md`）
- [x] `.gitignore` に Bubblewrap 成果物（鍵・apk・aab・gradle）を追加
- [ ] **【要・手元環境】** `bubblewrap build` で `.aab`/`.apk` 生成（Node + JDK17 + Android SDK 必要）
- [ ] **【要・別リポジトリ】** 署名鍵の SHA-256 を `assetlinks.json` に記入し、
      `methil1.github.io` のルート（`/.well-known/assetlinks.json`）へ配置 → ドメイン検証
- [ ] 実機で localStorage 永続化・オフライン起動・タッチ操作を確認

> ⚠️ 重要: assetlinks はサブパス(`/anime-list/...`)ではなく**オリジン直下**
> (`https://methil1.github.io/.well-known/assetlinks.json`) に置く必要がある。
> ルートはユーザーページ用の別リポジトリ `methil1/methil1.github.io` が配信するため、
> そちらに設置する。詳細は `docs/android-twa.md`。

### Phase 3: 仕上げ
- [ ] アイコン / スプラッシュスクリーン
- [ ] 署名キーストア作成、リリースビルド（`.aab` / `.apk`）
- [ ] 端末実機で localStorage 永続化・ホバー UI のタッチ対応を確認
- [ ] （任意）Google Play 内部テストトラックへ配信

> ~~メモ: ホバー前提の情報カードはタッチだと出しづらい~~
> ✅ 対応済み: タッチ端末では各ポスターに「i」ボタンを表示し、タップで情報カードを
> ピン留め表示（再タップ／外側タップで閉じる）。放送カレンダーの項目もタップ対応。

---

## 🧩 その他の改善候補（難易度低〜中）
- [ ] `/` キーで検索ボックスにフォーカス（数行・低リスク）
- [ ] 放送カレンダーの `.ics` エクスポート
- [ ] 漫画原作の掲載誌（青年誌/少年誌 等）分類 ※AniList に情報が無く別途タグ付けが必要

---

## ✔️ 完了済み（最近）
- [x] 放送カレンダーを別ページ（オーバーレイ）で表示するボタンを追加
- [x] 「先頭へ戻る ↑」フローティングボタンを追加
- [x] PWA 化（manifest / アイコン / Service Worker・オフライン対応）
- [x] Android TWA ビルド設定一式と手順書（`android/`・`docs/android-twa.md`）
- [x] タッチ端末向け情報カード（ポスター「i」ボタン＋カレンダー項目タップ）
