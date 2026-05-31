"""
seeds.py - スプレッドシート初期シードデータ

Google Sheets 上で編集することを前提としたデータ定義。
setup_sheets.py から呼ばれ、未存在の行のみ追加する（冪等）。
"""
from __future__ import annotations

# ------------------------------------------------------------------ #
# accounts
# ------------------------------------------------------------------ #

ACCOUNT_SEEDS_V2 = [
    {
        "account_id": "night_scout",
        "account_name": "夜職スカウト",
        "platform": "x,threads",
        "note_url": "",
        "x_handle": "",
        "threads_handle": "",
        "bio_summary": "夜職スカウトマン。キャバ嬢・夜職女性の相談受付中。",
        "target_persona": "キャバ嬢・夜職女性・夜職志望者・転職検討中の女性",
        "tone": "論理的・経験豊富・強め表現OK・夜職女性の味方",
        "main_genre": "夜職スカウト",
        "line_url": "",
        "cta_type": "LINE",
        "cta_text": "相談はLINEで↓",
        "auto_publish": "FALSE",
        "min_publish_score": "65",
        "brand_risk_threshold": "25",
        "post_time": "20:00",
        "timezone": "Asia/Tokyo",
        "active": "TRUE",
        "notes": "Phase 2シード。line_url・x_handle・threads_handleはシート上で更新してください。",
    },
    {
        "account_id": "liver_manager",
        "account_name": "ライバーマネージャー",
        "platform": "x,threads",
        "note_url": "",
        "x_handle": "",
        "threads_handle": "",
        "bio_summary": "ライバーマネージャー。TikTokライブで稼ぎたい人の相談受付中。",
        "target_persona": "TikTokライブ未経験者・既存ライバー・配信で稼ぎたい人",
        "tone": "ロジックと熱量・育成力・現場感・事務所営業っぽくしない",
        "main_genre": "ライバーマネジメント",
        "line_url": "",
        "cta_type": "LINE",
        "cta_text": "相談はLINEで↓",
        "auto_publish": "FALSE",
        "min_publish_score": "65",
        "brand_risk_threshold": "25",
        "post_time": "20:00",
        "timezone": "Asia/Tokyo",
        "active": "TRUE",
        "notes": "Phase 2シード。line_url・x_handle・threads_handleはシート上で更新してください。",
    },
]

# ------------------------------------------------------------------ #
# content_categories
# ------------------------------------------------------------------ #

