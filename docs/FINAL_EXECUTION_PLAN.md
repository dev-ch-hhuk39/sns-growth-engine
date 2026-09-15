# FINAL_EXECUTION_PLAN

仕様確定日: 2026-09-15 JST。対象: sns-growth-engine V1 / Night Scout・Liver Manager・Beauty。

この文書は実装指示書であり、実装済み・本番成功を示す報告書ではない。今回実施したのはコード・GitHub・本番Sheetsの読み取り監査のみ。コード変更、dispatch、commit、push、PR、本番書込み、投稿は実施していない。既存の `.runtime/` は変更しない。

## 1. Current production truth

### 1.1 正本と検証範囲

- GitHub main / local HEAD: `9c4d4fa0b6266c04e96edb2b50e8b42d45fc4af3`。open PR: 0件。local branch: `fix/vps-buffered-runtime`。
- PR #294〜#306はmainへmerge済み。#294がbuffered基盤、#295〜#304が準備・取得・caption・quotaの修正、#305がoffline reserve、#306がSheets RAW保存・文字列read-after-write修正。
- #306 head `135e5ffcf3e67533ce4fca333d755721246ed661` のfull CI `34922130708` は成功。前回実行のrepository regressionは910 PASS。今回テストを再実行していない。これらは本番自律運用の成功証拠ではない。
- 既存補充run `34944560802` は監査時点でもin_progress。検証SHAは上記main。Nightの `Refill validated non-AI emergency bank` 実行中で、Liver/Beauty完了とは扱わない。run終了を待つために本監査を無期限延長しない。
- 本番Sheets観測: `2026-09-15T17:17:26+09:00`。読み取り専用OAuth scopeを使用。補充runは同時進行なので、全タブが同時刻のtransaction snapshotであるとは主張しない。

| 項目 | Night Scout | Liver Manager | Beauty |
|---|---:|---:|---:|
| 現行72h coverageの充足text slots | 9/9 | 0/9 | 3/3 |
| 使用可能bank件数: public/hybrid/hash/履歴検査 | 18 | 0 | 30 |
| 単純なqueue READY行数 | 112 | 69 | 79 |
| metrics jobs: COMPLETE / FAILED / SCHEDULED / CANCELLED | 75 / 15 / 30 / 12 | 90 / 15 / 39 / 12 | 71 / 0 / 25 / 0 |
| real_post + READ_AFTER_WRITE_PASS + media識別子ありの過去記録 | 7 | 7 | 0 |

全体coverageは12/21 = **57.14%**。現行coverageは「各text slotに3候補」を要求し、bankによる充当可能性とmedia枠のtext fallbackを集計しない。READY総行数は使用可能在庫ではない。今回bank計数ではpublisherを呼ばず、最終publisher dry-runまで再検証した件数とは区別する。

media READYの直近確定値は3アカウントともdirect/clip各0。これは準備run `34921582346` と前回readinessの値であり、今回全mediaをpublisher dry-runし直した値ではない。

buffered activation: OFF。Xserver primary cron: 未設置。GitHub Recoveryは既存legacy経路を含む状態。したがって **PRODUCTION_AUTONOMOUS=未達**。

### 1.2 Xserver・既存証跡

- SSH接続済み、GitHub runner `sns-growth-xserver` online確認済み。既存サービスのuserは `snsrunner`。runner rootは `/opt/github-runners/sns-growth-engine`。
- 現在のrunner checkoutは古いrevisionであり、本番常設runtimeとして利用しない。専用venv・cron・常設credential同期は未設置。既存の別業務cronは触らない。
- 前回確認の空きdiskは約6.9GB。専用runtimeにはpublish用依存だけを入れ、動画・ASRモデルをVPSへ複製しない。
- Nightの過去media permalink: https://www.threads.com/@kyaba_consul_mizu/post/Dc_Cf0DjxIm
- Liverの過去media permalink: https://www.threads.com/@ran.liver_pro/post/Dc_pNB7DmGl
- 上記は既存pipelineの限定的な本番証拠。新しいXserver scheduler、Beauty media、全media routeの成功を代替しない。再投稿せず、WP4の証跡互換性条件で評価する。

### 1.3 media READY 0の実データ分類

準備run `34921582346` はNight 10、Liver 37、Beauty 50候補を最終候補評価で確認。下記拒否理由は重複計上であり合計しない。

