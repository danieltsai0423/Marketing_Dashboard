"""data_router：平行路由、合併、排序與錯誤隔離。"""

from __future__ import annotations

import pytest

import data_router
from content_model import ContentMetrics, UniversalContentModel
from data_router import DataRouterError, fetch_content_dataframe, fetch_contents


def _model(platform, native_id, views, likes, keyword="kw"):
    return UniversalContentModel(
        id=f"{platform}:{native_id}",
        platform=platform,
        authorName="a",
        title="t",
        content="c",
        url=f"https://x/{native_id}",
        mediaUrls=[],
        thumbnail=None,
        metrics=ContentMetrics(views=views, likes=likes, comments=0, reposts=None),
        publishedAt="2026-06-01T00:00:00+00:00",
        fetchedKeyword=keyword,
    )


def test_invalid_platform_raises():
    with pytest.raises(DataRouterError):
        fetch_contents(["x"], platforms=["tiktok"])  # type: ignore[list-item]


def test_empty_keywords_returns_empty():
    df, errors = fetch_content_dataframe([], platforms=["youtube"])
    assert df.empty
    assert errors == {}


def test_parallel_merge_and_sort(monkeypatch):
    # 無觀看數者以按讚數遞補排序：yt(1000) > threads(views=None,likes=900) > yt(500)
    monkeypatch.setattr(
        data_router,
        "fetch_youtube_contents",
        lambda **kw: [_model("youtube", "hi", 1000, 10), _model("youtube", "lo", 500, 5)],
    )
    monkeypatch.setattr(
        data_router,
        "fetch_apify_contents",
        lambda **kw: [_model("threads", "t", None, 900)],
    )
    df, errors = fetch_content_dataframe(["kw"], platforms=["youtube", "threads"])

    assert errors == {}
    assert len(df) == 3
    assert df.iloc[0]["id"] == "youtube:hi"
    order = df["id"].tolist()
    assert order.index("threads:t") < order.index("youtube:lo")


def test_one_platform_failure_does_not_kill_others(monkeypatch):
    def boom(**kw):
        raise RuntimeError("apify down")

    monkeypatch.setattr(
        data_router, "fetch_youtube_contents", lambda **kw: [_model("youtube", "ok", 100, 1)]
    )
    monkeypatch.setattr(data_router, "fetch_apify_contents", boom)

    result = fetch_contents(["kw"], platforms=["youtube", "instagram"])
    # YouTube 結果仍在，Instagram 失敗被記錄而非中斷整體
    assert len(result.contents) == 1
    assert result.contents[0].platform == "youtube"
    assert "instagram" in result.errors
    assert "apify down" in result.errors["instagram"]
