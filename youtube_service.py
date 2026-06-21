"""YouTube Shorts 數據抓取服務。

兩階段撈取邏輯：
  1. search.list  → 依關鍵字搜尋過去 N 天的影片，取得 videoId 清單。
  2. videos.list  → 用 videoId 批次撈取時長與統計數據，過濾出 <= 60 秒的 Shorts。

設計重點：
  - search.list 的 videoDuration=short 只能篩 < 4 分鐘，無法精準到 60 秒，
    因此真正的 Shorts 判定改用 videos.list 回傳的 contentDetails.duration 解析。
  - 每次 API 呼叫間加入延遲，避免觸發 quota / rate limit。
  - 業務邏輯與 UI 完全分離，回傳 pandas DataFrame 供上層使用。
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from content_model import ContentMetrics, UniversalContentModel, first_text

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv 未安裝時不阻斷
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("youtube_service")

# YouTube API 每次呼叫間的延遲（秒），保護 quota。
API_CALL_DELAY = 0.3
# search.list 單關鍵字最多抓幾頁（每頁 50 筆）。
MAX_SEARCH_PAGES = 1
# Shorts 時長上限（秒）。
SHORTS_MAX_SECONDS = 120

_DURATION_RE = re.compile(
    r"PT"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
)


class YouTubeServiceError(Exception):
    """YouTube 服務相關錯誤。"""


def parse_iso8601_duration(duration: str) -> int:
    """將 ISO 8601 時長（如 PT1M30S）轉成總秒數。無法解析時回傳 -1。"""
    if not duration:
        return -1
    match = _DURATION_RE.fullmatch(duration)
    if not match:
        return -1
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return hours * 3600 + minutes * 60 + seconds


def _get_client(api_key: str | None = None):
    """建立 YouTube API client。"""
    api_key = api_key or os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise YouTubeServiceError(
            "缺少 YOUTUBE_API_KEY，請在 .env 設定或以參數傳入。"
        )
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _search_video_ids(
    youtube,
    keyword: str,
    published_after: str,
    max_pages: int = MAX_SEARCH_PAGES,
) -> list[str]:
    """第一階段：search.list 取得符合關鍵字與時間範圍的 videoId。"""
    video_ids: list[str] = []
    page_token = None
    for _ in range(max_pages):
        try:
            response = (
                youtube.search()
                .list(
                    q=keyword,
                    part="id",
                    type="video",
                    order="viewCount",
                    publishedAfter=published_after,
                    maxResults=50,
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as exc:
            logger.error("search.list 失敗（關鍵字=%s）：%s", keyword, exc)
            raise YouTubeServiceError(str(exc)) from exc

        for item in response.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                video_ids.append(vid)

        page_token = response.get("nextPageToken")
        time.sleep(API_CALL_DELAY)
        if not page_token:
            break

    return video_ids


def _fetch_video_details(youtube, video_ids: list[str]) -> list[dict]:
    """第二階段：videos.list 批次撈取詳細資料（每批最多 50 筆）。"""
    rows: list[dict] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        try:
            response = (
                youtube.videos()
                .list(part="snippet,contentDetails,statistics", id=",".join(batch))
                .execute()
            )
        except HttpError as exc:
            logger.error("videos.list 失敗：%s", exc)
            raise YouTubeServiceError(str(exc)) from exc

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            details = item.get("contentDetails", {})
            duration_sec = parse_iso8601_duration(details.get("duration", ""))
            rows.append(
                {
                    "video_id": item.get("id"),
                    "title": snippet.get("title"),
                    "channel": snippet.get("channelTitle"),
                    "published_at": snippet.get("publishedAt"),
                    "duration_sec": duration_sec,
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "url": f"https://www.youtube.com/watch?v={item.get('id')}",
                }
            )

        time.sleep(API_CALL_DELAY)

    return rows


def fetch_shorts(
    keywords: list[str],
    days: int = 7,
    api_key: str | None = None,
    max_seconds: int = SHORTS_MAX_SECONDS,
    progress_callback=None,
) -> pd.DataFrame:
    """抓取多個關鍵字過去 N 天內的 YouTube Shorts。

    Args:
        keywords: 監控關鍵字清單。
        days: 往回回溯的天數（預設 7 天）。
        api_key: YouTube API 金鑰；省略時讀取 .env 的 YOUTUBE_API_KEY。
        max_seconds: Shorts 時長上限秒數（預設 60）。
        progress_callback: 可選的 callable(done, total, keyword)，供 UI 顯示進度。

    Returns:
        欄位包含 keyword/title/view_count/duration_sec/url 等的 DataFrame，
        已過濾 <= max_seconds 並依觀看數遞減排序。
    """
    if not keywords:
        return pd.DataFrame()

    youtube = _get_client(api_key)
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_rows: list[dict] = []
    total = len(keywords)
    for idx, keyword in enumerate(keywords, start=1):
        keyword = keyword.strip()
        if not keyword:
            continue
        logger.info("[%d/%d] 搜尋關鍵字：%s", idx, total, keyword)

        video_ids = _search_video_ids(youtube, keyword, published_after)
        logger.info("  search.list 取得 %d 支影片", len(video_ids))

        if video_ids:
            for row in _fetch_video_details(youtube, video_ids):
                row["keyword"] = keyword
                all_rows.append(row)

        if progress_callback:
            progress_callback(idx, total, keyword)

    df = pd.DataFrame(all_rows)
    if df.empty:
        logger.warning("未取得任何影片資料。")
        return df

    # 過濾真正的 Shorts（time 在合法範圍內且 <= max_seconds）。
    df = df[(df["duration_sec"] > 0) & (df["duration_sec"] <= max_seconds)]
    df = df.drop_duplicates(subset="video_id")
    df = df.sort_values("view_count", ascending=False).reset_index(drop=True)
    logger.info("過濾後共 %d 支 Shorts。", len(df))
    return df


def transform_youtube_row(row: dict, keyword: str | None = None) -> UniversalContentModel:
    video_id = first_text(row.get("video_id"), row.get("id"))
    title = first_text(row.get("title"), default="")
    return UniversalContentModel(
        id=f"youtube:{video_id}",
        platform="youtube",
        authorName=first_text(row.get("channel"), row.get("channelTitle"), default="Unknown"),
        title=title or None,
        content=title,
        url=first_text(row.get("url"), default=f"https://www.youtube.com/watch?v={video_id}"),
        mediaUrls=[],
        thumbnail=first_text(row.get("thumbnail"), row.get("thumbnailUrl"), default="") or None,
        metrics=ContentMetrics(
            views=int(row.get("view_count") or row.get("viewCount") or 0),
            likes=int(row.get("like_count") or row.get("likeCount") or 0),
            comments=int(row.get("comment_count") or row.get("commentCount") or 0),
            reposts=None,
        ),
        publishedAt=first_text(row.get("published_at"), row.get("publishedAt"), default=""),
        fetchedKeyword=first_text(keyword, row.get("keyword"), default=""),
    )


def fetch_youtube_contents(
    keywords: list[str],
    days: int = 7,
    api_key: str | None = None,
    max_seconds: int = SHORTS_MAX_SECONDS,
    progress_callback=None,
) -> list[UniversalContentModel]:
    df = fetch_shorts(
        keywords=keywords,
        days=days,
        api_key=api_key,
        max_seconds=max_seconds,
        progress_callback=progress_callback,
    )
    if df.empty:
        return []
    return [transform_youtube_row(row) for row in df.to_dict(orient="records")]


if __name__ == "__main__":
    # 本機快速驗證：python youtube_service.py
    # 需先在 .env 設定 YOUTUBE_API_KEY。
    test_keywords = ["8字線雕", "嘴邊肉下垂"]
    print(f"測試抓取關鍵字：{test_keywords}（過去 7 天）...")
    try:
        result = fetch_shorts(test_keywords, days=7)
    except YouTubeServiceError as e:
        print(f"\n[錯誤] {e}")
        raise SystemExit(1)

    if result.empty:
        print("\n沒有抓到任何 Shorts（可能是關鍵字無近期影片，或 API 金鑰/quota 問題）。")
    else:
        print(f"\n成功抓取 {len(result)} 支 Shorts，前 10 筆：\n")
        cols = ["keyword", "title", "view_count", "duration_sec", "url"]
        with pd.option_context("display.max_colwidth", 40, "display.width", 200):
            print(result[cols].head(10).to_string(index=False))
