# beauty_account コンセプト

## 初期方針

`beauty_account` は美容・コスメが好きな20〜30代女性向けのThreadsアカウントです。
一人称は「私」。美容に詳しい、少しお姉さん寄りの女友達として、女性的で柔らかい口語を使います。
初期目的はフォロー、保存、リーチ獲得で、販売やLINE・DM誘導は行いません。

通常テーマはコスメ、スキンケア、メイク、ヘアケア、美容家電、サロンです。
美容医療は通常テーマへ混ぜず、`BEAUTY_MEDICAL` レーンで必ず人間レビューします。

CTAは必須ではありません。約10%の候補だけに、保存・いいね・フォローのいずれか一つを軽く入れます。

## 運用契約

- 状態: `draft_only`
- 投稿先: Threadsのみ
- 生成量: 初期は1〜2件/日
- 生成候補: 全件 `WAITING_REVIEW`
- AUTO_READY: 無効
- 実投稿: handle、Threads user ID、OAuth credential、canary承認まで無効
- PDCA: `account_id=beauty_account` のMEASURED実績だけを使用
- 他アカウントの投稿や学習ルール: 混在禁止

## 5生成ルート

1. `new_text_generation`
2. `reference_text_generation`
3. `pdca_text_generation`
4. `direct_reference_media`
5. `approved_source_clip`

メディアルートは、権利証跡が承認済みになるまで `AWAITING_APPROVED_MEDIA` のままです。
参考情報として使えることと、元メディアを再利用できることは別に判定します。

## 参照元

オーナー指定の22件を `config/source_accounts/owner_reference_sources_20260817.json` に固定しています。
内訳はX 6件、YouTube 9件、TikTok 7件です。現段階では全件 `active=false` / `fetch_enabled=false` で、投稿や取得を自動開始しません。
