from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from content_model import (
    ContentMetrics,
    Platform,
    UniversalContentModel,
    collect_urls,
    first_int,
    first_optional_int,
    first_text,
    now_iso,
)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("apify_service")

APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_ACTORS: dict[Platform, str] = {
    "instagram": "apify/instagram-scraper",
    "facebook": "apify/facebook-videos-scraper",
    "threads": "apify/threads-scraper",
}


class ApifyServiceError(Exception):
    """Raised when an Apify actor cannot be run or parsed."""


def _actor_id(platform: Platform) -> str:
    env_key = f"APIFY_{platform.upper()}_ACTOR"
    return os.getenv(env_key, DEFAULT_ACTORS[platform])


def _token(api_token: str | None = None) -> str:
    token = api_token or os.getenv("APIFY_API_TOKEN")
    if not token:
        raise ApifyServiceError("Missing APIFY_API_TOKEN.")
    return token


def _run_actor(actor_id: str, payload: dict[str, Any], api_token: str | None, timeout: int) -> list[dict[str, Any]]:
    token = _token(api_token)
    url = (
        f"{APIFY_BASE_URL}/acts/{quote(actor_id, safe='')}"
        f"/run-sync-get-dataset-items?token={quote(token, safe='')}"
    )
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise ApifyServiceError(f"Apify actor failed ({exc.code}): {details}") from exc
    except URLError as exc:
        raise ApifyServiceError(f"Apify request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ApifyServiceError("Apify request timed out.") from exc

    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ApifyServiceError("Apify returned invalid JSON.") from exc
    if not isinstance(data, list):
        raise ApifyServiceError("Apify returned an unexpected dataset shape.")
    return [item for item in data if isinstance(item, dict)]


def build_actor_input(platform: Platform, keyword: str, limit: int) -> dict[str, Any]:
    keyword = keyword.strip()
    if platform == "instagram":
        return {
            "search": keyword,
            "hashtags": [keyword.lstrip("#")],
            "resultsLimit": limit,
            "resultsType": "posts",
            "proxy": {"useApifyProxy": True},
        }
    if platform == "facebook":
        return {
            "searchQueries": [keyword],
            "resultsLimit": limit,
            "videoType": "shorts",
            "proxy": {"useApifyProxy": True},
        }
    if platform == "threads":
        return {
            "searchQueries": [keyword],
            "resultsLimit": limit,
            "proxy": {"useApifyProxy": True},
        }
    raise ApifyServiceError(f"Unsupported Apify platform: {platform}")


def fetch_apify_contents(
    platform: Platform,
    keywords: list[str],
    result_limit: int = 50,
    api_token: str | None = None,
    timeout: int = 300,
) -> list[UniversalContentModel]:
    if platform not in ("instagram", "facebook", "threads"):
        raise ApifyServiceError(f"Unsupported Apify platform: {platform}")

    actor = _actor_id(platform)
    items: list[UniversalContentModel] = []
    for keyword in [kw.strip() for kw in keywords if kw.strip()]:
        logger.info("Running Apify actor %s for %s", actor, keyword)
        raw_items = _run_actor(actor, build_actor_input(platform, keyword, result_limit), api_token, timeout)
        items.extend(transform_apify_items(platform, raw_items, keyword))
    return items


def transform_apify_items(
    platform: Platform,
    raw_items: list[dict[str, Any]],
    keyword: str,
) -> list[UniversalContentModel]:
    return [transform_apify_item(platform, item, keyword) for item in raw_items]


def transform_apify_item(platform: Platform, item: dict[str, Any], keyword: str) -> UniversalContentModel:
    source_id = first_text(
        item.get("id"),
        item.get("shortCode"),
        item.get("postId"),
        item.get("pk"),
        item.get("url"),
        default=f"{keyword}-{hash(json.dumps(item, sort_keys=True, default=str))}",
    )
    canonical_id = source_id if source_id.startswith(f"{platform}:") else f"{platform}:{source_id}"

    author = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    author_name = first_text(
        item.get("authorName"),
        item.get("ownerUsername"),
        item.get("username"),
        author.get("username"),
        author.get("fullName"),
        user.get("username"),
        user.get("fullName"),
        default="Unknown",
    )

    text = first_text(
        item.get("text"),
        item.get("caption"),
        item.get("description"),
        item.get("message"),
        item.get("title"),
    )
    title = None if platform == "threads" else first_text(item.get("title"), text[:80], default="")
    if title == "":
        title = None

    attachments = item.get("attachments")
    media_urls = collect_urls(
        item.get("videoUrl"),
        item.get("video_url"),
        item.get("displayUrl"),
        item.get("imageUrl"),
        item.get("images"),
        item.get("media"),
        item.get("latestVideoUrl"),
        attachments,
    )
    thumbnail = first_text(
        item.get("thumbnailUrl"),
        item.get("displayUrl"),
        item.get("imageUrl"),
        media_urls[0] if media_urls else None,
        default="",
    ) or None

    published_at = normalize_datetime(
        item.get("timestamp"),
        item.get("publishedAt"),
        item.get("date"),
        item.get("createdAt"),
        item.get("takenAt"),
    )

    views = first_optional_int(
        item.get("videoViewCount"),
        item.get("viewCount"),
        item.get("views"),
        item.get("playCount"),
    )
    if platform == "threads":
        views = views if views is not None else None

    return UniversalContentModel(
        id=canonical_id,
        platform=platform,
        authorName=author_name,
        title=title,
        content=text,
        url=first_text(item.get("url"), item.get("postUrl"), default=""),
        mediaUrls=media_urls,
        thumbnail=thumbnail,
        metrics=ContentMetrics(
            views=views,
            likes=first_int(item.get("likesCount"), item.get("likeCount"), item.get("likes"), default=0),
            comments=first_int(item.get("commentsCount"), item.get("commentCount"), item.get("comments"), default=0),
            reposts=first_optional_int(item.get("repostsCount"), item.get("shareCount"), item.get("shares")),
        ),
        publishedAt=published_at,
        fetchedKeyword=keyword,
    )


def normalize_datetime(*values: Any) -> str:
    for value in values:
        if value is None or value == "":
            continue
        if isinstance(value, (int, float)):
            timestamp = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        text = str(value).strip()
        if not text:
            continue
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).astimezone(timezone.utc).isoformat()
        except ValueError:
            return str(value)
    return now_iso()
