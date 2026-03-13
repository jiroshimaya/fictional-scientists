import io
import csv
from urllib.error import HTTPError

from create_scientists_csv import (
    SCIENTISTS_FIELDNAMES,
    build_article_url,
    build_categorymembers_url,
    build_page_categories_url,
    build_scientist_row,
    collect_scientist_rows,
    fetch_categorymembers_page,
    fetch_page_category_titles,
    get_default_root_categories,
    get_retry_delay,
    infer_birth_year_from_categories,
    infer_era_name_from_birth_year,
    infer_gender_from_categories,
    infer_nationality_from_categories,
    infer_scientist_memo_fields,
    load_quota_reference,
    load_existing_scientists,
    list_category_members,
    resolve_scientists_output_path,
    write_scientists_csv,
)


class TestBuildCategorymembersUrl:
    def test_正常系_categorymembers_urlを組み立てる(self):
        url = build_categorymembers_url("Category:科学者", language="ja", limit=50)

        assert "ja.wikipedia.org" in url
        assert "cmtitle=Category:%E7%A7%91%E5%AD%A6%E8%80%85" in url
        assert "cmlimit=50" in url

    def test_正常系_continue_tokenを付けられる(self):
        url = build_categorymembers_url(
            "Category:Scientists",
            language="en",
            continue_token="next|token",
        )

        assert "cmcontinue=next|token" in url


class TestBuildPageCategoriesUrl:
    def test_正常系_page_categories_urlを組み立てる(self):
        url = build_page_categories_url("アリストテレス", language="ja")

        assert "prop=categories" in url
        assert (
            "titles=%E3%82%A2%E3%83%AA%E3%82%B9%E3%83%88%E3%83%86%E3%83%AC%E3%82%B9"
            in url
        )


class TestListCategoryMembers:
    def test_正常系_continueをたどって全件返す(self, monkeypatch):
        responses = [
            {
                "query": {"categorymembers": [{"pageid": 1, "ns": 0, "title": "A"}]},
                "continue": {"cmcontinue": "next"},
            },
            {
                "query": {"categorymembers": [{"pageid": 2, "ns": 0, "title": "B"}]},
            },
        ]

        def fake_fetch(category_title, language="ja", limit=500, continue_token=None):
            assert category_title == "Category:科学者"
            return responses.pop(0)

        monkeypatch.setattr(
            "create_scientists_csv.fetch_categorymembers_page",
            fake_fetch,
        )

        members = list_category_members("Category:科学者")

        assert [member["title"] for member in members] == ["A", "B"]


class TestRetryHandling:
    def test_正常系_retry_afterヘッダを待機秒に使う(self):
        error = HTTPError(
            url="https://example.com",
            code=429,
            msg="Too Many Requests",
            hdrs={"Retry-After": "3"},
            fp=io.BytesIO(b""),
        )

        assert get_retry_delay(error, attempt=1) == 3.0

    def test_正常系_429のあと再試行して取得できる(self, monkeypatch):
        responses = [
            HTTPError(
                url="https://example.com",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=io.BytesIO(b""),
            ),
            io.BytesIO(
                b'{"query":{"categorymembers":[{"pageid":1,"ns":0,"title":"A"}]}}'
            ),
        ]

        class _Response:
            def __init__(self, payload: io.BytesIO):
                self.payload = payload

            def read(self):
                return self.payload.read()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(request, timeout=None):
            current = responses.pop(0)
            if isinstance(current, HTTPError):
                raise current
            return _Response(current)

        monkeypatch.setattr("create_scientists_csv.urlopen", fake_urlopen)
        monkeypatch.setattr("create_scientists_csv.time.sleep", lambda _: None)

        result = fetch_categorymembers_page("Category:科学者")

        assert result["query"]["categorymembers"][0]["title"] == "A"

    def test_正常系_page_categories取得で429後に再試行できる(self, monkeypatch):
        responses = [
            HTTPError(
                url="https://example.com",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=io.BytesIO(b""),
            ),
            io.BytesIO(
                b'{"query":{"pages":{"1":{"categories":[{"title":"Category:%E7%B4%80%E5%85%83%E5%89%8D384%E5%B9%B4%E7%94%9F"}]}}}}'
            ),
        ]

        class _Response:
            def __init__(self, payload: io.BytesIO):
                self.payload = payload

            def read(self):
                return self.payload.read()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(request, timeout=None):
            current = responses.pop(0)
            if isinstance(current, HTTPError):
                raise current
            return _Response(current)

        monkeypatch.setattr("create_scientists_csv.urlopen", fake_urlopen)
        monkeypatch.setattr("create_scientists_csv.time.sleep", lambda _: None)

        result = fetch_page_category_titles("アリストテレス")

        assert "Category:%E7%B4%80%E5%85%83%E5%89%8D384%E5%B9%B4%E7%94%9F" in result


