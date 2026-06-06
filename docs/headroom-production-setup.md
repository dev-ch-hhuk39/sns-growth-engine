# Headroom Production Setup（Phase HR-1）

## 概要

Headroom は LLM API 呼び出しのトークン最適化プロキシです。
`headroom-ai[proxy]` のみをインストールします（`headroom-ai[all]` は **禁止**）。

---

## インストール方針

| 方針 | 理由 |
|------|------|
| `headroom-ai[proxy]` のみ | 必要最小限の依存 |
| `headroom-ai[all]` は **禁止** | 不要な依存が増加し、セキュリティリスクが高まる |
| `requirements.txt` への追加は **禁止** | プロジェクト全体の依存に混入させない |
| pipx または `~/.venvs/headroom` で隔離 | ホスト環境を汚染しない |

---

## インストール手順

### 実際の導入方法（2026-06-07 実施済み）

pipx が環境に存在しないため、`~/.venvs/headroom` 独立 venv で導入。

```bash
python3 -m venv ~/.venvs/headroom
~/.venvs/headroom/bin/python -m pip install -U pip
~/.venvs/headroom/bin/python -m pip install "headroom-ai[proxy]"

# 確認
~/.venvs/headroom/bin/headroom --version
# → headroom, version 0.23.0
```

### 方法 A: pipx（pipx が使える場合）

```bash
# pipx 未インストールの場合
brew install pipx
pipx ensurepath

# headroom-ai[proxy] インストール（[all] は禁止）
pipx install "headroom-ai[proxy]"

# インストール確認
pipx list | grep headroom
```

---

## ラッパースクリプト作成

### claude-hr ラッパー

```bash
cat > ~/.local/bin/claude-hr << 'EOF'
#!/bin/bash
# claude-hr: Claude Code を Headroom proxy 経由で実行するラッパー
# headroom-ai[proxy] が必要: pipx install "headroom-ai[proxy]"
exec headroom proxy -- claude "$@"
EOF
chmod +x ~/.local/bin/claude-hr
```

### codex-hr ラッパー

```bash
cat > ~/.local/bin/codex-hr << 'EOF'
#!/bin/bash
# codex-hr: Codex を Headroom proxy 経由で実行するラッパー
exec headroom proxy -- codex "$@"
EOF
chmod +x ~/.local/bin/codex-hr
```

### PATH 確認

```bash
echo $PATH | tr ':' '\n' | grep local/bin
# ~/.local/bin が含まれない場合は .zshrc に追加:
# export PATH="$HOME/.local/bin:$PATH"
```

---

## インストール確認

```bash
# Headroom インストール確認テスト（実API呼び出しなし）
python scripts/test_headroom_installation.py
```

---

## 禁止事項

```
headroom-ai[all] のインストール    → 依存過多・セキュリティリスク
requirements.txt への追加          → プロジェクト汚染
ANTHROPIC_API_KEY の直接出力       → 機密情報漏洩
Headroom 経由での SNS 本番投稿     → 誤操作防止
```

---

## 参考リンク

- headroom-ai PyPI: https://pypi.org/project/headroom-ai/
- このプロジェクトの安全ルール: `docs/safety-guards.md`
- Hermes Agent 設計: `docs/hermes-agent-integration-plan.md`
