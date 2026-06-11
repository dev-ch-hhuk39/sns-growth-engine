# CodeGraph Production Setup（Phase CG-1）

## 1. 導入目的

CodeGraph は MCP（Model Context Protocol）ベースのコードインテリジェンスツールです。

| 課題 | CodeGraph による解決 |
|------|---------------------|
| 影響範囲の把握に大量 grep/read | `codegraph_impact <symbol>` で一発確認 |
| 関連ファイルの特定に時間がかかる | `codegraph_search <keyword>` で高速検索 |
| 関数の呼び出し元/先が不明 | `codegraph_callers/callees <symbol>` で追跡 |
| テスト対象のファイルが不明 | `codegraph_affected` で変更影響テストを特定 |

**大量 grep/read 前に CodeGraph を優先する。**

---

## 2. 実際に使ったインストール方法（2026-06-11 実施済み）

### npm グローバルインストール

```bash
npm i -g @colbymchenry/codegraph
# → added 2 packages in 7s
# → @colbymchenry/codegraph@0.9.9
```

- MIT ライセンス
- 依存なし（バンドル型）
- Node.js v22.17.0 / npm 10.9.2 で動作確認済み

### バージョン確認

```bash
codegraph --version
# → 0.9.9
```

---

## 3. Claude Code への接続方法（MCP サーバー登録）

```bash
cd "/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2"
codegraph install --target claude --location local --yes
```

**`--target claude`**: Claude Code のみに登録（Cursor・Codex・opencode には登録しない）  
**`--location local`**: プロジェクトローカルに設定（グローバル設定を汚染しない）

実行結果（2026-06-11）:
- `.mcp.json` 作成（MCP サーバー設定）
- `.claude/settings.json` 更新（auto-allow 権限設定）
- `.codegraph/` 作成・115ファイル・2,373シンボル インデックス完了

---

## 4. 現行 v2 だけをindex対象にする方針

**インデックス対象: 現行 v2 のみ**

```
/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2
```

**絶対に index しない:**
```
/Users/hayatoa/claudecodeプロジェクトディレクトリ/使ってない_過去/
/Users/hayatoa/Documents/claudecodeプロジェクトディレクトリ/
```

別プロジェクトに codegraph init しない。`codegraph install` は v2 プロジェクト内でのみ実行。

---

## 5. `.codegraph/` をcommitしない方針

`.gitignore` に追加済み:

```gitignore
# CodeGraph（index/cache はcommit禁止）
.codegraph/
```

`.codegraph/` 内の `.gitignore` も自動生成される（`*.db`, `cache/` 等を除外）。

**commitしてよいもの:**
- `.mcp.json`（MCP サーバー設定 - プロジェクト共有可）
- `.claude/settings.json`（auto-allow 設定）

**commitしてはいけないもの:**
- `.codegraph/codegraph.db`（5.6MB のシンボル DB）
- `.codegraph/cache/` 以下

---

## 6. context-mode との役割分担

| 項目 | CodeGraph | context-mode |
|------|-----------|--------------|
| 目的 | コード構造の探索・分析 | 作業履歴管理・context 削減 |
| データ | シンボル/依存グラフ DB | 作業ログ・コマンド履歴 |
| 使うタイミング | grep/read の前 | compact 前後・長い出力退避 |
| 主な操作 | `codegraph_search`, `codegraph_impact` | `ctx_execute`, `ctx_search` |

**組み合わせフロー:**
```
実装前 → CodeGraph で影響範囲確認 → ctx_execute で結果退避 → 実装 → ctx_save → /compact
```

---

## 7. Headroom との役割分担

| 項目 | CodeGraph | Headroom |
|------|-----------|----------|
| 目的 | コード探索 | API コスト最適化 |
| 動作層 | MCP サーバー（code intelligence） | API プロキシ層 |
| 依存 | npm グローバル | Python venv |
| 起動方法 | `claude`（自動ロード） | `claude-hr`（proxy 経由） |

CodeGraph と Headroom は独立して動作。`claude-hr` 起動時も MCP サーバーとして動作する。

---

## 8. Hermes Agent との将来連携

将来的に Hermes Agent が導入された場合、CodeGraph のシンボル情報を活用した影響範囲付き提案が可能になる。ただし現時点では Hermes 実インストールは行わない。

---

## 9. uninstall 方法

```bash
# MCP 設定の削除
codegraph uninstall --target claude --location local

# プロジェクト index の削除
codegraph uninit "/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2"
# または
rm -rf .codegraph/

# npm グローバルアンインストール
npm uninstall -g @colbymchenry/codegraph
```

---

## 10. re-index 方法

```bash
cd "/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2"

# 変更分のみ sync
codegraph sync

# 全体再 index
codegraph index

# 状態確認
codegraph status
```

---

## 11. トラブル時の戻し方

1. `codegraph status` で index 状態を確認
2. lock ファイルが残っている場合: `codegraph unlock .`
3. DB 破損の場合: `rm -rf .codegraph/ && codegraph init -i`
4. MCP 接続が切れた場合: Claude Code を再起動（`--target claude` 設定は `.mcp.json` に保持される）

CodeGraph なしでも Claude Code は動作する。`--target none` でアンインストールすれば元の状態に戻る。

---

## 12. Codex には適用しない方針

**CodeGraph は現行 v2 / Claude Code 専用。**

- Codex CLI への `codegraph install` は実行しない
- `codegraph install --target all` は使用しない
- Cursor への接続も現時点では行わない

インストール時は必ず `--target claude` を指定する。

---

## 13. 大量 grep/read 前に CodeGraph を使う方針

```bash
# 旧来の方法（context を消費する）
grep -r "PostResultAnalyzer" scripts/ src/

# CodeGraph 推奨
# → Claude Code セッション内で MCP ツールとして利用:
#   codegraph_search("PostResultAnalyzer")
#   codegraph_impact("analyze")
```

**優先順位:**
1. CodeGraph でシンボル検索・影響確認
2. 対象ファイルが特定されたら Read で精読
3. どうしても grep が必要な場合のみ Bash で実行

---

## 更新履歴

- Phase CG-1: 初期セットアップ（2026-06-11）: npm install + Claude Code local 接続 + 115ファイル index
