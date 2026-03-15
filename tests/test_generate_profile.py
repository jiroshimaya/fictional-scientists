import json
from unittest.mock import patch

from generate_profile import (
    MODEL,
    PROFILE_SCHEMA,
    build_profile_record,
    build_profile_user_prompt,
    generate_one_profile,
    get_openai_client,
    resolve_quota_input_path,
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

    def test_エッジケース_空ファイルで空リストを返す(self, tmp_path):
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text("", encoding="utf-8")

        assert load_jsonl(str(jsonl_file)) == []


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

    def test_正常系_プロンプトに生年没年の柔軟な表記指示が含まれる(self):
        prompt = build_profile_user_prompt(
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            birth_year=-320,
            field="光学",
            recent_examples=[],
        )

        assert "頃" in prompt or "不明" in prompt


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

    def test_正常系_生年スキーマの型がstringである(self):
        assert PROFILE_SCHEMA["properties"]["生年"]["type"] == "string"

    def test_正常系_没年スキーマの型がstringとnullを含む(self):
        assert "string" in PROFILE_SCHEMA["properties"]["没年"]["type"]
        assert "null" in PROFILE_SCHEMA["properties"]["没年"]["type"]


class TestResolveQuotaInputPathForProfile:
    def test_正常系_dirからquota_csvのパスを返す(self, tmp_path):
        result = resolve_quota_input_path(str(tmp_path))

        expected = str(tmp_path / "quota.csv")
        assert result == expected


class TestResolveProfileOutputPath:
    def test_正常系_dirからprofiles_jsonlのパスを返す(self, tmp_path):
        result = resolve_profile_output_path(str(tmp_path))

        expected = str(tmp_path / "profiles.jsonl")
        assert result == expected


class TestBuildProfileRecord:
    def _make_profile(self):
        return {
            "生年": "1860年",
            "没年": "1928年",
            "研究内容（要約）": "電磁波の干渉現象を実験的に再検証した",
        }

    def test_正常系_主な分野がレコードに含まれる(self):
        profile = self._make_profile()
        record = build_profile_record(
            scientist_id="近代後期__実験物理__日本__0001",
            era="近代後期",
            gender="男性",
            nationality="日本",
            field="実験物理",
            profile=profile,
        )

        assert record["主な分野"] == "実験物理"

    def test_正常系_idがレコードに含まれる(self):
        profile = self._make_profile()
        record = build_profile_record(
            scientist_id="近代後期__実験物理__日本__0001",
            era="近代後期",
            gender="男性",
            nationality="日本",
            field="実験物理",
            profile=profile,
        )

        assert record["id"] == "近代後期__実験物理__日本__0001"

    def test_正常系_国籍がレコードに含まれる(self):
        profile = self._make_profile()
        record = build_profile_record(
            scientist_id="近代後期__実験物理__日本__0001",
            era="近代後期",
            gender="男性",
            nationality="日本",
            field="実験物理",
            profile=profile,
        )

        assert record["国籍"] == "日本"

    def test_正常系_profileの生年没年研究内容がレコードに含まれる(self):
        profile = self._make_profile()
        record = build_profile_record(
            scientist_id="近代後期__実験物理__日本__0001",
            era="近代後期",
            gender="男性",
            nationality="日本",
            field="実験物理",
            profile=profile,
        )

        assert record["生年"] == "1860年"
        assert record["没年"] == "1928年"
        assert record["研究内容（要約）"] == "電磁波の干渉現象を実験的に再検証した"

    def test_正常系_古代の人物で頃表記の生年没年がレコードに含まれる(self):
        profile = {
            "生年": "紀元前320年頃",
            "没年": "紀元前250年頃",
            "研究内容（要約）": "光の屈折と反射を体系的に論じた",
        }
        record = build_profile_record(
            scientist_id="古代前期__光学__古代ギリシア__0001",
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            field="光学",
            profile=profile,
        )

        assert record["生年"] == "紀元前320年頃"
        assert record["没年"] == "紀元前250年頃"

    def test_正常系_生年不明の人物でnull以外の没年がレコードに含まれる(self):
        profile = {
            "生年": "不明",
            "没年": None,
            "研究内容（要約）": "天体観測の方法を整理した",
        }
        record = build_profile_record(
            scientist_id="古代前期__天文学__古代ギリシア__0001",
            era="古代前期",
            gender="男性",
            nationality="古代ギリシア",
            field="天文学",
            profile=profile,
        )

        assert record["生年"] == "不明"
        assert record["没年"] is None


class TestGenerateOneProfileModel:
    _MOCK_RESULT = {
        "生年": "1900年",
        "没年": "1960年",
        "研究内容（要約）": "電磁波を研究した",
    }

    def test_正常系_デフォルトでMODEL定数が使われる(self):
        with patch(
            "generate_profile.create_structured_json", return_value=self._MOCK_RESULT
        ) as mock_create:
            generate_one_profile(
                era="現代前期",
                gender="男性",
                nationality="日本",
                birth_year=1900,
                field="物理学",
                existing_profiles=[],
            )
            assert mock_create.call_args.kwargs["model"] == MODEL

    def test_正常系_指定したmodelがcreate_structured_jsonに渡される(self):
        with patch(
            "generate_profile.create_structured_json", return_value=self._MOCK_RESULT
        ) as mock_create:
            generate_one_profile(
                era="現代前期",
                gender="男性",
                nationality="日本",
                birth_year=1900,
                field="物理学",
                existing_profiles=[],
                model="gpt-4o",
            )
            assert mock_create.call_args.kwargs["model"] == "gpt-4o"


class TestGetOpenAIClient:
    def test_異常系_apiキー未設定ならRuntimeErrorを送出する(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        get_openai_client.cache_clear()

        try:
            try:
                get_openai_client()
            except RuntimeError as exc:
                assert str(exc) == "OPENAI_API_KEY is not set"
            else:
                raise AssertionError("RuntimeError was not raised")
        finally:
            get_openai_client.cache_clear()
