"""共用測試 fixtures。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 讓測試能 import 專案根目錄的模組。
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_model import ContentMetrics, UniversalContentModel, content_to_dataframe  # noqa: E402

APP_PATH = str(ROOT / "app.py")


@pytest.fixture
def sample_models() -> list[UniversalContentModel]:
    """跨平台樣本，含 Threads（無 title、views=None）以覆蓋邊界。"""
    return [
        UniversalContentModel(
            id="youtube:vid1",
            platform="youtube",
            authorName="美食頻道",
            title="台北必吃牛肉麵",
            content="台北必吃牛肉麵",
            url="https://youtu.be/vid1",
            mediaUrls=[],
            thumbnail="https://i.ytimg.com/vi/vid1/hq.jpg",
            metrics=ContentMetrics(views=120000, likes=3400, comments=210, reposts=None),
            publishedAt="2026-06-10T00:00:00+00:00",
            fetchedKeyword="美食",
        ),
        UniversalContentModel(
            id="instagram:ig1",
            platform="instagram",
            authorName="travel_ig",
            title="沖繩潛水",
            content="沖繩潛水一日遊",
            url="https://instagram.com/p/ig1",
            mediaUrls=["https://cdn.example/a.jpg"],
            thumbnail="https://cdn.example/a.jpg",
            metrics=ContentMetrics(views=None, likes=2200, comments=90, reposts=None),
            publishedAt="2026-06-11T00:00:00+00:00",
            fetchedKeyword="旅遊",
        ),
        UniversalContentModel(
            id="threads:th1",
            platform="threads",
            authorName="beauty_user",
            title=None,
            content="京都三天兩夜行程分享，楓葉季必去清水寺",
            url="https://threads.net/@beauty_user/post/th1",
            mediaUrls=["https://cdn.example/b.jpg", "https://cdn.example/c.jpg"],
            thumbnail=None,
            metrics=ContentMetrics(views=None, likes=890, comments=45, reposts=12),
            publishedAt="2026-06-12T00:00:00+00:00",
            fetchedKeyword="旅遊",
        ),
    ]


@pytest.fixture
def sample_df(sample_models):
    return content_to_dataframe(sample_models)