CATEGORY_SEEDS = [
    # ---- night_scout（8件）----
    {
        "category_id": "ns_01",
        "account_id": "night_scout",
        "category_name": "夜職あるある",
        "description": "夜職で働く女性なら共感するリアルな体験・あるある。共感→保存→フォローを狙う。",
        "weight": "1.2",
        "examples": "出勤前の緊張、指名をもらった瞬間、常連さんとの距離感",
        "tags": "共感,バズ,保存",
        "active": "TRUE",
    },
    {
        "category_id": "ns_02",
        "account_id": "night_scout",
        "category_name": "キャバ嬢のリアル",
        "description": "キャバクラで働くリアルな実態・収入・働き方。誇張なく正直に伝える。",
        "weight": "1.0",
        "examples": "月収の内訳、売上を作るための考え方、同期との差がつく理由",
        "tags": "リアル,信頼,教育",
        "active": "TRUE",
    },
    {
        "category_id": "ns_03",
        "account_id": "night_scout",
        "category_name": "店選びノウハウ",
        "description": "良い店・悪い店を見分けるポイント。失敗しない店選びの判断基準。",
        "weight": "1.3",
        "examples": "面接で聞くべき質問、バック率の見方、悪徳店の見分け方",
        "tags": "ノウハウ,保存,CV",
        "active": "TRUE",
    },
    {
        "category_id": "ns_04",
        "account_id": "night_scout",
        "category_name": "移籍・環境変更",
        "description": "今の店に不満がある人向け。移籍のタイミングと判断基準。",
        "weight": "1.1",
        "examples": "移籍を考えるべき3つのサイン、辞め時の見極め方、環境を変えると結果が変わる理由",
        "tags": "移籍,相談,CV",
        "active": "TRUE",
    },
    {
        "category_id": "ns_05",
        "account_id": "night_scout",
        "category_name": "ガルバからキャバへのランクアップ",
        "description": "ガールズバーからキャバクラへのステップアップ。収入・キャリアのリアル。",
        "weight": "1.0",
        "examples": "ガルバとキャバの違い、ランクアップが向いている人・向いていない人",
        "tags": "ランクアップ,教育,CV",
        "active": "TRUE",
    },
    {
        "category_id": "ns_06",
        "account_id": "night_scout",
        "category_name": "TikTokライブという選択肢",
        "description": "夜職女性にTikTokライブという稼ぎ方を提案。比較・メリットを正直に伝える。",
        "weight": "0.8",
        "examples": "キャバとTikTokライブを並行する人の話、夜職からライバー転向のケース",
        "tags": "TikTok,選択肢,CV",
        "active": "TRUE",
    },
    {
        "category_id": "ns_07",
        "account_id": "night_scout",
        "category_name": "相談導線投稿",
        "description": "LINE相談・DM相談へ誘導するCTA強め投稿。",
        "weight": "1.5",
        "examples": "無料相談受付中、こんな悩みを抱えているなら相談してほしい",
        "tags": "CV,CTA,相談",
        "active": "TRUE",
    },
    {
        "category_id": "ns_08",
        "account_id": "night_scout",
        "category_name": "代理店向け投稿",
        "description": "代理店・パートナー候補向け。スカウト業界のビジネス構造や収益モデルを解説。",
        "weight": "0.7",
        "examples": "代理店として稼ぐ仕組み、パートナー募集の背景",
        "tags": "代理店,B2B,CV",
        "active": "FALSE",
    },
    # ---- liver_manager（8件）----
    {
        "category_id": "lm_01",
        "account_id": "liver_manager",
        "category_name": "ライバーあるある",
        "description": "TikTokライバーなら共感するリアルな体験・あるある。共感→保存→フォローを狙う。",
        "weight": "1.2",
        "examples": "初配信の緊張、ギフトをもらった瞬間、リスナーとの距離感",
        "tags": "共感,バズ,保存",
        "active": "TRUE",
    },
    {
        "category_id": "lm_02",
        "account_id": "liver_manager",
        "category_name": "TikTokライブ未経験向け",
        "description": "TikTokライブを始めたことがない人向けの入門情報。怖くない・始めやすい。",
        "weight": "1.3",
        "examples": "未経験から3ヶ月でギフト月10万円の人の話、最初の配信で必要なもの",
        "tags": "未経験,入門,バズ",
        "active": "TRUE",
    },
    {
        "category_id": "lm_03",
        "account_id": "liver_manager",
        "category_name": "伸びる人・伸びない人",
        "description": "TikTokライブで伸びる人と伸びない人の違い。原因を具体的に分析する投稿。",
        "weight": "1.2",
        "examples": "フォロワー1000人でも稼げない人の共通点、伸びるライバーがやっていること",
        "tags": "分析,保存,教育",
        "active": "TRUE",
    },
    {
        "category_id": "lm_04",
        "account_id": "liver_manager",
        "category_name": "事務所選び",
        "description": "良い事務所・悪い事務所を見分けるポイント。ブラック事務所の見分け方。",
        "weight": "1.1",
        "examples": "事務所面談で必ず聞くべき質問、契約書の確認ポイント",
        "tags": "ノウハウ,保存,信頼",
        "active": "TRUE",
    },
    {
        "category_id": "lm_05",
        "account_id": "liver_manager",
        "category_name": "配信で稼ぐ設計",
        "description": "TikTokライブを収益化するための配信設計・戦略。再現性のある稼ぎ方を伝える。",
        "weight": "1.0",
        "examples": "週何回配信すれば稼げるか、ギフトを増やすための配信構成",
        "tags": "戦略,保存,CV",
        "active": "TRUE",
    },
    {
        "category_id": "lm_06",
        "account_id": "liver_manager",
        "category_name": "今の環境を見直す投稿",
        "description": "今の事務所・環境に不満がある人向け。変えるべきかどうかの判断基準。",
        "weight": "1.0",
        "examples": "今の事務所で伸び悩んでいるなら読んでほしい、移籍を考えるべき3つのサイン",
        "tags": "移籍,相談,CV",
        "active": "TRUE",
    },
    {
        "category_id": "lm_07",
        "account_id": "liver_manager",
        "category_name": "相談導線投稿",
        "description": "LINE相談・DM相談へ誘導するCTA強め投稿。",
        "weight": "1.5",
        "examples": "TikTokライブを始めたいけど不安な人へ、無料相談受付中",
        "tags": "CV,CTA,相談",
        "active": "TRUE",
    },
    {
        "category_id": "lm_08",
        "account_id": "liver_manager",
        "category_name": "代理店向け投稿",
        "description": "代理店・パートナー候補向け。ライバーマネジメント業界の収益モデルを解説。",
        "weight": "0.7",
        "examples": "ライバーマネージャーとして稼ぐ仕組み、パートナー募集の背景",
        "tags": "代理店,B2B,CV",
        "active": "FALSE",
    },
]

