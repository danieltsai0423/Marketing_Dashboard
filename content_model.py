from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import pandas as pd

Platform = Literal["youtube", "instagram", "facebook", "threads"]


@dataclass(frozen=True)
class ContentMetrics:
    views: int | None
    likes: int
    comments: int
    reposts: int | None


@dataclass(frozen=True)
class UniversalContentModel:
    id: str
    platform: Platform
    authorName: str
    title: str | None
    content: str
    url: str
    mediaUrls: list[str]
    thumbnail: str | None
    metrics: ContentMetrics
    publishedAt: str
    fetchedKeyword: str

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["metrics_views"] = self.metrics.views
        record["metrics_likes"] = self.metrics.likes
        record["metrics_comments"] = self.metrics.comments
        record["metrics_reposts"] = self.metrics.reposts
        record.pop("metrics", None)

        # Backward-compatible aliases used by the existing report and history code.
        record["keyword"] = self.fetchedKeyword
        record["view_count"] = self.metrics.views or 0
        record["like_count"] = self.metrics.likes
        record["comment_count"] = self.metrics.comments
        record["repost_count"] = self.metrics.reposts or 0
        record["published_at"] = self.publishedAt
        record["author_name"] = self.authorName
        record["media_urls"] = self.mediaUrls
        record["video_id"] = self.id
        record["channel"] = self.authorName
        return record


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_to_dataframe(items: list[UniversalContentModel]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    return pd.DataFrame([item.to_record() for item in items])


def first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def first_int(*values: Any, default: int = 0) -> int:
    for value in values:
        parsed = parse_int(value)
        if parsed is not None:
            return parsed
    return default


def first_optional_int(*values: Any) -> int | None:
    for value in values:
        parsed = parse_int(value)
        if parsed is not None:
            return parsed
    return None


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    suffixes = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    try:
        suffix = text[-1:].lower()
        if suffix in suffixes:
            return int(float(text[:-1]) * suffixes[suffix])
        return int(float(text))
    except (ValueError, TypeError):
        return None


def collect_urls(*values: Any) -> list[str]:
    urls: list[str] = []

    def add(value: Any) -> None:
        if not value:
            return
        if isinstance(value, str):
            if value.startswith(("http://", "https://")) and value not in urls:
                urls.append(value)
            return
        if isinstance(value, dict):
            for key in ("url", "src", "displayUrl", "thumbnailUrl", "imageUrl", "videoUrl"):
                add(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)

    for value in values:
        add(value)
    return urls
