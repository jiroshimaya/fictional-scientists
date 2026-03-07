from generate import build_profile_user_prompt


class TestBuildProfileUserPromptSummaryLength:
    def test_正常系_要約が50字以内の制約がプロンプトに含まれる(self):
        prompt = build_profile_user_prompt(
            era="1900–1949",
            gender="男性",
            nationality="日本",
            birth_year=1900,
            field="物理学",
            recent_examples=[],
        )
        assert "50字以内" in prompt

    def test_正常系_旧い120から220字の制約がプロンプトに含まれない(self):
        prompt = build_profile_user_prompt(
            era="1900–1949",
            gender="男性",
            nationality="日本",
            birth_year=1900,
            field="物理学",
            recent_examples=[],
        )
        assert "120〜220字" not in prompt
