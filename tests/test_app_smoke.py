"""app：Streamlit 端到端冒煙測試（雙語切換、跨平台資料渲染）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


def _run():
    return AppTest.from_file(APP_PATH, default_timeout=60).run()


def test_app_renders_zh_default():
    at = _run()
    assert not list(at.exception)
    assert [tab.label for tab in at.tabs] == ["情報採集", "AI 深度洞察", "自動化排程", "歷史知識庫"]


def test_language_toggle_no_duplicate_id():
    # 迴歸測試：英文模式下兩個 Platforms 多選曾因相同 auto-id 衝突
    at = _run()
    at.sidebar.radio[0].set_value("English").run()
    assert not list(at.exception)
    assert at.tabs[0].label == "Collect"


def test_renders_cross_platform_data(sample_df):
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["df_results"] = sample_df
    at.run()
    assert not list(at.exception)
    rendered = "\n".join(m.value for m in at.main.markdown)
    assert "youtube" in rendered
    assert "threads" in rendered
    # Threads 圖文版以大字內文呈現
    assert "京都三天兩夜" in rendered


def test_no_aesthetics_copy_in_ui():
    at = _run()
    rendered = "\n".join(m.value for m in at.main.markdown)
    assert "醫美" not in rendered
