# Phase 2.29: TikTok dry-run planning 対応

## 変更内容

`src/video/video_downloader.py` に TikTok dry-run planning を追加した。

### Phase 2.26（旧）の挙動

```
TikTok + dry_run=True → success=False, error="TikTok は未対応です"
```

### Phase 2.29（新）の挙動

| 条件 | 挙動 |
|------|------|
| `dry_run=True` | `success=True`, `local_path=<予定パス>`, `error="TikTok: dry-run planning (手動ダウンロードが必要)"` |
| `dry_run=False, confirm_download=False` | `success=True`（dry 扱い、planning）|
| `dry_run=False, confirm_download=True` | `success=False`, `error="TikTok 実ダウンロードは未対応です"` |

### 追加関数

```python
def _extract_tiktok_video_id(url: str) -> str:
    """TikTok URL から video_id を抽出（dry-run planning 用）。"""
    # https://www.tiktok.com/@user/video/7123456789012345678 → "tt_7123456789012345678"
    # https://vm.tiktok.com/ZMeXYZ/ → "tt_ZMeXYZ"
```

---

## 設計上の判断

**なぜ dry-run で success=True にするか**:  
パイプライン全体（sources→collect→analyze→cut→generate）を dry-run 実行する際、
TikTok 動画もプランニング対象として扱えるようにするため。
実際のダウンロードは手動で行い、local_path を直接指定する運用を想定。

**なぜ error フィールドに注記を入れるか**:  
success=True で返すものの「手動ダウンロードが必要」という情報を
後続処理やログが確認できるようにするため。

---

## テスト

```bash
python scripts/test_phase229_230.py
```

- `_extract_tiktok_video_id` 4ケース
- TikTok dry-run planning 10ケース
- YouTube との共存確認 2ケース
- preflight 確認 3ケース
- 環境変数ガード 4ケース

---

## 使い方

```bash
# TikTok を含む reference_posts の dry-run planning
python scripts/download_video_assets.py \
  --account-id night_scout \
  --use-sheets
  # --download --confirm-download なし → dry-run
```

TikTok の planning 結果（success=True）は、手動ダウンロード後に
`local_path` を直接指定して以降のパイプラインに渡す。
