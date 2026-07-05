"""
sheets_client.py - SNS統合スプレッドシート v2 クライアント

1スプレッドシートで2アカウント（night_scout / liver_manager）を管理する。
12タブの定義・初期化・CRUDをすべてここに集約する。

冪等設計:
  - タブが存在しなければ作成、存在すれば触らない
  - ヘッダーは不足列のみ右端に追加し、既存列を絶対に削除・並び替えしない
  - accountsシードは account_id が存在しない行のみ追加する

dry_run=True のとき書き込みメソッドはすべて print のみで早期リターンする。
認証情報がない場合は make_client() 経由で MockSheetsClient を返す。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from seeds import ACCOUNT_SEEDS_V2, CATEGORY_SEEDS, PROMPT_TEMPLATE_SEEDS

# ------------------------------------------------------------------ #
# タブ定義（ヘッダー列の順序が正式仕様）
# ------------------------------------------------------------------ #

TAB_DEFINITIONS: dict[str, list[str]] = {
    # アカウント設定。2行シード（night_scout / liver_manager）。
    "accounts": [
        "account_id", "account_name", "platform", "note_url",
        "x_handle", "threads_handle", "bio_summary", "target_persona",
        "tone", "main_genre",
        "line_url", "cta_type", "cta_text",
        "auto_publish", "min_publish_score", "brand_risk_threshold",
        "post_time", "timezone",
        "active", "notes",
        # Threads-first recovery columns. Appended for backward compatibility.
        "x_enabled", "threads_enabled", "status",
        "line_cta_enabled", "dm_cta_enabled", "sns_dm_cta_enabled",
        "default_queue_status",
    ],
    # 参考投稿。本文模倣でなく「勝ち要素」を抽出して再利用する。
    "reference_posts": [
        "id", "created_at", "account_id", "platform",
        "post_url", "post_id", "title", "text", "media_urls",
        "likes", "reposts", "impressions",
        "source_type", "author", "published_at",
        "hook_type", "extracted_hook", "extracted_pain",
        "extracted_desire", "reusable_pattern", "imitation_risk",
        "status", "notes",
        # Phase 2.10 追加: X reference collector 移植に必要な列
        "original_text",    # 元投稿の生テキスト（text は要約・整形後）
        "account_handle",   # @ハンドル名（author は表示名）
        "reply_count",      # 返信数
        "bookmark_count",   # 保存数（Xブックマーク）
        "collected_at",     # 収集日時（ISO8601）
        "keywords",         # 収集元キーワード（|区切り）
        # Phase 2.18 追加: video reference pipeline 用列
        "content_type",           # video / text / image
        "video_id",               # プラットフォーム固有の動画ID
        "video_url",              # 動画URL
        "creator_handle",         # 投稿者ハンドル（YouTubeチャンネル等）
        "channel_id",             # YouTubeチャンネルID / TikTokユーザーID
        "channel_name",           # チャンネル名・表示名
        "description",            # 動画説明文
        "duration_seconds",       # 動画長（秒）
        "thumbnail_url",          # サムネイルURL
        "comment_count",          # コメント数
        "raw_payload_json",       # API生レスポンス（JSON文字列）
        "transcription_status",   # pending / processing / done / failed / skipped
        "clip_generation_status", # pending / done / failed / skipped
    ],
    # カテゴリ重み定義。分量配分に使う。
    "content_categories": [
        "category_id", "account_id", "category_name",
        "description", "weight", "examples", "tags", "active",
    ],
    # SNS投稿下書き。body_md を主カラムとし content は後方互換で残す。
    "drafts": [
        "draft_id", "created_at", "account_id",
        "title", "body_md", "content",
        "cta_text", "thumbnail_copy", "source_refs",
        "status", "scheduled_at", "posted_at", "note_url",
        "generation_model", "prompt_version",
        "pv_score", "cv_score", "brand_risk_score", "score", "score_reason",
        "ai_review", "rewrite_count", "post_mode",
        "notes",
        # Phase 2.13-2.15 追加
        "generation_mode", "hypothesis", "media_strategy",
        "imitation_risk", "media_reuse_risk",
        "buzz_potential_score", "conversion_potential_score",
        "confidence_level", "ai_publish_recommendation",
        # Phase 2.21-2.24 追加
        "media_asset_id",     # 使用メディア資産 ID
        "video_clip_id",      # クリップ候補 clip_id
        "source_video_url",   # 元動画 URL
        "source_time_range",  # 元動画の使用区間（例: 00:01:30-00:02:15）
    ],
    # X / Threads 向け派生投稿。draft_id + platform で1行。
    "social_derivatives": [
        "derivative_id", "draft_id", "account_id",
        "platform", "text", "hashtags",
        "status", "reason", "created_at",
        # Phase 2.16 追加
        "char_count", "text_policy_status", "media_asset_id", "media_strategy",
        # Phase 2.21-2.24 追加
        "video_clip_id",      # クリップ候補 clip_id
        "source_time_range",  # 元動画の使用区間
    ],
    # 投稿後の計測結果。PV以外に最終CV（LINE追加・応募等）を追跡。
    "posted_results": [
        "result_id", "draft_id", "account_id",
        "posted_at", "note_url", "title",
        "measurement_window",
        "views", "likes", "comments", "follows",
        "profile_clicks", "line_adds",
        "applications", "site_registrations",
        "screening_requests", "sales",
        "manual_memo", "collected_at",
        # Threads-first recovery columns.
        "platform", "external_post_id", "post_url", "status",
        "queue_id", "derivative_id", "metrics_status",
        "real_post", "media_used", "posted_text",
        "source_queue_status", "save_source", "created_by",
    ],
    # Threads投稿などの計測スナップショット。取得不能値は空欄のまま保存し、0確定と区別する。
    "metric_snapshots": [
        "snapshot_id", "result_id", "account_id", "platform", "post_url",
        "collected_at", "source", "confidence", "metrics_status",
        "views", "likes", "comments", "reposts", "quotes",
        "profile_clicks", "follows", "line_adds",
        "memo", "error_reason",
    ],
    # カテゴリ別パフォーマンス集計。AIが投稿比率を調整するために参照。
    "category_scores": [
        "category_id", "account_id", "category_name",
        "post_count", "avg_views", "avg_likes",
        "avg_cv", "buzz_score", "cv_score",
        "total_score", "recommendation", "last_updated",
    ],
    # 投稿頻度・時間帯ルール。
    "distribution_rules": [
        "rule_id", "account_id", "rule_type",
        "parameter", "value", "description", "active",
    ],
    # AI改善インサイト。有効な知見を蓄積してプロンプト改善に使う。
    "learning_rules": [
        "rule_id", "account_id", "insight_type",
        "content", "source_draft_id",
        "confidence", "applied_count", "created_at", "active",
        "auto_apply", "status",
    ],
    # プロンプトテンプレートのバージョン管理。prompt_version で drafts と紐づく。
    "prompt_templates": [
        "template_id", "account_id", "template_name",
        "version", "purpose", "prompt_text",
        "active", "created_at", "notes",
    ],
    # 投稿キュー。scheduled_at に基づいて自動投稿を実行する（Phase 3以降）。
    "queue": [
        "queue_id", "draft_id", "account_id",
        "platform", "scheduled_at", "priority",
        "status", "error", "created_at", "processed_at",
        "auto_publish",
        # Phase 2.13-2.15 追加
        "generation_mode", "confidence_level", "ai_publish_recommendation",
        "media_asset_id", "text_policy_status",
        # Phase 2.21-2.24 追加
        "video_clip_id",      # クリップ候補 clip_id
        "rights_status",      # unknown / allowed / not_allowed
        "permission_status",  # unknown / granted / denied / not_required
        # Phase 2.28 追加
        "rights_review_required",  # true / false（unknown rights は人間レビュー必要）
        "media_reuse_risk",        # low / medium / high（queue 追加時にコピー）
        "source_video_url",        # 元動画 URL（queue 追加時にコピー）
        "source_time_range",       # 使用区間（queue 追加時にコピー）
        # AUTO_READY（品質・安全スコアでWAITING_REVIEW→READYへ自動承認した記録）。
        "auto_ready_by", "auto_ready_reason", "auto_ready_score", "auto_ready_at",
        "quality_score", "safety_score", "risk_score",
    ],
    # 操作ログ。エラー追跡・実行履歴に使う。
    "logs": [
        "log_id", "timestamp", "account_id",
        "operation", "level", "status", "message", "details",
    ],
    # ------------------------------------------------------------------ #
    # Phase 2.8 追加タブ（reference pipeline / 8:2 strategy）
    # ------------------------------------------------------------------ #
    # メディア資産管理。Cloudinaryに保存した画像・動画を一元管理する。
    "media_assets": [
        "media_id", "account_id", "reference_post_id",
        "source_platform", "source_post_url",
        "original_media_url", "storage_provider", "storage_url",
        "cloudinary_public_id",
        "media_type", "mime_type",
        "width", "height", "duration",
        "reuse_status", "media_reuse_risk", "imitation_risk",
        "downloaded_at", "uploaded_at",
        "used_count", "notes",
        # Phase 2.21-2.24 追加
        "video_clip_id",      # クリップ候補 clip_id との紐付け
        "local_path",         # ローカル切り抜き済みファイルパス
        "rights_status",      # unknown / allowed / not_allowed
        "permission_status",  # unknown / granted / denied / not_required
        "aspect_ratio",       # 16:9 / 9:16 / 1:1 等
        "duration_seconds",   # 動画長（秒）
        "rights_policy", "reuse_policy", "media_policy",
        "allow_download", "allow_cut", "allow_upload", "upload_status",
    ],
    # 参考投稿のパフォーマンス分析結果。スコアリング・分類を保存する。
    "reference_post_scores": [
        "score_id", "reference_post_id", "account_id",
        "performance_score", "buzz_score",
        "like_score", "reply_score", "repost_score",
        "bookmark_score", "impression_score",
        "account_percentile", "keyword_percentile",
        "why_it_grew", "replay_tip",
        "hook_style", "content_angle",
        "media_label", "text_length_bucket",
        "analyzed_at",
        # 質的ルーブリックスコア（score_reference_posts.py / 内容適合の人手評価軸）。
        # performance/buzz とは別軸で「自社アカウントに刺さるか」を 0〜100 で評価する。
        "collected_post_id",          # source_account_posts.post_id への紐付け
        "hook_score",                 # 冒頭フックの強さ
        "insight_score",              # 悩み解決・気づきの深さ
        "cta_score",                  # LINE/DM等への導線の自然さ
        "originality_score",          # 独自性（模倣リスクの裏返し）
        "reuse_risk_score",           # 素材・表現の流用リスク（高いほど危険）
        "total_score",                # 上記の合算/加重
        "reason",                     # 採点根拠（日本語）
        "recommended_use",            # REFERENCE_ONLY / IDEA_SEED など
        "scored_at",                  # 採点日時
    ],
    # ------------------------------------------------------------------ #
    # Phase 2.18 追加タブ（video reference pipeline / transcription）
    # ------------------------------------------------------------------ #
    # 動画収集元管理。YouTube/TikTokの指定チャンネル・アカウントを管理する。
    "reference_sources": [
        "source_id", "account_id", "platform", "source_url",
        "handle", "priority", "active",
        "collection_frequency", "last_collected_at",
        "notes",
        "source_category", "collection_method", "candidate_status",
        "fetch_enabled", "allow_network_fetch",
        "rights_policy", "reuse_policy", "media_policy",
        "allow_download", "allow_cut", "allow_upload",
        "auto_priority_change_allowed", "blocked",
        "review_status", "default_queue_status",
        "future_track", "source_track", "usage_scope",
        "use_policy", "can_reuse_media", "draft_only",
        "beauty_account_status",
        "canonical_url", "post_url", "author_handle",
        "manual_only", "target_account_id", "category",
        "collection_mode", "source_type",
        # 動画参照登録（prepare_video_reference.py）追加。メタ情報のみ。動画/サムネはdownloadしない。
        "title",                      # 動画タイトル（メタ情報）
        "transcript_status",         # PENDING（既定）/ COMPLETED / FAILED
    ],
    # 許可済みチャンネル/アカウントから発見した動画単位のregistry。
    "source_videos": [
        "source_video_id", "source_id", "account_id", "platform", "source_type",
        "source_url", "video_id", "canonical_video_url", "original_video_url",
        "title", "description_preview", "author_handle", "published_at",
        "duration_seconds", "view_count", "like_count", "comment_count",
        "transcript_status", "analysis_status", "clip_candidate_count",
        "download_status", "cut_status", "upload_status", "post_status",
        "rights_status", "permission_status", "discovery_status",
        "discovered_at", "last_seen_at", "processed_at", "skip_reason",
        "content_hash", "duplicate_key",
    ],
    # 動画文字起こし結果。Cloudflare Whisper の出力を保存する。
    "video_transcripts": [
        "transcript_id", "account_id", "reference_post_id",
        "source_platform", "video_url",
        "transcription_provider", "transcription_status",
        "duration_seconds", "transcript_text", "segments_json",
        "language", "processed_minutes",
        "error", "created_at", "updated_at",
    ],
    # 動画クリップ候補。文字起こしから抽出した切り抜き候補を管理する。
    "video_clip_candidates": [
        "clip_id", "account_id", "reference_post_id", "transcript_id",
        "source_platform", "source_video_url",
        "start_time", "end_time", "duration_seconds",
        "clip_title", "hook", "why_it_works",
        "target_persona", "x_post_angle", "threads_post_angle",
        "transcript_excerpt",
        "clip_status",
        "media_asset_id", "storage_url",
        "reuse_status", "media_reuse_risk", "imitation_risk",
        "rights_status", "permission_status",
        "created_at", "notes",
        # Phase 2.21-2.24 追加
        "confidence_score",           # Gemini による候補信頼スコア（0〜1）
        "cut_status",                 # pending / cutting / done / failed
        "local_clip_path",            # ローカル切り抜き済みファイルパス
        "clip_media_asset_id",        # 切り抜き後の media_assets.media_id
        "text_generation_status",     # pending / done / failed
        "generated_draft_id",         # 生成された draft_id
        "generated_at",               # 投稿文生成日時
        # Phase 2.28 追加
        "rights_review_required",     # true / false（human review required）
    ],
    # 文字起こし日次実行記録。120分/日の上限管理に使う。
    "transcription_runs": [
        "run_id", "date", "provider",
        "daily_limit_minutes", "used_minutes", "remaining_minutes",
        "processed_count", "skipped_daily_limit_count", "failed_count",
        "status", "created_at", "notes",
    ],
    # 8:2投稿生成計画。アカウント・プラットフォームごとの生成ルールを管理する。
    "generation_jobs": [
        "job_id", "account_id", "platform",
        "generation_mode", "reference_based_ratio", "original_hypothesis_ratio",
        "daily_target_count", "min_reference_score",
        "media_allowed", "max_reference_reuse_per_source",
        "auto_approve_threshold",
        "x_max_chars", "threads_max_chars",
        "active", "notes",
        # Phase 2.13 追加
        "reference_post_id", "reference_post_score_id", "media_asset_id",
        "status", "generated_draft_id", "generated_at",
    ],
    # ------------------------------------------------------------------ #
    # Phase 4.0 追加タブ（Learning / Self-Improvement foundation）
    # ------------------------------------------------------------------ #
    # プロンプト改善提案。Hermes Agent / PerformanceAnalyzer の出力を保存する。
    # 全提案は status=WAITING_REVIEW で保存され、人間の承認が必要（active=true 自動昇格禁止）。
    "prompt_improvement_suggestions": [
        "suggestion_id", "account_id", "created_at",
        "source",              # hermes / manual / performance_analyzer
        "suggestion_type",     # prompt_change / rule_addition / strategy_change
        "target_template",     # prompt_templates.template_id（省略可）
        "current_behavior",    # 現在の挙動の説明
        "suggested_change",    # 提案する変更内容
        "reason",              # 変更理由・根拠データ
        "expected_impact",     # 期待効果（例: X文字超過率 -20%）
        "priority",            # high / medium / low
        "status",              # WAITING_REVIEW / APPROVED / REJECTED
        "reviewed_by",         # human / auto（自動承認は禁止）
        "reviewed_at",         # レビュー日時
        "notes",
    ],
    # ------------------------------------------------------------------ #
    # Phase 6 追加タブ（thread_series）
    # ------------------------------------------------------------------ #
    "thread_series": [
        "series_id", "account_id", "platform", "theme",
        "hook", "status", "post_count",
        "created_at", "updated_at", "notes",
    ],
    "thread_series_posts": [
        "post_id", "series_id", "account_id", "platform",
        "post_order", "text", "media_asset_id",
        "char_count", "status",
        "created_at", "notes",
    ],
    # ------------------------------------------------------------------ #
    # Phase 8 追加タブ（content_mix / source_registry / preflight / pdca）
    # ------------------------------------------------------------------ #
    # content_mix_plannerの計画記録
    "content_mix_plans": [
        "plan_id", "account_id", "platform",
        "content_type", "status",
        "seed", "force_mode",
        "planned_at", "notes",
    ],
    # source account registry（設定管理）
    "source_accounts": [
        "source_id", "source_name", "source_platform",
        "source_handle", "source_url",
        "target_account_ids",
        "collection_method",
        "active", "blocked", "priority",
        "min_engagement_rate", "min_views", "top_n",
        "rights_policy", "reuse_policy", "media_policy",
        "notes", "created_at", "updated_at",
        "source_category", "candidate_status", "fetch_enabled",
        "allow_network_fetch", "allow_download", "allow_cut", "allow_upload",
        "auto_priority_change_allowed",
        "review_status", "default_queue_status",
        "future_track", "source_track", "usage_scope",
        "use_policy", "can_reuse_media", "draft_only",
        "beauty_account_status",
        "canonical_url", "post_url", "author_handle",
        "manual_only", "target_account_id", "category",
        "collection_mode", "source_type",
    ],
    # source account別の収集した投稿記録
    "source_account_posts": [
        "post_id", "source_id", "account_id",
        "source_platform", "source_handle",
        "post_text", "media_urls",
        "likes", "reposts", "replies", "views", "bookmarks",
        "engagement_rate", "buzz",
        "rights_policy", "reuse_policy",
        "status", "collected_at",
        # 収集/インポート系（collect_reference_posts.py / import_reference_urls.py）追加。
        "post_url",                   # 元投稿URL。重複検知キー（同一URLは再収集しない）。
        "use_status",                 # REFERENCE_ONLY（既定）/ IDEA_SEED。自動投稿対象にはしない。
        "rights_status",             # unknown / reference_only（既定）。許諾未確認は流用不可。
        "can_reuse_media",           # 第三者メディア流用可否。既定 false（許諾なしは流用禁止）。
    ],
    # source collection計画記録
    "source_collection_plans": [
        "plan_id", "account_id", "source_id",
        "platform", "content_type", "top_n",
        "status", "created_at", "notes",
    ],
    # media ingestion実行記録
    "media_ingestion_runs": [
        "run_id", "account_id", "source_id",
        "media_asset_id", "source_url", "media_type",
        "rights_status", "reuse_risk", "media_policy",
        "upload_status", "plan_status",
        "created_at", "notes",
    ],
    # end-to-end preflight実行記録
    "end_to_end_preflight_runs": [
        "run_id", "account_id", "platform", "post_type",
        "queue_id", "series_id", "media_asset_id",
        "overall_status", "pass_count", "fail_count",
        "warn_count", "blocked_count",
        "created_at", "notes",
    ],
    # PDCA実行記録
    "pdca_runs": [
        "run_id", "account_id", "platform", "days",
        "total_results", "suggestion_count", "next_jobs_count",
        "best_content_type", "best_er",
        "created_at", "notes",
    ],
}

TAB_DISPLAY_NAMES: dict[str, str] = {
    "accounts":                       "アカウント管理",
    "reference_posts":                "参考投稿",
    "content_categories":             "投稿カテゴリ",
    "drafts":                         "投稿下書き",
    "social_derivatives":             "SNS投稿文",
    "posted_results":                 "投稿結果",
    "category_scores":                "カテゴリ成績",
    "distribution_rules":             "配信ルール",
    "learning_rules":                 "学習ルール",
    "prompt_templates":               "プロンプト管理",
    "queue":                          "投稿キュー",
    "logs":                           "実行ログ",
    "media_assets":                   "メディア資産",
    "reference_post_scores":          "参考投稿スコア",
    "reference_sources":              "動画収集元",
    "source_videos":                  "参照元動画",
    "metric_snapshots":                "計測スナップショット",
    "video_transcripts":              "動画文字起こし",
    "video_clip_candidates":          "動画クリップ候補",
    "transcription_runs":             "文字起こし実行履歴",
    "generation_jobs":                "生成ジョブ",
    "prompt_improvement_suggestions": "改善提案",
    "thread_series":                  "スレッド構成",
    "thread_series_posts":            "スレッド投稿",
    "content_mix_plans":              "投稿配分計画",
    "source_accounts":                "収集元アカウント",
    "source_account_posts":           "収集済み投稿",
    "source_collection_plans":        "収集計画",
    "media_ingestion_runs":           "メディア取込履歴",
    "end_to_end_preflight_runs":      "投稿前チェック履歴",
    "pdca_runs":                      "PDCA実行履歴",
}

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


# ------------------------------------------------------------------ #
# SheetsClient
# ------------------------------------------------------------------ #

class SheetsClient:
    def __init__(self, sheet_id: str, sa_dict: dict, dry_run: bool = False):
        self.sheet_id = sheet_id
        self.dry_run = dry_run
        self._gc = _auth(sa_dict)
        self._sh = self._gc.open_by_key(sheet_id)
        self._ws_cache: dict[str, gspread.Worksheet] = {}
        self._ws_cache_loaded = False

    # ---------------------------------------------------------------- #
    # セットアップ
    # ---------------------------------------------------------------- #

    def setup_all(self) -> None:
        """全12タブを冪等に初期化し、accounts に seeds.py のアカウントをシードする。"""
        print("[setup] タブ初期化を開始します")
        for tab_name, headers in TAB_DEFINITIONS.items():
            self._ensure_tab(tab_name, headers)
        self._seed_accounts()
        print("[setup] 完了")

    def _ws(self, logical_name: str) -> gspread.Worksheet:
        """論理名（英語キー）または表示名（日本語）でワークシートを取得する。

        表示名が存在すれば優先し、なければ論理名でフォールバックする。
        これにより英語→日本語タブ移行後も既存呼び出しが壊れない。
        """
        if not self._ws_cache_loaded:
            self._ws_cache = {ws.title: ws for ws in self._sh.worksheets()}
            self._ws_cache_loaded = True
        display_name = TAB_DISPLAY_NAMES.get(logical_name, logical_name)
        if display_name in self._ws_cache:
            return self._ws_cache[display_name]
        if display_name != logical_name and logical_name in self._ws_cache:
            return self._ws_cache[logical_name]
        raise gspread.exceptions.WorksheetNotFound(
            f"Worksheet not found: {display_name}"
        )

    def _ensure_tab(self, name: str, headers: list[str]) -> gspread.Worksheet:
        """タブがなければ作成し、ヘッダー不足列を右端に追記する（冪等）。"""
        display_name = TAB_DISPLAY_NAMES.get(name, name)
        try:
            ws = self._ws(name)
        except gspread.exceptions.WorksheetNotFound:
            print(f"  [create] タブ '{display_name}' を作成します")
            if not self.dry_run:
                ws = self._sh.add_worksheet(title=display_name, rows=1000, cols=len(headers) + 10)
                self._ws_cache[display_name] = ws
                if display_name != name:
                    self._ws_cache[name] = ws
                ws.update([headers], "A1")
            else:
                print(f"  [dry-run] タブ '{display_name}' 作成をスキップ")
            return ws if not self.dry_run else None  # type: ignore[return-value]

        existing = ws.row_values(1)
        missing = [h for h in headers if h not in existing]
        if missing:
            print(f"  [update] タブ '{display_name}' にカラムを追加: {missing}")
            if not self.dry_run:
                next_col = len(existing) + 1
                required_cols = len(existing) + len(missing)
                current_cols = ws.col_count
                if required_cols > current_cols:
                    new_cols = max(required_cols + 10, current_cols + 20)
                    print(f"  [resize] タブ '{display_name}' 列数を {current_cols} → {new_cols} に拡張")
                    ws.resize(rows=ws.row_count, cols=new_cols)
                col_letter = _col_letter(next_col)
                ws.update(
                    [[h] for h in missing],
                    f"{col_letter}1",
                    major_dimension="COLUMNS",
                )
        else:
            print(f"  [ok] タブ '{display_name}' のヘッダーは最新です")
        return ws

    def _seed_accounts(self) -> None:
        """accounts タブに night_scout/liver_manager が存在しなければ追加する（冪等）。"""
        ws = self._ws("accounts")
        existing_rows = ws.get_all_records()
        existing_ids = {r.get("account_id", "") for r in existing_rows}

        to_add = [s for s in ACCOUNT_SEEDS_V2 if s["account_id"] not in existing_ids]
        if not to_add:
            print("  [ok] accounts シードはすでに存在します")
            return

        headers = ws.row_values(1)
        for seed in to_add:
            row = [seed.get(h, "") for h in headers]
            print(f"  [seed] accounts に追加: {seed['account_id']}")
            if not self.dry_run:
                ws.append_row(row, value_input_option="USER_ENTERED")

    def seed_tab(self, tab_name: str, rows: list[dict], id_column: str) -> int:
        """指定タブに id_column が存在しない行だけ追加する（冪等）。追加件数を返す。"""
        if self.dry_run:
            print(f"  [dry-run] seed_tab({tab_name}): {len(rows)} 件を確認（書き込みスキップ）")
            return 0
        ws = self._ws(tab_name)
        existing_rows = ws.get_all_records()
        existing_ids = {str(r.get(id_column, "")) for r in existing_rows}
        headers = ws.row_values(1)
        added = 0
        for seed in rows:
            sid = str(seed.get(id_column, ""))
            if sid and sid not in existing_ids:
                row = [str(seed.get(h, "")) for h in headers]
                ws.append_row(row, value_input_option="USER_ENTERED")
                print(f"  [seed] {tab_name}: {id_column}={sid!r} を追加")
                added += 1
        if added == 0:
            print(f"  [ok] {tab_name} シードはすでに存在します")
        return added

    def list_tabs(self) -> list[str]:
        """スプレッドシート上の全ワークシート名を返す。"""
        return [ws.title for ws in self._sh.worksheets()]

    # ---------------------------------------------------------------- #
    # 参照系メソッド
    # ---------------------------------------------------------------- #

    def get_account(self, account_id: str) -> dict | None:
        """accounts タブから account_id に一致する行を返す。"""
        ws = self._ws("accounts")
        for row in ws.get_all_records():
            if row.get("account_id") == account_id:
                return dict(row)
        return None

    def get_active_accounts(self) -> list[dict]:
        """accounts タブから active=TRUE の行をすべて返す。"""
        ws = self._ws("accounts")
        return [
            dict(r) for r in ws.get_all_records()
            if str(r.get("active", "")).upper() == "TRUE"
        ]

    def get_active_categories(self, account_id: str) -> list[dict]:
        """content_categories タブから active=TRUE かつ account_id に一致する行を返す。"""
        ws = self._ws("content_categories")
        return [
            dict(r) for r in ws.get_all_records()
            if str(r.get("active", "")).upper() == "TRUE"
            and r.get("account_id") == account_id
        ]

    def get_reference_posts(
        self,
        account_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """reference_posts タブから条件に一致する行を返す。"""
        ws = self._ws("reference_posts")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_reference_post_by_post_id(self, post_id: str) -> dict | None:
        """post_id に一致する reference_posts 行を返す。なければ None。"""
        ws = self._ws("reference_posts")
        for row in ws.get_all_records():
            if str(row.get("post_id", "")) == str(post_id):
                return dict(row)
        return None

    def save_reference_post(self, post: dict[str, Any]) -> bool:
        """reference_posts タブに1行を保存する。post_id が重複する場合はスキップして False を返す。"""
        if self.dry_run:
            print(f"[dry-run] save_reference_post: post_id={post.get('post_id', '?')!r}")
            return False
        post_id = str(post.get("post_id", ""))
        if post_id and self.find_reference_post_by_post_id(post_id) is not None:
            print(f"[skip] reference_posts: post_id={post_id!r} は既存のためスキップ")
            return False
        ws = self._ws("reference_posts")
        headers = ws.row_values(1)
        row = [str(post.get(h, "")) for h in headers]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True

    def save_reference_posts(
        self, posts: list[dict[str, Any]], *, skip_duplicates: bool = True
    ) -> dict[str, int]:
        """reference_posts タブに複数行を保存する。追加/スキップ/エラー件数を返す。"""
        added = skipped = errors = 0
        for post in posts:
            try:
                result = self.save_reference_post(post)
                if result:
                    added += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[ERROR] save_reference_post 失敗 (post_id={post.get('post_id', '?')}): {e}")
                errors += 1
        return {"added": added, "skipped": skipped, "errors": errors}

    # ---- media_assets ----

    def get_media_assets(
        self,
        account_id: str | None = None,
        reference_post_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """media_assets タブから条件に一致する行を返す。"""
        ws = self._ws("media_assets")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if reference_post_id:
            rows = [r for r in rows if str(r.get("reference_post_id", "")) == str(reference_post_id)]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_media_asset_by_reference_post_id(self, reference_post_id: str) -> dict | None:
        """reference_post_id に一致する最初のアセット行を返す。なければ None。"""
        ws = self._ws("media_assets")
        for row in ws.get_all_records():
            if str(row.get("reference_post_id", "")) == str(reference_post_id):
                return dict(row)
        return None

    def find_media_asset_by_original_media_url(self, original_media_url: str) -> dict | None:
        """original_media_url に一致するアセット行を返す。なければ None。"""
        ws = self._ws("media_assets")
        for row in ws.get_all_records():
            if str(row.get("original_media_url", "")) == str(original_media_url):
                return dict(row)
        return None

    def save_media_asset(self, asset: dict[str, Any]) -> bool:
        """media_assets タブに1行を保存する（reference_post_id + original_media_url でアップサート）。

        dry_run の場合は False を返す。
        """
        if self.dry_run:
            print(
                f"[dry-run] save_media_asset: "
                f"reference_post_id={asset.get('reference_post_id', '?')!r} "
                f"url={str(asset.get('original_media_url', ''))[:60]!r}"
            )
            return False
        reference_post_id = str(asset.get("reference_post_id", ""))
        original_media_url = str(asset.get("original_media_url", ""))
        ws = self._ws("media_assets")
        headers = ws.row_values(1)
        row_data = [str(asset.get(h, "")) for h in headers]
        if reference_post_id and original_media_url:
            all_rows = ws.get_all_records()
            for i, row in enumerate(all_rows, start=2):
                if (str(row.get("reference_post_id", "")) == reference_post_id
                        and str(row.get("original_media_url", "")) == original_media_url):
                    ws.update([row_data], f"A{i}")
                    return True
        ws.append_row(row_data, value_input_option="USER_ENTERED")
        return True

    def save_media_assets(self, assets: list[dict[str, Any]]) -> dict[str, int]:
        """media_assets タブに複数行を保存する。保存/スキップ/エラー件数を返す。"""
        saved = skipped = errors = 0
        for asset in assets:
            try:
                result = self.save_media_asset(asset)
                if result:
                    saved += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[ERROR] save_media_asset 失敗: {e}")
                errors += 1
        return {"saved": saved, "skipped": skipped, "errors": errors}

    # ---- reference_post_scores ----

    def get_reference_post_scores(
        self,
        account_id: str | None = None,
        reference_post_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """reference_post_scores タブから条件に一致する行を返す。"""
        ws = self._ws("reference_post_scores")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if reference_post_id:
            rows = [r for r in rows if str(r.get("reference_post_id", "")) == str(reference_post_id)]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_reference_post_score_by_reference_post_id(
        self, reference_post_id: str
    ) -> dict | None:
        """reference_post_id に一致するスコア行を返す。なければ None。"""
        ws = self._ws("reference_post_scores")
        for row in ws.get_all_records():
            if str(row.get("reference_post_id", "")) == str(reference_post_id):
                return dict(row)
        return None

    def save_reference_post_score(self, score: dict[str, Any]) -> bool:
        """reference_post_scores タブに1行を保存する（reference_post_id でアップサート）。

        reference_post_id が既存の場合は行全体を更新、なければ追記する。
        dry_run の場合は False を返す。
        """
        if self.dry_run:
            print(
                f"[dry-run] save_reference_post_score: "
                f"reference_post_id={score.get('reference_post_id', '?')!r}"
            )
            return False
        reference_post_id = str(score.get("reference_post_id", ""))
        ws = self._ws("reference_post_scores")
        headers = ws.row_values(1)
        row_data = [str(score.get(h, "")) for h in headers]
        if reference_post_id:
            existing = self.find_reference_post_score_by_reference_post_id(reference_post_id)
            if existing:
                col_id = headers.index("reference_post_id") + 1
                cell = ws.find(reference_post_id, in_column=col_id)
                if cell:
                    ws.update([row_data], f"A{cell.row}")
                    return True
        ws.append_row(row_data, value_input_option="USER_ENTERED")
        return True

    def save_reference_post_scores(
        self, scores: list[dict[str, Any]]
    ) -> dict[str, int]:
        """reference_post_scores タブに複数行を保存する。保存/スキップ/エラー件数を返す。"""
        saved = skipped = errors = 0
        for score in scores:
            try:
                result = self.save_reference_post_score(score)
                if result:
                    saved += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[ERROR] save_reference_post_score 失敗: {e}")
                errors += 1
        return {"saved": saved, "skipped": skipped, "errors": errors}

    # ---------------------------------------------------------------- #
    # reference_sources
    # ---------------------------------------------------------------- #

    def get_reference_sources(
        self,
        account_id: str | None = None,
        platform: str | None = None,
        active_only: bool = False,
    ) -> list[dict]:
        """reference_sources タブから条件に一致する行を返す。"""
        ws = self._ws("reference_sources")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if platform:
            rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
        if active_only:
            rows = [r for r in rows if str(r.get("active", "")).upper() == "TRUE"]
        return [dict(r) for r in rows]

    def find_reference_source_by_source_id(self, source_id: str) -> dict | None:
        """source_id に一致する reference_source 行を返す。なければ None。"""
        ws = self._ws("reference_sources")
        for row in ws.get_all_records():
            if str(row.get("source_id", "")) == str(source_id):
                return dict(row)
        return None

    def save_reference_source(self, source: dict[str, Any]) -> bool:
        """reference_sources タブに1行を保存する（source_id でアップサート）。"""
        if self.dry_run:
            print(f"[dry-run] save_reference_source: source_id={source.get('source_id', '?')!r}")
            return False
        source_id = str(source.get("source_id", ""))
        ws = self._ws("reference_sources")
        headers = ws.row_values(1)
        row_data = [str(source.get(h, "")) for h in headers]
        if source_id:
            existing = self.find_reference_source_by_source_id(source_id)
            if existing:
                col_id = headers.index("source_id") + 1
                cell = ws.find(source_id, in_column=col_id)
                if cell:
                    ws.update([row_data], f"A{cell.row}")
                    return True
        ws.append_row(row_data, value_input_option="USER_ENTERED")
        return True

    def update_reference_source(self, source_id: str, **fields: Any) -> bool:
        """reference_sources タブの指定行を更新する。"""
        if self.dry_run:
            print(f"[dry-run] update_reference_source: source_id={source_id!r} fields={fields}")
            return False
        ws = self._ws("reference_sources")
        headers = ws.row_values(1)
        col_id = headers.index("source_id") + 1 if "source_id" in headers else None
        if col_id is None:
            return False
        cell = ws.find(source_id, in_column=col_id)
        if cell is None:
            return False
        for field, value in fields.items():
            if field in headers:
                ws.update_cell(cell.row, headers.index(field) + 1, str(value))
        return True

    # ---------------------------------------------------------------- #
    # video_transcripts
    # ---------------------------------------------------------------- #

    def get_video_transcripts(
        self,
        account_id: str | None = None,
        reference_post_id: str | None = None,
        transcription_status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """video_transcripts タブから条件に一致する行を返す。"""
        ws = self._ws("video_transcripts")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if reference_post_id:
            rows = [r for r in rows if str(r.get("reference_post_id", "")) == str(reference_post_id)]
        if transcription_status:
            rows = [r for r in rows if str(r.get("transcription_status", "")).lower() == transcription_status.lower()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_video_transcript_by_reference_post_id(self, reference_post_id: str) -> dict | None:
        """reference_post_id に一致する video_transcript を返す。なければ None。"""
        ws = self._ws("video_transcripts")
        for row in ws.get_all_records():
            if str(row.get("reference_post_id", "")) == str(reference_post_id):
                return dict(row)
        return None

    def find_video_transcript_by_id(self, transcript_id: str) -> dict | None:
        """transcript_id に一致する video_transcript を返す。なければ None。"""
        ws = self._ws("video_transcripts")
        for row in ws.get_all_records():
            if str(row.get("transcript_id", "")) == str(transcript_id):
                return dict(row)
        return None

    def save_video_transcript(self, transcript: dict[str, Any]) -> bool:
        """video_transcripts タブに1行を保存する（transcript_id でアップサート）。"""
        if self.dry_run:
            print(f"[dry-run] save_video_transcript: transcript_id={transcript.get('transcript_id', '?')!r}")
            return False
        transcript_id = str(transcript.get("transcript_id", ""))
        ws = self._ws("video_transcripts")
        headers = ws.row_values(1)
        row_data = [str(transcript.get(h, "")) for h in headers]
        if transcript_id:
            existing = self.find_video_transcript_by_id(transcript_id)
            if existing:
                col_id = headers.index("transcript_id") + 1
                cell = ws.find(transcript_id, in_column=col_id)
                if cell:
                    ws.update([row_data], f"A{cell.row}")
                    return True
        ws.append_row(row_data, value_input_option="USER_ENTERED")
        return True

    def update_video_transcript(self, transcript_id: str, **fields: Any) -> bool:
        """video_transcripts タブの指定行を更新する。"""
        if self.dry_run:
            print(f"[dry-run] update_video_transcript: transcript_id={transcript_id!r} fields={fields}")
            return False
        ws = self._ws("video_transcripts")
        headers = ws.row_values(1)
        col_id = headers.index("transcript_id") + 1 if "transcript_id" in headers else None
        if col_id is None:
            return False
        cell = ws.find(transcript_id, in_column=col_id)
        if cell is None:
            return False
        for field, value in fields.items():
            if field in headers:
                ws.update_cell(cell.row, headers.index(field) + 1, str(value))
        return True

    # ---------------------------------------------------------------- #
    # source_videos
    # ---------------------------------------------------------------- #

    def get_source_videos(
        self,
        account_id: str | None = None,
        source_id: str | None = None,
        discovery_status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """source_videos タブから条件に一致する行を返す。"""
        ws = self._ws("source_videos")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if str(r.get("account_id", "")) == str(account_id)]
        if source_id:
            rows = [r for r in rows if str(r.get("source_id", "")) == str(source_id)]
        if discovery_status:
            rows = [r for r in rows if str(r.get("discovery_status", "")).upper() == discovery_status.upper()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_source_video_by_id(self, source_video_id: str) -> dict | None:
        """source_video_id に一致する source_video を返す。なければ None。"""
        ws = self._ws("source_videos")
        for row in ws.get_all_records():
            if str(row.get("source_video_id", "")) == str(source_video_id):
                return dict(row)
        return None

    def save_source_video(self, source_video: dict[str, Any]) -> bool:
        """source_videos タブに1行を保存する（source_video_id でアップサート）。"""
        if self.dry_run:
            print(f"[dry-run] save_source_video: source_video_id={source_video.get('source_video_id', '?')!r}")
            return False
        source_video_id = str(source_video.get("source_video_id", ""))
        ws = self._ws("source_videos")
        headers = ws.row_values(1)
        row_data = [str(source_video.get(h, "")) for h in headers]
        if source_video_id:
            existing = self.find_source_video_by_id(source_video_id)
            if existing:
                col_id = headers.index("source_video_id") + 1
                cell = ws.find(source_video_id, in_column=col_id)
                if cell:
                    ws.update([row_data], f"A{cell.row}")
                    return True
        ws.append_row(row_data, value_input_option="USER_ENTERED")
        return True

    def save_source_videos(self, source_videos: list[dict[str, Any]]) -> dict[str, int]:
        """source_videos タブへ複数行を保存する。"""
        saved = skipped = errors = 0
        existing_ids = {str(r.get("source_video_id", "")) for r in self.get_source_videos()}
        for row in source_videos:
            if str(row.get("source_video_id", "")) in existing_ids:
                skipped += 1
                continue
            try:
                if self.save_source_video(row):
                    saved += 1
                    existing_ids.add(str(row.get("source_video_id", "")))
            except Exception:
                errors += 1
        return {"saved": saved, "skipped": skipped, "errors": errors}

    # ---------------------------------------------------------------- #
    # video_clip_candidates
    # ---------------------------------------------------------------- #

    def get_video_clip_candidates(
        self,
        account_id: str | None = None,
        reference_post_id: str | None = None,
        transcript_id: str | None = None,
        clip_status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """video_clip_candidates タブから条件に一致する行を返す。"""
        ws = self._ws("video_clip_candidates")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if reference_post_id:
            rows = [r for r in rows if str(r.get("reference_post_id", "")) == str(reference_post_id)]
        if transcript_id:
            rows = [r for r in rows if str(r.get("transcript_id", "")) == str(transcript_id)]
        if clip_status:
            rows = [r for r in rows if str(r.get("clip_status", "")).lower() == clip_status.lower()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_video_clip_candidate_by_clip_id(self, clip_id: str) -> dict | None:
        """clip_id に一致する video_clip_candidate を返す。なければ None。"""
        ws = self._ws("video_clip_candidates")
        for row in ws.get_all_records():
            if str(row.get("clip_id", "")) == str(clip_id):
                return dict(row)
        return None

    def save_video_clip_candidate(self, clip: dict[str, Any]) -> bool:
        """video_clip_candidates タブに1行を保存する（clip_id でアップサート）。"""
        if self.dry_run:
            print(f"[dry-run] save_video_clip_candidate: clip_id={clip.get('clip_id', '?')!r}")
            return False
        clip_id = str(clip.get("clip_id", ""))
        ws = self._ws("video_clip_candidates")
        headers = ws.row_values(1)
        row_data = [str(clip.get(h, "")) for h in headers]
        if clip_id:
            existing = self.find_video_clip_candidate_by_clip_id(clip_id)
            if existing:
                col_id = headers.index("clip_id") + 1
                cell = ws.find(clip_id, in_column=col_id)
                if cell:
                    ws.update([row_data], f"A{cell.row}")
                    return True
        ws.append_row(row_data, value_input_option="USER_ENTERED")
        return True

    def update_video_clip_candidate(self, clip_id: str, **fields: Any) -> bool:
        """video_clip_candidates タブの指定行を更新する。"""
        if self.dry_run:
            print(f"[dry-run] update_video_clip_candidate: clip_id={clip_id!r} fields={fields}")
            return False
        ws = self._ws("video_clip_candidates")
        headers = ws.row_values(1)
        col_id = headers.index("clip_id") + 1 if "clip_id" in headers else None
        if col_id is None:
            return False
        cell = ws.find(clip_id, in_column=col_id)
        if cell is None:
            return False
        for field, value in fields.items():
            if field in headers:
                ws.update_cell(cell.row, headers.index(field) + 1, str(value))
        return True

    # ---------------------------------------------------------------- #
    # transcription_runs
    # ---------------------------------------------------------------- #

    def get_transcription_run_by_date(self, date: str, provider: str = "cloudflare_whisper") -> dict | None:
        """指定日付・プロバイダーの transcription_run を返す。なければ None。"""
        ws = self._ws("transcription_runs")
        for row in ws.get_all_records():
            if str(row.get("date", "")) == date and str(row.get("provider", "")) == provider:
                return dict(row)
        return None

    def save_transcription_run(self, run: dict[str, Any]) -> bool:
        """transcription_runs タブに1行を保存する（run_id でアップサート）。"""
        if self.dry_run:
            print(f"[dry-run] save_transcription_run: run_id={run.get('run_id', '?')!r} date={run.get('date', '?')!r}")
            return False
        run_id = str(run.get("run_id", ""))
        ws = self._ws("transcription_runs")
        headers = ws.row_values(1)
        row_data = [str(run.get(h, "")) for h in headers]
        if run_id:
            all_rows = ws.get_all_records()
            for i, existing in enumerate(all_rows, start=2):
                if str(existing.get("run_id", "")) == run_id:
                    ws.update([row_data], f"A{i}")
                    return True
        ws.append_row(row_data, value_input_option="USER_ENTERED")
        return True

    def update_transcription_run(self, run_id: str, **fields: Any) -> bool:
        """transcription_runs タブの指定行を更新する。"""
        if self.dry_run:
            print(f"[dry-run] update_transcription_run: run_id={run_id!r} fields={fields}")
            return False
        ws = self._ws("transcription_runs")
        headers = ws.row_values(1)
        col_id = headers.index("run_id") + 1 if "run_id" in headers else None
        if col_id is None:
            return False
        cell = ws.find(run_id, in_column=col_id)
        if cell is None:
            return False
        for field, value in fields.items():
            if field in headers:
                ws.update_cell(cell.row, headers.index(field) + 1, str(value))
        return True

    # ---------------------------------------------------------------- #
    # generation_jobs
    # ---------------------------------------------------------------- #

    def save_generation_job(self, job: dict[str, Any]) -> bool:
        """generation_jobs タブに1行を保存する（job_id でアップサート）。"""
        if self.dry_run:
            print(
                f"[dry-run] save_generation_job: "
                f"job_id={job.get('job_id', '?')!r} "
                f"account_id={job.get('account_id', '?')!r} "
                f"mode={job.get('generation_mode', '?')!r}"
            )
            return False
        job_id = str(job.get("job_id", ""))
        ws = self._ws("generation_jobs")
        headers = ws.row_values(1)
        row_data = [str(job.get(h, "")) for h in headers]
        if job_id:
            col_id = headers.index("job_id") + 1 if "job_id" in headers else None
            if col_id:
                cell = ws.find(job_id, in_column=col_id)
                if cell:
                    ws.update([row_data], f"A{cell.row}")
                    return True
        ws.append_row(row_data, value_input_option="USER_ENTERED")
        return True

    def save_generation_jobs(
        self, jobs: list[dict[str, Any]]
    ) -> dict[str, int]:
        """generation_jobs タブに複数行を保存する。保存/スキップ/エラー件数を返す。"""
        saved = skipped = errors = 0
        for job in jobs:
            try:
                result = self.save_generation_job(job)
                if result:
                    saved += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[ERROR] save_generation_job 失敗: {e}")
                errors += 1
        return {"saved": saved, "skipped": skipped, "errors": errors}

    def get_generation_jobs(
        self,
        account_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """generation_jobs タブから条件に一致する行を返す。"""
        ws = self._ws("generation_jobs")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if platform:
            rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).lower() == status.lower()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_generation_job_by_id(self, job_id: str) -> dict | None:
        """job_id に一致する generation_job 行を返す。なければ None。"""
        ws = self._ws("generation_jobs")
        for row in ws.get_all_records():
            if str(row.get("job_id", "")) == str(job_id):
                return dict(row)
        return None

    def update_generation_job(self, job_id: str, **fields: Any) -> bool:
        """generation_jobs タブの指定行を更新する。"""
        if self.dry_run:
            print(f"[dry-run] update_generation_job: job_id={job_id!r} fields={fields}")
            return False
        ws = self._ws("generation_jobs")
        headers = ws.row_values(1)
        col_id = headers.index("job_id") + 1 if "job_id" in headers else None
        if col_id is None:
            return False
        cell = ws.find(job_id, in_column=col_id)
        if cell is None:
            return False
        row = cell.row
        for field, value in fields.items():
            if field in headers:
                col = headers.index(field) + 1
                ws.update_cell(row, col, str(value))
        return True

    def get_drafts(
        self,
        account_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """drafts タブから条件に一致する行を返す。"""
        ws = self._ws("drafts")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def get_pending_drafts(self, account_id: str | None = None) -> list[dict]:
        """drafts タブから status='draft' の行を返す。account_id でフィルタ可能。"""
        return self.get_drafts(account_id=account_id, status="draft")

    def get_social_derivatives(
        self,
        account_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """social_derivatives タブから条件に一致する行を返す。"""
        ws = self._ws("social_derivatives")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if platform:
            rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_social_derivative(self, draft_id: str, platform: str) -> dict | None:
        """指定 draft_id + platform の social_derivative を返す。なければ None。"""
        ws = self._ws("social_derivatives")
        for row in ws.get_all_records():
            if (row.get("draft_id") == draft_id
                    and str(row.get("platform", "")).lower() == platform.lower()):
                return dict(row)
        return None

    def find_queue_item(self, draft_id: str, platform: str) -> dict | None:
        """指定 draft_id + platform の queue 行を返す。なければ None。"""
        ws = self._ws("queue")
        for row in ws.get_all_records():
            if (row.get("draft_id") == draft_id
                    and str(row.get("platform", "")).lower() == platform.lower()):
                return dict(row)
        return None

    def get_queue_items(
        self,
        account_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """queue タブから条件に一致する行を返す。"""
        ws = self._ws("queue")
        rows = ws.get_all_records()
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if platform:
            rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def get_queue_item(self, queue_id: str) -> dict | None:
        """queue_id に一致する queue 行を返す。なければ None。"""
        ws = self._ws("queue")
        for row in ws.get_all_records():
            if row.get("queue_id") == queue_id:
                return dict(row)
        return None

    def update_queue_item(self, queue_id: str, **fields: Any) -> None:
        """queue タブの指定行を更新する。"""
        if self.dry_run:
            print(f"[dry-run] update_queue_item: queue_id={queue_id} fields={fields}")
            return
        ws = self._ws("queue")
        headers = ws.row_values(1)
        col_qid = headers.index("queue_id") + 1
        cell = ws.find(queue_id, in_column=col_qid)
        if cell is None:
            raise KeyError(f"queue_id={queue_id!r} が queue タブに見つかりません")
        for field, value in fields.items():
            if field in headers:
                ws.update_cell(cell.row, headers.index(field) + 1, str(value))

    def get_prompt_templates(
        self,
        account_id: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        """prompt_templates タブから条件に一致する行を返す。"""
        ws = self._ws("prompt_templates")
        rows = ws.get_all_records()
        if active_only:
            rows = [r for r in rows if str(r.get("active", "")).upper() == "TRUE"]
        if account_id is not None:
            rows = [r for r in rows if r.get("account_id") in (account_id, "")]
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- #
    # 書き込み系メソッド
    # ---------------------------------------------------------------- #

    def save_draft(self, account_id: str, title: str, body_md: str, **kwargs: Any) -> str:
        """下書きを drafts タブに追加する。draft_id を返す。"""
        draft_id = kwargs.pop("draft_id", None) or f"d-{_short_uuid()}"
        if self.dry_run:
            print(f"[dry-run] save_draft: account_id={account_id} draft_id={draft_id} title={title!r}")
            return draft_id

        ws = self._ws("drafts")
        headers = ws.row_values(1)
        data: dict[str, Any] = {
            "draft_id": draft_id,
            "created_at": _now(),
            "account_id": account_id,
            "title": title,
            "body_md": body_md,
            "status": kwargs.pop("status", "DRAFT"),
            **kwargs,
        }
        row = [str(data.get(h, "")) for h in headers]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return draft_id

    def update_draft(self, draft_id: str, **fields: Any) -> None:
        """drafts タブの指定行を更新する。"""
        if self.dry_run:
            print(f"[dry-run] update_draft: draft_id={draft_id} fields={fields}")
            return

        ws = self._ws("drafts")
        headers = ws.row_values(1)
        col_id = headers.index("draft_id") + 1
        cell = ws.find(draft_id, in_column=col_id)
        if cell is None:
            raise KeyError(f"draft_id={draft_id!r} が drafts タブに見つかりません")
        for field, value in fields.items():
            if field in headers:
                ws.update_cell(cell.row, headers.index(field) + 1, str(value))

    def update_reference_post_status(self, post_id: str, status: str) -> None:
        """reference_posts タブの id 列を検索してstatus を更新する。"""
        if self.dry_run:
            print(f"[dry-run] update_reference_post_status: id={post_id} status={status}")
            return

        ws = self._ws("reference_posts")
        headers = ws.row_values(1)
        col_id = headers.index("id") + 1
        col_status = headers.index("status") + 1
        cell = ws.find(post_id, in_column=col_id)
        if cell is None:
            raise KeyError(f"reference_post id={post_id!r} が見つかりません")
        ws.update_cell(cell.row, col_status, status)

    def append_social_derivative(self, derivative: dict) -> str:
        """social_derivatives タブに1行追加する。derivative_id を返す。"""
        derivative_id = derivative.get("derivative_id") or f"sd-{_short_uuid()}"
        if self.dry_run:
            print(
                f"[dry-run] append_social_derivative: "
                f"draft_id={derivative.get('draft_id')} "
                f"platform={derivative.get('platform')} "
                f"status={derivative.get('status')}"
            )
            return derivative_id

        ws = self._ws("social_derivatives")
        headers = ws.row_values(1)
        data = {
            "derivative_id": derivative_id,
            "created_at": _now(),
            **derivative,
        }
        row = [str(data.get(h, "")) for h in headers]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return derivative_id

    def append_queue_item(self, item: dict) -> str:
        """queue タブに1行追加する。queue_id を返す。"""
        queue_id = item.get("queue_id") or f"q-{_short_uuid()}"
        if self.dry_run:
            print(
                f"[dry-run] append_queue_item: "
                f"draft_id={item.get('draft_id')} "
                f"platform={item.get('platform')} "
                f"status={item.get('status')} "
                f"scheduled_at={item.get('scheduled_at')}"
            )
            return queue_id

        ws = self._ws("queue")
        headers = ws.row_values(1)
        data = {
            "queue_id": queue_id,
            "created_at": _now(),
            **item,
        }
        row = [str(data.get(h, "")) for h in headers]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return queue_id

    def mark_posted(self, draft_id: str, note_url: str, posted_at: str | None = None) -> None:
        """drafts タブの該当行のステータスを posted に更新する。"""
        if self.dry_run:
            print(f"[dry-run] mark_posted: draft_id={draft_id} note_url={note_url}")
            return

        ws = self._ws("drafts")
        headers = ws.row_values(1)
        col_id = headers.index("draft_id") + 1
        col_status = headers.index("status") + 1
        col_posted_at = headers.index("posted_at") + 1 if "posted_at" in headers else None
        col_note_url = headers.index("note_url") + 1 if "note_url" in headers else None

        cell = ws.find(draft_id, in_column=col_id)
        if cell is None:
            raise KeyError(f"draft_id={draft_id!r} が drafts タブに見つかりません")

        row = cell.row
        ws.update_cell(row, col_status, "POSTED")
        if col_posted_at:
            ws.update_cell(row, col_posted_at, posted_at or _now())
        if col_note_url:
            ws.update_cell(row, col_note_url, note_url)

    def save_result(self, draft_id: str, account_id: str,
                    measurement_window: str = "24h", **kwargs: Any) -> str:
        """計測結果を posted_results タブに追加する。result_id を返す。"""
        result_id = f"r-{_short_uuid()}"
        if self.dry_run:
            print(f"[dry-run] save_result: draft_id={draft_id} account_id={account_id} window={measurement_window}")
            return result_id

        ws = self._ws("posted_results")
        headers = ws.row_values(1)
        data: dict[str, Any] = {
            "result_id": result_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "measurement_window": measurement_window,
            "collected_at": _now(),
            **kwargs,
        }
        row = [str(data.get(h, "")) for h in headers]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return result_id

    def log(self, operation: str, status: str, message: str,
            account_id: str = "", details: str = "", level: str = "") -> None:
        """操作ログを logs タブに追記する。"""
        if not level:
            s = status.upper()
            if s in ("ERROR", "FAIL", "FAILED"):
                level = "ERROR"
            elif s in ("WARN", "WARNING"):
                level = "WARN"
            else:
                level = "INFO"

        if self.dry_run:
            print(f"[dry-run] log: [{level}/{status}] {operation} - {message}")
            return

        ws = self._ws("logs")
        headers = ws.row_values(1)
        data: dict[str, Any] = {
            "log_id": f"l-{_short_uuid()}",
            "timestamp": _now(),
            "account_id": account_id,
            "operation": operation,
            "level": level,
            "status": status,
            "message": message,
            "details": details,
        }
        row = [str(data.get(h, "")) for h in headers]
        ws.append_row(row, value_input_option="USER_ENTERED")


# ------------------------------------------------------------------ #
# MockSheetsClient — 認証情報なしで動くモッククライアント
# ------------------------------------------------------------------ #

class MockSheetsClient:
    """認証情報・ネットワーク接続なしで動くモッククライアント。

    読み取りは seeds.py のデータを返す。書き込みはインメモリに保持しつつログ表示。
    dry-run パイプライン確認・テスト・CI 向け。
    """

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self._drafts: list[dict] = []
        self._derivatives: list[dict] = []
        self._queue: list[dict] = []
        self._logs: list[dict] = []
        self._posted_results: list[dict] = []

    # ---- 参照系 ----

    def get_account(self, account_id: str) -> dict | None:
        for s in ACCOUNT_SEEDS_V2:
            if s["account_id"] == account_id:
                return dict(s)
        return None

    def get_active_accounts(self) -> list[dict]:
        return [
            dict(s) for s in ACCOUNT_SEEDS_V2
            if str(s.get("active", "")).upper() == "TRUE"
        ]

    def get_active_categories(self, account_id: str) -> list[dict]:
        return [
            dict(c) for c in CATEGORY_SEEDS
            if c.get("account_id") == account_id
            and str(c.get("active", "")).upper() == "TRUE"
        ]

    def get_reference_posts(
        self,
        account_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._reference_posts) if hasattr(self, "_reference_posts") else []
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
        if limit:
            rows = rows[:limit]
        return rows

    def find_reference_post_by_post_id(self, post_id: str) -> dict | None:
        for r in (self._reference_posts if hasattr(self, "_reference_posts") else []):
            if str(r.get("post_id", "")) == str(post_id):
                return dict(r)
        return None

    def save_reference_post(self, post: dict[str, Any]) -> bool:
        if not hasattr(self, "_reference_posts"):
            self._reference_posts: list[dict] = []
        post_id = str(post.get("post_id", ""))
        if post_id and self.find_reference_post_by_post_id(post_id) is not None:
            print(f"[mock-sheets] save_reference_post skip: post_id={post_id!r} 重複")
            return False
        self._reference_posts.append(dict(post))
        print(f"[mock-sheets] save_reference_post: post_id={post_id!r}")
        return True

    def save_reference_posts(
        self, posts: list[dict[str, Any]], *, skip_duplicates: bool = True
    ) -> dict[str, int]:
        added = skipped = errors = 0
        for post in posts:
            try:
                result = self.save_reference_post(post)
                if result:
                    added += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[mock-sheets] save_reference_post error: {e}")
                errors += 1
        return {"added": added, "skipped": skipped, "errors": errors}

    # ---- media_assets (mock) ----

    def get_media_assets(
        self,
        account_id: str | None = None,
        reference_post_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._media_assets) if hasattr(self, "_media_assets") else []
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if reference_post_id:
            rows = [r for r in rows if str(r.get("reference_post_id", "")) == str(reference_post_id)]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_media_asset_by_reference_post_id(self, reference_post_id: str) -> dict | None:
        for r in (self._media_assets if hasattr(self, "_media_assets") else []):
            if str(r.get("reference_post_id", "")) == str(reference_post_id):
                return dict(r)
        return None

    def find_media_asset_by_original_media_url(self, original_media_url: str) -> dict | None:
        for r in (self._media_assets if hasattr(self, "_media_assets") else []):
            if str(r.get("original_media_url", "")) == str(original_media_url):
                return dict(r)
        return None

    def save_media_asset(self, asset: dict[str, Any]) -> bool:
        if not hasattr(self, "_media_assets"):
            self._media_assets: list[dict] = []
        reference_post_id = str(asset.get("reference_post_id", ""))
        original_media_url = str(asset.get("original_media_url", ""))
        if reference_post_id and original_media_url:
            for i, r in enumerate(self._media_assets):
                if (str(r.get("reference_post_id", "")) == reference_post_id
                        and str(r.get("original_media_url", "")) == original_media_url):
                    self._media_assets[i] = dict(asset)
                    print(f"[mock-sheets] save_media_asset update: ref={reference_post_id!r}")
                    return True
        self._media_assets.append(dict(asset))
        print(f"[mock-sheets] save_media_asset: ref={reference_post_id!r} url={original_media_url[:60]!r}")
        return True

    def save_media_assets(self, assets: list[dict[str, Any]]) -> dict[str, int]:
        saved = skipped = errors = 0
        for asset in assets:
            try:
                result = self.save_media_asset(asset)
                if result:
                    saved += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[mock-sheets] save_media_asset error: {e}")
                errors += 1
        return {"saved": saved, "skipped": skipped, "errors": errors}

    # ---- reference_post_scores (mock) ----

    def get_reference_post_scores(
        self,
        account_id: str | None = None,
        reference_post_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._reference_post_scores) if hasattr(self, "_reference_post_scores") else []
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if reference_post_id:
            rows = [r for r in rows if str(r.get("reference_post_id", "")) == str(reference_post_id)]
        if limit:
            rows = rows[:limit]
        return rows

    def find_reference_post_score_by_reference_post_id(
        self, reference_post_id: str
    ) -> dict | None:
        for r in (self._reference_post_scores if hasattr(self, "_reference_post_scores") else []):
            if str(r.get("reference_post_id", "")) == str(reference_post_id):
                return dict(r)
        return None

    def save_reference_post_score(self, score: dict[str, Any]) -> bool:
        if not hasattr(self, "_reference_post_scores"):
            self._reference_post_scores: list[dict] = []
        reference_post_id = str(score.get("reference_post_id", ""))
        if reference_post_id:
            existing = self.find_reference_post_score_by_reference_post_id(reference_post_id)
            if existing:
                for i, r in enumerate(self._reference_post_scores):
                    if str(r.get("reference_post_id", "")) == reference_post_id:
                        self._reference_post_scores[i] = dict(score)
                        print(f"[mock-sheets] save_reference_post_score update: reference_post_id={reference_post_id!r}")
                        return True
        self._reference_post_scores.append(dict(score))
        print(f"[mock-sheets] save_reference_post_score: reference_post_id={reference_post_id!r}")
        return True

    def save_reference_post_scores(
        self, scores: list[dict[str, Any]]
    ) -> dict[str, int]:
        saved = skipped = errors = 0
        for score in scores:
            try:
                result = self.save_reference_post_score(score)
                if result:
                    saved += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[mock-sheets] save_reference_post_score error: {e}")
                errors += 1
        return {"saved": saved, "skipped": skipped, "errors": errors}

    # ---- generation_jobs ----

    def save_generation_job(self, job: dict[str, Any]) -> bool:
        if not hasattr(self, "_generation_jobs"):
            self._generation_jobs: list[dict] = []
        job_id = str(job.get("job_id", ""))
        for i, existing in enumerate(self._generation_jobs):
            if str(existing.get("job_id", "")) == job_id:
                self._generation_jobs[i] = dict(job)
                print(
                    f"[mock-sheets] save_generation_job (update): "
                    f"job_id={job_id!r} mode={job.get('generation_mode', '?')!r}"
                )
                return True
        self._generation_jobs.append(dict(job))
        print(
            f"[mock-sheets] save_generation_job (insert): "
            f"job_id={job_id!r} account_id={job.get('account_id', '?')!r} "
            f"mode={job.get('generation_mode', '?')!r}"
        )
        return True

    def save_generation_jobs(
        self, jobs: list[dict[str, Any]]
    ) -> dict[str, int]:
        saved = skipped = errors = 0
        for job in jobs:
            try:
                result = self.save_generation_job(job)
                if result:
                    saved += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[mock-sheets] save_generation_job error: {e}")
                errors += 1
        return {"saved": saved, "skipped": skipped, "errors": errors}

    def get_generation_jobs(
        self,
        account_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._generation_jobs) if hasattr(self, "_generation_jobs") else []
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if platform:
            rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).lower() == status.lower()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_generation_job_by_id(self, job_id: str) -> dict | None:
        if not hasattr(self, "_generation_jobs"):
            return None
        for r in self._generation_jobs:
            if str(r.get("job_id", "")) == str(job_id):
                return dict(r)
        return None

    def update_generation_job(self, job_id: str, **fields: Any) -> bool:
        if not hasattr(self, "_generation_jobs"):
            return False
        print(f"[mock-sheets] update_generation_job: job_id={job_id!r} fields={fields}")
        for r in self._generation_jobs:
            if str(r.get("job_id", "")) == job_id:
                r.update(fields)
                return True
        return False

    def get_drafts(
        self,
        account_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._drafts)
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
        if limit:
            rows = rows[:limit]
        return rows

    def get_pending_drafts(self, account_id: str | None = None) -> list[dict]:
        return self.get_drafts(account_id=account_id, status="DRAFT")

    def get_social_derivatives(
        self,
        account_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._derivatives)
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if platform:
            rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
        if limit:
            rows = rows[:limit]
        return rows

    def find_social_derivative(self, draft_id: str, platform: str) -> dict | None:
        for r in self._derivatives:
            if (r.get("draft_id") == draft_id
                    and str(r.get("platform", "")).lower() == platform.lower()):
                return dict(r)
        return None

    def find_queue_item(self, draft_id: str, platform: str) -> dict | None:
        for r in self._queue:
            if (r.get("draft_id") == draft_id
                    and str(r.get("platform", "")).lower() == platform.lower()):
                return dict(r)
        return None

    def get_queue_items(
        self,
        account_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._queue)
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if platform:
            rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def get_queue_item(self, queue_id: str) -> dict | None:
        for r in self._queue:
            if r.get("queue_id") == queue_id:
                return dict(r)
        return None

    def update_queue_item(self, queue_id: str, **fields: Any) -> None:
        print(f"[mock-sheets] update_queue_item: queue_id={queue_id} fields={fields}")
        for r in self._queue:
            if r.get("queue_id") == queue_id:
                r.update(fields)
                return

    def get_prompt_templates(
        self,
        account_id: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        rows = list(PROMPT_TEMPLATE_SEEDS)
        if active_only:
            rows = [r for r in rows if str(r.get("active", "")).upper() == "TRUE"]
        if account_id is not None:
            rows = [r for r in rows if r.get("account_id") in (account_id, "")]
        return rows

    # ---- 書き込み系 ----

    def save_draft(self, account_id: str, title: str, body_md: str, **kwargs: Any) -> str:
        draft_id = kwargs.pop("draft_id", None) or f"d-{_short_uuid()}"
        data = {
            "draft_id": draft_id,
            "created_at": _now(),
            "account_id": account_id,
            "title": title,
            "body_md": body_md,
            "status": kwargs.pop("status", "DRAFT"),
            **kwargs,
        }
        self._drafts.append(data)
        print(f"[mock-sheets] save_draft: account_id={account_id} draft_id={draft_id} title={title!r}")
        return draft_id

    def update_draft(self, draft_id: str, **fields: Any) -> None:
        print(f"[mock-sheets] update_draft: draft_id={draft_id} fields={fields}")
        for d in self._drafts:
            if d.get("draft_id") == draft_id:
                d.update(fields)
                return

    def update_reference_post_status(self, post_id: str, status: str) -> None:
        print(f"[mock-sheets] update_reference_post_status: id={post_id} status={status}")

    def append_social_derivative(self, derivative: dict) -> str:
        derivative_id = derivative.get("derivative_id") or f"sd-{_short_uuid()}"
        data = {"derivative_id": derivative_id, "created_at": _now(), **derivative}
        self._derivatives.append(data)
        print(
            f"[mock-sheets] append_social_derivative: "
            f"draft_id={derivative.get('draft_id')} "
            f"platform={derivative.get('platform')} "
            f"status={derivative.get('status')}"
        )
        return derivative_id

    def append_queue_item(self, item: dict) -> str:
        queue_id = item.get("queue_id") or f"q-{_short_uuid()}"
        data = {"queue_id": queue_id, "created_at": _now(), **item}
        self._queue.append(data)
        print(
            f"[mock-sheets] append_queue_item: "
            f"draft_id={item.get('draft_id')} "
            f"platform={item.get('platform')} "
            f"status={item.get('status')} "
            f"scheduled_at={item.get('scheduled_at')}"
        )
        return queue_id

    def mark_posted(self, draft_id: str, note_url: str, posted_at: str | None = None) -> None:
        print(f"[mock-sheets] mark_posted: draft_id={draft_id} note_url={note_url}")

    def save_result(self, draft_id: str, account_id: str,
                    measurement_window: str = "24h", **kwargs: Any) -> str:
        result_id = f"r-{_short_uuid()}"
        data: dict[str, Any] = {
            "result_id": result_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "measurement_window": measurement_window,
            "collected_at": _now(),
            **kwargs,
        }
        self._posted_results.append(data)
        print(f"[mock-sheets] save_result: draft_id={draft_id} account_id={account_id} result_id={result_id}")
        return result_id

    def log(self, operation: str, status: str, message: str,
            account_id: str = "", details: str = "", level: str = "") -> None:
        if not level:
            s = status.upper()
            if s in ("ERROR", "FAIL", "FAILED"):
                level = "ERROR"
            elif s in ("WARN", "WARNING"):
                level = "WARN"
            else:
                level = "INFO"
        entry = {
            "timestamp": _now(),
            "account_id": account_id,
            "operation": operation,
            "level": level,
            "status": status,
            "message": message,
        }
        self._logs.append(entry)
        print(f"[mock-sheets] log: [{level}/{status}] {operation} - {message}")

    # ---- reference_sources (mock) ----

    def get_reference_sources(
        self,
        account_id: str | None = None,
        platform: str | None = None,
        active_only: bool = False,
    ) -> list[dict]:
        rows = list(self._reference_sources) if hasattr(self, "_reference_sources") else []
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if platform:
            rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
        if active_only:
            rows = [r for r in rows if str(r.get("active", "")).upper() == "TRUE"]
        return [dict(r) for r in rows]

    def find_reference_source_by_source_id(self, source_id: str) -> dict | None:
        for r in (self._reference_sources if hasattr(self, "_reference_sources") else []):
            if str(r.get("source_id", "")) == str(source_id):
                return dict(r)
        return None

    def save_reference_source(self, source: dict[str, Any]) -> bool:
        if not hasattr(self, "_reference_sources"):
            self._reference_sources: list[dict] = []
        source_id = str(source.get("source_id", ""))
        for i, r in enumerate(self._reference_sources):
            if str(r.get("source_id", "")) == source_id:
                self._reference_sources[i] = dict(source)
                print(f"[mock-sheets] save_reference_source update: source_id={source_id!r}")
                return True
        self._reference_sources.append(dict(source))
        print(f"[mock-sheets] save_reference_source: source_id={source_id!r}")
        return True

    def update_reference_source(self, source_id: str, **fields: Any) -> bool:
        if not hasattr(self, "_reference_sources"):
            return False
        print(f"[mock-sheets] update_reference_source: source_id={source_id!r} fields={fields}")
        for r in self._reference_sources:
            if str(r.get("source_id", "")) == source_id:
                r.update(fields)
                return True
        return False

    # ---- video_transcripts (mock) ----

    def get_video_transcripts(
        self,
        account_id: str | None = None,
        reference_post_id: str | None = None,
        transcription_status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._video_transcripts) if hasattr(self, "_video_transcripts") else []
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if reference_post_id:
            rows = [r for r in rows if str(r.get("reference_post_id", "")) == str(reference_post_id)]
        if transcription_status:
            rows = [r for r in rows if str(r.get("transcription_status", "")).lower() == transcription_status.lower()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_video_transcript_by_reference_post_id(self, reference_post_id: str) -> dict | None:
        for r in (self._video_transcripts if hasattr(self, "_video_transcripts") else []):
            if str(r.get("reference_post_id", "")) == str(reference_post_id):
                return dict(r)
        return None

    def find_video_transcript_by_id(self, transcript_id: str) -> dict | None:
        for r in (self._video_transcripts if hasattr(self, "_video_transcripts") else []):
            if str(r.get("transcript_id", "")) == str(transcript_id):
                return dict(r)
        return None

    def save_video_transcript(self, transcript: dict[str, Any]) -> bool:
        if not hasattr(self, "_video_transcripts"):
            self._video_transcripts: list[dict] = []
        transcript_id = str(transcript.get("transcript_id", ""))
        for i, r in enumerate(self._video_transcripts):
            if str(r.get("transcript_id", "")) == transcript_id:
                self._video_transcripts[i] = dict(transcript)
                print(f"[mock-sheets] save_video_transcript update: transcript_id={transcript_id!r}")
                return True
        self._video_transcripts.append(dict(transcript))
        print(f"[mock-sheets] save_video_transcript: transcript_id={transcript_id!r}")
        return True

    def update_video_transcript(self, transcript_id: str, **fields: Any) -> bool:
        if not hasattr(self, "_video_transcripts"):
            return False
        print(f"[mock-sheets] update_video_transcript: transcript_id={transcript_id!r} fields={fields}")
        for r in self._video_transcripts:
            if str(r.get("transcript_id", "")) == transcript_id:
                r.update(fields)
                return True
        return False

    # ---- source_videos (mock) ----

    def get_source_videos(
        self,
        account_id: str | None = None,
        source_id: str | None = None,
        discovery_status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._source_videos) if hasattr(self, "_source_videos") else []
        if account_id:
            rows = [r for r in rows if str(r.get("account_id", "")) == str(account_id)]
        if source_id:
            rows = [r for r in rows if str(r.get("source_id", "")) == str(source_id)]
        if discovery_status:
            rows = [r for r in rows if str(r.get("discovery_status", "")).upper() == discovery_status.upper()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_source_video_by_id(self, source_video_id: str) -> dict | None:
        for r in (self._source_videos if hasattr(self, "_source_videos") else []):
            if str(r.get("source_video_id", "")) == str(source_video_id):
                return dict(r)
        return None

    def save_source_video(self, source_video: dict[str, Any]) -> bool:
        if not hasattr(self, "_source_videos"):
            self._source_videos: list[dict] = []
        source_video_id = str(source_video.get("source_video_id", ""))
        for i, r in enumerate(self._source_videos):
            if str(r.get("source_video_id", "")) == source_video_id:
                self._source_videos[i] = dict(source_video)
                print(f"[mock-sheets] save_source_video update: source_video_id={source_video_id!r}")
                return True
        self._source_videos.append(dict(source_video))
        print(f"[mock-sheets] save_source_video: source_video_id={source_video_id!r}")
        return True

    def save_source_videos(self, source_videos: list[dict[str, Any]]) -> dict[str, int]:
        saved = skipped = errors = 0
        existing_ids = {str(r.get("source_video_id", "")) for r in self.get_source_videos()}
        for row in source_videos:
            if str(row.get("source_video_id", "")) in existing_ids:
                skipped += 1
                continue
            try:
                if self.save_source_video(row):
                    saved += 1
                    existing_ids.add(str(row.get("source_video_id", "")))
            except Exception:
                errors += 1
        return {"saved": saved, "skipped": skipped, "errors": errors}

    # ---- video_clip_candidates (mock) ----

    def get_video_clip_candidates(
        self,
        account_id: str | None = None,
        reference_post_id: str | None = None,
        transcript_id: str | None = None,
        clip_status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = list(self._video_clip_candidates) if hasattr(self, "_video_clip_candidates") else []
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        if reference_post_id:
            rows = [r for r in rows if str(r.get("reference_post_id", "")) == str(reference_post_id)]
        if transcript_id:
            rows = [r for r in rows if str(r.get("transcript_id", "")) == str(transcript_id)]
        if clip_status:
            rows = [r for r in rows if str(r.get("clip_status", "")).lower() == clip_status.lower()]
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def find_video_clip_candidate_by_clip_id(self, clip_id: str) -> dict | None:
        for r in (self._video_clip_candidates if hasattr(self, "_video_clip_candidates") else []):
            if str(r.get("clip_id", "")) == str(clip_id):
                return dict(r)
        return None

    def save_video_clip_candidate(self, clip: dict[str, Any]) -> bool:
        if not hasattr(self, "_video_clip_candidates"):
            self._video_clip_candidates: list[dict] = []
        clip_id = str(clip.get("clip_id", ""))
        for i, r in enumerate(self._video_clip_candidates):
            if str(r.get("clip_id", "")) == clip_id:
                self._video_clip_candidates[i] = dict(clip)
                print(f"[mock-sheets] save_video_clip_candidate update: clip_id={clip_id!r}")
                return True
        self._video_clip_candidates.append(dict(clip))
        print(f"[mock-sheets] save_video_clip_candidate: clip_id={clip_id!r}")
        return True

    def update_video_clip_candidate(self, clip_id: str, **fields: Any) -> bool:
        if not hasattr(self, "_video_clip_candidates"):
            return False
        print(f"[mock-sheets] update_video_clip_candidate: clip_id={clip_id!r} fields={fields}")
        for r in self._video_clip_candidates:
            if str(r.get("clip_id", "")) == clip_id:
                r.update(fields)
                return True
        return False

    # ---- transcription_runs (mock) ----

    def get_transcription_run_by_date(self, date: str, provider: str = "cloudflare_whisper") -> dict | None:
        for r in (self._transcription_runs if hasattr(self, "_transcription_runs") else []):
            if str(r.get("date", "")) == date and str(r.get("provider", "")) == provider:
                return dict(r)
        return None

    def save_transcription_run(self, run: dict[str, Any]) -> bool:
        if not hasattr(self, "_transcription_runs"):
            self._transcription_runs: list[dict] = []
        run_id = str(run.get("run_id", ""))
        for i, r in enumerate(self._transcription_runs):
            if str(r.get("run_id", "")) == run_id:
                self._transcription_runs[i] = dict(run)
                print(f"[mock-sheets] save_transcription_run update: run_id={run_id!r}")
                return True
        self._transcription_runs.append(dict(run))
        print(f"[mock-sheets] save_transcription_run: run_id={run_id!r} date={run.get('date', '?')!r}")
        return True

    def update_transcription_run(self, run_id: str, **fields: Any) -> bool:
        if not hasattr(self, "_transcription_runs"):
            return False
        print(f"[mock-sheets] update_transcription_run: run_id={run_id!r} fields={fields}")
        for r in self._transcription_runs:
            if str(r.get("run_id", "")) == run_id:
                r.update(fields)
                return True
        return False

    def seed_tab(self, tab_name: str, rows: list[dict], id_column: str) -> int:
        """MockSheetsClient では内容を表示するだけで書き込まない。"""
        print(f"  [mock-sheets] seed_tab({tab_name}): {len(rows)} 件（モックのため書き込みなし）")
        return 0

    def list_tabs(self) -> list[str]:
        """TAB_DEFINITIONS のキー一覧を返す（モック）。"""
        return list(TAB_DEFINITIONS.keys())

    def setup_all(self) -> None:
        print("[mock-sheets] setup_all: モックのため実際のタブ初期化はスキップします")


# ------------------------------------------------------------------ #
# ファクトリ関数
# ------------------------------------------------------------------ #

def make_client(
    cfg: dict,
    dry_run: bool = False,
    force_mock: bool = False,
) -> "SheetsClient | MockSheetsClient":
    """設定に応じて SheetsClient または MockSheetsClient を返す。

    force_mock=True: 常に MockSheetsClient を返す（--mock-sheets フラグ対応）。
    force_mock=False + 認証情報なし + dry_run=True: MockSheetsClient を返す。
    force_mock=False + 認証情報あり: SheetsClient を返す。
    """
    if force_mock:
        print("[INFO] force_mock=True のため MockSheetsClient を使用します")
        return MockSheetsClient(dry_run=dry_run)
    if not cfg.get("sa_dict") or not cfg.get("sheet_id"):
        if dry_run:
            print("[INFO] 認証情報またはシートIDが未設定のため MockSheetsClient を使用します")
            return MockSheetsClient(dry_run=True)
        raise ValueError(
            "認証情報（SA_JSON_BASE64 または GCP_SA_JSON）と SNS_MASTER_SHEET_ID が必要です"
        )
    return SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=dry_run)


# ------------------------------------------------------------------ #
# ユーティリティ
# ------------------------------------------------------------------ #

def _auth(sa_dict: dict) -> gspread.Client:
    creds = Credentials.from_service_account_info(sa_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def _col_letter(n: int) -> str:
    """1始まりの列番号をA1記法のアルファベットに変換する（例: 27 → AA）。"""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result
