# Threads 本番投稿 最終チェックリスト

実投稿前に必ずこのチェックリストを完了すること。

**禁止事項（厳守）**:
- beauty_account / draft_only アカウントへの実投稿
- ALLOW_REAL_THREADS_POST=true の長期維持
- READY化・POSTED化なしで投稿

## 前提条件

```bash
cd /Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2
python3 scripts/preflight_threads_real_post.py --account-id night_scout --mock
```

→ FAIL が 0 件であること。WARN は認証情報関連のみ許容。

## 対象アカウント

| アカウント | ステータス | Threads実投稿 |
|-----------|-----------|-------------|
| night_scout | active | ○（active化後） |
| liver_manager | active | ○（active化後） |
| beauty_account | draft_only | **禁止** |

## チェックリスト

### 1. 環境確認

- [ ] `PUBLISH_ENABLED=false` であること
- [ ] `ALLOW_REAL_THREADS_POST=false` であること
- [ ] 作業ディレクトリが `v2` であること
- [ ] beauty_account は `status=draft_only` のままであること

### 2. 認証情報確認

```bash
python3 scripts/preflight_threads_real_post.py --account-id night_scout
```

必要な環境変数:
- `THREADS_APP_ID`
- `THREADS_APP_SECRET`
- `THREADS_ACCESS_TOKEN`
- `THREADS_USER_ID`

### 3. queue確認

```bash
python3 scripts/review_queue.py --account-id night_scout --status READY
```

- [ ] READY queue に投稿候補があること
- [ ] rights_review_required=false であること
- [ ] platform=threads であること

### 4. thread_series確認（thread_seriesを投稿する場合）

```bash
python3 scripts/review_thread_series.py --account-id night_scout
```

- [ ] 全投稿が WAITING_REVIEW であること
- [ ] FAIL が 0 件であること
- [ ] draft_only アカウントの投稿が含まれていないこと

### 5. 実投稿（手動テスト 1件目）

```bash
# .env を変更
# ALLOW_REAL_THREADS_POST=true
# PUBLISH_ENABLED=true

python3 scripts/publish_queue.py \
  --account-id night_scout \
  --platform threads \
  --status READY \
  --limit 1 \
  --confirm-real-post \
  --queue-id {queue_id} \
  --max-real-posts 1

# 投稿後すぐに false へ戻す（必須）
python3 -c "
import re, pathlib
env = pathlib.Path('.env').read_text()
env = re.sub(r'ALLOW_REAL_THREADS_POST=true', 'ALLOW_REAL_THREADS_POST=false', env)
env = re.sub(r'PUBLISH_ENABLED=true', 'PUBLISH_ENABLED=false', env)
pathlib.Path('.env').write_text(env)
print('安全フラグを false に戻しました')
"
```

### 6. 投稿後確認

```bash
python3 scripts/check_pipeline_integrity.py --account-id night_scout
```

- [ ] FAIL=0 であること
- [ ] posted_results に記録されていること

## 緊急停止

問題発生時 → `docs/emergency-rollback.md` 参照

## 注意

- Threads 実投稿は現時点（2026-06-12）でまだ未実施
- 実投稿前に必ず一人で全チェックリストを完了すること
- beauty_account は draft_only につき絶対に実投稿しないこと