# ------------------------------------------------------------------ #
# prompt_templates
# ------------------------------------------------------------------ #

_DRAFT_GEN_NIGHT_SCOUT = """\
あなたは夜職スカウトマンです。キャバ嬢・夜職女性向けのSNS投稿を生成してください。

## キャラクター設定
- 一人称：「僕」
- スタンス：プロ個人のスカウトマン。論理的・経験豊富・結果重視。
- 夜職女性の味方。稼ぎたいなら・困っているなら、ロジックで言える人。
- 強め表現OK。ただし怪しさ・情報商材感・女性を軽く扱う表現は絶対NG。
- 「〜なんだよね」「〜なんよね」「〜だよ」をアクセントとして使ってもOK。

## アカウント情報
- ターゲット：{{target_persona}}
- トーン：{{tone}}
- CTA：{{cta_text}}
- LINE URL：{{line_url}}

## カテゴリ
- カテゴリ：{{category_name}}
- 説明：{{category_description}}

## 参考情報（本文は模倣しない。勝ち要素・パターンのみ参考にする）
{{reference_summary}}
- フック参考：{{reference_hook}}
- 読者の痛み参考：{{reference_pain}}
- 読者の欲求参考：{{reference_desire}}
- 再利用パターン：{{reusable_pattern}}

## 絶対NG
- 怪しい・情報商材感・女性を雑に扱う表現
- 夜職を軽く見る・蔑む表現
- 無責任に「絶対稼げる」と煽る
- 他店舗・他スカウトを名指しで攻撃
- 差別的表現・コミュニティガイドライン違反
- 代理店・パートナー募集・紹介業として稼ぐ話
- 組織的に高収益を狙う話・スカウト代理店向け投稿
- 情報商材っぽいビジネスノウハウ・収益モデル解説
- 夜職女性ではなく紹介者側・代理店側に向けた投稿

## 出力フォーマット
JSONのみを返してください。前後に説明文を入れないでください。
{
  "title": "投稿タイトル（20文字以内が理想）",
  "body_md": "Threads形式：1行目にキャッチーなコピー（フック）、その後2行空ける、本文。500文字以内。",
  "content": "body_md のプレーンテキスト版",
  "cta_text": "本文末の自然なCTA文言",
  "thumbnail_copy": "サムネコピー（不要なら空文字）",
  "pv_score": "整数 0-100（PV獲得力）",
  "cv_score": "整数 0-100（LINE相談・申込CV力）",
  "brand_risk_score": "整数 0-100（低いほど安全）",
  "score": "整数 0-100（総合スコア）",
  "score_reason": "スコア算出理由",
  "ai_review": "改善提案（具体的に）",
  "post_mode": "buzz または trust または cv または mixed"
}
"""