| 種別 | 観測 | 判定 |
|---|---|---|
| candidate / acquisition | Nightは新規materialization 0、外部取得不能5件。LiverとBeautyはそれぞれ5 bundlesの新規materializationあり | 全SNSで動画取得不能ではない。特定候補の取得不能はB、失敗後の無限再試行はA |
| rights | 現行の権利gateを通らない素材は使用不可。今回の集計から権利不足件数を捏造しない | 個別permission不足はB。照合の実装不良だけA |
| account fit | source evidence不足: Night 5 / Liver 24 / Beauty 35。media evidence不足: 7 / 9 / 28 | 実際に無関係・説明不足ならB。Beautyの正当な美容用語認識漏れはA |
| transcript / understanding | ASR証拠があってもvision要約が空のレコードあり。aggregate PASSをvision成功と誤読できるprovider表示 | 空visionをPASSにする・provider誤表示はA。音声や内容から根拠が得られない素材はB |
| source text | Liverはsource_post_text_unusable 10、Beauty 2。Nightには店舗名と短い質問だけの本文あり | 根拠不足の個別素材はB。取得時の本文欠落ならA |
| caption / alignment | topic mismatch、短文、unsupported copyedit、元投稿にない体験の移転等 | 生成・伝達・再試行契約の不良はA。素材が主張を支えないならBで除外 |
| provider | `GeminiRuntimeError:http_0` などで本当の理由が失われている | まずA: 構造化理由保持。認証/上限/一時障害を判別してからBとする |

「account-fitで拒否されたからvalidatorを緩める」は禁止。Beautyではチーク・洗顔・美容液など正当な用語と現行辞書の不一致をpositive/negative fixtureで確認して修正する。全拒否を辞書のせいにもしない。

## 2. Root causes remaining

| ID | 分類 | 残原因と固定する対応 |
|---|---|---|
| A1 | A | 実在するslot在庫・bankが不足。有限catalog、履歴重複、補充中のquota/品質停止を一括検証してWP1で閉じる |
| A2 | A | coverageがbank充当・media fallbackを評価せず、readinessとruntimeの使用可能判定が一致しない。共通の副作用なし判定を使用する |
| A3 | A | Sheets claimはread→writeでCASではない。GitHub concurrencyは外部cronを排他しない。投稿主体を同一VPS実行入口に限定する |
| A4 | A | primary cron/runtime/credential refresh連携が未設置。config activationとGitHub変数の二重正本、legacy publishとのcutoverも未完 |
| A5 | A | media理解の空結果表示、Beauty用語認識漏れ、providerエラー情報欠落、失敗候補の再評価制御をWP3でまとめて修正 |
| A6 | A | readinessがmedia在庫不足・全legacy台帳の欠損をdevelopment failureへ直結。空external IDや同一IDの台帳重複を実二重投稿と混同 |
| A7 | A | `feature_attribution.build_observations` はsnapshotをresult_idだけでjoinし、snapshotのaccount一致/MEASUREDを明示要求していない。実際に混線した証拠ではないが契約上の穴 |
| A8 | A | aftercareは全accountを1job、metrics最大20/日。12投稿/日×3窓なら定常最大36 jobs/日でbacklogが増える。読取失敗を空データへ変えるattribution入口も修正 |
| B1 | B | 権利確認済み・対象アカウントに適合・必要根拠を含む素材が存在しない場合 |
| B2 | B | 個別素材への実アクセス拒否、期限切れ許可、削除投稿、外部APIの提供しない指標 |
| B3 | B | 不足が実確認されたcredential/サービス権限。SSH自体は取得済みで、未設置runtimeを外部blockerとは呼ばない |

PR306のRAW修正は再設計しない。今後の429は要求回数・batch境界・retryをWP1で一度に閉じ、エラー1件につきPRを増やさない。

## 3. Frozen architecture

### 3.1 Prepareとpublishの分離

GitHubの既存取得・準備workflows → account別のcanonical queue/evergreen/media READY → **同一VPS上のreconciler** → publisher → posted_results/metrics jobs。準備系は投稿権限を持たない。publisherは生成・download・ASR・Cloudinary uploadを行わない。

textは既存AI生成をprimary、既存offline catalogをAI停止時の予備とする。offlineだから品質検査不要とはしない。承認はcanonical本文hash・account・profile versionと結び付け、変更時失効する。

mediaは既存direct/approved clipのみ。権利→取得→理解→caption→全gate→READYを準備側で完結。元の縦横比、parentとmedia順序、public_post_textのみ公開、Beauty complianceを維持する。権利不明素材をownedと偽らない。新しいsynthetic media機能を追加しない。

media不足時はreconcilerが**別の検証済みtext queue**をconsumeする。media queueをtextに変形しない。slotに `expected_type=media`, `actual_type=text_fallback`, `expected_route`, `actual_route`, `fallback_reason=NO_READY_MEDIA` を保存。media delivery成功には数えない。

### 3.2 スケジュールと単一publisher