class TestBuildArticleUrl:
    def test_正常系_記事urlを組み立てる(self):
        url = build_article_url("アルベルト・アインシュタイン", language="ja")

        assert url.startswith("https://ja.wikipedia.org/wiki/")
        assert "%E3%82%A2" in url


class TestLoadExistingScientists:
    def test_正常系_既存scientists_csvからメモ列を読み込める(self, tmp_path):
        output_path = tmp_path / "scientists.csv"
        rows = [
            {
                "id": "wikipedia-ja-736",
                "名前": "アルベルト・アインシュタイン",
                "era_name": "近代後期",
                "gender": "男性",
                "nationality_region": "西欧",
                "nationality": "ドイツ",
                "wikipedia_title": "アルベルト・アインシュタイン",
                "url": "https://ja.wikipedia.org/wiki/Albert_Einstein",
                "language": "ja",
                "source_category": "Category:物理学者",
                "pageid": "736",
            }
        ]
        write_scientists_csv(str(output_path), rows)

        result = load_existing_scientists(str(output_path))

        assert result["wikipedia-ja-736"]["era_name"] == "近代後期"


class TestInferenceHelpers:
    def test_正常系_カテゴリから生年を推定できる(self):
        birth_year = infer_birth_year_from_categories(
            ["Category:紀元前384年生"], language="ja"
        )

        assert birth_year == -384

    def test_正常系_生年からera_nameを推定できる(self):
        era_ranges, _ = load_quota_reference()

        era_name = infer_era_name_from_birth_year(1879, era_ranges)

        assert era_name == "近代後期"

    def test_正常系_カテゴリからgenderを推定できる(self):
        gender = infer_gender_from_categories(["Category:女性物理学者"])

        assert gender == "女性"

    def test_正常系_カテゴリからnationalityを推定できる(self):
        _, nationality_to_region = load_quota_reference()

        nationality = infer_nationality_from_categories(
            ["Category:古代ギリシアの哲学者"], nationality_to_region
        )

        assert nationality == "古代ギリシア"

    def test_正常系_カテゴリからメモ列をまとめて推定できる(self, monkeypatch):
        era_ranges, nationality_to_region = load_quota_reference()
        monkeypatch.setattr(
            "create_scientists_csv.fetch_page_category_titles",
            lambda title, language="ja", request_sleep=0.2: [
                "Category:紀元前384年生",
                "Category:古代ギリシアの哲学者",
            ],
        )

        fields = infer_scientist_memo_fields(
            title="アリストテレス",
            language="ja",
            existing_row=None,
            era_ranges=era_ranges,
            nationality_to_region=nationality_to_region,
        )

        assert fields["era_name"] == "古代前期"
        assert fields["gender"] == "男性"
        assert fields["nationality_region"] == "東地中海"
        assert fields["nationality"] == "古代ギリシア"


