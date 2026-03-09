from unittest.mock import patch

from generate_portrait_prompt import (
    MODEL,
    build_portrait_user_prompt,
    generate_one_portrait_prompt,
    resolve_portrait_prompt_paths,
)


class TestBuildPortraitUserPromptEraMedia:
    def _make_profile(self):
        return {
            "国籍": "古代ギリシア",
            "生年": -300,
            "没年": -230,
            "主な分野": "光学",
            "研究内容（要約）": "光の屈折について研究した",
        }

    def test_正常系_古代前期のプロンプトに石像系の媒体が含まれる(self):
        profile = {**self._make_profile(), "生年": -300}
        prompt = build_portrait_user_prompt(
            profile=profile, era="古代前期", gender="男性"
        )

        assert any(kw in prompt for kw in ["石彫", "大理石", "フレスコ", "モザイク"])

    def test_正常系_近代後期のプロンプトに写真系の媒体が含まれる(self):
        profile = {**self._make_profile(), "生年": 1870, "没年": 1940}
        prompt = build_portrait_user_prompt(
            profile=profile, era="近代後期", gender="女性"
        )

        assert "写真" in prompt

    def test_正常系_ルネサンスのプロンプトに油彩系の媒体が含まれる(self):
        profile = {**self._make_profile(), "生年": 1480, "没年": 1550}
        prompt = build_portrait_user_prompt(
            profile=profile, era="ルネサンス・初期近世", gender="男性"
        )

        assert any(kw in prompt for kw in ["油彩", "木版"])

    def test_正常系_古代前期のプロンプトに保存状態の記述が含まれる(self):
        profile = {**self._make_profile(), "生年": -300}
        prompt = build_portrait_user_prompt(
            profile=profile, era="古代前期", gender="女性"
        )

        assert any(kw in prompt for kw in ["磨耗", "欠損", "断片", "風化"])

    def test_正常系_プロンプトに名前が含まれない(self):
        profile = self._make_profile()
        prompt = build_portrait_user_prompt(
            profile=profile, era="古代前期", gender="男性"
        )

        assert "名前" not in prompt


class TestResolvePortraitPromptPaths:
    def test_正常系_dirからinputとoutputパスを解決する(self, tmp_path):
        input_p, output_p = resolve_portrait_prompt_paths(str(tmp_path))

        assert input_p == str(tmp_path / "profiles.jsonl")
        assert output_p == str(tmp_path / "portrait_prompts.jsonl")


class TestGenerateOnePortraitPromptModel:
    _MOCK_RESULT = {"portrait_prompt": "テスト用プロンプト"}
    _PROFILE = {
        "国籍": "日本",
        "生年": "1900年",
        "没年": "1960年",
        "主な分野": "物理学",
        "研究内容（要約）": "電磁波を研究した",
    }

    def test_正常系_デフォルトでMODEL定数が使われる(self):
        with patch(
            "generate_portrait_prompt.create_structured_json",
            return_value=self._MOCK_RESULT,
        ) as mock_create:
            generate_one_portrait_prompt(
                profile=self._PROFILE,
                era="現代前期",
                gender="男性",
            )
            assert mock_create.call_args.kwargs["model"] == MODEL

    def test_正常系_指定したmodelがcreate_structured_jsonに渡される(self):
        with patch(
            "generate_portrait_prompt.create_structured_json",
            return_value=self._MOCK_RESULT,
        ) as mock_create:
            generate_one_portrait_prompt(
                profile=self._PROFILE,
                era="現代前期",
                gender="男性",
                model="gpt-4o",
            )
            assert mock_create.call_args.kwargs["model"] == "gpt-4o"