- 正本は `content_schedule.slots_for_account`。Night: 14/16/18/21/25時、Liver: 10/13/16/18/21時、Beauty: 11:30/20:30。25時は前営業日所属の翌01時。Beauty20:30のroute cycleは現行設定を維持。
- primary: Xserver cron `*/5 * * * *`。起動時刻ではなくJST target時刻からdue判定。現在のjitter=0を維持。正常時はtargetから10分以内を受入基準とし、外部障害時まで正刻保証とは言わない。
- secondary/recovery: 既存 `content-slot-recovery.yml` を同じself-hosted VPSの同じlauncherへ接続。GitHubだけで別ubuntu publisherを動かさない。
- accountごとのOS `flock` をpublish開始前から永続化確認まで保持。3アカウントは独立プロセス・独立lock。GitHub手動exact publishもこの入口外から本番投稿不可。
- VPS全停止を別hostから自動代行しない。Sheetsだけでsplit-brainを解決したことにしない。VPS復旧後のrecoveryと明示alertを保証する。高可用性の別DB/分散lock導入は今回の非対象。
- recovery窓は既存240分。1account/1起動最大1件、daily cap/cooldownを維持。曖昧なpublishは再送禁止。古いslotの再投稿で帳尻を合わせない。

### 3.3 在庫と保証範囲

72h全slotに一意な使用可能候補を割り当てる。text slotsは既存目標3件/slotを維持し、media slotsには少なくともtext fallback 1件/slotを別確保。さらに未割当bankを各30件保持する。1 queue/hashを複数slotやbankへ二重計上しない。

AI停止の受入保証は**完全停止した状態で次72hを賄えること**。有限catalogが無期限に未使用投稿を生めるとは主張しない。現在のcatalogが履歴除外後に容量不足なら、このWP内で安全な独立テーマを追加し上記容量まで埋める。閾値変更・語尾替え量産・POSTED再利用は禁止。復旧しない長期障害と将来の枯渇はremaining_hoursで通知し、無限継続と表示しない。

### 3.4 正本と安全

buffered実行正本は `config/production_inventory.json`。`BUFFERED_INVENTORY_ACTIVE` GitHub変数は互換mirrorであって独立判定元にしない。mirror不一致は明示cutover failure。kill switchは従来の正本を維持し、全実行入口で優先する。

Sheetsは引き続き台帳。新DB・新queue serviceを導入しない。読み取りsnapshotは1準備batch内で再利用可能だが、claim後のqueue・permission・保存照合には未cacheの再読を使用する。投稿直前の安全検査を削らない。

## 4. Exact remaining work packages

### WP1: 実在するAI非依存在庫と共通runtime判定

**Objective:** Night/Liverの不足を解消し、全3アカウントの72h coverageとbank30を本番Sheetsで実証する。

**Files/modules:** `scripts/maintain_text_ready_inventory.py` (`replenish`, `replenish_bank`, `_run`), `scripts/production_inventory.py` (`coverage`, `eligible_ready`, `select_evergreen`), `scripts/evergreen_inventory.py` (`admit_bank_batch`, `allocate_bank_candidate`), `scripts/offline_original_catalog.py`, `config/offline_original_posts.json`, `scripts/generate_threads_ideas_from_references.py` (`run_offline_original_generation`, `_append_missing`), `scripts/run_hybrid_ai_queue_gate.py`, `scripts/run_hybrid_ready_pipeline.py`, `src/sheets_record_reader.py`, `.github/workflows/autopilot-auto-ready.yml`。既存testsを拡張する。

**Exact behavior:**

1. `34944560802` の終了結果・account別artifactを先に読む。進行中は同一accountの補充を重複起動しない。実際の候補reject理由を採取し、public/voice/duplicate/RAW/provider/quotaに分類する。
2. `production_inventory.py` に副作用のない共通inventory eligibility関数を置き、coverage、maintainer、bank、reconciler候補選定、readinessが同じ根拠を使用。外部providerを呼ばず、保存された承認証拠のhash/version/期限を検証する。process_oneの最終checkは維持。
3. coverageにはslot別 `primary_ids`, `backup_ids`, `allocated_bank_ids`, `media_fallback_ids`, `coverage_status` を返す。一意account+queue ID+正規化hashで予約し、未来slotの横取り・bankの二重計数を禁止。現在と将来のslot日付をJSTで扱う。
4. AI用routeを使い切ったら同run内でofflineへ切替。provider budget/auth停止後は次slotで同じ有料呼出しを繰り返さない。offlineはGemini/GitHub ModelsへのHTTP呼出し0。quality不合格は別テーマで最大5候補、bank batch最大10を維持し、枯渇はQUALITY_EXHAUSTEDとして理由付きで停止する。
5. 全体に十分な未使用catalog容量があるか先に計算する。必要容量は72h text slot数×3 + media slot数×1 + 未割当30。現行slot数ならNight/Liverは各63、Beautyは42が目安。履歴・意味類似除外後の**実使用可能数**で満たす。単なるJSON行数では判定しない。
6. 生成batchでqueue/drafts/履歴/quality evidenceを一度batch read。列追加確認も1run1回。書込みをbatch化しPR306のRAW保存を維持。書込み直後は対象行をuncached再読し完全一致。429/5xxは既存bounded backoffを共用する。
7. bankと72hの補充を再開可能にし、部分成功したREADYを再生成しない。approval rejectionは理由を返す。1account失敗で他accountを中断しない。prepareはpublish env falseのまま。

