# Android アプリ化ガイド（TWA / Bubblewrap）

PWA をそのまま Android アプリ（TWA = Trusted Web Activity）として包み、`.aab` / `.apk` を生成する手順。
このリポジトリには設定ファイル（`android/twa-manifest.json`・`android/assetlinks.json`）を同梱済み。
**実ビルドは Android SDK / JDK が必要なため、手元のマシン（または CI）で実施する。**

---

## 前提

- 公開 PWA: https://methil1.github.io/anime-list/ （Phase 1 で対応済み・installable）
- パッケージ ID: `io.github.methil1.animelist`
- **オリジン**: `methil1.github.io`（← assetlinks の置き場所に関わる重要点。後述）

## 必要なもの

| ツール | 用途 |
|---|---|
| Node.js 18+ | Bubblewrap CLI |
| JDK 17 | Android ビルド（Bubblewrap が JDK/SDK を自動取得も可） |
| Android SDK | `bubblewrap` が `~/.bubblewrap` に自動DL可（手動不要なことが多い） |

```bash
npm i -g @bubblewrap/cli
```

---

## 1. プロジェクト初期化 〜 ビルド

同梱の `android/twa-manifest.json` をそのまま使えるので `init` を省略してビルドできる：

```bash
cd android
# 初回のみ JDK/SDK のセットアップに同意
bubblewrap build
```

- 初回は署名キーストア（`android.keystore`, alias `android`）の作成を促される。
  パスワードは安全に保管（紛失するとアプリ更新を公開できなくなる）。
- 成功すると `app-release-signed.apk` と `app-release-bundle.aab` が生成される。

> もし `twa-manifest.json` を作り直したい場合:
> `bubblewrap init --manifest https://methil1.github.io/anime-list/manifest.webmanifest`

## 2. 署名鍵の SHA-256 フィンガープリントを取得

```bash
bubblewrap fingerprint list
# または
keytool -list -v -keystore android.keystore -alias android | grep SHA256
```

`AB:CD:...:EF` 形式の SHA-256 が出る。

## 3. ⚠️ assetlinks.json をオリジンのルートに配置（最重要）

TWA の URL バー非表示（全画面化）には **Digital Asset Links 検証**が必須。Android は必ず
**オリジンのルート**を見に行く：

```
https://methil1.github.io/.well-known/assetlinks.json
```

このアプリは `…/anime-list/` というサブパスにあるが、**検証ファイルはサブパスではなく
ドメイン直下**でなければならない。`methil1.github.io/anime-list/.well-known/...` では検証されない。

### このリポジトリでは serve できない点に注意

`methil1.github.io` のルートは**別リポジトリ（ユーザーページ `methil1/methil1.github.io`）**が配信する。
そのため:

1. `methil1/methil1.github.io` リポジトリ（無ければ作成）に
   `.well-known/assetlinks.json` を置く。
2. 中身は本リポジトリの `android/assetlinks.json` をコピーし、
   `REPLACE_WITH_YOUR_SIGNING_KEY_SHA256_FINGERPRINT` を手順2のフィンガープリントに置換。
3. `https://methil1.github.io/.well-known/assetlinks.json` で取得できることを確認。

> 検証ツール: https://developers.google.com/digital-asset-links/tools/generator
> 反映確認: `curl -s https://methil1.github.io/.well-known/assetlinks.json`

（assetlinks が無くてもアプリは動くが、上部に Chrome の URL バーが残る。全画面ブランド化には必須。）

## 4. 端末で確認

```bash
adb install android/app-release-signed.apk
```

- localStorage（視聴状態）が保持されるか
- ホバー前提の情報カード／放送表がタッチで使えるか（→ TODO: タップ表示フォールバック）
- オフライン起動（機内モードで起動 → SW キャッシュから表示）

## 5. Google Play へ（任意）

- `app-release-bundle.aab` を Play Console の内部テストトラックにアップロード
- Play App Signing を使う場合、**Play が再署名する鍵の SHA-256** も assetlinks に追加する
  （Play Console → アプリの整合性 → アップロード鍵証明書 と App signing 鍵証明書の両方）

---

## バージョン更新時

`android/twa-manifest.json` の `appVersionCode`（整数を +1）と `appVersionName` を上げて
再度 `bubblewrap build`。Web 側（PWA）の更新は自動反映されるので、TWA の再ビルドは
アイコン・名前・スプラッシュ等のネイティブ要素を変えたときのみ必要。
