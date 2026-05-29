# Publisher Interface 設計

`v2/src/publishers/` パッケージの設計と使い方。

---

## パッケージ構成

```
src/publishers/
  __init__.py     # BasePublisher, PublishResult, DryRunPublisher, get_publisher を公開
  base.py         # 抽象基底クラス + 結果値オブジェクト
  dry_run.py      # Phase 3-A で使う DryRunPublisher
  factory.py      # get_publisher() ファクトリ
```

Phase 3-B 以降に追加予定:
```
src/publishers/
  x_publisher.py       # X API 本番 Publisher（未実装）
  threads_publisher.py # Threads API 本番 Publisher（未実装）
```

---

## PublishResult

```python
@dataclass
class PublishResult:
    platform: str           # "x" / "threads" 等
    success: bool           # 投稿成功 or dry-run 検証成功
    dry_run: bool           # True = dry-run, False = 本番投稿
    posted_url: str | None  # 投稿URL（dry-run時は None）
    external_post_id: str | None  # SNS側の投稿ID（dry-run時は None）
    message: str            # ログ用メッセージ
    raw_response: dict | None  # SNS API レスポンス（dry-run時は None）
```

dry-run 時は常に:
- `posted_url = None`
- `external_post_id = None`
- `dry_run = True`

---

## BasePublisher

```python
class BasePublisher:
    platform: str = ""

    def publish(
        self,
        text: str,
        *,
        account: dict,       # accounts タブの行データ
        derivative: dict,    # social_derivatives タブの行データ
        queue_item: dict,    # queue タブの行データ
        dry_run: bool = True,
    ) -> PublishResult:
        raise NotImplementedError
```

`dry_run=True` がデフォルト — 呼び出し元が明示的に `dry_run=False` にしない限り実投稿しない。

---

## DryRunPublisher

実 SNS API を呼ばず、テキストの検証のみを行う。
Phase 3-A で全プラットフォームに使用するデフォルト Publisher。

### 検証内容

| platform | チェック内容 |
|---|---|
| x | 空チェック → 140字制限(FAIL) → 120字推奨(WARN) → OK |
| threads | 空チェック → フック+空行+本文形式チェック(WARN) → OK |
| その他 | 空チェックのみ |

### 返り値

- `success=True` かつ `dry_run=True`（テキストが正常な場合）
- `success=False` かつ `dry_run=True`（テキストが空または140字超の場合）
- `posted_url=None`, `external_post_id=None`（常に）

---

## get_publisher ファクトリ

```python
from publishers.factory import get_publisher

# Phase 3-A: 常に DryRunPublisher を返す
publisher = get_publisher("x", dry_run=True)
publisher = get_publisher("threads", dry_run=True)

# dry_run=False は NotImplementedError（Phase 3-B まで）
publisher = get_publisher("x", dry_run=False)  # → NotImplementedError
```

### Phase 3-B での差し替え

`factory.py` のコメント部分を解除するだけで本番 Publisher に切り替わる:

```python
# factory.py (Phase 3-B 以降)
if plat == "x":
    from publishers.x_publisher import XPublisher
    return XPublisher()
elif plat == "threads":
    from publishers.threads_publisher import ThreadsPublisher
    return ThreadsPublisher()
```

---

## 使用例

```python
from publishers.factory import get_publisher

publisher = get_publisher("x", dry_run=True)
result = publisher.publish(
    text="投稿テキスト",
    account={"account_id": "night_scout"},
    derivative={"derivative_id": "sd-xxx", "platform": "x"},
    queue_item={"queue_id": "q-xxx"},
    dry_run=True,
)

print(result.success)       # True
print(result.dry_run)       # True
print(result.posted_url)    # None（実投稿しないため）
print(result.message)       # "DRY_RUN: would post to X (50字) | ..."
```
