# sns-growth-engine

SNS growth automation engine for collection, analysis, generation, approval, publishing, and learning.

## 目的

Threads向け投稿の**収集・分析・生成・自動品質判定・投稿・実測学習**を、アカウント境界と権利証跡を保ったまま継続運転するエンジンです。Xは参照取得のみで、投稿は無効です。

- 参照元と過去実績をアカウント別に収集・分析
- Geminiと安全な決定論fallbackで投稿候補を生成
- 低リスク候補は品質・persona・重複検査後に自動READY化
- 高リスク、権利不明、美容医療候補だけを人間レビューへ分離
- GitHub Actionsの予定slotからThreadsへ投稿し、結果をSheetsへread-after-write
- 24h / 72h / 168hの実測metricsだけを次回PDCAへ反映

## 対象アカウント

| アカウントID | 用途 |
|---|---|
| `night_scout` | 夜職ジャンル |
| `liver_manager` | ライバージャンル |
| `beauty_account` | 20〜30代女性向け美容・コスメ。美容医療は常時レビュー |

## 現在の実装状況

| 領域 | コード状態 | 本番受入条件 |
|---|---|---|
| 3アカウントのテキスト生成・自動READY | 実装済み | 各アカウント3回連続の実schedule投稿 |
| READY在庫維持・投稿直前recovery | 実装済み | 在庫不足slotが運用障害として検出・復旧されること |
| Threads投稿・idempotency・read-after-write | 実装済み | permalink、result、metrics予約の実証 |
| 許諾済みdirect media / clip | 権利ゲート付きで実装済み | 許諾済みassetごとの実投稿証拠 |
| Metrics / PDCA | 24h/72h/168h実測限定で実装済み | 実時間経過後の3窓取得と次回生成への入力証拠 |
| X投稿 / Beauty以外の未登録アカウント | 無効 | V1対象外 |

コードの存在やCI成功だけでは本番完成とは判定しません。`config/production_capability_matrix.json`の48能力は、実schedule・Threads・Sheets・metricsの本番証拠が揃った時だけPASSになります。

## 投稿戦略方針

- アカウント別の参照・実測PDCA・新規仮説を混ぜ、同一テーマや締め文の連発を防止
- PDCAの数値や過去投稿への言及は内部分析に限定し、公開本文は通常の新規投稿にする
- Cloudinary でメディア資産を一元管理
- 低リスク通常投稿は自動承認し、本当に人間判断が必要な候補だけを保留

## 安全ガード

本番投稿はworkflowのapply step内だけで投稿権限を持ちます。通常コードやdry-runに権限はありません。

```
PUBLISH_ENABLED=false          # Layer 1: 全投稿の大元スイッチ
ALLOW_REAL_X_POST=false        # X投稿は常時無効
ALLOW_REAL_THREADS_POST=false  # Layer 2: Threads投稿専用スイッチ
--confirm-real-post            # Layer 3: publish_queue.py 実行時フラグ
--max-real-posts 1             # Layer 4: 最大投稿件数上限
```

## セットアップ概要

```bash
# 1. 依存パッケージ
pip install -r requirements.txt

# 2. 環境変数の設定
cp .env.template .env
# .env を編集して各APIキーを設定

# 3. 動作確認
python scripts/preflight_check.py

# 4. 安全確認
PYTHONPATH=src python3 scripts/phase3_safety_check.py
```

## 検証

```bash
python3 scripts/evaluate_goal.py
python3 scripts/evaluate_capability_matrix.py
python3 scripts/check_autonomous_health.py --account-id all --dry-run
```

## 絶対にコミットしてはいけないもの

- `.env`（APIキー・Sheetsシークレットが含まれる）
- `GCP_SA_JSON` / `SA_JSON_BASE64`（Google Cloud サービスアカウント）
- `GEMINI_API_KEY`
- X API Key / Access Token / Secret
- Threads アクセストークン
- Cloudinary API Secret
- `*.json`（サービスアカウントJSONなど）
- `*.pem` / `*.key` / `*.b64`

設定例は `.env.template` を参照してください。

## ドキュメント

詳細なドキュメントは `docs/` ディレクトリを参照してください。

| ドキュメント | 内容 |
|---|---|
| `docs/roadmap.md` | フェーズ別実装ロードマップ |
| `docs/current-state-audit.md` | 現状棚卸しと差分分析 |
| `docs/security-and-secrets.md` | シークレット管理方針 |
| `docs/safety-guards.md` | 安全ガード詳細 |
| `docs/phase3d-x-manual-post.md` | X手動投稿テスト手順 |
| `docs/x-publisher-setup.md` | X Developer Portal設定手順 |
