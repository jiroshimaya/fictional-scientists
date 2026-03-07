import csv
import json
import pathlib


from generate_profile import (
    build_portrait_user_prompt,
    build_profile_user_prompt,
    is_id_already_generated,
    load_jsonl,
    load_names_by_id,
)


class TestLoadJsonl:
    def test_正常系_存在するjsonlファイルを読み込む(self, tmp_path):
        jsonl_file = tmp_path / "test.jsonl"
        records = [
            {"id": "id1", "era": "古代前期", "名前": "テスト"},
            {"id": "id2", "era": "1900–1949", "名前": "テスト2"},
        ]
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        result = load_jsonl(str(jsonl_file))

        assert len(result) == 2
        assert result[0]["id"] == "id1"

    def test_エッジケース_ファイルが存在しない場合に空リストを返す(self, tmp_path):
        assert load_jsonl(str(tmp_path / "nonexistent.jsonl")) == []


class TestLoadNamesById:
    def _write_names_csv(self, path: pathlib.Path, rows: list[dict]) -> None:
        fieldnames = ["id", "名前", "姓", "名", "ナマエ", "セイ", "メイ"]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_正常系_CSVからidをキーとした辞書を返す(self, tmp_path):
        csv_file = tmp_path / "names.csv"
        self._write_names_csv(
            csv_file,
            [
                {
                    "id": "古代前期__光学__古代ギリシア__0001",
                    "名前": "テスト太郎",
                    "姓": "テスト",
                    "名": "太郎",
                    "ナマエ": "テストタロウ",
                    "セイ": "テスト",
                    "メイ": "タロウ",
                },
            ],
        )

        result = load_names_by_id(str(csv_file))

        assert "古代前期__光学__古代ギリシア__0001" in result
        assert result["古代前期__光学__古代ギリシア__0001"]["名前"] == "テスト太郎"

    def test_エッジケース_ファイルが存在しない場合に空辞書を返す(self, tmp_path):
        assert load_names_by_id(str(tmp_path / "nonexistent.csv")) == {}


class TestIsIdAlreadyGenerated:
    def test_正常系_同じidのレコードが存在する場合にTrueを返す(self):
        records = [{"id": "id1", "名前": "テスト"}, {"id": "id2"}]

        assert is_id_already_generated(records, "id1") is True

    def test_正常系_idが存在しない場合にFalseを返す(self):
        records = [{"id": "id1", "名前": "テスト"}]

        assert is_id_already_generated(records, "id_unknown") is False

    def test_エッジケース_空リストでFalseを返す(self):
        assert is_id_already_generated([], "id1") is False

    def test_正常系_複合idでも判定できる(self):
        records = [{"id": "古代前期__光学__古代ギリシア__0001"}]

        assert (
            is_id_already_generated(records, "古代前期__光学__古代ギリシア__0001")
            is True
        )
        assert (
            is_id_already_generated(records, "古代前期__光学__古代ギリシア__0002")
            is False
        )


class TestBuildProfileUserPrompt:
    def test_正常系_プロンプトに名前が含まれる(self):
        prompt = build_profile_user_prompt(
            name="テスト・アリストテレス",
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            birth_year=-350,
            field="光学",
            recent_examples=[],
        )

        assert "テスト・アリストテレス" in prompt

    def test_正常系_要約が50字以内の制約がプロンプトに含まれる(self):
        prompt = build_profile_user_prompt(
            name="テスト",
            era="1900–1949",
            gender="男性",
            nationality="日本",
            birth_year=1900,
            field="物理学",
            recent_examples=[],
        )

        assert "50字以内" in prompt

    def test_正常系_プロンプトに時代区分が含まれる(self):
        prompt = build_profile_user_prompt(
            name="テスト",
            era="現代前期",
            gender="女性",
            nationality="日本",
            birth_year=1920,
            field="化学",
            recent_examples=[],
        )

        assert "現代前期" in prompt

    def test_正常系_プロンプトに生年が含まれる(self):
        prompt = build_profile_user_prompt(
            name="テスト",
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            birth_year=-320,
            field="光学",
            recent_examples=[],
        )

        assert "-320" in prompt or "320" in prompt


class TestBuildPortraitUserPromptEraMedia:
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
