from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from apify_service import ApifyServiceError, fetch_apify_contents
from content_model import Platform, UniversalContentModel, content_to_dataframe
from youtube_service import YouTubeServiceError, fetch_youtube_contents

logger = logging.getLogger("data_router")

DEFAULT_PLATFORMS: list[Platform] = ["youtube", "threads"]
SUPPORTED_PLATFORMS: tuple[Platform, ...] = ("youtube", "instagram", "facebook", "threads")


@dataclass
class FetchResult:
    contents: list[UniversalContentModel]
    errors: dict[str, str]

    @property
    def dataframe(self) -> pd.DataFrame:
        return content_to_dataframe(self.contents)


class DataRouterError(Exception):
    """Raised when the data router receives an invalid request."""


ProgressCallback = Callable[[int, int, str], None]


def fetch_contents(
    keywords: list[str],
    platforms: list[Platform] | None = None,
    days: int = 7,
    max_seconds: int = 120,
    result_limit: int = 50,
    progress_callback: ProgressCallback | None = None,
) -> FetchResult:
    clean_keywords = [keyword.strip() for keyword in keywords if keyword.strip()]
    if not clean_keywords:
        return FetchResult(contents=[], errors={})

    selected_platforms = DEFAULT_PLATFORMS if platforms is None else platforms
    invalid = [platform for platform in selected_platforms if platform not in SUPPORTED_PLATFORMS]
    if invalid:
        raise DataRouterError(f"Unsupported platform(s): {', '.join(invalid)}")

    contents: list[UniversalContentModel] = []
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max(1, len(selected_platforms))) as executor:
        futures = {
            executor.submit(
                _fetch_platform,
                platform,
                clean_keywords,
                days,
                max_seconds,
                result_limit,
                _platform_progress(progress_callback, platform, len(selected_platforms)),
            ): platform
            for platform in selected_platforms
        }
        for future in as_completed(futures):
            platform = futures[future]
            try:
                contents.extend(future.result())
            except (YouTubeServiceError, ApifyServiceError, Exception) as exc:
                logger.exception("%s fetch failed", platform)
                errors[platform] = str(exc)

    contents.sort(
        key=lambda item: (
            item.metrics.views if item.metrics.views is not None else item.metrics.likes,
            item.metrics.likes,
        ),
        reverse=True,
    )
    return FetchResult(contents=contents, errors=errors)


def fetch_content_dataframe(*args, **kwargs) -> tuple[pd.DataFrame, dict[str, str]]:
    result = fetch_contents(*args, **kwargs)
    return result.dataframe, result.errors


def _fetch_platform(
    platform: Platform,
    keywords: list[str],
    days: int,
    max_seconds: int,
    result_limit: int,
    progress_callback: ProgressCallback | None,
) -> list[UniversalContentModel]:
    if platform == "youtube":
        return fetch_youtube_contents(
            keywords=keywords,
            days=days,
            max_seconds=max_seconds,
            progress_callback=progress_callback,
        )
    return fetch_apify_contents(platform=platform, keywords=keywords, result_limit=result_limit)


def _platform_progress(
    progress_callback: ProgressCallback | None,
    platform: Platform,
    platform_count: int,
) -> ProgressCallback | None:
    if progress_callback is None:
        return None

    def wrapped(done: int, total: int, keyword: str) -> None:
        progress_callback(done, total * platform_count, f"{platform}:{keyword}")

    return wrapped
