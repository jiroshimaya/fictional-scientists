import json


from generate_profile import (
    build_profile_user_prompt,
    is_id_already_generated,
    load_jsonl,
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

    def test_正常系_プロンプトに時代区分が含まれる(self):
        prompt = build_profile_user_prompt(
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
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            birth_year=-320,
            field="光学",
            recent_examples=[],
        )

        assert "-320" in prompt or "320" in prompt
