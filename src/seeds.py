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
        "tone": "論理的・経験豊富・強め表現OK・夜職女性の味方。一人称は「僕」。ノウハウと経験を語るスタンス。キャバあるある・稼げる子の特徴分析・店選びのポイントなど現場知識を語る。",
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
        "notes": "Phase 2シード。【重要：トンマナ厳守】OK：現場ノウハウ・キャバあるある・失敗しない店選び・稼げる子の特徴分析。NG：応援系/美容系/ポエム/汎用自己啓発/求人LP調/薄い励まし。Xはハッシュタグなし・絵文字なし・120字以内。Threadsは冒頭1行フック+2行空け。line_url・x_handle・threads_handleはシート上で更新。",
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
        "tone": "ロジックと熱量・育成力・現場感。数字と具体例を使って語る。一人称は「僕」または省略。「この人に相談したら伸びそう」と思わせる。事務所営業っぽくしない。",
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
        "notes": "Phase 2シード。【重要：トンマナ厳守】OK：TikTokライブの仕組み・稼ぐための配信設計・伸びる人の特徴分析・事務所見極め方。NG：「誰でも稼げる」/ポエム/汎用自己啓発/事務所営業っぽい文章/「一緒に頑張ろう」系。Xはハッシュタグなし・絵文字なし。line_url・x_handle・threads_handleはシート上で更新。",
    },
    {
        "account_id": "beauty_account",
        "account_name": "美容アドバイザー",
        "platform": "x,threads",
        "note_url": "",
        "x_handle": "",
        "threads_handle": "",
        "bio_summary": "美容アドバイザー。スキンケア・コスメ知識を発信。",
        "target_persona": "美容に興味のある女性・スキンケアに悩む20〜40代",
        "tone": "丁寧で親しみやすい・専門知識あり・読者目線",
        "main_genre": "美容・スキンケア",
        "line_url": "",
        "cta_type": "LINE",
        "cta_text": "美容相談はLINEで↓",
        "auto_publish": "FALSE",
        "min_publish_score": "70",
        "brand_risk_threshold": "20",
        "post_time": "20:00",
        "timezone": "Asia/Tokyo",
        "active": "FALSE",
        "notes": "Phase 6.1シード。status=draft_only。実投稿禁止。READY化・POSTED化禁止。",
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

## 投稿スタイル
### X 投稿の場合
- 120文字以内（厳守）
- ハッシュタグなし（原則）
- 絵文字なし
- 短く・強く・核心を突く1文か短文
- 「この言葉で止まる」1文を狙う

### Threads 投稿の場合
- 冒頭1行にキャッチーなフックを入れる
- その後2行空ける（空行2行）
- 本文（500文字以内）
- CTAは本文末に自然に入れる

## 良い投稿の例（このスタイルを参考にする）
例1: キャバで長く稼げる子って、見た目だけじゃなくて「また話したい」と思わせる返しが上手い。LINEも接客も、相手を気持ちよくさせる一言を積み重ねられる子は強いんだよね。
→ ノウハウ・キャバ特有の観察・分析。応援ではなく「稼げる子の特徴」を語る。

例2: 店選びを間違えると、同じ努力でも結果が半分になる。面接でバック率だけ聞いて決めた子が、3ヶ月後に移籍したがってた。最初から聞くべきポイントがある。
→ 実体験に近い話・共感・保存されやすい。

## 絶対NG（トンマナNG）— これを書いたら失敗
- 「今日もお疲れ様」「頑張ってるね」だけの薄い応援投稿
- 「君はすごい」「ずっと応援してるよ」「信じてるよ」系の励まし
- 美容だけの話（メイク・リップ・アイシャドウ・スキンケア・コスメ）
- ふわっとしたメンタル系（「自分を大切に」「自分を信じて」「諦めないで」「可能性は無限大」）
- 求人LP・スカウト広告っぽい文章
- ポエム・詩的表現・抽象的なメッセージ
- 汎用自己啓発（夜職・キャバ・スカウト関係なく誰にでも通じる薄いコンテンツ）

## 絶対NG（コンテンツ）
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
- 一人称：「僕」または省略
- プロ個人のライバーマネージャー。
- ロジックと熱量を持ち、育成力と現場感がある。
- 未経験者にも経験者にも「伸びる道筋」を示せる。
- 数字と具体例を使って語る。
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

## 投稿スタイル
### X 投稿の場合
- 120文字以内（厳守）
- ハッシュタグなし（原則）
- 絵文字なし
- 短く・強く・核心を突く1文か短文

### Threads 投稿の場合
- 冒頭1行にキャッチーなフックを入れる
- その後2行空ける（空行2行）
- 本文（500文字以内）
- CTAは本文末に自然に入れる

## 良い投稿の例（このスタイルを参考にする）
例1: TikTokライブで月20万稼いでいる人の共通点を3つ挙げると、配信頻度・コメント返し・ギフトの活用方法。逆にいうと、これだけ意識すれば未経験でも3ヶ月で結果が出る。
→ 数字・具体的・分析系・再現性のある情報。

例2: フォロワー1000人いるのに月収3万しかない人の配信を見ると、コメントを拾えていない。ギフトをくれた人を名前で呼んでいない。リスナーが「返ってくる」体験を作れていない。
→ 原因分析・具体的な観察・保存されやすい。

## 絶対NG（トンマナNG）— これを書いたら失敗
- 「一緒に頑張ろう」「応援してます」系の薄い応援
- 「可能性がある」「夢を追える」「諦めないで」系のポエム
- 「誰でも稼げる」「スマホ1台で」「副業感覚で」「お試し感覚で」系
- 事務所営業・勧誘っぽい文章
- ポエム・詩的表現・抽象的なメッセージ
- 汎用自己啓発（TikTokライブ関係なく誰にでも通じる薄いビジネスコンテンツ）
- 「簡単に稼げる」「楽して稼ぐ」系

## 絶対NG（コンテンツ）
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

_SOCIAL_DERIVATIVE_X_NIGHT_SCOUT = """\
あなたは夜職スカウトマンです。以下の投稿本文からX（旧Twitter）投稿用の短文を生成してください。

## 元の投稿
タイトル：{{title}}
本文：
{{body_md}}
CTA：{{cta_text}}
アカウント：{{account_name}}
ターゲット：{{target_persona}}

## キャラクター設定
- 一人称：「僕」
- スタンス：プロ個人のスカウトマン。論理的・経験豊富・結果重視。
- 「〜なんだよね」「〜なんよね」「〜だよ」をアクセントとして使ってもOK。

## X投稿の要件（厳守）
- 120文字以内（厳守）
- ハッシュタグなし（原則）
- 絵文字なし
- 短く・強く・核心を突く1文か短文
- 単なる要約ではなく「これを見た人が止まる」1文を狙う

## NG投稿パターン（絶対に書かない）
- 「今日もお疲れ様」「頑張ってるね」系の薄い応援
- 「君はすごい」「ずっと応援してる」「信じてるよ」系の励まし
- 美容（メイク・リップ・アイシャドウ・スキンケア）だけの話
- ふわっとしたメンタル系（「自分を大切に」「可能性は無限大」）
- ポエム・詩的表現
- 汎用自己啓発
- 怪しさ・情報商材感

## 良い投稿例（参考）
> キャバで長く稼げる子って、見た目だけじゃなくて「また話したい」と思わせる返しが上手い。LINEも接客も、相手を気持ちよくさせる一言を積み重ねられる子は強いんだよね。

## 出力フォーマット（JSONのみ）
{
  "platform": "x",
  "text": "120文字以内の投稿文",
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
    {
        "template_id": "pt_06",
        "account_id": "night_scout",
        "template_name": "social_derivative_x_night_scout_v1",
        "version": "v1",
        "purpose": "night_scout アカウント専用X投稿用派生テキスト生成（トンマナ強制）",
        "prompt_text": _SOCIAL_DERIVATIVE_X_NIGHT_SCOUT,
        "active": "TRUE",
        "notes": "night_scout専用。NG：応援系/美容系/ポエム/汎用自己啓発/ハッシュタグ/絵文字。pt_04の汎用テンプレートより優先される。",
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
    "beauty_account": [
        "絶対に治る", "100%効果あり", "病院いらず", "薬と同じ効果",
        "代理店", "会員募集", "MLM", "ねずみ講", "痩せ薬", "飲むだけで痩せる",
    ],
}

ACCOUNT_FORBIDDEN_THEMES: dict[str, list[str]] = {
    "night_scout": [
        "代理店募集", "紹介者募集", "スカウト業界のビジネス解説", "情報商材型の稼ぎ方訴求",
    ],
    "liver_manager": [
        "代理店募集", "情報商材的な副業訴求",
    ],
    "beauty_account": [
        "医療行為の代替推奨", "特定商品の断定的効果訴求",
        "MLM・マルチ商法的勧誘", "過度なダイエット・過激な痩身訴求", "誇張・虚偽の美容効果",
    ],
}

# ------------------------------------------------------------------ #
# アカウント別NGトーンパターン（生成後のトンマナチェック用）
# ------------------------------------------------------------------ #

ACCOUNT_NG_TONE_PATTERNS: dict[str, list[str]] = {
    "night_scout": [
        # 薄い応援・励まし系
        "お疲れ様",
        "今日も頑張",
        "頑張ってるね",
        "君はすごい",
        "本当にすごい",
        "ずっと応援",
        "応援してる",
        "応援してるよ",
        "信じてるよ",
        "味方だよ",
        # 美容系
        "メイク",
        "リップ",
        "アイシャドウ",
        "スキンケア",
        "コスメ",
        # ふわっとしたメンタル系・ポエム系
        "自分を大切",
        "自分を信じて",
        "諦めないで",
        "可能性は無限",
        "ワクワクするはず",
        "大切な存在",
    ],
    "liver_manager": [
        # 薄い応援・励まし系
        "一緒に頑張ろう",
        "応援してます",
        "応援してるよ",
        # ポエム・汎用自己啓発系
        "可能性がある",
        "夢を追える",
        "諦めないで",
        # 怪しい・誇大系
        "誰でも稼げる",
        "スマホ1台で",
        "副業感覚で",
        "お試し感覚で",
        "簡単に稼げる",
        "楽して稼ぐ",
    ],
    "beauty_account": [],
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
