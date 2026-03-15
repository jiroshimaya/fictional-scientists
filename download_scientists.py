#!/usr/bin/env python3
"""
日本語 Wikipedia のカテゴリ木から科学者記事をたどり、Commons 画像を保存する CLI。
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

JA_API = "https://ja.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

ROOT_CATEGORY = "Category:科学者"
DEFAULT_OUTPUT_DIR = "scientist_faces"
DEFAULT_TITLES_CACHE_NAME = "titles_ja_scientists.txt"
DEFAULT_CSV_NAME = "scientist_images.csv"
DEFAULT_API_TIMEOUT_SECONDS = 60
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 180
DEFAULT_MAX_RETRIES = 8
DEFAULT_CATEGORY_SLEEP = 0.8
DEFAULT_PAGEPROPS_SLEEP = 0.45
DEFAULT_WIKIDATA_SLEEP = 0.35
DEFAULT_DOWNLOAD_SLEEP = 0.25
USER_AGENT = "fictional-scientists/1.0 (Wikipedia scientist image collector)"

CSV_FIELDNAMES = [
    "title_ja",
    "qid",
    "image_name",
    "image_url",
    "license_short_name",
    "license_url",
    "saved_path",
    "source",
]


@dataclass(frozen=True)
class OutputPaths:
    output_dir: Path
    titles_cache: Path
    csv_path: Path


@dataclass
class DownloadScientistsStats:
    downloaded: int = 0
    csv_appended: int = 0
    skipped_nonhuman: int = 0
    skipped_noimage: int = 0
    skipped_existing: int = 0


def build_output_paths(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    titles_cache: str | Path | None = None,
    csv_path: str | Path | None = None,
) -> OutputPaths:
    """出力先一式を解決する。"""
    output_dir_path = Path(output_dir)
    titles_cache_path = (
        Path(titles_cache)
        if titles_cache is not None
        else output_dir_path / DEFAULT_TITLES_CACHE_NAME
    )
    csv_path_value = (
        Path(csv_path) if csv_path is not None else output_dir_path / DEFAULT_CSV_NAME
    )
    return OutputPaths(
        output_dir=output_dir_path,
        titles_cache=titles_cache_path,
        csv_path=csv_path_value,
    )


def create_session(user_agent: str = USER_AGENT) -> requests.Session:
    """既定ヘッダー付き Session を生成する。"""
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    return session


def jitter(base: float, spread: float = 0.3) -> None:
    """API 連打を避けるために少し待つ。"""
    if base <= 0:
        return
    time.sleep(base + random.uniform(0, max(spread, 0.0)))


def api_get(
    session: requests.Session,
    url: str,
    params: dict[str, str],
    timeout: int = DEFAULT_API_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """
    MediaWiki / Wikidata API 用の共通 GET。
    429, 503, maxlag, ratelimited にバックオフ付きで耐える。
    """
    request_params = dict(params)
    request_params.setdefault("format", "json")

    if "w/api.php" in url:
        request_params.setdefault("maxlag", "5")
        request_params.setdefault("formatversion", "2")
        request_params.setdefault("errorformat", "plaintext")
        request_params.setdefault("errorsuselocal", "1")

    backoff = 5.0
    last_error: BaseException | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, params=request_params, timeout=timeout)

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and "error" in data:
                    error = data["error"]
                    code = error.get("code", "")
                    if code in {"maxlag", "ratelimited"}:
                        wait = min(backoff, 120.0)
                        print(
                            f"[warn] API error={code}, retry in {wait:.1f}s",
                            file=sys.stderr,
                        )
                        jitter(wait, 1.0)
                        backoff *= 2
                        continue
                    raise RuntimeError(f"MediaWiki API error: {error}")
                return data

            if response.status_code in {429, 503}:
                retry_after = response.headers.get("Retry-After")
                wait = backoff
                if retry_after is not None:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = backoff

                wait = min(wait, 120.0)
                print(
                    f"[warn] HTTP {response.status_code} on {url}, "
                    f"retry {attempt}/{max_retries} in {wait:.1f}s",
                    file=sys.stderr,
                )
                jitter(wait, 1.0)
                backoff *= 2
                continue

            response.raise_for_status()

        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt == max_retries:
                break
            wait = min(backoff, 120.0)
            print(
                f"[warn] request failed ({type(exc).__name__}: {exc}), "
                f"retry {attempt}/{max_retries} in {wait:.1f}s",
                file=sys.stderr,
            )
            jitter(wait, 1.0)
            backoff *= 2

    raise RuntimeError(
        f"API retry exhausted: {url} params={request_params} last_error={last_error}"
    )


def chunks(values: list[str], size: int) -> list[str]:
    """指定サイズのチャンクで値を返す。"""
    for index in range(0, len(values), size):
        yield values[index : index + size]


def sanitize_filename(name: str) -> str:
    """保存用ファイル名をサニタイズする。"""
    normalized = re.sub(r'[\\/:*?"<>|]+', "_", name)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:180] if len(normalized) > 180 else normalized


def is_bad_image_name(filename: str) -> bool:
    """顔写真より図版らしいファイル名を除外する。"""
    lowered = filename.lower()
    bad_keywords = [
        "logo",
        "diagram",
        "signature",
        "coat of arms",
        "coat_of_arms",
        "map",
        "flag",
        "symbol",
        "icon",
        "seal",
        "crest",
    ]
    return any(keyword in lowered for keyword in bad_keywords)


def load_title_cache(cache_path: Path) -> list[str]:
    """保存済みタイトル一覧を読み込む。"""
    if not cache_path.exists():
        return []
    with cache_path.open("r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f if line.strip()]


def save_title_cache(cache_path: Path, titles: list[str]) -> None:
    """タイトル一覧をキャッシュ保存する。"""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as f:
        for title in titles:
            f.write(f"{title}\n")


def get_category_members_recursive(
    session: requests.Session,
    root_category: str,
    base_sleep: float = DEFAULT_CATEGORY_SLEEP,
) -> list[str]:
    """カテゴリ木を再帰的にたどり、記事タイトルだけを集める。"""
    seen_categories: set[str] = set()
    article_titles: set[str] = set()
    queue = deque([root_category])

    while queue:
        category = queue.popleft()
        if category in seen_categories:
            continue
        seen_categories.add(category)

        print(f"[category] {category} (queue={len(queue)})")

        cmcontinue: str | None = None
        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category,
                "cmlimit": "200",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue

            data = api_get(session, JA_API, params)
            members = data.get("query", {}).get("categorymembers", [])

            for member in members:
                namespace = member["ns"]
                title = member["title"]
                if namespace == 0:
                    article_titles.add(title)
                elif namespace == 14 and title not in seen_categories:
                    queue.append(title)

            cmcontinue = data.get("continue", {}).get("cmcontinue")
            if not cmcontinue:
                break
            jitter(base_sleep, 0.4)

        jitter(base_sleep, 0.4)

    return sorted(article_titles)


def get_pageprops_for_titles(
    session: requests.Session,
    titles: list[str],
    base_sleep: float = DEFAULT_PAGEPROPS_SLEEP,
) -> list[dict[str, Any]]:
    """jawiki の pageprops から wikibase_item と page_image_free を取得する。"""
    results: list[dict[str, Any]] = []

    for index, batch in enumerate(chunks(titles, 50), start=1):
        print(f"[pageprops] batch {index} ({len(batch)} titles)")
        data = api_get(
            session,
            JA_API,
            {
                "action": "query",
                "prop": "pageprops",
                "titles": "|".join(batch),
                "ppprop": "wikibase_item|page_image_free",
            },
        )
        pages = data.get("query", {}).get("pages", [])

        for page in pages:
            if page.get("missing"):
                continue
            pageprops = page.get("pageprops", {})
            results.append(
                {
                    "title": page["title"],
                    "pageid": page.get("pageid"),
                    "qid": pageprops.get("wikibase_item"),
                    "page_image_free": pageprops.get("page_image_free"),
                }
            )

        jitter(base_sleep, 0.3)

    return results


def get_wikidata_entities(
    session: requests.Session,
    qids: list[str],
    base_sleep: float = DEFAULT_WIKIDATA_SLEEP,
) -> dict[str, dict[str, Any]]:
    """Wikidata から claims / labels をまとめて取得する。"""
    entity_map: dict[str, dict[str, Any]] = {}
    filtered_qids = [qid for qid in qids if qid]

    for index, batch in enumerate(chunks(filtered_qids, 50), start=1):
        print(f"[wikidata] batch {index} ({len(batch)} qids)")
        data = api_get(
            session,
            WD_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "claims|labels",
                "languages": "ja|en",
            },
        )
        entities = data.get("entities", {})
        entity_map.update(entities)
        jitter(base_sleep, 0.3)

    return entity_map


def has_claim_value(entity: dict[str, Any], prop: str, target_qid: str) -> bool:
    """指定 claim が target_qid を持つかを返す。"""
    claims = entity.get("claims", {}).get(prop, [])
    for claim in claims:
        mainsnak = claim.get("mainsnak")
        if not isinstance(mainsnak, dict):
            continue
        datavalue = mainsnak.get("datavalue")
        if not isinstance(datavalue, dict):
            continue
        value = datavalue.get("value")
        if isinstance(value, dict) and value.get("id") == target_qid:
            return True
    return False


def get_first_p18(entity: dict[str, Any]) -> str | None:
    """最初の P18 ファイル名を返す。"""
    claims = entity.get("claims", {}).get("P18", [])
    for claim in claims:
        mainsnak = claim.get("mainsnak")
        if not isinstance(mainsnak, dict):
            continue
        datavalue = mainsnak.get("datavalue")
        if not isinstance(datavalue, dict):
            continue
        value = datavalue.get("value")
        if isinstance(value, str) and value:
            return value
    return None


def commons_imageinfo(
    session: requests.Session,
    filename: str,
) -> dict[str, str | None] | None:
    """Commons API から URL とライセンス情報を取得する。"""
    data = api_get(
        session,
        COMMONS_API,
        {
            "action": "query",
            "titles": f"File:{filename}",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
        },
    )
    pages = data.get("query", {}).get("pages", [])

    for page in pages:
        imageinfo = page.get("imageinfo")
        if not imageinfo:
            continue
        info = imageinfo[0]
        metadata = info.get("extmetadata", {})
        return {
            "url": info.get("url"),
            "license_short_name": metadata.get("LicenseShortName", {}).get("value"),
            "license_url": metadata.get("LicenseUrl", {}).get("value"),
        }

    return None


def download_file(
    session: requests.Session,
    url: str,
    outpath: Path,
    timeout: int = DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
) -> None:
    """ファイルをテンポラリ経由で保存する。"""
    outpath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = outpath.with_suffix(f"{outpath.suffix}.part")

    with session.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with tmp_path.open("wb") as f:
            for chunk in response.iter_content(1024 * 64):
                if chunk:
                    f.write(chunk)

    tmp_path.replace(outpath)


def load_existing_csv(csv_path: Path) -> dict[str, dict[str, str]]:
    """既存 CSV を title_ja キーで読み込む。"""
    if not csv_path.exists():
        return {}

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return {row["title_ja"]: row for row in reader}


def append_csv_row(csv_path: Path, row: dict[str, str | None]) -> None:
    """結果 CSV に 1 行追記する。"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def choose_image(
    page_image_free: str | None,
    p18: str | None,
) -> tuple[str | None, str | None]:
    """代表画像優先。ただし図版っぽい名前なら P18 を優先する。"""
    if page_image_free and not is_bad_image_name(page_image_free):
        return page_image_free, "page_image_free"
    if p18:
        return p18, "P18"
    if page_image_free:
        return page_image_free, "page_image_free"
    return None, None


