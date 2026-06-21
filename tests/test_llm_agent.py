"""llm_agent：樣本抽樣與平台感知脈絡（不呼叫真實 LLM）。"""

from __future__ import annotations

import pandas as pd

import llm_agent
from content_model import ContentMetrics, UniversalContentModel, content_to_dataframe


def _many(keyword, n, base_views):
    return [
        UniversalContentModel(
            id=f"youtube:{keyword}-{i}",
            platform="youtube",
            authorName="ch",
            title=f"{keyword}-{i}",
            content=f"{keyword}-{i}",
            url=f"https://youtu.be/{keyword}-{i}",
            mediaUrls=[],
            thumbnail=None,
            metrics=ContentMetrics(views=base_views + i, likes=i, comments=0, reposts=None),
            publishedAt="2026-06-01T00:00:00+00:00",
            fetchedKeyword=keyword,
        )
        for i in range(n)
    ]


def test_select_samples_caps_per_keyword_and_total():
    df = content_to_dataframe(_many("美食", 7, 1000) + _many("旅遊", 7, 500))
    sampled = llm_agent._select_samples(df, top_per_kw=5, max_total=25)
    # 每關鍵字最多 5 → 共 10
    assert len(sampled) == 10
    assert (sampled.groupby("keyword").size() <= 5).all()


def test_context_is_platform_aware(sample_df):
    ctx = llm_agent._dataframe_to_context(sample_df)
    assert "各平台概況" in ctx
    assert "[youtube]" in ctx
    assert "[threads]" in ctx
    # Threads 無標題 → 取內文，且不可出現 nan
    assert "京都三天兩夜" in ctx
    assert "nan" not in ctx.lower()
    # 已去醫美化
    assert "醫美" not in ctx


def test_build_messages_generic_role_and_structure(sample_df):
    messages = llm_agent._build_messages(sample_df)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "跨平台" in messages[0]["content"]
    assert "醫美" not in messages[0]["content"]
    assert "跨平台社群內容市場情報報告" in messages[1]["content"]
    assert "診所" not in messages[1]["content"]


def test_context_empty():
    assert llm_agent._dataframe_to_context(pd.DataFrame()) == "（沒有任何內容資料）"
