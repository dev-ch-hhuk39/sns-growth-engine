# Emergency Rollback 手順

誤投稿・誤実行・APIキー漏洩などの緊急時の対応手順。

## 1. .env 安全フラグを全部 false へ戻す

**最優先で実行する:**

```bash
python -c "
import re, pathlib
env_path = pathlib.Path('/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2/.env')
if not env_path.exists():
    print('ERROR: .env が見つかりません')
    exit(1)
env = env_path.read_text()
flags = [
    ('PUBLISH_ENABLED', 'false'),
    ('ALLOW_REAL_X_POST', 'false'),
    ('ALLOW_REAL_THREADS_POST', 'false'),
    ('ALLOW_TRANSCRIPTION_API', 'false'),
    ('ALLOW_CLOUDINARY_UPLOAD', 'false'),
]
for flag, val in flags:
    env = re.sub(rf'{flag}=true', f'{flag}={val}', env, flags=re.IGNORECASE)
env_path.write_text(env)
print('全安全フラグを false に戻しました')
"
```

確認:
```bash
python scripts/print_env_status.py
```

---

## 2. queue.status を READY から WAITING_REVIEW へ戻す

誤投稿を防ぐために queue を停止:

```bash
# 対象 queue_id が明確な場合
python scripts/review_queue.py \
  --queue-id {queue_id} \
  --set-status WAITING_REVIEW \
  --account-id night_scout

# 全 READY を停止する場合（Sheetsで手動変更推奨）
python scripts/review_queue.py \
  --account-id night_scout \
  --status READY \
  --dry-run   # 対象を確認してから実行
```

---

## 3. posted_results 確認

誤投稿が発生した場合:

```bash
python scripts/check_pipeline_integrity.py --account-id night_scout
```

Sheets で `posted_results` タブを直接確認し、誤投稿の `result_id` をメモする。

X の場合は以下で投稿を削除（APIまたはWebから）:
- Web: https://x.com/ にログインして投稿を削除
- API: tweepy で `delete_tweet(id)` を実行

---

## 4. GitHub Actions 無効化

Actions タブから workflow を無効化:
1. https://github.com/dev-ch-hhuk39/sns-growth-engine/actions
2. "v2 Dry-Run Safety Check" workflow を選択
3. "..." → "Disable workflow"

または workflow ファイルを削除してコミット:
```bash
# 注意: 削除前に確認
git rm .github/workflows/v2-dry-run-check.yml
git commit -m "emergency: disable GitHub Actions workflow"
git push origin main
```

---

## 5. Cloudinary テストファイル削除

smoke test でアップロードしたファイルを削除:

```bash
# 認証情報が有効な場合
python -c "
import cloudinary, cloudinary.uploader, os
from dotenv import load_dotenv
load_dotenv()
cloudinary.config(
  cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
  api_key=os.environ.get('CLOUDINARY_API_KEY'),
  api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
)
# smoke test フォルダの全ファイル削除
result = cloudinary.api.delete_resources_by_prefix('sns_growth_engine/smoke_test/')
print('削除結果:', result)
"
```

または Cloudinary Dashboard → Media Library → smoke_test フォルダを削除。

---

## 6. APIキー漏洩時のローテーション

### X API キー漏洩

1. https://developer.twitter.com/en/portal/projects にアクセス
2. 漏洩したアプリの "Regenerate" で新しいキーを生成
3. `.env` を更新
4. 旧キーが含まれる git history がある場合は GitHub に報告

### Cloudflare API トークン漏洩

1. https://dash.cloudflare.com/profile/api-tokens にアクセス
2. 漏洩したトークンを削除
3. 新しいトークンを作成
4. `.env` を更新

### Cloudinary API キー漏洩

1. https://cloudinary.com/console にアクセス
2. Security → "Invalidate all signing credentials"
3. または API Key を再生成
4. `.env` を更新

### GCP サービスアカウントキー漏洩

1. https://console.cloud.google.com/iam-admin/serviceaccounts にアクセス
2. 対象SAのキーを削除
3. 新しいキーを生成・ダウンロード
4. Base64エンコード → `.env` の `SA_JSON_BASE64` を更新

---

## 緊急連絡先メモ

- GitHub リポジトリ: https://github.com/dev-ch-hhuk39/sns-growth-engine
- Cloudflare Dashboard: https://dash.cloudflare.com
- Cloudinary Console: https://cloudinary.com/console
- X Developer Portal: https://developer.twitter.com/en/portal

---

## ロールバック後の確認チェックリスト

- [ ] 全安全フラグが false であること
- [ ] `.env` にシークレット値が正しく設定されていること
- [ ] queue.status=POSTED が意図しない件数増えていないこと
- [ ] posted_results に不正なデータがないこと
- [ ] GitHub Actions が無効化されていること（必要な場合）
- [ ] Cloudinaryのテストファイルが削除されていること
- [ ] 再発防止策を検討・実施すること
