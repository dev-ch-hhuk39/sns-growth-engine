# SNS READY在庫｜生成成功と投稿前検証の不一致診断（2026-10-21）

## 事実と問題

2026-10-21のno-post `Autopilot AUTO_READY Pilot` GitHub Actions #39522078604はNight Scout、Liver Manager、Beauty Accountの全アカウントで`NO_PUBLISHABLE_READY`となり、配信準備SLOに失敗した。生成タイムアウト、AI審査の予算上限、実際の投稿枠・日付・品質・安全ゲートが関連する。特にBeauty Accountでは生成側`READY_REPLENISHED`が返った一方、後続の本番相当ドライランでpublishable READYが0件だった。

生成成功と投稿可能なREADYは別指標であり、生成成功だけではSLO成功にしない。現在のコードも最終的には`_publishable_ready_rows`で検査しているが、失敗原因の分類が不足していた。

## 今回のソース変更

- `scripts/maintain_text_ready_inventory.py`に、生成したキューIDだけを対象に、後続の検査を読み取り専用で分類する`generated_ready_rejection_counts`を追加。
- `READY_REPLENISHED`なのに配信準備が0件となったとき、既存の失敗状態を維持したまま、`READY_CREATED_NOT_PUBLISHABLE`と理由別**件数のみ**を付与。
- 固定分類：キューIDの不整合、アカウント/投稿枠/日付の不一致、READY以外の状態、審査フラグ不備、文字投稿種別不一致、媒体権限、文章品質、Hybrid AI審査、最終ドライラン拒否、診断中の想定外など。
- `scripts/ready_inventory_diagnostics.py`側は既知の理由コードだけを集計。未認識の値は`UNCLASSIFIED_REJECTION`として匿名化。未公開の投稿文、候補者ID、APIレスポンス、秘密情報、例外メッセージは出力しない。数字は1スロットあたり最大12件に制限。
- **重要：** `process_one(..., dry_run=True, confirm_real_post=False)`のみを利用。自動READY承認、キュー書き込み、SNS投稿、審査閾値・予算上限の引き上げは行わない。

## 受け入れ・残件

- 新規`scripts/test_ready_generated_rejection_diagnostics.py`に不一致・未承認・複数ID・秘密情報漏洩・異常件数等の12例を追加、PASS。
- 既存`scripts/test_ready_inventory_diagnostics.py`7例もPASS。
- 全体QA、GitHub安全検査、PRの統合が必要。現在のVPS容量は使用率約80%で、今回の診断だけを本番へ新規デプロイすると約700MiBの追加容量が発生するため、旧リリース期限処理後の通常更新へまとめる。
- 診断は**原因分類機能**であり、AI審査予算・生成タイムアウト・実際のPublishable READYゼロの改善自体は未完了。次のno-post受入実験を実施し、分類結果から厳密に原因特定して最小改修する。別途実投稿有効化の許可がなければ外部送信OFFを維持する。
- 経緯：[Issue #441](https://github.com/dev-ch-hhuk39/sns-growth-engine/issues/441)。開発完了/容量・R2の全体管理：[Issue #439](https://github.com/dev-ch-hhuk39/sns-growth-engine/issues/439)。
