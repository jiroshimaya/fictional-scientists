"""
Wikipedia のカテゴリから科学者一覧を取得して scientists.csv を生成する。
"""

import argparse
import csv
import json
import pathlib
import re
import time
from collections import deque
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_DIR = "data/sample/two"
DEFAULT_OUTPUT_FILE = "scientists.csv"
DEFAULT_LANGUAGE = "ja"
DEFAULT_MAX_DEPTH = 2
DEFAULT_PAGE_SIZE = 500
DEFAULT_REQUEST_SLEEP = 0.2
DEFAULT_MAX_RETRIES = 5
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "fictional-scientists/1.0 (Wikipedia scientist scraper)"
MASTER_QUOTA_CSV = "data/attributes/fictional_scientist_quota_master_10000.csv"

DEFAULT_ROOT_CATEGORIES: dict[str, list[str]] = {
    "ja": [
        "Category:科学者",
        "Category:自然哲学者",
        "Category:科学哲学者",
        "Category:数学者",
        "Category:物理学者",
        "Category:化学者",
        "Category:生物学者",
        "Category:天文学者",
        "Category:博物学者",
    ],
    "en": [
        "Category:Scientists",
        "Category:Natural philosophers",
        "Category:Philosophers of science",
        "Category:Mathematicians",
        "Category:Physicists",
        "Category:Chemists",
        "Category:Biologists",
        "Category:Astronomers",
        "Category:Naturalists",
    ],
}

SCIENTISTS_FIELDNAMES = [
    "id",
    "名前",
    "era_name",
    "gender",
    "nationality_region",
    "nationality",
    "wikipedia_title",
    "url",
    "language",
    "source_category",
    "pageid",
]

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def build_categorymembers_url(
    category_title: str,
    language: str = DEFAULT_LANGUAGE,
    limit: int = DEFAULT_PAGE_SIZE,
    continue_token: str | None = None,
) -> str:
    """categorymembers API の URL を組み立てる。"""
    params = [
        ("action", "query"),
        ("list", "categorymembers"),
        ("cmtitle", category_title),
        ("cmtype", "page|subcat"),
        ("cmlimit", str(limit)),
        ("format", "json"),
    ]
    if continue_token:
        params.append(("cmcontinue", continue_token))

    query = "&".join(f"{key}={quote(value, safe=':_|')}" for key, value in params)
    return f"https://{language}.wikipedia.org/w/api.php?{query}"


def build_page_categories_url(
    title: str,
    language: str = DEFAULT_LANGUAGE,
    continue_token: str | None = None,
) -> str:
    """記事カテゴリ取得 API の URL を組み立てる。"""
    params = [
        ("action", "query"),
        ("titles", title),
        ("prop", "categories"),
        ("cllimit", "max"),
        ("format", "json"),
    ]
    if continue_token:
        params.append(("clcontinue", continue_token))

    query = "&".join(f"{key}={quote(value, safe=':_|')}" for key, value in params)
    return f"https://{language}.wikipedia.org/w/api.php?{query}"


def get_retry_delay(exc: HTTPError, attempt: int) -> float:
    """HTTPエラー時の再試行待機秒数を返す。"""
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after is not None:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return min(float(2 ** (attempt - 1)), 30.0)


def load_quota_reference(
    path: str = MASTER_QUOTA_CSV,
) -> tuple[list[tuple[str, int, int]], dict[str, str]]:
    """era_name の年範囲と nationality -> region 対応を読み込む。"""
    era_ranges: dict[str, tuple[int, int]] = {}
    nationality_to_region: dict[str, str] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            era_ranges[row["era_name"]] = (
                int(row["birth_year_start"]),
                int(row["birth_year_end"]),
            )
            nationality_to_region[row["nationality"]] = row["nationality_region"]
    return (
        [(era_name, start, end) for era_name, (start, end) in era_ranges.items()],
        nationality_to_region,
    )