**Tests required:** 3accounts×AI HTTP全禁止×72h割当、同hash/queueの二重割当、過去/future/POSTED排除、Beauty voice/compliance、catalog量不足、429→回復/枯渇、RAW数値文字列/式風文字列、部分成功後再開、キャッシュ後の書換えをRAWで検出、prepared判定とpublisher dry-runの一致。

**Production verification:** 既存Autopilot workflowをコード完成後にaccount別補充。実Sheetsで72h coverage100%、media slot fallback coverage100%、各未割当bank>=30、採用queueのpublisher dry-run PASSを確認。AIを無効にした同一runtimeのreadonly選定で全slot充足し、provider呼出し0を記録する。

**Rollback condition:** account混線、承認hash不一致、誤READY、literal破損で補充停止。新規対象行だけ非投稿化し、既存POSTEDには触れない。実装rollbackで保留行を勝手にREADYへ戻さない。

**DoD:** 上記live在庫条件とfocused testsが全部PASS。quality gateを通せないLiver在庫をBと呼んで未完了のまま進めない。公開本文に内部PDCA情報を混ぜない。

### WP2: Xserver単一publisher・cutover・recovery

**Objective:** 既存reconcilerを実scheduleから安全に動かし、GitHub遅延と二重起動を切り離す。

**Files/modules:** `scripts/reconcile_due_production_slots.py` (`reconcile`, `candidates`, `verify_delivery`), `scripts/content_slot_runs.py` (`claim_slot_run`, `release_unpublished_claim`), `scripts/run_scheduled_text_slot_pipeline.py`, `scripts/scheduled_publish_activation_gate.py`, `config/production_inventory.json`, `src/publishers/threads_credentials.py`, `.github/workflows/content-slot-recovery.yml`, `.github/workflows/refresh-threads-tokens.yml`、既存account別publish workflows。必要な新規運用ファイルは `scripts/run_buffered_production_host.sh` と `scripts/install_buffered_production_runtime.sh` の2本以内。新しい監査workflowは作らない。

**Exact behavior:**

1. runtimeを `/opt/github-runners/sns-growth-engine/.buffered-runtime/releases/<sha>` と `current` symlink、共有stateを同ディレクトリ配下の `shared` に固定。これはrunnerの可変 `_work` checkout外で、実行userが書込可能な専用領域である。venvはrequirementsから必要publish依存を固定導入。release検証後だけatomic切替。
2. launcherは固定列挙3accountsのみ、固定runtime/venvを使用。account別lockを共有stateに置き `flock -n`。lock済みはALREADY_RUNNING。cronとself-hosted GitHub recoveryが同一launcherを呼ぶ。ユーザー入力shell展開・任意コマンド実行は禁止。
3. cronは既存snsrunner crontabへ管理marker付きで1エントリ追加し、既存cronを保持。5分ごとにaccount別独立実行。bounded各10分、1account1件。timeout中にpublisherを強制終了した場合はpersistent attemptをUNCERTAIN扱いにして再送不可。OSlock解放だけで安全と判断しない。
4. GitHub recoveryは既存self-hosted labelsを使用し、production environment・main限定でlauncherを呼ぶ。PR/外部forkはこのrunnerに載せない。従来ubuntu publish jobsはcutover後no-opまたは同入口へ転送。手動workflowも迂回禁止。古い実行が残った状態でcutoverしない。
5. production secrets初期配置は既存GitHub environmentから承認済みruntime設定手順で行う。ファイル0600、directory0700、非git・非artifact・ログ非表示。3accounts token/user ID/expected handleを既存resolverで個別照合する。
6. 既存token-refresh workflowを同runtimeのaccount token storeへ安全に接続する。refresh成功tokenをatomic保存しread/credential self-check、必要なGitHub secret更新も既存方式で同期。raw tokenをjob output/artifactにしない。失敗は古いtokenを破壊せずexpiry alert。GitHub書換権限不足が実確認された場合だけ具体的blockerにする。
7. runtimeはactual triggerを `xserver_cron` / `github_schedule_recovery` / `manual` として記録。host execution ID、code SHA、started_at、slot ID、queue/result ID、verificationを既存slot台帳へ保存。GitHub event/run IDをcron用に捏造しない。
8. metadata claimのfresh ownership確認も追加。ただしこれを分散lockと呼ばない。全publish経路のVPS集約を排他保証にする。出力はPOSTED_PRIMARY/POSTED_FALLBACK/ALREADY_POSTED/SAFETY_BLOCK/RECOVERY_REQUIRED/OPERATIONAL_FAILUREを区別する。
9. source/mediaがなくても割当済みtext fallbackをconsume。AI/取得をslot処理から呼ばない。cap/cooldownで見送ったslotも理由を記録。240分を超える過去slotを無断backfillしない。
10. cutoverは旧publisher停止→稼働中attempt確認→runtime dry-run→credential/在庫条件確認→configとmirror整合→cron有効化の順。kill switchは全launcherで読み、読み取り失敗時fail-closed。

