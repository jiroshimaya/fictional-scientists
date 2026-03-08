import json

import pytest

from generate_profile import (
    PROFILE_SCHEMA,
    build_profile_record,
    build_profile_user_prompt,
    find_expanded_csv_in_dir,
    is_id_already_generated,
    load_jsonl,
    resolve_profile_output_path,
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

    def test_正常系_プロンプトに業績受賞歴が含まれない(self):
        prompt = build_profile_user_prompt(
            era="1900–1949",
            gender="男性",
            nationality="日本",
            birth_year=1900,
            field="物理学",
            recent_examples=[],
        )

        assert "業績" not in prompt
        assert "受賞歴" not in prompt

    def test_正常系_プロンプトに研究内容詳細が含まれない(self):
        prompt = build_profile_user_prompt(
            era="1900–1949",
            gender="男性",
            nationality="日本",
            birth_year=1900,
            field="物理学",
            recent_examples=[],
        )

        assert "研究内容（詳細）" not in prompt


class TestProfileSchema:
    def test_正常系_業績受賞歴がスキーマのpropertiesに含まれない(self):
        assert "業績・受賞歴" not in PROFILE_SCHEMA["properties"]

    def test_正常系_研究内容詳細がスキーマのpropertiesに含まれない(self):
        assert "研究内容（詳細）" not in PROFILE_SCHEMA["properties"]

    def test_正常系_業績受賞歴がスキーマのrequiredに含まれない(self):
        assert "業績・受賞歴" not in PROFILE_SCHEMA["required"]

    def test_正常系_研究内容詳細がスキーマのrequiredに含まれない(self):
        assert "研究内容（詳細）" not in PROFILE_SCHEMA["required"]

    def test_正常系_主な分野がスキーマのpropertiesに含まれない(self):
        assert "主な分野" not in PROFILE_SCHEMA["properties"]

    def test_正常系_主な分野がスキーマのrequiredに含まれない(self):
        assert "主な分野" not in PROFILE_SCHEMA["required"]


class TestFindExpandedCsvInDirForProfile:
    def test_正常系_1つのexpanded_csvを発見してパスを返す(self, tmp_path):
        csv_file = tmp_path / "fictional_scientist_quota_expanded_test.csv"
        csv_file.touch()

        result = find_expanded_csv_in_dir(str(tmp_path))

        assert result == str(csv_file)

    def test_異常系_csvが存在しない場合FileNotFoundErrorを送出する(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            find_expanded_csv_in_dir(str(tmp_path))

    def test_異常系_csvが複数ある場合ValueErrorを送出する(self, tmp_path):
        (tmp_path / "fictional_scientist_quota_expanded_a.csv").touch()
        (tmp_path / "fictional_scientist_quota_expanded_b.csv").touch()

        with pytest.raises(ValueError):
            find_expanded_csv_in_dir(str(tmp_path))


class TestResolveProfileOutputPath:
    def test_正常系_dirからprofiles配下のjsonlパスを返す(self, tmp_path):
        result = resolve_profile_output_path(str(tmp_path))

        expected = str(tmp_path / "profiles" / "fictional_scientist_profiles.jsonl")
        assert result == expected


class TestBuildProfileRecord:
    def _make_profile(self):
        return {
            "生年": -300,
            "没年": -230,
            "研究内容（要約）": "光の屈折について研究した",
        }

    def test_正常系_主な分野がレコードに含まれる(self):
        profile = self._make_profile()
        record = build_profile_record(
            scientist_id="古代前期__光学__古代ギリシア__0001",
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            field="光学",
            profile=profile,
        )

        assert record["主な分野"] == "光学"

    def test_正常系_idがレコードに含まれる(self):
        profile = self._make_profile()
        record = build_profile_record(
            scientist_id="古代前期__光学__古代ギリシア__0001",
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            field="光学",
            profile=profile,
        )

        assert record["id"] == "古代前期__光学__古代ギリシア__0001"

    def test_正常系_プロフィールのフィールドがレコードに含まれる(self):
        profile = self._make_profile()
        record = build_profile_record(
            scientist_id="古代前期__光学__古代ギリシア__0001",
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            field="光学",
            profile=profile,
        )

        assert record["生年"] == -300
        assert record["没年"] == -230
        assert record["研究内容（要約）"] == "光の屈折について研究した"