def fetch_categorymembers_page(
    category_title: str,
    language: str = DEFAULT_LANGUAGE,
    limit: int = DEFAULT_PAGE_SIZE,
    continue_token: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """カテゴリメンバー取得 API を1ページ呼ぶ。"""
    request = Request(
        build_categorymembers_url(
            category_title=category_title,
            language=language,
            limit=limit,
            continue_token=continue_token,
        ),
        headers={"User-Agent": USER_AGENT},
    )
    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in RETRYABLE_STATUS_CODES or attempt == max_retries:
                raise
            time.sleep(get_retry_delay(exc, attempt))

    raise RuntimeError("unreachable")


def fetch_page_categories_page(
    title: str,
    language: str = DEFAULT_LANGUAGE,
    continue_token: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """記事カテゴリ取得 API を1ページ呼ぶ。"""
    request = Request(
        build_page_categories_url(
            title=title,
            language=language,
            continue_token=continue_token,
        ),
        headers={"User-Agent": USER_AGENT},
    )
    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in RETRYABLE_STATUS_CODES or attempt == max_retries:
                raise
            time.sleep(get_retry_delay(exc, attempt))

    raise RuntimeError("unreachable")


def list_category_members(
    category_title: str,
    language: str = DEFAULT_LANGUAGE,
    limit: int = DEFAULT_PAGE_SIZE,
    request_sleep: float = DEFAULT_REQUEST_SLEEP,
) -> list[dict[str, Any]]:
    """カテゴリ配下のメンバーを全件取得する。"""
    members: list[dict[str, Any]] = []
    continue_token: str | None = None

    while True:
        payload = fetch_categorymembers_page(
            category_title=category_title,
            language=language,
            limit=limit,
            continue_token=continue_token,
        )
        members.extend(payload.get("query", {}).get("categorymembers", []))
        continue_token = payload.get("continue", {}).get("cmcontinue")
        if continue_token is None:
            return members
        if request_sleep > 0:
            time.sleep(request_sleep)


def fetch_page_category_titles(
    title: str,
    language: str = DEFAULT_LANGUAGE,
    request_sleep: float = DEFAULT_REQUEST_SLEEP,
) -> list[str]:
    """記事に紐づくカテゴリ名を全件取得する。"""
    category_titles: list[str] = []
    continue_token: str | None = None

    while True:
        payload = fetch_page_categories_page(
            title=title,
            language=language,
            continue_token=continue_token,
        )
        pages = payload.get("query", {}).get("pages", {})
        for page in pages.values():
            category_titles.extend(
                category["title"] for category in page.get("categories", [])
            )
        continue_token = payload.get("continue", {}).get("clcontinue")
        if continue_token is None:
            return category_titles
        if request_sleep > 0:
            time.sleep(request_sleep)


def build_article_url(title: str, language: str = DEFAULT_LANGUAGE) -> str:
    """記事URLを組み立てる。"""
    normalized_title = title.strip().replace(" ", "_")
    return (
        f"https://{language}.wikipedia.org/wiki/{quote(normalized_title, safe='()_')}"
    )


def infer_birth_year_from_categories(
    category_titles: list[str],
    language: str = DEFAULT_LANGUAGE,
) -> int | None:
    """カテゴリ名から生年を推定する。"""
    if language == "ja":
        for title in category_titles:
            if match := re.search(r"Category:紀元前(\d+)年生", title):
                return -int(match.group(1))
            if match := re.search(r"Category:(\d+)年生", title):
                return int(match.group(1))
        return None

    for title in category_titles:
        if match := re.search(r"Category:(\d+)\s*BC births", title):
            return -int(match.group(1))
        if match := re.search(r"Category:(\d+)\s+births", title):
            return int(match.group(1))
    return None


def infer_era_name_from_birth_year(
    birth_year: int | None,
    era_ranges: list[tuple[str, int, int]],
) -> str:
    """生年から era_name を推定する。"""
    if birth_year is None:
        return ""
    for era_name, start, end in era_ranges:
        if start <= birth_year <= end:
            return era_name
    return ""


def infer_gender_from_categories(category_titles: list[str]) -> str:
    """カテゴリ名から性別を推定する。"""
    normalized = " ".join(category_titles)
    if (
        "女性" in normalized
        or "women" in normalized.lower()
        or "female" in normalized.lower()
    ):
        return "女性"
    if "男性" in normalized or "male" in normalized.lower():
        return "男性"
    return "男性"


def infer_nationality_from_categories(
    category_titles: list[str],
    nationality_to_region: dict[str, str],
) -> str:
    """カテゴリ名から nationality を推定する。"""
    for nationality in sorted(nationality_to_region, key=len, reverse=True):
        if any(nationality in category_title for category_title in category_titles):
            return nationality
    return ""


def infer_scientist_memo_fields(
    title: str,
    language: str,
    existing_row: dict[str, str] | None,
    era_ranges: list[tuple[str, int, int]],
    nationality_to_region: dict[str, str],
    request_sleep: float = DEFAULT_REQUEST_SLEEP,
) -> dict[str, str]:
    """カテゴリから分類メモの初期値を推定する。"""
    existing_row = existing_row or {}
    current = {
        "era_name": (existing_row.get("era_name") or "").strip(),
        "gender": (existing_row.get("gender") or "").strip(),
        "nationality_region": (existing_row.get("nationality_region") or "").strip(),
        "nationality": (existing_row.get("nationality") or "").strip(),
    }
    if all(current.values()):
        return current

    category_titles = fetch_page_category_titles(
        title,
        language=language,
        request_sleep=request_sleep,
    )

    nationality = current["nationality"] or infer_nationality_from_categories(
        category_titles, nationality_to_region
    )
    nationality_region = current["nationality_region"] or nationality_to_region.get(
        nationality, ""
    )
    birth_year = infer_birth_year_from_categories(category_titles, language=language)
    era_name = current["era_name"] or infer_era_name_from_birth_year(
        birth_year, era_ranges
    )
    gender = current["gender"] or infer_gender_from_categories(category_titles)

    return {
        "era_name": era_name,
        "gender": gender,
        "nationality_region": nationality_region,
        "nationality": nationality,
    }


def load_existing_scientists(path: str) -> dict[str, dict[str, str]]:
    """既存 scientists.csv を id キーで読み込む。"""
    csv_path = pathlib.Path(path)
    if not csv_path.exists():
        return {}

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        return {
            row["id"]: row for row in csv.DictReader(f) if (row.get("id") or "").strip()
        }


def build_scientist_row(
    member: dict[str, Any],
    language: str,
    source_category: str,
    existing_row: dict[str, str] | None = None,
) -> dict[str, str]:
    """APIの1メンバーから scientists.csv の1行を作る。"""
    pageid = str(member["pageid"])
    title = str(member["title"])
    existing_row = existing_row or {}
    return {
        "id": f"wikipedia-{language}-{pageid}",
        "名前": title,
        "era_name": (existing_row.get("era_name") or "").strip(),
        "gender": (existing_row.get("gender") or "").strip(),
        "nationality_region": (existing_row.get("nationality_region") or "").strip(),
        "nationality": (existing_row.get("nationality") or "").strip(),
        "wikipedia_title": title,
        "url": build_article_url(title, language=language),
        "language": language,
        "source_category": source_category,
        "pageid": pageid,
    }


def get_default_root_categories(language: str = DEFAULT_LANGUAGE) -> list[str]:
    """言語ごとの既定起点カテゴリを返す。"""
    return list(DEFAULT_ROOT_CATEGORIES.get(language, DEFAULT_ROOT_CATEGORIES["en"]))


def collect_scientist_rows(
    root_categories: list[str],
    language: str = DEFAULT_LANGUAGE,
    max_depth: int = DEFAULT_MAX_DEPTH,
    limit: int = DEFAULT_PAGE_SIZE,
    max_members: int | None = None,
    request_sleep: float = DEFAULT_REQUEST_SLEEP,
    existing_by_id: dict[str, dict[str, str]] | None = None,
    era_ranges: list[tuple[str, int, int]] | None = None,
    nationality_to_region: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """カテゴリを再帰走査して科学者ページ一覧を集める。"""
    queue = deque((category, 0) for category in root_categories)
    visited_categories: set[str] = set()
    seen_pageids: set[str] = set()
    rows: list[dict[str, str]] = []
    existing_by_id = existing_by_id or {}
    if era_ranges is None or nationality_to_region is None:
        era_ranges, nationality_to_region = load_quota_reference()

    while queue:
        category_title, depth = queue.popleft()
        if category_title in visited_categories:
            continue
        visited_categories.add(category_title)

        members = list_category_members(
            category_title,
            language=language,
            limit=limit,
            request_sleep=request_sleep,
        )
        for member in members:
            namespace = member.get("ns")
            title = str(member.get("title", ""))

            if namespace == 0:
                pageid = str(member["pageid"])
                if pageid in seen_pageids:
                    continue
                seen_pageids.add(pageid)
                existing_row = existing_by_id.get(f"wikipedia-{language}-{pageid}")
                memo_fields = infer_scientist_memo_fields(
                    title=title,
                    language=language,
                    existing_row=existing_row,
                    era_ranges=era_ranges,
                    nationality_to_region=nationality_to_region,
                    request_sleep=request_sleep,
                )
                rows.append(
                    build_scientist_row(
                        member=member,
                        language=language,
                        source_category=category_title,
                        existing_row={**(existing_row or {}), **memo_fields},
                    )
                )
                if max_members is not None and len(rows) >= max_members:
                    return rows

            if namespace == 14 and depth < max_depth:
                queue.append((title, depth + 1))

    return rows


def resolve_scientists_output_path(dir_path: str) -> str:
    """--dir から出力 scientists.csv の既定パスを返す。"""
    return str(pathlib.Path(dir_path) / DEFAULT_OUTPUT_FILE)


def write_scientists_csv(path: str, rows: list[dict[str, str]]) -> None:
    """scientists.csv を書き出す。"""
    output_path = pathlib.Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCIENTISTS_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wikipediaカテゴリから科学者一覧を取得して scientists.csv を生成する"
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_DIR,
        help="出力ディレクトリの基準 (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="出力 scientists.csv のパス (省略時: --dir/scientists.csv)",
    )
    parser.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        help="Wikipedia の言語サブドメイン (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=None,
        help="起点カテゴリ名。複数指定可。省略時は言語別の広域カテゴリ群を使う",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help="再帰するサブカテゴリの深さ上限 (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--max-members",
        type=int,
        default=None,
        help="取得する最大人数 (省略時: 全件)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="API 1回あたりの取得件数 (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--request-sleep",
        type=float,
        default=DEFAULT_REQUEST_SLEEP,
        help="API リクエスト間の待機秒数 (デフォルト: %(default)s)",
    )
    args = parser.parse_args()

    output_path = args.output or resolve_scientists_output_path(args.dir)
    root_categories = args.category or get_default_root_categories(args.language)
    existing_by_id = load_existing_scientists(output_path)
    rows = collect_scientist_rows(
        root_categories=root_categories,
        language=args.language,
        max_depth=args.max_depth,
        limit=args.page_size,
        max_members=args.max_members,
        request_sleep=args.request_sleep,
        existing_by_id=existing_by_id,
    )
    write_scientists_csv(output_path, rows)

    print(f"完了: {output_path} ({len(rows)} 件)")


if __name__ == "__main__":
    main()