**Tests required:** 同時cron+GHA+手動でpublish1回、3account独立、lockプロセスcrash、API timeout/429/5xx、publish成否不明で再送0、POSTED保存失敗後reconcileのみ、24/72/168 jobsのexact3、25時境界、cap/cooldown、未来stock横取り禁止、host revision/triggerの真正記録、全旧workflow迂回不可、token refresh/旧token保持・account非混線。

**Production verification:** 各accountで実cron起動から新規due slot1件以上、permalink/正しいaccount/queue POSTED/RAW/3metrics予約を確認。cronとsecondaryを同時起動して二重投稿0。recoveryは同既存slotを再判定しALREADY_POSTED、missed-slot recovery本体はfixture clockで240分境界まで検証。cron開始だけではACTIVE判定しない。

**Rollback condition:** 二重投稿/誤account/不明publishで即kill switch、cronとlegacy双方停止。過去releaseへの切替は可能だが、旧schedulerを自動で再開しない。新規POSTED・idempotency・metrics記録は保持する。

**DoD:** Xserver実起動と正常投稿が3accountで確認でき、GitHub secondaryが同入口を呼び、無生成consume/recovery/refresh/kill switchが試験済み。VPS停止時の独立host failoverはDoDに含めない。

### WP3: Media準備の確定修正と在庫不足の終了条件

**Objective:** 既存direct/clip経路の実装不良だけをまとめて閉じ、素材不足を正確にreportする。

**Files/modules:** `scripts/run_direct_media_preparation_loop.py`, `scripts/run_direct_reference_media_pipeline_batched.py`, `scripts/ingest_direct_reference_media_reliable.py` (`select_pending_media_id`, `external_unavailable_cooldown_active`), `src/media/direct_content_understanding.py` (`vision_summary`, `analyze_local_media`), `src/generation/source_grounded_caption.py`, `scripts/media_activation_source_suitability.py`, `scripts/inventory_media_activation_sources.py`, `scripts/run_media_production_pipeline.py`、既存account profileのevidence terms、`.github/workflows/media-preparation-scheduler.yml`, `.github/workflows/approved-source-clip-preparation.yml`, `.github/workflows/direct-media-preparation.yml`。

**Exact behavior:**

1. 保存済みrights-valid素材を先に処理。なければ既存bounded acquisition routerへ。各sourceのscan上限・全体予算・backoffを増やさない。Liver/Beautyでmaterialized済みの候補を再downloadせず、queue READYまで進められるか検証する。
2. 根拠はmodality別status/hash/provider/versionとaggregateを分離。空dict/空summaryをvision PASSにしない。ASRだけ成功した場合はASR成功と明記し、vision成功を偽らない。transcript全文・動画ファイルを新たな外部AIへ送る範囲は拡大しない。
3. canonical account profileの用語とsuitability辞書を一致させる。Beautyの実美容語を追加する際は同語を含む無関係広告/他account例をnegative testsにする。source/mediaの双方に実根拠を要求する現行閾値は維持。
4. captionへ許可済みの取得本文・既存grounding要約を欠落なく渡す。短い本文から不明な店舗事情や本人の体験を補わない。full transcriptが必要でも送信同意がない範囲は自動拡張せず、その候補をEVIDENCE_INSUFFICIENTとする。
5. provider errorをauth_missing/auth_rejected/quota_exhausted/rate_limited/timeout/invalid_response/internal_errorへ分類し、fallbackでも原因を保持。http_0だけで終わらせない。同一入力でretryは既存上限、恒久エラーは同runで再呼出ししない。
6. 失敗候補はsource content hash+permission hash+understanding version+caption versionで評価済みを識別。入力や実装修正versionが変わるまで同run再評価しない。caption改善可能時だけ別候補/別構成を既存上限で試す。no stockでもtextへのmedia偽装はしない。
7. 既存inventory評価の2account固定箇所をmanaged registryの3account対象へ揃える。候補単位にprimary exclusion reasonと詳細reason配列を残す。reason件数は重複集計であることを明示。
8. 既存prepare schedulerで3account direct/clipの独立補充を継続。各route目標3、理想7は維持。ただしstock<3だけでsoftware FAILにしない。deadline付きbounded runで尽きたらRESOURCE_SHORTAGE、実装例外/保存不整合はPREPARATION_FAILEDと区別。

**Tests required:** 3accounts×direct/clip、rights不明/期限切れ/parent mismatch、元縦横比、source順序、ASR-only/空vision、Beauty語彙positive/negative、caption誤帰属、provider分類保持、入力不変の再downloadなし、account別circuit、media不足時slotは別textへ明示fallback、media pipeline自体はtext成功を返さない。

