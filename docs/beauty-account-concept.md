# beauty_account コンセプト（Phase 6.1）

## 概要

beauty_account は美容アドバイザーアカウント。スキンケア・コスメ・美容知識を発信し、LINE相談獲得を目指す。

**現状ステータス: `draft_only`（実投稿禁止）**

---

## 1. アカウント設定

| 項目 | 内容 |
|------|------|
| account_id | beauty_account |
| display_name | 美容アドバイザー |
| status | **draft_only** |
| platforms | x, threads |
| primary_goal | LINE相談獲得 |
| tone | 丁寧で親しみやすい・専門知識あり・読者目線 |
| first_person | 私 |

---

## 2. ターゲット読者

- 美容に興味のある女性
- スキンケアに悩む 20〜40代
- コスメ購入検討層
- 美容知識を増やしたい人

---

## 3. コンテンツカテゴリ

1. スキンケアあるある
2. 美容知識・成分解説
3. コスメレビュー視点
4. 美容ルーティン
5. 美容の誤解を解く
6. 季節の美容対策
7. プチプラ美容
8. 美容と健康の関係

---

## 4. 禁止事項（厳守）

### 禁止テーマ
- 医療行為の代替推奨
- 特定商品の断定的効果訴求
- MLM・マルチ商法的勧誘
- 過度なダイエット・過激な痩身訴求
- 誇張・虚偽の美容効果

### 禁止キーワード
- 絶対に治る / 100%効果あり / 病院いらず / 薬と同じ効果
- 代理店 / 会員募集 / MLM / ねずみ講
- 痩せ薬 / 飲むだけで痩せる

---

## 5. 安全ポリシー

| 項目 | 値 |
|------|-----|
| allow_real_post | false（STRICT） |
| requires_human_review | true |
| min_publish_score | 70（通常より厳しめ） |
| brand_risk_threshold | 20（通常より低め） |
| draft_only_enforcement | STRICT |

---

## 6. READY 化の条件（将来）

beauty_account を `active` に変更するには以下が必要:

1. draft_only 期間中に thread_series を 10 件以上生成・レビュー済み
2. 禁止キーワード違反ゼロを確認
3. ユーザーが明示的に status = "active" に変更を承認
4. seeds.py の active = "TRUE" に変更

**自動的に READY 化することは禁止。必ずユーザー承認を経る。**

---

## 更新履歴

- Phase 6.1: 初期コンセプト作成（2026-06-11）
