"""
Wikipedia から科学者の顔画像をダウンロードする standalone CLI。
"""

import argparse
import csv
import json
import pathlib
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

DEFAULT_DIR = "data/sample/two"
DEFAULT_INPUT_FILE = "scientists.csv"
DEFAULT_OUTPUT_DIR = "wikipedia_faces"
DEFAULT_LANGUAGE = "ja"
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
) -> pathlib.Path:
    """1件分の Wikipedia 顔画像をダウンロードして保存する。"""
    page_title = resolve_page_title(
        row,
        title_column=title_column,
        name_column=name_column,
    )
    summary = fetch_page_summary(page_title, language=language)
    image_url = extract_image_url(summary)
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
        help="Wikipedia の言語サブドメイン (デフォルト: %(default)s)",
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