**Production verification:** 既存準備workflowを1bounded cycle実行。素材が適合するならCloudinary/provenance/全gate/READY/RAWまで確認。失敗は候補単位の分類表へ。今回利用可能な素材が尽きたらそこでavailability判定を確定し、quota/権利/素材をコードで捏造せずWP4へ進む。

**Rollback condition:** rights/parent/account/geometry/公開本文に誤りが出た場合その新規media queueだけ隔離し、投稿対象から除外。text補充・正常アカウントは継続。既存Cloudinary assetやPOSTEDを削除しない。

**DoD:** 実装バグ分類が0、shared pipelineの全route契約tests PASS、適合素材を実際にREADYまで通すか物理的拒否理由が確定。MEDIA_INVENTORY_AVAILABILITYがLOWでも終了できる。未実証のmedia deliveryをPASSにしない。

### WP4: Metrics/PDCAと証拠ベースの有限production acceptance

**Objective:** コード完成と本番運転と資源不足を分け、現行mainから再現できる1つのacceptance出力へ統一する。

**Files/modules:** `scripts/run_production_readiness_acceptance.py` (`evaluate`), `scripts/process_threads_metric_jobs.py`, `scripts/run_growth_attribution_cycle.py` (`_read_tab`), `src/learning/feature_attribution.py` (`build_observations`, `build_attributions`), `scripts/generate_threads_ideas_from_references.py` (`build_measured_pdca_inputs`, `run_reference_generation`), `scripts/prepare_beauty_review_candidates.py`、`.github/workflows/production-autopilot-aftercare.yml`, `.github/workflows/ci.yml`, `GOAL.md`, `README.md`, `config/goal_acceptance.json`, `config/production_capability_matrix.json`、現行roadmap。新しい監査script/workflowを増やさない。

**Exact behavior:**

1. `evaluate` の結果を `development_complete`, `production_autonomous`, `text_ready_72h`, `ai_independent_text_fallback`, `media_pipeline_capability`, `media_inventory_availability`, `media_delivery`, `scheduler`, `metrics`, `pdca`, `operational_failures`, `resource_constraints`, `legacy_audit` に分離する。判定の根拠IDと観測時刻を保存。
2. `MEDIA_PIPELINE_CAPABILITY` はcode proofとlive proofを分ける。3accounts×direct/clipの厳格contract/E2E fixture testsがcode proof。live proofは個別routeの実素材→READY→正しい形式で投稿→RAW→metrics予約。既存証拠もsource/permission/asset hash/caption/実投稿/現在のguard互換性が再読で一致する場合に限り採用する。Night/Liverの7記録を自動的に全能力PASSへしない。
3. 総合media capability PASSは対象routeのcodeとlive proofが揃ったときだけ。素材がないrouteはlive UNVERIFIED + resource理由を保持。これはsoftware code completionとは別。Beauty実media未実証などaccount別delivery行はそのまま未実証と書く。テキストfallbackでmedia PASSにしない。
4. cutover時に新しいacceptance対象の最初のSHA/time/slot IDを記録。新規deliveryは全件exact proof必須。legacy不足は削除せず別集計し、過去64件の欠損を新slotの永続blockerにしない。ただしlegacyの不明publishはduplicate安全判定では引き続き参照。単なる同external IDの台帳重複と、同queueから別external IDができた実二重投稿を区別する。
5. cron evidenceはWP2の実trigger/host execution ID/code SHAで判定する。`workflow_name == Content Slot Recovery` 固定条件を除き、GitHub偽装なしでprimary/secondaryの真正証跡を評価する。config ONのみではACTIVE不可。
6. aftercareをaccount matrix・fail-fast false、1時間ごと、各account最大20 due jobs/実行へ。account別読取・batch更新・exact job idempotencyを維持。失敗accountが他accountの収集を止めない。max attempts/backoffは既存契約を使い、待機中を成功取得としない。
7. attributionの読取例外を空配列に変えない。READ_FAILEDとNO_DATAを分離。snapshotはaccount+result_id+platformでjoinし、実測status=MEASURED、実posted、非legacy除外、有限数値、valid windowだけを入力にする。PARTIAL/NOT_AVAILABLE/AUTH_ERROR等は保存するが非測定値を0で補完せず、現行の厳格なMEASURED適格条件を満たさない間は配分変更に使わない。
8. 現行account>=8、feature>=3、confidence>=0.45、exploration floor20%を維持。学習は同accountのtopic等に限定。credential/rights/quality/cap/schedule安全境界は変更不可。weighted topicが次候補生成に入力された `strategy_id`, `evidence_result_ids`, `metrics windows` を内部保存。本文で過去投稿の実績を語らない。
9. 24/72/168 jobs予約は投稿ごとにexact3。既にdueの実jobでcollector保存→RAW→次回PDCA入力を確認。将来時刻を前倒しして本番取得したことにしない。dueがなければfixture clockで3窓を検証し、実取得未到来をPENDING_NOT_DUEと明記する。168時間の待機を開発完了条件にしない。
10. stale failureは既存recovery機構の証拠で解消する。実publish不明は自動再送しない。新規領域のunresolved due text slots=0、system failure非隠蔽を確認。resource shortage+正しいtext fallbackは正常degraded deliveryとする。
11. GOAL/config/matrix/README/roadmapをこの判定に同期。既存安全テストを消して通さない。旧media fallback禁止テストは「media pipeline内の偽fallback禁止」を維持し、「slotが別text queueを明示consume可」を追加する。

