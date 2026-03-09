from unittest.mock import patch

from generate_portrait_prompt import (
    MODEL,
    build_portrait_user_prompt,
    generate_one_portrait_prompt,
    resolve_portrait_prompt_paths,
    select_appearance,
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


class TestBuildPortraitUserPromptFacialFeatures:
    def _make_profile(self):
        return {
            "国籍": "フランス",
            "生年": 1850,
            "没年": 1920,
            "主な分野": "化学",
            "研究内容（要約）": "有機化合物の合成を研究した",
        }

    def test_正常系_プロンプトに顔の特徴セクションが含まれる(self):
        prompt = build_portrait_user_prompt(
            profile=self._make_profile(), era="近代後期", gender="男性"
        )
        assert "顔" in prompt and (
            "輪郭" in prompt or "目" in prompt or "特徴" in prompt
        )

    def test_正常系_古代前期のプロンプトに具体的な顔の選択肢が含まれる(self):
        profile = {
            **self._make_profile(),
            "国籍": "古代ギリシア",
            "生年": -300,
            "没年": -230,
        }
        prompts = [
            build_portrait_user_prompt(profile=profile, era="古代前期", gender="男性")
            for _ in range(20)
        ]
        assert any(
            any(kw in p for kw in ["楕円", "面長", "四角", "丸顔", "逆三角", "卵形"])
            for p in prompts
        )

    def test_正常系_ルネサンスのプロンプトに目の形の選択肢が含まれる(self):
        profile = {**self._make_profile(), "生年": 1490, "没年": 1555}
        prompts = [
            build_portrait_user_prompt(
                profile=profile, era="ルネサンス・初期近世", gender="女性"
            )
            for _ in range(20)
        ]
        assert any(
            any(kw in p for kw in ["切れ長", "アーモンド", "丸み", "奥まった", "深み"])
            for p in prompts
        )

    def test_正常系_現代前期のプロンプトに年齢感の記述が含まれる(self):
        profile = {**self._make_profile(), "生年": 1910, "没年": 1975}
        prompt = build_portrait_user_prompt(
            profile=profile, era="現代前期", gender="男性"
        )
        assert any(kw in prompt for kw in ["しわ", "年齢", "老齢", "壮年", "中年"])

    def test_正常系_近代後期のプロンプトに鼻の記述が含まれる(self):
        prompt = build_portrait_user_prompt(
            profile=self._make_profile(), era="近代後期", gender="女性"
        )
        assert "鼻" in prompt


class TestBuildPortraitUserPromptClothing:
    def _make_profile(self):
        return {
            "国籍": "古代ギリシア",
            "生年": -300,
            "没年": -230,
            "主な分野": "光学",
            "研究内容（要約）": "光の屈折について研究した",
        }

    def test_正常系_プロンプトに服装セクションが含まれる(self):
        prompt = build_portrait_user_prompt(
            profile=self._make_profile(), era="古代前期", gender="男性"
        )
        assert "服装" in prompt

    def test_正常系_古代前期のプロンプトに古代衣装の記述が含まれる(self):
        prompt = build_portrait_user_prompt(
            profile=self._make_profile(), era="古代前期", gender="男性"
        )
        assert any(
            kw in prompt
            for kw in ["キトン", "ヒマティオン", "トガ", "リネン", "チュニック"]
        )

    def test_正常系_近代後期のプロンプトに近代衣装の記述が含まれる(self):
        profile = {**self._make_profile(), "生年": 1870, "没年": 1940}
        prompt = build_portrait_user_prompt(
            profile=profile, era="近代後期", gender="男性"
        )
        assert any(kw in prompt for kw in ["スーツ", "フロックコート", "和装", "燕尾"])

    def test_正常系_ルネサンスのプロンプトにルネサンス衣装の記述が含まれる(self):
        profile = {**self._make_profile(), "生年": 1490, "没年": 1555}
        prompt = build_portrait_user_prompt(
            profile=profile, era="ルネサンス・初期近世", gender="男性"
        )
        assert any(kw in prompt for kw in ["ダブレット", "ガウン", "ラフ", "袍"])

    def test_正常系_現代前期のプロンプトに現代衣装の記述が含まれる(self):
        profile = {**self._make_profile(), "生年": 1910, "没年": 1975}
        prompt = build_portrait_user_prompt(
            profile=profile, era="現代前期", gender="女性"
        )
        assert any(kw in prompt for kw in ["スーツ", "白衣", "和装", "ワンピース"])


class TestBuildPortraitUserPromptPose:
    def _make_profile(self):
        return {
            "国籍": "古代ギリシア",
            "生年": -300,
            "没年": -230,
            "主な分野": "光学",
            "研究内容（要約）": "光の屈折について研究した",
        }

    def test_正常系_古代前期のプロンプトに左右向きの指定が含まれる(self):
        prompt = build_portrait_user_prompt(
            profile=self._make_profile(), era="古代前期", gender="男性"
        )
        assert any(kw in prompt for kw in ["右向き", "左向き"])

    def test_正常系_近代後期のプロンプトに左右向きの指定が含まれる(self):
        profile = {**self._make_profile(), "生年": 1870, "没年": 1940}
        prompt = build_portrait_user_prompt(
            profile=profile, era="近代後期", gender="女性"
        )
        assert any(kw in prompt for kw in ["右向き", "左向き"])

    def test_正常系_ルネサンスのプロンプトに左右向きの指定が含まれる(self):
        profile = {**self._make_profile(), "生年": 1490, "没年": 1555}
        prompt = build_portrait_user_prompt(
            profile=profile, era="ルネサンス・初期近世", gender="男性"
        )
        assert any(kw in prompt for kw in ["右向き", "左向き"])


class TestBuildPortraitUserPromptPhysicalTraits:
    def _make_profile(self):
        return {
            "国籍": "フランス",
            "生年": 1850,
            "没年": 1920,
            "主な分野": "化学",
            "研究内容（要約）": "有機化合物の合成を研究した",
        }

    def test_正常系_プロンプトに外見特徴セクションが含まれる(self):
        prompt = build_portrait_user_prompt(
            profile=self._make_profile(), era="近代後期", gender="女性"
        )
        assert "外見" in prompt or "体格" in prompt or "髪" in prompt

    def test_正常系_古代前期のプロンプトに肌色の記述が含まれる(self):
        profile = {
            **self._make_profile(),
            "国籍": "古代エジプト",
            "生年": -500,
            "没年": -430,
        }
        prompt = build_portrait_user_prompt(
            profile=profile, era="古代前期", gender="男性"
        )
        assert any(kw in prompt for kw in ["肌", "オリーブ", "浅黒"])

    def test_正常系_近代後期のプロンプトに髪の記述が含まれる(self):
        prompt = build_portrait_user_prompt(
            profile=self._make_profile(), era="近代後期", gender="男性"
        )
        assert "髪" in prompt

    def test_正常系_現代前期のプロンプトに外見特徴が含まれる(self):
        profile = {**self._make_profile(), "生年": 1910, "没年": 1975}
        prompt = build_portrait_user_prompt(
            profile=profile, era="現代前期", gender="女性"
        )
        assert "髪" in prompt


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


class TestSelectAppearance:
    def test_正常系_返値に必須の外見項目が含まれる(self):
        result = select_appearance(
            nationality="フランス", era="近代後期", gender="男性"
        )
        for key in [
            "skin_tone",
            "hair_color",
            "hair_style",
            "eye_shape",
            "face_shape",
            "build",
            "nose_shape",
        ]:
            assert key in result, f"キー '{key}' が結果に含まれていない"

    def test_正常系_東アジア国籍で自然な肌色が返る(self):
        result = select_appearance(nationality="日本", era="現代中期", gender="男性")
        assert any(kw in result["skin_tone"] for kw in ["白", "黄", "明るい", "淡い"])

    def test_正常系_北欧国籍で白い肌系が返る(self):
        assert any(
            any(
                kw
                in select_appearance(
                    nationality="スウェーデン", era="近代後期", gender="女性"
                )["skin_tone"]
                for kw in ["白", "薄い", "淡い", "明るい"]
            )
            for _ in range(20)
        )

    def test_正常系_アフリカ国籍で暗い肌系が返る(self):
        result = select_appearance(
            nationality="ナイジェリア", era="現代後期", gender="男性"
        )
        assert any(
            kw in result["skin_tone"] for kw in ["褐色", "黒", "暗い", "深い", "濃い"]
        )

    def test_正常系_男性に髭属性が含まれる(self):
        result = select_appearance(
            nationality="フランス", era="近代後期", gender="男性"
        )
        assert "beard" in result

    def test_正常系_女性に髭属性が含まれない(self):
        result = select_appearance(
            nationality="フランス", era="近代後期", gender="女性"
        )
        assert "beard" not in result

    def test_正常系_東アジア国籍で黒髪系が返る(self):
        result = select_appearance(nationality="中国", era="現代中期", gender="女性")
        assert any(kw in result["hair_color"] for kw in ["黒", "黒褐"])

    def test_正常系_顔の輪郭に楕円系のキーワードが含まれうる(self):
        results = [
            select_appearance(nationality="フランス", era="近代後期", gender="男性")[
                "face_shape"
            ]
            for _ in range(20)
        ]
        assert any(
            any(kw in r for kw in ["楕円", "面長", "四角", "丸顔", "逆三角", "卵形"])
            for r in results
        )

    def test_正常系_目の形にアーモンド系のキーワードが含まれうる(self):
        results = [
            select_appearance(
                nationality="古代ギリシア", era="ルネサンス・初期近世", gender="女性"
            )["eye_shape"]
            for _ in range(20)
        ]
        assert any(
            any(kw in r for kw in ["アーモンド", "切れ長", "丸い", "奥まった"])
            for r in results
        )

    def test_正常系_未知の国籍でもデフォルト候補が返る(self):
        result = select_appearance(
            nationality="架空の国", era="現代中期", gender="男性"
        )
        assert "skin_tone" in result
        assert "hair_color" in result

    def test_正常系_複数回の呼び出しでバリエーションが生じる(self):
        results = set()
        for _ in range(30):
            r = select_appearance(nationality="フランス", era="近代後期", gender="男性")
            results.add(r["skin_tone"] + "|" + r["hair_color"] + "|" + r["hair_style"])
        assert len(results) > 1, "30回呼び出してもバリエーションが生じなかった"

    def test_正常系_ノンバイナリーでも外見項目が返る(self):
        result = select_appearance(
            nationality="フランス", era="近代後期", gender="ノンバイナリー／その他"
        )
        for key in [
            "skin_tone",
            "hair_color",
            "hair_style",
            "eye_shape",
            "face_shape",
            "build",
            "nose_shape",
        ]:
            assert key in result