_DRAFT_GEN_LIVER_MANAGER = """\
あなたはライバーマネージャーです。TikTokライバー向けのSNS投稿を生成してください。

## キャラクター設定
- プロ個人のライバーマネージャー。
- ロジックと熱量を持ち、育成力と現場感がある。
- 未経験者にも経験者にも「伸びる道筋」を示せる。
- 怪しい事務所営業っぽくしない。「この人に相談したら伸びそう」と思わせる。

## アカウント情報
- ターゲット：{{target_persona}}
- トーン：{{tone}}
- CTA：{{cta_text}}
- LINE URL：{{line_url}}

## カテゴリ
- カテゴリ：{{category_name}}
- 説明：{{category_description}}

## 参考情報（本文は模倣しない。勝ち要素・パターンのみ参考にする）
{{reference_summary}}
- フック参考：{{reference_hook}}
- 読者の痛み参考：{{reference_pain}}
- 読者の欲求参考：{{reference_desire}}
- 再利用パターン：{{reusable_pattern}}

## 絶対NG
- ライバーを軽く扱う・蔑む表現
- 怪しい事務所営業っぽい表現
- 無責任に「絶対稼げる」と煽る
- 他事務所・他マネージャーを名指しで攻撃
- 差別的表現・コミュニティガイドライン違反

## 出力フォーマット
JSONのみを返してください。前後に説明文を入れないでください。
{
  "title": "投稿タイトル（20文字以内が理想）",
  "body_md": "Threads形式：1行目にキャッチーなコピー（フック）、その後2行空ける、本文。500文字以内。",
  "content": "body_md のプレーンテキスト版",
  "cta_text": "本文末の自然なCTA文言",
  "thumbnail_copy": "サムネコピー（不要なら空文字）",
  "pv_score": "整数 0-100（PV獲得力）",
  "cv_score": "整数 0-100（LINE相談・申込CV力）",
  "brand_risk_score": "整数 0-100（低いほど安全）",
  "score": "整数 0-100（総合スコア）",
  "score_reason": "スコア算出理由",
  "ai_review": "改善提案（具体的に）",
  "post_mode": "buzz または trust または cv または mixed"
}
"""

_DRAFT_SCORING = """\
以下の投稿下書きをSNSグロース・CV観点でスコアリングしてください。

## 投稿下書き
タイトル：{{title}}
本文：
{{body_md}}
カテゴリ：{{category_name}}

## スコアリング基準
- pv_score（0-100）：キャッチーさ・検索流入・シェア・保存されやすさ
- cv_score（0-100）：LINE問い合わせ・相談・申込に繋がりやすいか
- brand_risk_score（0-100）：低いほど安全（怪しさ・炎上リスク・ガイドライン違反リスク）
- score（0-100）：総合スコア

## 出力フォーマット（JSONのみ）
{
  "pv_score": "整数 0-100",
  "cv_score": "整数 0-100",
  "brand_risk_score": "整数 0-100",
  "score": "整数 0-100",
  "score_reason": "スコア算出理由",
  "ai_review": "改善提案（具体的に）"
}
"""

_SOCIAL_DERIVATIVE_X = """\
以下の投稿本文から X（旧Twitter）投稿用の短文を生成してください。

## 元の投稿
タイトル：{{title}}
本文：
{{body_md}}
CTA：{{cta_text}}
アカウント：{{account_name}}
ターゲット：{{target_persona}}

## X投稿の要件
- 120文字以内（厳守）
- 強い1文または短文で要点を凝縮
- CTAは必要なら自然に短く入れる（省略も可）
- ハッシュタグは不要（省略可）
- 怪しさ・情報商材感は絶対NG
- 単なる要約ではなく「これを見た人が止まる」1文を狙う

## 出力フォーマット（JSONのみ）
{
  "platform": "x",
  "text": "120文字以内の投稿文",
  "hashtags": "ハッシュタグ（スペース区切り、不要なら空文字）",
  "status": "READY または HUMAN_REVIEW または REJECT",
  "reason": "ステータス判断理由"
}
"""

_SOCIAL_DERIVATIVE_THREADS = """\
以下の投稿本文から Threads 投稿用の文章を生成してください。

## 元の投稿
タイトル：{{title}}
本文：
{{body_md}}
CTA：{{cta_text}}
アカウント：{{account_name}}
ターゲット：{{target_persona}}

## Threads投稿の要件
- 1行目にキャッチーなコピー（フック）
- その後2行空ける（空行を2行入れる）
- 本文（500文字以内）
- CTAは本文末に自然に入れる
- 怪しさ・情報商材感は絶対NG

## フォーマット例
キャバ始めたての子に伝えたいこと


最初の店選びで3年後の年収が変わる。

（以下本文...）

相談はLINEで↓

## 出力フォーマット（JSONのみ）
{
  "platform": "threads",
  "text": "上記フォーマット通りの投稿文",
  "hashtags": "",
  "status": "READY または HUMAN_REVIEW または REJECT",
  "reason": "ステータス判断理由"
}
"""