**Tests required:** account違いの同result ID、非MEASURED数値入りsnapshot、legacy除外、null指標、window別履歴保持、aftercare一部失敗継続・36jobs/日相当処理、最低サンプル未達、bounded topic反映、公開本文非PDCA、legacy台帳重複と実duplicateの区別、resource不足でもcode completeだがmedia delivery未証明、GHA/cron真正event、future168hをPASS偽装しない。

**Production verification:** WP1/2のlive在庫と各account実cron投稿、既存due metrics取得、内部strategy lineage、次生成入力を既存readinessへ集約。全修正後の同一code SHAでfull CIを1回成功させ、その後に検証対象コードを変更しない。失敗修正が必要なら修正SHAで該当testsと最終full CIをやり直す。

**Rollback condition:** cross-account学習/非実測採用/誤activation判定はstrategy更新停止。投稿本体を無関係な旧aftercareへ戻さない。wrong account/duplicateだけは全publish停止。partial結果を全成功に書き換えない。

**DoD:** code defects 0、full CI PASS、3account実cron deliveryの完全証跡、72h text/fallback inventory充足、metrics/PDCA接続と必要な実測入力確認。将来metricsや物理素材が未到来ならそれだけを別状態で列挙し、開発作業を無期限延長しない。

## 5. Explicit non-work

- buffered architecture、DB、queue service、acquisition frameworkを新規設計しない。
- #306 RAW修正、既存strict validator、account persona、publisher形式、元縦横比維持を理由なく改造しない。
- 素材に合わせてaccount-fit/rights/semantic alignmentを緩めない。未許諾素材をownedへ変更しない。
- X投稿はOFF。Threads参照取得のMeta API化、Beautyの禁止医療表現解禁、字幕・デザイン追加をしない。
- 過去canaryの延命、既存POSTEDの改変、legacy欠損の全件修復、過去mediaの再投稿はしない。
- GitHub停止やVPS停止にも無限に耐えるHA基盤、新規監査workflow、3〜5年分のoffline素材bankなどを追加しない。
- 人工的なmetrics、偽permalink、手動dispatchをcron成功扱い、text fallbackをmedia成功扱いにしない。
- この監査に便乗した実装・本番操作・commit/pushはしない。

## 6. Physical/external blockers

現時点で確定しているものは、一部素材の取得不能・根拠不足・account不適合。すべての素材が存在しないとは確認していない。Liver/Beautyには取得成功素材があり、WP3を先に実行する。

source permissions不足、providerの恒久auth拒否、refresh secret-write権限不足は、個別に存在が確認された場合だけblockerへ追加する。`http_0`、runtime未設置、Liver bank0、Sheets過剰読取429、GitHub cron遅延はそのまま物理blockerにしない。

provider完全停止での無期限新規投稿は、有限在庫だけでは保証不能。今回は72h outage coverageを実証し、長期枯渇はremaining_hoursとalertで明示する。個々のmedia shortageはtextでslotを保護し、media deliveryはDEGRADEDとして公開する。

## 7. Final acceptance command/checklist

以下は**次の実装フェーズで実行する**。本監査では実行しない。新規installer/launcherのCLIもここで固定する。

### 7.1 Local/CI

```bash
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
python3 scripts/validate_source_registry.py
python3 scripts/test_offline_original_ready_reserve.py
python3 scripts/test_production_inventory.py
python3 scripts/test_buffered_generation.py
python3 scripts/test_buffered_reconciler.py
python3 scripts/test_feature_attribution_cycle.py
python3 scripts/test_process_threads_metric_jobs.py
python3 scripts/test_metric_job_batch_writes_and_resume.py
python3 scripts/test_direct_media_preparation_loop_failover.py
python3 scripts/test_direct_media_requires_prepared.py
git diff --check
```

WP内の追加testsも上記既存test entrypointから実行する。full suiteは最終SHAの既存 `CI Security and Regression` workflow_dispatchで一度実施。repository tests、Mypy、secret scan、dependency audit、workflow安全契約を含める。runのcheckout SHAを確認する。

### 7.2 Production手順とコマンド契約

