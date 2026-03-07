import json

from generate_text import (
    build_profile_user_prompt,
    build_portrait_user_prompt,
    count_generated_for_row,
    is_id_already_generated,
    load_jsonl,
)


class TestLoadJsonl:
    def test_正常系_存在するjsonlファイルを読み込む(self, tmp_path):
        jsonl_file = tmp_path / "test.jsonl"
        records = [
            {
                "era": "古代前期",
                "gender": "女性",
                "国籍": "古代ギリシア",
                "主な分野": "光学",
            },
            {
                "era": "1900–1949",
                "gender": "男性",
                "国籍": "日本",
                "主な分野": "物理学",
            },
        ]
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        result = load_jsonl(str(jsonl_file))

        assert len(result) == 2
        assert result[0]["era"] == "古代前期"
        assert result[1]["国籍"] == "日本"

    def test_エッジケース_ファイルが存在しない場合に空リストを返す(self, tmp_path):
        result = load_jsonl(str(tmp_path / "nonexistent.jsonl"))

        assert result == []

    def test_エッジケース_空ファイルで空リストを返す(self, tmp_path):
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text("", encoding="utf-8")

        result = load_jsonl(str(jsonl_file))

        assert result == []


class TestCountGeneratedForRow:
    def _make_record(self, era, gender, nationality, field):
        return {"era": era, "gender": gender, "国籍": nationality, "主な分野": field}

    def test_正常系_一致するレコードの数を返す(self):
        records = [
            self._make_record("古代前期", "女性", "古代ギリシア", "光学"),
            self._make_record("古代前期", "女性", "古代ギリシア", "光学"),
            self._make_record("1900–1949", "男性", "日本", "物理学"),
        ]

        result = count_generated_for_row(
            records, "古代前期", "女性", "古代ギリシア", "光学"
        )

        assert result == 2

    def test_正常系_一致しない場合に0を返す(self):
        records = [
            self._make_record("1900–1949", "男性", "日本", "物理学"),
        ]

        result = count_generated_for_row(
            records, "古代前期", "女性", "古代ギリシア", "光学"
        )

        assert result == 0

    def test_エッジケース_空リストで0を返す(self):
        result = count_generated_for_row([], "古代前期", "女性", "古代ギリシア", "光学")

        assert result == 0

    def test_正常系_eraのみ一致してもカウントしない(self):
        records = [
            self._make_record("古代前期", "男性", "古代ギリシア", "光学"),
        ]

        result = count_generated_for_row(
            records, "古代前期", "女性", "古代ギリシア", "光学"
        )

        assert result == 0

    def test_正常系_nationalityのみ異なる場合はカウントしない(self):
        records = [
            self._make_record("古代前期", "女性", "ローマ共和政・帝政圏", "光学"),
        ]

        result = count_generated_for_row(
            records, "古代前期", "女性", "古代ギリシア", "光学"
        )

        assert result == 0


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


class TestIsIdAlreadyGenerated:
    def test_正常系_同じidのレコードが存在する場合にTrueを返す(self):
        records = [{"id": 1, "名前": "テスト"}, {"id": 2, "名前": "テスト2"}]

        assert is_id_already_generated(records, 1) is True

    def test_正常系_idが存在しない場合にFalseを返す(self):
        records = [{"id": 1, "名前": "テスト"}, {"id": 2, "名前": "テスト2"}]

        assert is_id_already_generated(records, 99) is False

    def test_エッジケース_空リストでFalseを返す(self):
        assert is_id_already_generated([], 1) is False

    def test_エッジケース_id列のないレコードはスキップされる(self):
        records = [{"名前": "テスト"}]

        assert is_id_already_generated(records, 1) is False


class TestBuildPortraitUserPromptEraMedia:
    """ポートレートプロンプトが時代に応じた媒体情報を含むことを確認する。"""

    def _make_profile(self):
        return {
            "名前": "テスト太郎",
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

    def test_正常系_胸像固定でなくポーズバリエーションの指示が含まれる(self):
        profile = {**self._make_profile(), "生年": 1900, "没年": None}
        prompt = build_portrait_user_prompt(
            profile=profile, era="現代前期", gender="男性"
        )

        assert "胸像、半身像、上半身ポートレートを基本にする" not in prompt
