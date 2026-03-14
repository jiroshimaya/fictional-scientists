"""
Wikipedia から科学者の顔画像をダウンロードする standalone CLI。
"""

import argparse
import csv
import json
import pathlib
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

DEFAULT_DIR = "data/sample/two"
DEFAULT_INPUT_FILE = "scientists.csv"
DEFAULT_OUTPUT_DIR = "wikipedia_faces"
DEFAULT_LANGUAGE = "ja"
DEFAULT_FALLBACK_LANGUAGES = ("en",)
USER_AGENT = "fictional-scientists/1.0 (Wikipedia image downloader)"
DEFAULT_MAX_RETRIES = 5
REQUEST_TIMEOUT_SECONDS = 30
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class WikipediaPageNotFoundError(RuntimeError):
    """Wikipedia ページが存在しない。"""


class WikipediaImageNotFoundError(RuntimeError):
    """Wikipedia ページに代表画像が存在しない。"""


def get_retry_delay(exc: HTTPError, attempt: int) -> float:
    """HTTPエラー時の再試行待機秒数を返す。"""
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after is not None:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return min(float(2 ** (attempt - 1)), 30.0)


def is_retryable_network_error(exc: BaseException) -> bool:
    """一時的なネットワークエラーなら再試行対象とみなす。"""
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, URLError):
        return True
    return False


def load_input_rows(path: str) -> list[dict[str, str]]:
    """入力 CSV を読み込む。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def resolve_wikipedia_paths(dir_path: str) -> tuple[str, str]:
    """--dir から既定の入力 CSV と出力ディレクトリを返す。"""
    base = pathlib.Path(dir_path)
    return str(base / DEFAULT_INPUT_FILE), str(base / DEFAULT_OUTPUT_DIR)


def resolve_page_title(
    row: dict[str, str],
    title_column: str = "wikipedia_title",
    name_column: str = "名前",
) -> str:
    """Wikipedia のページタイトルを決定する。"""
    title = (row.get(title_column) or "").strip()
    if title:
        return title

    name = (row.get(name_column) or "").strip()
    if name:
        return name

    raise ValueError(
        f"Wikipedia title not found: title_column={title_column}, name_column={name_column}"
    )


def build_summary_url(title: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Wikipedia summary API の URL を組み立てる。"""
    normalized_title = title.strip().replace(" ", "_")
    return (
        f"https://{language}.wikipedia.org/api/rest_v1/page/summary/"
        f"{quote(normalized_title, safe='()_')}"
    )


def build_langlinks_url(
    title: str,
    source_language: str = DEFAULT_LANGUAGE,
    target_language: str = "en",
) -> str:
    """Wikipedia 言語間リンク API の URL を組み立てる。"""
    params = [
        ("action", "query"),
        ("titles", title),
        ("prop", "langlinks"),
        ("lllang", target_language),
        ("format", "json"),
    ]
    query = "&".join(f"{key}={quote(value, safe='()_')}" for key, value in params)
    return f"https://{source_language}.wikipedia.org/w/api.php?{query}"


