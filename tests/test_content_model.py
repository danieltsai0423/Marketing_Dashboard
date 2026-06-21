"""content_model：統一資料模型與解析輔助。"""

from __future__ import annotations

import math

import pandas as pd

from content_model import (
    ContentMetrics,
    UniversalContentModel,
    collect_urls,
    content_to_dataframe,
    first_int,
    first_optional_int,
    first_text,
    parse_int,
)


def test_parse_int_variants():
    assert parse_int(1234) == 1234
    assert parse_int("1,234") == 1234
    assert parse_int("1.2k") == 1200
    assert parse_int("3M") == 3_000_000
    assert parse_int(None) is None
    assert parse_int("") is None
    assert parse_int("abc") is None


def test_first_helpers():
    assert first_text(None, "", "  ", "hit") == "hit"
    assert first_text(None, default="fallback") == "fallback"
    assert first_int(None, "x", "5") == 5
    assert first_optional_int(None, "x") is None
    assert first_optional_int(None, "7") == 7


def test_collect_urls_dedup_and_filter():
    urls = collect_urls(
        "https://a.com/1.jpg",
        "https://a.com/1.jpg",  # 重複
        "not-a-url",
        {"videoUrl": "https://a.com/v.mp4"},
        ["https://a.com/2.jpg", {"src": "https://a.com/3.jpg"}],
    )
    assert urls == [
        "https://a.com/1.jpg",
        "https://a.com/v.mp4",
        "https://a.com/2.jpg",
        "https://a.com/3.jpg",
    ]


def test_to_record_backward_compatible_aliases():
    model = UniversalContentModel(
        id="threads:1",
        platform="threads",
        authorName="user",
        title=None,
        content="貼文內文",
        url="https://threads.net/1",
        mediaUrls=["https://x/img.jpg"],
        thumbnail=None,
        metrics=ContentMetrics(views=None, likes=10, comments=2, reposts=3),
        publishedAt="2026-06-01T00:00:00+00:00",
        fetchedKeyword="旅遊",
    )
    record = model.to_record()
    # 向後相容別名（既有 UI / 報告 / 歷史程式仍用這些欄位）
    assert record["keyword"] == "旅遊"
    assert record["channel"] == "user"
    assert record["video_id"] == "threads:1"
    assert record["view_count"] == 0  # None 觀看數補 0
    assert record["like_count"] == 10
    # 攤平的 metrics 欄位，None 觀看數保留 None
    assert record["metrics_views"] is None
    assert record["metrics_likes"] == 10
    assert record["metrics_reposts"] == 3
    assert "metrics" not in record


def test_content_to_dataframe_preserves_none_views(sample_df):
    # metrics_views 必須保留 None（NaN），排序/篩選「無觀看數置底」才會正確
    views = sample_df["metrics_views"].tolist()
    assert views[0] == 120000
    assert math.isnan(views[1])  # instagram
    assert math.isnan(views[2])  # threads
    # 重要欄位齊全
    for col in ["platform", "authorName", "title", "content", "url", "mediaUrls", "keyword"]:
        assert col in sample_df.columns


def test_content_to_dataframe_empty():
    df = content_to_dataframe([])
    assert isinstance(df, pd.DataFrame)
    assert df.empty