def collect_titles(
    session: requests.Session,
    root_category: str,
    cache_path: Path,
    refresh_cache: bool = False,
) -> list[str]:
    """カテゴリ木からタイトル一覧を取得し、必要ならキャッシュする。"""
    if cache_path.exists() and not refresh_cache:
        titles = load_title_cache(cache_path)
        print(f"Loaded {len(titles)} titles from cache: {cache_path}")
        return titles

    print("Collecting titles from category tree...")
    titles = get_category_members_recursive(session, root_category)
    save_title_cache(cache_path, titles)
    print(f"Saved {len(titles)} titles to cache: {cache_path}")
    return titles


def process_pages(
    session: requests.Session,
    pages: list[dict[str, Any]],
    entities: dict[str, dict[str, Any]],
    paths: OutputPaths,
    download_sleep: float = DEFAULT_DOWNLOAD_SLEEP,
) -> DownloadScientistsStats:
    """取得済み記事一覧から画像保存と CSV 更新を行う。"""
    stats = DownloadScientistsStats()
    existing = load_existing_csv(paths.csv_path)
    if existing:
        print(f"Loaded existing CSV rows: {len(existing)}")

    for index, page in enumerate(pages, start=1):
        title = page["title"]

        if title in existing:
            stats.skipped_existing += 1
            continue

        qid = page.get("qid")
        if not qid:
            stats.skipped_nonhuman += 1
            continue

        entity = entities.get(qid)
        if entity is None or not has_claim_value(entity, "P31", "Q5"):
            stats.skipped_nonhuman += 1
            continue

        image_name, source = choose_image(
            page.get("page_image_free"), get_first_p18(entity)
        )
        if image_name is None or source is None:
            stats.skipped_noimage += 1
            continue

        info = commons_imageinfo(session, image_name)
        if info is None or not info.get("url"):
            stats.skipped_noimage += 1
            continue

        image_url = str(info["url"])
        extension = os.path.splitext(image_url.split("?", 1)[0])[1] or ".jpg"
        outpath = paths.output_dir / f"{sanitize_filename(title)}{extension}"

        try:
            if not outpath.exists():
                download_file(session, image_url, outpath)
                stats.downloaded += 1
                jitter(download_sleep, download_sleep)

            row = {
                "title_ja": title,
                "qid": qid,
                "image_name": image_name,
                "image_url": image_url,
                "license_short_name": info.get("license_short_name"),
                "license_url": info.get("license_url"),
                "saved_path": str(outpath),
                "source": source,
            }
            append_csv_row(paths.csv_path, row)
            existing[title] = {key: value or "" for key, value in row.items()}
            stats.csv_appended += 1
            print(f"[{index}/{len(pages)}] OK  {title} -> {image_name} ({source})")
        except (OSError, requests.RequestException, RuntimeError) as exc:
            print(
                f"[{index}/{len(pages)}] NG  {title} -> {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    return stats


def run(
    root_category: str = ROOT_CATEGORY,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    titles_cache: str | Path | None = None,
    csv_path: str | Path | None = None,
    refresh_cache: bool = False,
    session: requests.Session | None = None,
) -> DownloadScientistsStats:
    """科学者画像収集を実行する。"""
    paths = build_output_paths(output_dir, titles_cache=titles_cache, csv_path=csv_path)
    own_session = session is None
    active_session = session or create_session()

    try:
        titles = collect_titles(
            active_session,
            root_category=root_category,
            cache_path=paths.titles_cache,
            refresh_cache=refresh_cache,
        )

        print("Fetching pageprops...")
        pages = get_pageprops_for_titles(active_session, titles)
        print(f"Page records: {len(pages)}")

        qids = sorted({page["qid"] for page in pages if page.get("qid")})
        print(f"Wikidata items: {len(qids)}")

        print("Fetching Wikidata entities...")
        entities = get_wikidata_entities(active_session, qids)

        stats = process_pages(active_session, pages, entities, paths)

        print("\nDone.")
        print(f"downloaded      : {stats.downloaded}")
        print(f"csv_appended    : {stats.csv_appended}")
        print(f"skipped_nonhuman: {stats.skipped_nonhuman}")
        print(f"skipped_noimage : {stats.skipped_noimage}")
        print(f"skipped_existing: {stats.skipped_existing}")
        print(f"titles_cache    : {paths.titles_cache}")
        print(f"csv             : {paths.csv_path}")
        return stats
    finally:
        if own_session:
            active_session.close()


def build_argument_parser() -> argparse.ArgumentParser:
    """CLI 引数パーサを生成する。"""
    parser = argparse.ArgumentParser(
        description="Wikipedia と Commons から科学者画像を収集する。"
    )
    parser.add_argument(
        "--root-category",
        default=ROOT_CATEGORY,
        help="起点にする日本語 Wikipedia カテゴリ名",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="画像出力ディレクトリ",
    )
    parser.add_argument(
        "--titles-cache",
        help="タイトルキャッシュファイルの保存先。未指定時は output-dir 配下。",
    )
    parser.add_argument(
        "--csv-path",
        help="画像メタデータ CSV の保存先。未指定時は output-dir 配下。",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="タイトルキャッシュがあっても再取得する。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI エントリポイント。"""
    args = build_argument_parser().parse_args(argv)
    run(
        root_category=args.root_category,
        output_dir=args.output_dir,
        titles_cache=args.titles_cache,
        csv_path=args.csv_path,
        refresh_cache=args.refresh_cache,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