class TestBuildScientistRow:
    def test_正常系_memberからscientists行を作る(self):
        row = build_scientist_row(
            member={"pageid": 736, "title": "アルベルト・アインシュタイン"},
            language="ja",
            source_category="Category:科学者",
        )

        assert row == {
            "id": "wikipedia-ja-736",
            "名前": "アルベルト・アインシュタイン",
            "era_name": "",
            "gender": "",
            "nationality_region": "",
            "nationality": "",
            "wikipedia_title": "アルベルト・アインシュタイン",
            "url": "https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%AB%E3%83%99%E3%83%AB%E3%83%88%E3%83%BB%E3%82%A2%E3%82%A4%E3%83%B3%E3%82%B7%E3%83%A5%E3%82%BF%E3%82%A4%E3%83%B3",
            "language": "ja",
            "source_category": "Category:科学者",
            "pageid": "736",
        }

    def test_正常系_既存メモ列を保持する(self):
        row = build_scientist_row(
            member={"pageid": 736, "title": "アルベルト・アインシュタイン"},
            language="ja",
            source_category="Category:科学者",
            existing_row={
                "era_name": "近代後期",
                "gender": "男性",
                "nationality_region": "西欧",
                "nationality": "ドイツ",
            },
        )

        assert row["era_name"] == "近代後期"
        assert row["gender"] == "男性"
        assert row["nationality_region"] == "西欧"
        assert row["nationality"] == "ドイツ"


class TestGetDefaultRootCategories:
    def test_正常系_日本語版の既定カテゴリに自然哲学者が含まれる(self):
        categories = get_default_root_categories("ja")

        assert "Category:科学者" in categories
        assert "Category:自然哲学者" in categories
        assert "Category:科学哲学者" in categories

    def test_正常系_英語版の既定カテゴリにNatural_philosophersが含まれる(self):
        categories = get_default_root_categories("en")

        assert "Category:Scientists" in categories
        assert "Category:Natural philosophers" in categories