```bash
# 各accountで既存prepare。X投稿/Threads投稿envはfalse。
python3 scripts/maintain_text_ready_inventory.py --account-id night_scout --apply --confirm-ready-maintenance --use-sheets
python3 scripts/maintain_text_ready_inventory.py --account-id liver_manager --apply --confirm-ready-maintenance --use-sheets
python3 scripts/maintain_text_ready_inventory.py --account-id beauty_account --apply --confirm-ready-maintenance --use-sheets
# bank追加は既存CLIの--evergreen-bankを併用。同時に同accountへ実行しない。

# WP2で追加するinstaller: apply/確認なしは計画とread-only検証だけ。
bash scripts/install_buffered_production_runtime.sh --revision <FINAL_SHA> --dry-run
bash scripts/install_buffered_production_runtime.sh --revision <FINAL_SHA> --apply --confirm-install
# installerはインストールまで。activation/cron有効化はWP順序に従い明示--enable-scheduler --confirm-enableを追加して行う。
bash scripts/run_buffered_production_host.sh --account-id all --dry-run

# 実投稿確認はcronで行う。これを手動applyで代替しない。
python3 scripts/process_threads_metric_jobs.py --account-id all --max-jobs 20 --dry-run --use-sheets
python3 scripts/run_production_readiness_acceptance.py --output .ai-tmp/final-acceptance/readiness.json
```

installerはsecretを引数で受け取らず、既存production environmentから渡された環境変数/保護token storeのみ利用する。readinessはread-only scopeを使用し、dry-run中のschema作成や結果更新を禁止する。足りないschemaの明示initializerは既存経路を使用する。

### 7.3 合否の固定

- `DEVELOPMENT_COMPLETE=YES`: WP1〜4のコード・契約・fault injection・full CIがPASS、既知A原因0。将来168hや適合素材の不在をここへ混ぜない。
- `PRODUCTION_AUTONOMOUS=YES`: 実cronの3account新規投稿、permalink、queue POSTED、RAW、duplicate0、exact metrics3jobs、72h text/fallback coverage100%、bank30、recovery/kill switch/refresh接続。人間の日常操作不要。media不足で別textが投稿された場合は明示degraded情報付き。
- `MEDIA_PIPELINE_CAPABILITY`: code/liveを分け、証拠が揃ったrouteだけPASS。全route一括PASSは全対象証拠がある場合のみ。
- `MEDIA_INVENTORY_AVAILABILITY`: account×routeでREADY数、検査時刻、最優先除外理由、次prepare。LOWはLOWのまま。
- `MEDIA_DELIVERY`: 実slotで投稿したmedia queue/result/permalinkだけ記録。text_fallbackは未達であり成功件数0。
- `METRICS`: 予約と実取得を区別。COMPLETE行数だけでは実測確認にならない。未到来windowはPENDING_NOT_DUE、AUTH_ERRORは明示外部blocker。
- `PDCA`: account別MEASURED evidence→strategy→次生成入力まで。最低サンプル未達はOBSERVEで安全に継続。現実に結果が出ていないのに改善効果を断定しない。
- `UNRESOLVED_DUE_TEXT_SLOTS=0`: cutover以降の対象に限る。legacyは別集計・安全dedupe参照を維持。

上記を満たさない状態を「全形式が完璧に本番稼働」と表現しない。一方、software PASSで素材だけ不足ならRESOURCE_SHORTAGEで開発を閉じ、外部待ちを新しいPRへ変換しない。

## 8. Exact implementation order

1. mainが本監査SHAの続きであること、dirty変更、既存補充run結果を確認。既存変更をreset/clean/rebaseしない。
2. 最終完成用branch/PRは1本。WP1 → WP2のコード → WP3 → WP4を実装。各WPのfocused testsだけを途中実行し、個別エラーごとにPRを分けない。
3. WP1のlive在庫検証はpublish=false。WP3のbounded準備でmedia availabilityを確定。新規実素材がないならBとして記録し、追加ライブラリ探索へ拡張しない。
4. WP2はruntime配置・credential/refresh確認・dry-runまで実施し、cron未activationを維持。すべての旧publisher入口と共有lockを確認する。
5. 最終headでfull CI一度、通常merge。mergeでコードが変わった場合は証跡対象SHAを更新して必要検証をやり直す。admin bypassしない。
6. merge SHAをVPSへ配置し、在庫/credential/旧process不在を確認してcutover。Xserver cron/secondary/recoveryを有効化。3accountそれぞれ実due slot1件以上を確認する。
7. metricsの既存due実取得とPDCAへの入力を確認。将来window待ちで開発を延長しない。readinessを最終取得し、development・production・media availability・deliveryを分けて一度報告する。
8. 真の外部blockerのみ残した場合、対象/必要入力/他accountへの影響/安全fallback/再試行条件を明記して停止する。A原因が残る場合はこの4WP内で修正し、第五WP・新アーキテクチャを作らない。
