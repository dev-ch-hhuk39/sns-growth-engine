# Manual Smoke Test Sequence

最終版の初回スモーク手順です。初回運用では実投稿・実download・実cut・実uploadを行いません。

## 固定順序

1. tool doctor
2. source registry validate
3. source candidate review
4. mock fetch dry-run
5. source_to_post pipeline mock dry-run
6. media preflight dry-run
7. publisher dry-run
8. posted_results import dry-run
9. PDCA dry-run
10. 人間承認後に confirm-fetch を1sourceだけ
11. confirm-fetch後もdownload/cut/upload/postはしない
12. download/cut/upload/postは別承認
13. 初回1投稿はpublisher dry-runまで
14. 実投稿はさらに別承認

## 0. 作業ディレクトリ

```bash
cd "/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2"
git status -sb
```

`.env`, cookie, token, API key の値は表示しないでください。

## 1. Tool Doctor

```bash
python3 scripts/check_source_fetcher_tools.py --dry-run
```

`NOT_INSTALLED` は WARN 扱いでよいです。実fetchはしません。

## 2. Source Registry Validate

```bash
python3 scripts/manage_source_accounts.py --validate --dry-run
```

確認ポイント:

- production source は inactive / fetch disabled
- `beauty_account` は WAITING_REVIEW / draft-only
- source priority 自動変更なし

## 3. Source Candidate Review

```bash
python3 scripts/review_source_candidates.py --account-id night_scout --dry-run
python3 scripts/review_source_candidates.py --account-id liver_manager --dry-run
python3 scripts/review_source_candidates.py --account-id beauty_account --dry-run
```

## 4. Mock Fetch Dry-run

```bash
python3 scripts/fetch_source_posts.py --account-id night_scout --platform x --mock --dry-run
python3 scripts/fetch_source_posts.py --account-id night_scout --platform youtube --mock --dry-run
python3 scripts/fetch_source_posts.py --account-id liver_manager --platform youtube --mock --dry-run
python3 scripts/fetch_source_posts.py --account-id liver_manager --platform note --mock --dry-run
python3 scripts/fetch_source_posts.py --account-id beauty_account --platform youtube --mock --dry-run
python3 scripts/fetch_source_posts.py --account-id beauty_account --platform tiktok --mock --dry-run
```

## 5. Source-to-post Pipeline Mock Dry-run

```bash
python3 scripts/run_source_to_post_pipeline.py --account-id night_scout --platform x --mock --dry-run
python3 scripts/run_source_to_post_pipeline.py --account-id night_scout --platform threads --source-platform youtube --mock --dry-run
python3 scripts/run_source_to_post_pipeline.py --account-id liver_manager --platform threads --source-platform youtube --mock --dry-run
python3 scripts/run_source_to_post_pipeline.py --account-id liver_manager --platform threads --source-platform note --mock --dry-run
python3 scripts/run_source_to_post_pipeline.py --account-id beauty_account --platform threads --source-platform youtube --mock --dry-run
```

publish step は confirmなしのため BLOCKED で正常です。

## 6. Media Preflight Dry-run

```bash
python3 scripts/preflight_media_assets.py --account-id night_scout --mock --dry-run
python3 scripts/download_media_assets.py --account-id night_scout --download --dry-run
python3 scripts/cut_video_clips.py --account-id liver_manager --cut --dry-run
python3 scripts/upload_media_assets.py --account-id night_scout --upload --dry-run
```

`download`, `cut`, `upload` は confirmなしなので必ず BLOCKED です。

## 7. Publisher Dry-run

```bash
python3 scripts/publish_threads_post.py --account-id night_scout --confirm-post --dry-run
python3 scripts/publish_x_post.py --account-id night_scout --confirm-post --dry-run
```

`--dry-run` が付いているため実投稿は行いません。

## 8. Posted Results Import Dry-run

```bash
python3 scripts/import_posted_results.py --mock --dry-run
```

## 9. PDCA Dry-run

```bash
python3 scripts/run_pdca_cycle.py --account-id night_scout --platform x --days 7 --dry-run --mock --generate-next-plan
```

PDCA 提案は `WAITING_REVIEW` / `auto_apply=false` のままにします。

## 10. Human-approved Confirm Fetch, One Source Only

人間が明示承認した後だけ、1 source だけ confirm-fetch を試します。

```bash
python3 scripts/fetch_source_posts.py \
  --account-id night_scout \
  --platform x \
  --source-id <approved_source_id> \
  --fetch \
  --confirm-fetch \
  --dry-run
```

この段階でも `download`, `cut`, `upload`, `post` は行いません。

## 11. Separate Approval Required

以下は初回スモークの範囲外です。必ず別承認に分けてください。

- 実download
- 実cut
- 実upload
- 実投稿
- `PUBLISH_ENABLED=true`
- `ALLOW_REAL_X_POST=true`
- `ALLOW_REAL_THREADS_POST=true`
- `ALLOW_CLOUDINARY_UPLOAD=true`

## PASS 判定

- source URL 反映済み
- mock fetch dry-run PASS
- source_to_post mock dry-run PASS
- media preflight dry-run PASS
- confirmなし download/cut/upload/post BLOCKED
- publisher dry-run PASS
- posted_results import dry-run PASS
- PDCA dry-run PASS
- 実fetch/download/cut/upload/post 未実行