class TestCollectScientistRows:
    def test_正常系_複数カテゴリとサブカテゴリを再帰してページだけ集める(
        self, monkeypatch
    ):
        def fake_list(category_title, language="ja", limit=500, request_sleep=0.2):
            if category_title == "Category:科学者":
                return [
                    {"pageid": 1, "ns": 0, "title": "科学者"},
                    {"pageid": 2, "ns": 14, "title": "Category:物理学者"},
                ]
            if category_title == "Category:自然哲学者":
                return [
                    {"pageid": 10, "ns": 0, "title": "アリストテレス"},
                ]
            if category_title == "Category:物理学者":
                return [
                    {"pageid": 3, "ns": 0, "title": "アルベルト・アインシュタイン"},
                    {"pageid": 4, "ns": 0, "title": "マリ・キュリー"},
                ]
            return []

        monkeypatch.setattr("create_scientists_csv.list_category_members", fake_list)
        monkeypatch.setattr(
            "create_scientists_csv.fetch_page_category_titles",
            lambda title, language="ja", request_sleep=0.2: [],
        )

        rows = collect_scientist_rows(
            root_categories=["Category:科学者", "Category:自然哲学者"],
            language="ja",
            max_depth=1,
        )

        assert [row["名前"] for row in rows] == [
            "科学者",
            "アリストテレス",
            "アルベルト・アインシュタイン",
            "マリ・キュリー",
        ]

    def test_正常系_existing_by_idがあればメモ列を保持する(self, monkeypatch):
        monkeypatch.setattr(
            "create_scientists_csv.list_category_members",
            lambda category_title, language="ja", limit=500, request_sleep=0.2: [
                {"pageid": 736, "ns": 0, "title": "アルベルト・アインシュタイン"},
            ],
        )
        monkeypatch.setattr(
            "create_scientists_csv.fetch_page_category_titles",
            lambda title, language="ja", request_sleep=0.2: [],
        )

        rows = collect_scientist_rows(
            ["Category:科学者"],
            existing_by_id={
                "wikipedia-ja-736": {
                    "era_name": "近代後期",
                    "gender": "男性",
                    "nationality_region": "西欧",
                    "nationality": "ドイツ",
                }
            },
        )

        assert rows[0]["era_name"] == "近代後期"
        assert rows[0]["nationality"] == "ドイツ"

    def test_正常系_ページカテゴリからメモ列の初期値を埋める(self, monkeypatch):
        era_ranges, nationality_to_region = load_quota_reference()
        monkeypatch.setattr(
            "create_scientists_csv.list_category_members",
            lambda category_title, language="ja", limit=500, request_sleep=0.2: [
                {"pageid": 8761, "ns": 0, "title": "アリストテレス"},
            ],
        )
        monkeypatch.setattr(
            "create_scientists_csv.fetch_page_category_titles",
            lambda title, language="ja", request_sleep=0.2: [
                "Category:紀元前384年生",
                "Category:古代ギリシアの哲学者",
            ],
        )

        rows = collect_scientist_rows(
            ["Category:自然哲学者"],
            era_ranges=era_ranges,
            nationality_to_region=nationality_to_region,
        )

        assert rows[0]["era_name"] == "古代前期"
        assert rows[0]["nationality_region"] == "東地中海"

    def test_正常系_pageid重複を除外する(self, monkeypatch):
        def fake_list(category_title, language="ja", limit=500, request_sleep=0.2):
            if category_title == "Category:科学者":
                return [
                    {"pageid": 2, "ns": 14, "title": "Category:物理学者"},
                    {"pageid": 3, "ns": 0, "title": "アルベルト・アインシュタイン"},
                ]
            return [{"pageid": 3, "ns": 0, "title": "アルベルト・アインシュタイン"}]

        monkeypatch.setattr("create_scientists_csv.list_category_members", fake_list)
        monkeypatch.setattr(
            "create_scientists_csv.fetch_page_category_titles",
            lambda title, language="ja", request_sleep=0.2: [],
        )

        rows = collect_scientist_rows(["Category:科学者"], max_depth=1)

        assert len(rows) == 1

    def test_正常系_max_membersで打ち切る(self, monkeypatch):
        monkeypatch.setattr(
            "create_scientists_csv.list_category_members",
            lambda category_title, language="ja", limit=500, request_sleep=0.2: [
                {"pageid": 1, "ns": 0, "title": "A"},
                {"pageid": 2, "ns": 0, "title": "B"},
            ],
        )
        monkeypatch.setattr(
            "create_scientists_csv.fetch_page_category_titles",
            lambda title, language="ja", request_sleep=0.2: [],
        )

        rows = collect_scientist_rows(["Category:科学者"], max_members=1)

        assert len(rows) == 1


class TestResolveScientistsOutputPath:
    def test_正常系_dirからscientists_csvを返す(self, tmp_path):
        output_path = resolve_scientists_output_path(str(tmp_path))

        assert output_path == str(tmp_path / "scientists.csv")


class TestWriteScientistsCsv:
    def test_正常系_scientists_csvを書き出す(self, tmp_path):
        output_path = tmp_path / "scientists.csv"
        rows = [
            {
                "id": "wikipedia-ja-736",
                "名前": "アルベルト・アインシュタイン",
                "era_name": "近代後期",
                "gender": "男性",
                "nationality_region": "西欧",
                "nationality": "ドイツ",
                "wikipedia_title": "アルベルト・アインシュタイン",
                "url": "https://ja.wikipedia.org/wiki/Albert_Einstein",
                "language": "ja",
                "source_category": "Category:科学者",
                "pageid": "736",
            }
        ]

        write_scientists_csv(str(output_path), rows)

        with open(output_path, "r", encoding="utf-8", newline="") as f:
            saved_rows = list(csv.DictReader(f))

        assert saved_rows[0]["wikipedia_title"] == "アルベルト・アインシュタイン"
        assert saved_rows[0]["pageid"] == "736"
        assert saved_rows[0]["era_name"] == "近代後期"
        assert list(saved_rows[0].keys()) == SCIENTISTS_FIELDNAMES
