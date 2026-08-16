#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from generation.source_copyedit import clean_source_post_text  # noqa: E402
from public_post_quality import final_public_post_validator, voice_persona_validation  # noqa: E402


GOOD = {
    "night_scout": "これからキャバやりたい子は、体入前に時給だけで決めない方がいい。\n\n僕が一番見るのは、週何回なら無理なく続けられるかなんだよね。早上がり、ノルマ、控除、客層で、同じ時給でも手取りと疲れ方はかなり変わる。\n\n担当には週2出勤の手取り例まで聞いておく。ここが働き方に合う店を選ぶのが大事だよ。",
    "liver_manager": "コメントが止まると、話題を増やさなきゃって焦るよね。\n\nでも、今日は忙しかった？ゆっくりできた？の二択なら、初見さんも返しやすい。\n\n私なら冒頭10分で使う二択を3つだけ用意するかな。全部変えなくて大丈夫。答えやすい入口を一つ作るだけで、会話は始まりやすくなるよ。",
}


def main() -> int:
    fixtures = json.loads((ROOT / "tests/fixtures/v27_v28_voice_regressions.json").read_text(encoding="utf-8"))
    for account_id, texts in fixtures.items():
        assert len(texts) == 5
        for text in texts:
            result = voice_persona_validation(text, account_id)
            assert result["status"] == "BLOCKED", (account_id, result)

    for account_id, text in GOOD.items():
        voice = voice_persona_validation(text, account_id)
        final = final_public_post_validator(text, account_id)
        assert voice["status"] == "VOICE_PERSONA_PASS", (account_id, voice)
        assert voice["score"] >= 85
        assert final["voice_persona_check"]["status"] == "VOICE_PERSONA_PASS"

    wrong_liver = GOOD["liver_manager"].replace("私なら", "僕なら")
    assert voice_persona_validation(wrong_liver, "liver_manager")["status"] == "BLOCKED"
    formal = "僕は夜職の店選びについて判断します。時給とノルマを確認します。客層も確認します。担当へ相談します。"
    assert voice_persona_validation(formal, "night_scout")["status"] == "BLOCKED"
    cleaned = clean_source_post_text("僕が次の配信で試します。", account_id="liver_manager")
    assert "僕" not in cleaned and "私" in cleaned, cleaned
    print("PASS: canonical account voice blocks all V27/V28 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
