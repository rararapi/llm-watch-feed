# Apple Developer Program 個人登録ガイド

> 前提: **Windows PC + iPhone/iPad** で登録。種別は **個人（Individual）**。
> 用途: `app/` の Expo アプリを EAS Build → TestFlight で配布するため。

## 要点

- 年額 **99 USD**（円建て・税込、自動更新）。
- 個人登録に **D-U-N-S 番号は不要**。
- App Store の販売者名は**本名**になる（屋号にしたいなら後日「組織」へ変更）。

## 事前準備

- **Apple Account**（2ファクタ認証を有効化。未設定だと進めない）
- **本人名義のクレジットカード**
- **写真付き身分証**（パスポート / 運転免許証 / マイナンバーカード等）
- 氏名・住所は身分証と一致させる（**私書箱不可**）

## 手順

1. PC ブラウザで <https://developer.apple.com/programs/enroll/> → サインイン → 登録開始。
2. 種別で **Individual / Sole Proprietor** を選択（Organization を選ぶと D-U-N-S を要求される）。
3. 法的氏名・住所・電話番号を入力。
4. **本人確認**: iPhone/iPad の Apple Developer アプリに誘導される → 身分証の撮影＋顔認証。
5. ライセンス契約に同意 → **99 USD を決済**（本人名義カード）。
6. 確認メールを待つ（通常〜24時間。来なければ Enrollment ID を添えて [Apple サポート](https://developer.apple.com/contact/)へ）。

## 登録後（本アプリ）

1. [App Store Connect](https://appstoreconnect.apple.com) で App 作成。Bundle ID を `app/app.json` の `ios.bundleIdentifier` と一致させる。
2. EAS でビルド → 提出:
   ```bash
   cd app
   npx eas login
   npx eas build --platform ios --profile preview
   npx eas submit --platform ios --latest
   ```
3. App Store Connect の TestFlight で内部テスターに配布。
   - CI で回すなら `EXPO_TOKEN` をリポジトリ Secrets に設定。

## 出典

- [Program enrollment](https://developer.apple.com/help/account/membership/program-enrollment/)
- [Enrolling with the Apple Developer app](https://developer.apple.com/help/account/membership/enrolling-in-the-app/)