PROMPT_TEMPLATE_SEEDS = [
    {
        "template_id": "pt_01",
        "account_id": "night_scout",
        "template_name": "draft_generation_night_scout_v1",
        "version": "v1",
        "purpose": "night_scout アカウント向け下書き生成",
        "prompt_text": _DRAFT_GEN_NIGHT_SCOUT,
        "active": "TRUE",
        "notes": "Phase 2シード。Google Sheetsのprompt_textセルで直接編集可能。",
    },
    {
        "template_id": "pt_02",
        "account_id": "liver_manager",
        "template_name": "draft_generation_liver_manager_v1",
        "version": "v1",
        "purpose": "liver_manager アカウント向け下書き生成",
        "prompt_text": _DRAFT_GEN_LIVER_MANAGER,
        "active": "TRUE",
        "notes": "Phase 2シード。Google Sheetsのprompt_textセルで直接編集可能。",
    },
    {
        "template_id": "pt_03",
        "account_id": "",
        "template_name": "draft_scoring_v1",
        "version": "v1",
        "purpose": "既存下書きのスコアリング（全アカウント共通）",
        "prompt_text": _DRAFT_SCORING,
        "active": "TRUE",
        "notes": "account_id空=全アカウント共通",
    },
    {
        "template_id": "pt_04",
        "account_id": "",
        "template_name": "social_derivative_x_v1",
        "version": "v1",
        "purpose": "X（旧Twitter）投稿用派生テキスト生成（全アカウント共通）",
        "prompt_text": _SOCIAL_DERIVATIVE_X,
        "active": "TRUE",
        "notes": "account_id空=全アカウント共通",
    },
    {
        "template_id": "pt_05",
        "account_id": "",
        "template_name": "social_derivative_threads_v1",
        "version": "v1",
        "purpose": "Threads投稿用派生テキスト生成（全アカウント共通）",
        "prompt_text": _SOCIAL_DERIVATIVE_THREADS,
        "active": "TRUE",
        "notes": "account_id空=全アカウント共通",
    },
]

# ------------------------------------------------------------------ #
# distribution_rules
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
# アカウント別禁止キーワード（Sheetsには格納しない。Pythonコードで管理）
# ------------------------------------------------------------------ #

ACCOUNT_FORBIDDEN_KEYWORDS: dict[str, list[str]] = {
    "night_scout": [
        "代理店", "パートナー募集", "代理店パートナー", "紹介業",
        "スカウト代理店", "組織的に稼ぐ", "組織的なロジック", "高収益",
        "稼ぎ方を教えます", "ノウハウを共有", "ビジネス構造", "収益モデル",
    ],
    "liver_manager": [
        "代理店", "パートナー募集", "情報商材",
    ],
}

ACCOUNT_FORBIDDEN_THEMES: dict[str, list[str]] = {
    "night_scout": [
        "代理店募集", "紹介者募集", "スカウト業界のビジネス解説", "情報商材型の稼ぎ方訴求",
    ],
    "liver_manager": [
        "代理店募集", "情報商材的な副業訴求",
    ],
}

# ------------------------------------------------------------------ #
# distribution_rules
# ------------------------------------------------------------------ #

DISTRIBUTION_RULE_SEEDS = [
    {
        "rule_id": "dr_01",
        "account_id": "",
        "rule_type": "platform_format",
        "parameter": "x",
        "value": "120",
        "description": "X投稿は120文字以内。超過した場合は生成をやり直す。",
        "active": "TRUE",
    },
    {
        "rule_id": "dr_02",
        "account_id": "",
        "rule_type": "platform_format",
        "parameter": "threads",
        "value": "hook+blank2+body",
        "description": "Threads投稿は「1行目フック → 2行空け → 本文」の形式にする。",
        "active": "TRUE",
    },
    {
        "rule_id": "dr_03",
        "account_id": "",
        "rule_type": "brand_risk_gate",
        "parameter": "brand_risk_score",
        "value": "HUMAN_REVIEW",
        "description": "brand_risk_scoreがaccount.brand_risk_thresholdを超えた場合はHUMAN_REVIEWへ。",
        "active": "TRUE",
    },
    {
        "rule_id": "dr_04",
        "account_id": "",
        "rule_type": "auto_publish_gate",
        "parameter": "auto_publish",
        "value": "WAITING_REVIEW",
        "description": "auto_publish=FALSEのアカウントはqueueをWAITING_REVIEWにする。",
        "active": "TRUE",
    },
]