def fetch_page_summary(
    title: str,
    language: str = DEFAULT_LANGUAGE,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Wikipedia page summary を取得する。"""
    request = Request(
        build_summary_url(title, language=language),
        headers={"User-Agent": USER_AGENT},
    )
    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                raise WikipediaPageNotFoundError(title) from exc
            if exc.code not in RETRYABLE_STATUS_CODES or attempt == max_retries:
                raise
            time.sleep(get_retry_delay(exc, attempt))
        except (TimeoutError, URLError) as exc:
            if not is_retryable_network_error(exc) or attempt == max_retries:
                raise
            time.sleep(min(float(2 ** (attempt - 1)), 30.0))

    raise RuntimeError("unreachable")


def fetch_langlinks_page(
    title: str,
    source_language: str = DEFAULT_LANGUAGE,
    target_language: str = "en",
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Wikipedia 言語間リンクを取得する。"""
    request = Request(
        build_langlinks_url(
            title,
            source_language=source_language,
            target_language=target_language,
        ),
        headers={"User-Agent": USER_AGENT},
    )
    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                raise WikipediaPageNotFoundError(title) from exc
            if exc.code not in RETRYABLE_STATUS_CODES or attempt == max_retries:
                raise
            time.sleep(get_retry_delay(exc, attempt))
        except (TimeoutError, URLError) as exc:
            if not is_retryable_network_error(exc) or attempt == max_retries:
                raise
            time.sleep(min(float(2 ** (attempt - 1)), 30.0))

    raise RuntimeError("unreachable")


def extract_image_url(summary: dict[str, Any]) -> str:
    """summary レスポンスから代表画像 URL を取り出す。"""
    original = summary.get("originalimage") or {}
    thumbnail = summary.get("thumbnail") or {}
    image_url = original.get("source") or thumbnail.get("source")
    if not image_url:
        raise WikipediaImageNotFoundError("Lead image not found")
    return image_url


def guess_extension(image_url: str) -> str:
    """画像 URL から拡張子を推定する。"""
    suffix = pathlib.PurePosixPath(urlparse(image_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".svg"}:
        return suffix
    return ".jpg"


def sanitize_output_stem(value: str) -> str:
    """ファイル名に使う stem を簡易サニタイズする。"""
    return str(value).replace("/", "_").replace("\\", "_").strip()


def resolve_output_stem(
    row: dict[str, str],
    id_column: str = "id",
    title_column: str = "wikipedia_title",
    name_column: str = "名前",
) -> str:
    """出力ファイル名の stem を決める。"""
    identifier = (row.get(id_column) or "").strip()
    if identifier:
        return sanitize_output_stem(identifier)
    return sanitize_output_stem(
        resolve_page_title(row, title_column=title_column, name_column=name_column)
    )


def get_output_path(
    row: dict[str, str],
    output_dir: str,
    image_url: str,
    id_column: str = "id",
    title_column: str = "wikipedia_title",
    name_column: str = "名前",
) -> pathlib.Path:
    """保存先パスを返す。"""
    stem = resolve_output_stem(
        row,
        id_column=id_column,
        title_column=title_column,
        name_column=name_column,
    )
    return pathlib.Path(output_dir) / f"{stem}{guess_extension(image_url)}"


def find_existing_output_path(
    row: dict[str, str],
    output_dir: str,
    id_column: str = "id",
    title_column: str = "wikipedia_title",
    name_column: str = "名前",
) -> pathlib.Path | None:
    """既に保存済みの画像があるかを確認する。"""
    stem = resolve_output_stem(
        row,
        id_column=id_column,
        title_column=title_column,
        name_column=name_column,
    )
    matches = sorted(pathlib.Path(output_dir).glob(f"{stem}.*"))
    if matches:
        return matches[0]
    return None


def filter_unprocessed_rows(
    rows: list[dict[str, str]],
    output_dir: str,
    id_column: str = "id",
    title_column: str = "wikipedia_title",
    name_column: str = "名前",
    force: bool = False,
) -> list[dict[str, str]]:
    """未ダウンロードの行だけを返す。"""
    if force:
        return list(rows)

    return [
        row
        for row in rows
        if find_existing_output_path(
            row,
            output_dir,
            id_column=id_column,
            title_column=title_column,
            name_column=name_column,
        )
        is None
    ]


def parse_fallback_languages(value: str) -> tuple[str, ...]:
    """カンマ区切りのフォールバック言語一覧を正規化する。"""
    languages: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        language = part.strip()
        if not language or language in seen:
            continue
        seen.add(language)
        languages.append(language)
    return tuple(languages)


def resolve_source_language(
    row: dict[str, str],
    default_language: str = DEFAULT_LANGUAGE,
) -> str:
    """行データから元の Wikipedia 言語を決定する。"""
    return (row.get("language") or default_language).strip() or default_language


def resolve_translated_title(
    title: str,
    source_language: str = DEFAULT_LANGUAGE,
    target_language: str = "en",
) -> str | None:
    """指定言語へ対応する Wikipedia ページタイトルを返す。"""
    payload = fetch_langlinks_page(
        title,
        source_language=source_language,
        target_language=target_language,
    )
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        for langlink in page.get("langlinks", []):
            translated_title = (langlink.get("*") or "").strip()
            if translated_title:
                return translated_title
    return None


def resolve_image_url(
    row: dict[str, str],
    language: str = DEFAULT_LANGUAGE,
    title_column: str = "wikipedia_title",
    name_column: str = "名前",
    fallback_languages: tuple[str, ...] = DEFAULT_FALLBACK_LANGUAGES,
) -> str:
    """代表画像 URL を見つける。必要なら他言語版へフォールバックする。"""
    page_title = resolve_page_title(
        row,
        title_column=title_column,
        name_column=name_column,
    )
    source_language = resolve_source_language(row, default_language=language)
    attempts: list[BaseException] = []
    candidates = [(source_language, page_title)]

    for fallback_language in fallback_languages:
        if fallback_language == source_language:
            continue
        translated_title = resolve_translated_title(
            page_title,
            source_language=source_language,
            target_language=fallback_language,
        )
        if translated_title:
            candidates.append((fallback_language, translated_title))

    seen: set[tuple[str, str]] = set()
    for candidate_language, candidate_title in candidates:
        key = (candidate_language, candidate_title)
        if key in seen:
            continue
        seen.add(key)
        try:
            summary = fetch_page_summary(candidate_title, language=candidate_language)
            return extract_image_url(summary)
        except (WikipediaPageNotFoundError, WikipediaImageNotFoundError) as exc:
            attempts.append(exc)

    if attempts:
        raise attempts[-1]
    raise WikipediaImageNotFoundError("Lead image not found")


def download_image_bytes(
    image_url: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> bytes:
    """画像 URL からバイナリを取得する。"""
    request = Request(image_url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code not in RETRYABLE_STATUS_CODES or attempt == max_retries:
                raise
            time.sleep(get_retry_delay(exc, attempt))
        except (TimeoutError, URLError) as exc:
            if not is_retryable_network_error(exc) or attempt == max_retries:
                raise
            time.sleep(min(float(2 ** (attempt - 1)), 30.0))

    raise RuntimeError("unreachable")


def save_image(path: pathlib.Path, image_bytes: bytes) -> None:
    """画像を保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)


def download_face_image(
    row: dict[str, str],
    output_dir: str,
    language: str = DEFAULT_LANGUAGE,
    id_column: str = "id",
    title_column: str = "wikipedia_title",
    name_column: str = "名前",
    fallback_languages: tuple[str, ...] = DEFAULT_FALLBACK_LANGUAGES,
) -> pathlib.Path:
    """1件分の Wikipedia 顔画像をダウンロードして保存する。"""
    image_url = resolve_image_url(
        row,
        language=language,
        title_column=title_column,
        name_column=name_column,
        fallback_languages=fallback_languages,
    )
    output_path = get_output_path(
        row,
        output_dir,
        image_url=image_url,
        id_column=id_column,
        title_column=title_column,
        name_column=name_column,
    )
    image_bytes = download_image_bytes(image_url)
    save_image(output_path, image_bytes)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="入力CSVをもとにWikipediaから科学者の顔画像をダウンロードする"
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_DIR,
        help="入力CSVと出力ディレクトリの基準ディレクトリ (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help=f"入力CSVのパス (省略時: --dir/{DEFAULT_INPUT_FILE})",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"画像保存先ディレクトリ (省略時: --dir/{DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--id-column",
        default="id",
        help="出力ファイル名に使う識別子列 (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--name-column",
        default="名前",
        help="科学者名の列名 (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--title-column",
        default="wikipedia_title",
        help="Wikipediaページ名の列名。値があれば name-column より優先",
    )
    parser.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        help="Wikipedia の既定言語サブドメイン。行に language 列があればそちらを優先",
    )
    parser.add_argument(
        "--fallback-languages",
        default="en",
        help="画像が見つからないときに試すフォールバック言語のカンマ区切り一覧",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="処理する最大行数 (省略時: 全件)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="リクエスト間の待機秒数 (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="既存画像があっても再取得する",
    )
    args = parser.parse_args()

    default_input_path, default_output_dir = resolve_wikipedia_paths(args.dir)
    input_path = args.input or default_input_path
    output_dir = args.output_dir or default_output_dir

    rows = load_input_rows(input_path)
    fallback_languages = parse_fallback_languages(args.fallback_languages)
    targets = filter_unprocessed_rows(
        rows,
        output_dir,
        id_column=args.id_column,
        title_column=args.title_column,
        name_column=args.name_column,
        force=args.force,
    )

    if args.max_rows is not None:
        targets = targets[: args.max_rows]

    print(f"対象: {len(targets)} 件 / 全体 {len(rows)} 件")

    downloaded = 0
    for index, row in enumerate(targets, start=1):
        label = (
            row.get(args.id_column)
            or row.get(args.title_column)
            or row.get(args.name_column)
            or f"row-{index}"
        )
        try:
            path = download_face_image(
                row=row,
                output_dir=output_dir,
                language=args.language,
                id_column=args.id_column,
                title_column=args.title_column,
                name_column=args.name_column,
                fallback_languages=fallback_languages,
            )
            downloaded += 1
            print(f"[ok] {index}/{len(targets)} {label} -> {path}")
        except (
            ValueError,
            WikipediaPageNotFoundError,
            WikipediaImageNotFoundError,
        ) as exc:
            print(f"[skip] {index}/{len(targets)} {label}: {exc}")
        except HTTPError as exc:
            print(f"[error] {index}/{len(targets)} {label}: HTTP {exc.code}")

        time.sleep(args.sleep)

    print(f"完了: {downloaded} 件ダウンロード")


if __name__ == "__main__":
    main()
