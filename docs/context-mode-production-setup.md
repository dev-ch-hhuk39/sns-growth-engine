# context-mode Production Setup（Phase ENV-1）

## 1. 導入目的

context-mode は Claude Code のプラグインとして動作する作業継続性向上ツールです。

| 課題 | context-mode による解決 |
|------|-------------------------|
| `/compact` 後の作業履歴忘却 | SQLite/FTS5 による作業履歴検索 |
| ログ・JSON・CSV の巨大 tool output | `ctx_execute` で context に流さず記録 |
| セッション間の文脈断絶 | `ctx_search` で過去の作業内容を参照 |
| tool output の爆発的増加 | 長い出力を context 外に退避 |

---

## 2. 実際の導入方法（Claude Code Plugin）

### 前提条件

- Claude Code v1.0.33 以上
- インターネット接続（plugin marketplace アクセス）

### インストール手順

Claude Code セッション内で以下を実行:

```
/plugin marketplace add mksglu/context-mode
/plugin install context-mode@context-mode
/reload-plugins
```

### 動作確認

```
/context-mode:ctx-doctor
/context-mode:ctx-stats
```

### MCP-only install（代替方法）

Claude Code の `/plugin` が使えない環境では MCP 経由でインストール可能:

```bash
claude mcp add context-mode -- npx -y context-mode
```

この場合も **Claude Code にのみ** 追加する。Cursor・Codex・他エージェントには追加しない。

---

## 3. Claude Code Plugin としての設定

- plugin は `~/.claude/plugins/` に格納される
- project レベル `.claude/settings.json` への影響なし
- context-mode の設定は `~/.claude/context-mode/` 以下に保存される（コミット禁止）

---

## 4. ctx-doctor 結果の確認

```
/context-mode:ctx-doctor
```

正常時の期待出力:
```
✓ SQLite FTS5 extension available
✓ Storage directory writable
✓ Context mode active
✓ No stale locks detected
```

異常時: `/context-mode:ctx-doctor` の出力に従ってトラブルシュート。

---

## 5. ctx-stats 確認方法

```
/context-mode:ctx-stats
```

出力例:
```
Sessions: 12
Commands recorded: 341
Storage used: 2.3 MB
Oldest entry: 2026-05-01
```

---

## 6. compact 前後の使い方

### /compact 前

```
/context-mode:ctx_save "作業中断ポイント: Phase 5.4 import_post_results.py テスト修正中"
```

### /compact 後（再開時）

```
/context-mode:ctx_search "Phase 5.4 import_post_results"
/context-mode:ctx_stats
```

### ctx_execute の使い方（長い出力を context に流さない）

```python
# 通常（context に全部流れる）
result = subprocess.run(["python", "scripts/test_phase2.py"], capture_output=True)
print(result.stdout)  # 巨大な出力が context を消費

# context-mode 推奨（ctx_execute でログに退避）
# /context-mode:ctx_execute python scripts/test_phase2.py
```

---

## 7. /clear と /compact の使い分け

| コマンド | 用途 | context-mode との関係 |
|----------|------|----------------------|
| `/clear` | context を完全リセット。作業も記憶も消える | ctx_save で記録してから使う |
| `/compact` | context を要約圧縮。作業継続できるが記憶が落ちる | ctx_save で詳細を記録してから使う |

**推奨フロー:**

```
(長い作業の節目) → ctx_save "現状" → /compact → ctx_search "現状" → 作業再開
```

---

## 8. Headroom との違い

| 項目 | context-mode | Headroom |
|------|--------------|----------|
| 用途 | 作業履歴管理・context 削減 | LLM API コスト最適化・proxy |
| 動作層 | Claude Code プラグイン | API プロキシ層 |
| 優先度 | **優先（通常運用）** | 補助・追加検証枠 |
| 起動方法 | `claude`（通常起動） | `claude-hr`（proxy 経由） |
| 依存追加 | なし | headroom-ai[proxy] venv |

---

## 9. CodeGraph との違い

| 項目 | context-mode | CodeGraph |
|------|--------------|-----------|
| 用途 | 作業履歴・context 管理 | コード探索・影響範囲分析 |
| データ | 作業ログ・コマンド履歴 | シンボル DB・依存グラフ |
| 使うタイミング | compact 前後・長い出力退避 | grep/read 前・影響調査前 |
| ストレージ | `~/.claude/context-mode/` | `.codegraph/codegraph.db` |

**両方を組み合わせた推奨フロー:**

```
新機能調査 → CodeGraph で影響範囲確認 → ctx_execute で長い結果を退避 → 実装
```

---

## 10. uninstall 方法

### Plugin 経由でインストールした場合

```
/plugin uninstall context-mode
/reload-plugins
```

### MCP 経由でインストールした場合

```bash
claude mcp remove context-mode
```

### キャッシュ削除

```bash
rm -rf ~/.claude/context-mode/
```

---

## 11. トラブル時の戻し方

1. `/reload-plugins` で plugin をリロード
2. `ctx-doctor` で診断
3. 解決しない場合は `uninstall → reinstall`
4. それでも解決しない場合: context-mode なしの通常 `claude` で作業継続

context-mode は **補助ツール**。なくても Claude Code は動作する。

---

## 12. Codex には適用しない方針

**context-mode は Claude Code 専用。** Codex CLI・Cursor・opencode・他エージェントには導入しない。

理由:
- Codex は本プロジェクトの開発対象外
- context-mode の設計は Claude Code の plugin システムに依存
- 他エージェントへの設定混入を防ぐ

---

## 13. 旧zip退避フォルダを触らない方針

context-mode のインデックス・検索対象は **現行 v2 のみ**:

```
/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2
```

以下には一切アクセスしない:

```
/Users/hayatoa/claudecodeプロジェクトディレクトリ/使ってない_過去/SNS自動投稿システム/
/Users/hayatoa/Documents/claudecodeプロジェクトディレクトリ/SNS自動投稿システム/
```

---

## 14. secrets 非表示方針

context-mode の作業履歴（SQLite DB）には以下を **保存しない・表示しない**:

- APIキー・トークン・シークレット値
- `.env` の中身
- 個人情報・顧客情報
- 機密情報を含むコマンド出力

`ctx_execute` で長い出力を退避する場合も、実行前にシークレット値が含まれないことを確認する。

## 15. cache/SQLite/index をcommitしない方針

`.gitignore` に以下を追加済み:

```gitignore
# context-mode（SQLite/cache/index はcommit禁止）
.context-mode/
context-mode.db
context-mode*.db
```

**絶対にcommitしてはいけないもの:**
- `context-mode.db` / `*.db`（作業履歴）
- `~/.claude/context-mode/` 配下（ローカル専用）
- plugin の cache ファイル

---

## 更新履歴

- Phase ENV-1: 初期セットアップ（2026-06-11）
