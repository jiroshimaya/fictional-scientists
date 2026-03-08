from generate_portrait_prompt import build_portrait_user_prompt, resolve_portrait_prompt_paths


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

        assert any(
            kw in prompt
            for kw in ["石", "stone", "sculpture", "fresco", "mosaic", "relief"]
        )

    def test_正常系_近代後期のプロンプトに写真系の媒体が含まれる(self):
        profile = {**self._make_profile(), "生年": 1870, "没年": 1940}
        prompt = build_portrait_user_prompt(
            profile=profile, era="近代後期", gender="女性"
        )

        assert any(kw in prompt for kw in ["photograph", "写真", "photo"])

    def test_正常系_ルネサンスのプロンプトに油彩系の媒体が含まれる(self):
        profile = {**self._make_profile(), "生年": 1480, "没年": 1550}
        prompt = build_portrait_user_prompt(
            profile=profile, era="ルネサンス・初期近世", gender="男性"
        )

        assert any(
            kw in prompt for kw in ["oil", "painting", "engraving", "木版", "油彩"]
        )

    def test_正常系_古代前期のプロンプトに保存状態の記述が含まれる(self):
        profile = {**self._make_profile(), "生年": -300}
        prompt = build_portrait_user_prompt(
            profile=profile, era="古代前期", gender="女性"
        )

        assert any(
            kw in prompt
            for kw in [
                "weathered",
                "damaged",
                "fragment",
                "worn",
                "磨耗",
                "欠損",
                "断片",
            ]
        )

    def test_正常系_プロンプトに名前が含まれない(self):
        profile = self._make_profile()
        prompt = build_portrait_user_prompt(
            profile=profile, era="古代前期", gender="男性"
        )

        assert "名前" not in prompt


class TestResolvePortraitPromptPaths:
    def test_正常系_dirからinputとoutputパスを解決する(self, tmp_path):
        input_p, output_p = resolve_portrait_prompt_paths(str(tmp_path))

        assert input_p == str(tmp_path / "profiles" / "fictional_scientist_profiles.jsonl")
        assert output_p == str(tmp_path / "fictional_scientists_portraits.jsonl")
