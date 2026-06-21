"""apify_service：actor input 建構與跨平台資料轉換。"""

from __future__ import annotations

import pytest

from apify_service import (
    ApifyServiceError,
    build_actor_input,
    normalize_datetime,
    transform_apify_item,
)


def test_build_actor_input_per_platform():
    ig = build_actor_input("instagram", "#美食", 30)
    assert ig["resultsLimit"] == 30
    assert "美食" in ig["hashtags"][0]

    fb = build_actor_input("facebook", "旅遊", 20)
    assert fb["videoType"] == "shorts"
    assert fb["searchQueries"] == ["旅遊"]

    th = build_actor_input("threads", "健身", 50)
    assert th["searchQueries"] == ["健身"]
    assert th["proxy"]["useApifyProxy"] is True


def test_build_actor_input_rejects_unsupported():
    with pytest.raises(ApifyServiceError):
        build_actor_input("tiktok", "x", 10)  # type: ignore[arg-type]


def test_normalize_datetime_formats():
    assert normalize_datetime("2026-06-01T00:00:00Z").startswith("2026-06-01")
    # epoch 秒
    assert normalize_datetime(1717200000).startswith("2024-")
    # epoch 毫秒
    assert normalize_datetime(1717200000000).startswith("2024-")
    # 全空 → 退回現在時間（ISO 字串）
    assert "T" in normalize_datetime(None, "")


def test_transform_instagram_item():
    raw = {
        "id": "123",
        "ownerUsername": "foodie",
        "caption": "台北美食",
        "likesCount": 100,
        "commentsCount": 5,
        "videoViewCount": 2000,
        "url": "https://instagram.com/p/123",
        "displayUrl": "https://cdn/img.jpg",
        "timestamp": "2026-06-01T00:00:00Z",
    }
    item = transform_apify_item("instagram", raw, "美食")
    assert item.platform == "instagram"
    assert item.id == "instagram:123"
    assert item.authorName == "foodie"
    assert item.title == "台北美食"
    assert item.metrics.views == 2000
    assert item.metrics.likes == 100
    assert item.thumbnail == "https://cdn/img.jpg"
    assert item.fetchedKeyword == "美食"


def test_transform_threads_item_no_title_no_views():
    raw = {
        "id": "t1",
        "username": "walker",
        "text": "京都行程分享",
        "likesCount": 50,
        "commentsCount": 3,
        "repostsCount": 7,
        "url": "https://threads.net/t1",
        "timestamp": 1717200000,
    }
    item = transform_apify_item("threads", raw, "旅遊")
    assert item.title is None          # Threads 無標題
    assert item.content == "京都行程分享"
    assert item.metrics.views is None  # 抓不到觀看數時為 None，不報錯
    assert item.metrics.reposts == 7


def test_transform_empty_item_is_defensive():
    # 缺欄位的 item 不可拋例外，給合理預設
    item = transform_apify_item("threads", {}, "美食")
    assert item.platform == "threads"
    assert item.id.startswith("threads:")
    assert item.authorName == "Unknown"
    assert item.metrics.likes == 0
    assert item.metrics.views is None
