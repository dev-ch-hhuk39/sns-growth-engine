# Development Environment Strategy（Phase ENV-2）

## 概要

本プロジェクトの Claude Code 開発環境を以下の役割で整理します。

---

## 1. context-mode を優先する理由

Claude Code の最大の課題は「context の消耗と記憶の断絶」です。

| 問題 | 影響 |
|------|------|
| `/compact` 後の詳細忘却 | 作業の重複・方針のブレ |
| 大量 tool output の context 消費 | 早期の context limit 到達 |
| セッション間の文脈断絶 | 毎回の「現状確認」コスト |

context-mode はこれを **Claude Code プラグイン** として解決します:
- `ctx_save` / `ctx_search` で作業継続性を確保
- `ctx_execute` で長い出力を context 外に退避
- SQLite/FTS5 による高速な過去作業参照

**通常運用では `claude`（context-mode 込み）を使います。**

---

## 2. CodeGraph の役割

大量の grep/read は context を消費し、かつ遅い。CodeGraph はこれを MCP ベースのコードインテリジェンスで解決します。

| 操作 | 旧来 | CodeGraph |
|------|------|-----------|
| シンボル検索 | `grep -r "symbol" src/` | `codegraph_search("symbol")` |
| 影響範囲確認 | 手動 grep + Read | `codegraph_impact("function_name")` |
| 呼び出し元追跡 | 手動調査 | `codegraph_callers("method")` |
| テスト対象判断 | 経験則 | `codegraph_affected [changed_files]` |

**実装前・変更前に必ず CodeGraph で影響範囲を確認する。**

---

## 3. Headroom の位置付け

Headroom はすでに導入済みです（`~/.venvs/headroom/`）。

**ただし通常運用の必須ツールにはしない。**

| 項目 | 位置付け |
|------|----------|
| 役割 | API コスト最適化プロキシ |
| 優先度 | **補助・追加検証枠** |
| 起動方法 | `claude-hr`（proxy 経由、通常は不要） |
| 削除 | しない（後で必要になる可能性がある） |
| 必須運用 | しない |
| requirements.txt | 追加しない |
| headroom-ai[all] | **禁止** |

`claude-hr` は長時間セッションや API コスト削減が必要になったときに使う。

---

## 4. Hermes Agent の位置付け

Hermes Agent は **将来の長期記憶・自動改善エージェント**です。

| 項目 | 位置付け |
|------|----------|
| 現状 | 未インストール（実インストール禁止） |
| 連携方法 | file export/import のみ |
| SNS 投稿権限 | 与えない |
| Sheets 直接編集権限 | 与えない |
| コード自動変更権限 | 与えない |
| 実インストール | Hermes Agent 統合計画承認後のみ |

詳細: `docs/hermes-agent-integration-plan.md`

---

## 5. 推奨起動方法

### 通常運用（推奨）

```bash
cd "/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2"
claude
# → context-mode + CodeGraph が自動でロードされる
```

### 補助検証（API コスト削減が必要な場合）

```bash
claude-hr
# → Headroom proxy 経由 + context-mode + CodeGraph
```

### 将来（Hermes Agent 導入後）

```bash
# file export/import 連携のみ
python scripts/export_context_for_hermes.py
# → Hermes が改善提案を file に出力 → 人間がレビュー → import
```

---

## 6. compact 前後の手順

### compact 前

```
1. ctx_save "作業内容サマリー"
2. 重要な判断や方針を ctx_save に記録
3. /compact
```

### compact 後

```
1. ctx_search "前回の作業"
2. ctx_stats で履歴確認
3. 必要なら CodeGraph で影響範囲を再確認
4. 作業再開
```

---

## 7. /clear と /compact の使い分け

| コマンド | 用途 | 注意 |
|----------|------|------|
| `/compact` | context 圧縮・要約。作業継続可 | 詳細は落ちる。ctx_save 推奨 |
| `/clear` | context 完全リセット。新しい作業開始 | ctx_save しないと記録が消える |

**`/clear` は慎重に使う。`/compact` を優先する。**

---

## 8. どのツールが何を削減するか

| ツール | 削減するもの |
|--------|-------------|
| context-mode | tool output の context 消費・セッション間忘却 |
| CodeGraph | grep/read の context 消費・探索コスト |
| Headroom | API トークンコスト（補助） |
| `/compact` | context window の圧迫（要約） |

---

## 9. 併用時の注意点

- `claude-hr`（Headroom 経由）でも CodeGraph MCP は動作する
- context-mode と CodeGraph は独立して動作（干渉しない）
- context-mode の SQLite DB と CodeGraph の DB は別物
- Headroom proxy を経由しても context-mode/CodeGraph の機能に影響なし

---

## 10. トラブル時の戻し方

| 症状 | 対処 |
|------|------|
| context-mode が動かない | `/reload-plugins` → `ctx-doctor` |
| CodeGraph が応答しない | `codegraph status` → `codegraph unlock .` |
| Headroom proxy エラー | `claude`（通常起動）に切り替え |
| 全部動かない | `claude` のみで作業継続。ツールは補助なので必須ではない |

---

## 11. 旧zip退避フォルダを触らない方針

**作業対象は以下のみ:**

```
/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2
```

**以下には絶対に触らない:**

```
/Users/hayatoa/claudecodeプロジェクトディレクトリ/使ってない_過去/SNS自動投稿システム/
/Users/hayatoa/Documents/claudecodeプロジェクトディレクトリ/SNS自動投稿システム/
```

context-mode・CodeGraph・Headroom のすべてにおいて、上記フォルダをインデックス・検索・編集の対象にしない。

---

## 12. Codex を使わない方針

本プロジェクトでは **Codex CLI は使用しない。**

- context-mode は Claude Code 専用プラグイン
- CodeGraph の `--target` は `claude` のみ指定
- `codegraph install --target all` は実行しない
- Headroom の `codex-hr` ラッパーは作成・使用しない

---

## ツール役割一覧

```
通常:
  claude + context-mode + CodeGraph
    └ context 管理・コード探索の標準セット

補助検証:
  claude-hr + context-mode + CodeGraph
    └ API コスト削減が必要な場合のみ

将来:
  Hermes Agent + file export/import
    └ 長期記憶・自動改善提案（未実装）
```

---

## 更新履歴

- Phase ENV-2: 初期作成（2026-06-11）: context-mode + CodeGraph + Headroom 役割整理
