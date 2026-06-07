# Phase 4.4: 週次改善レポート生成

## 概要

アカウント別の週次成長レポートを生成する。
Hermes Agent への入力として使用する。自動反映は行わない。

## 使い方

```bash
# 1アカウント
python scripts/generate_weekly_growth_report.py --account-id night_scout

# 全アカウント
python scripts/generate_weekly_growth_report.py --all-accounts

# モック確認
python scripts/generate_weekly_growth_report.py --account-id night_scout --mock
```

## 出力ファイル

```
exports/hermes/
  weekly_growth_report_night_scout_YYYYMMDD.md
  weekly_growth_report_night_scout_YYYYMMDD.json
```

## レポート内容

### 投稿実績サマリー
- 期間内投稿数（直近7日間）
- 全体投稿数
- プラットフォーム別（x / threads）
- 投稿タイプ別（reference_based / original_hypothesis / video_clip_reference）

### PV系指標 vs CV系指標
- PV系: impressions / views
- CV系: engagement_rate / likes / follow_count_delta

### 伸びた投稿 / 伸びなかった投稿
- PV Top 3（直近7日間）
- パフォーマンス下位（要改善候補）

### 学習システム状態
- active=true ルール件数
- WAITING_REVIEW 提案件数

### 次週の改善仮説
- データドリブンな仮説（自動反映しない）

## 安全ガード

- 自動投稿なし
- learning_rules の自動 active=true なし
- Sheets書き込みなし（読み取り専用）
- git commit 禁止

## Hermesへの渡し方

1. レポートを生成
2. exports/hermes/ のファイルを Hermes Agent に渡す
3. Hermes の提案を imports/hermes/ に保存
4. import_improvement_suggestions.py でインポート
