"""跨平台社群情報儀表板（Streamlit）。

升級自 YouTube Shorts 儀表板，現支援 YouTube / Instagram / Facebook / Threads，
資料統一走 UniversalContentModel（見 content_model.py）。

介面雙語：預設繁體中文，可於側邊欄切換英文。
啟動：py -m streamlit run app.py
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import db_service
from data_router import SUPPORTED_PLATFORMS, DataRouterError, fetch_content_dataframe
from line_service import LineServiceError, push_report
from llm_agent import LLMAgentError, generate_report, stream_report

KEYWORDS_CSV = "keywords.csv"
# APScheduler day_of_week 索引（0=mon）。
WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

PLATFORM_COLORS = {
    "youtube": "#FF0000",
    "instagram": "#E1306C",
    "facebook": "#1877F2",
    "threads": "#111111",
}

st.set_page_config(
    page_title="跨平台社群情報儀表板",
    page_icon="✦",
    layout="wide",
)


# ---------------------------------------------------------------------------
# i18n：雙語字典與翻譯輔助
# ---------------------------------------------------------------------------
I18N: dict[str, dict[str, str]] = {
    "zh": {
        "app_title": "跨平台社群情報與 AI 分析",
        "app_caption": "UniversalContentModel 統一資料流 · Asia/Taipei · {time}",
        "app_subtitle": "整合 YouTube、Instagram、Facebook、Threads 的熱門社群內容情報，並無縫產出 AI 洞察報告。",
        "lang_label": "語言 / Language",
        "tab_search": "情報採集",
        "tab_report": "AI 深度洞察",
        "tab_auto": "自動化排程",
        "tab_history": "歷史知識庫",
        # sidebar
        "sb_env": "系統設定與狀態",
        "sb_key_status": "API 金鑰整合",
        "sb_configured": "已啟用",
        "sb_missing": "待設定",
        "sb_automation": "自動化排程狀態",
        "sb_next_run": "下次執行：{time}",
        "sb_no_job": "排程未啟用",
        "sb_model": "模型",
        # scraper
        "sc_header": "跨平台情報採集",
        "sc_settings": "數據抓取設定",
        "sc_keywords": "監控關鍵字（讀自 keywords.csv）",
        "sc_extra": "額外自訂關鍵字（以逗號分隔）",
        "sc_platform_hint": "Facebook 目前使用公開粉專/個人頁 URL；Instagram 與 Threads 使用關鍵字/hashtag 搜尋。",
        "sc_platforms": "監控平台",
        "sc_days": "YouTube 回溯天數",
        "sc_max_sec": "YouTube 影片時長上限（秒）",
        "sc_limit": "Apify 每平台抓取上限",
        "sc_fetch": "開始跨平台抓取",
        "sc_fetching": "正在抓取內容…",
        "sc_fetching_one": "正在抓取：{label}",
        "sc_fail": "{platform} 抓取失敗：{message}",
        "sc_empty": "請先執行抓取以建立跨平台內容流。",
        "sc_kw_table": "檢視關鍵字分類表 (keywords.csv)",
        "sc_done": "抓取完成！共取得 {n} 筆內容。",
        # metrics
        "m_items": "採集內容總數",
        "m_platforms": "涵蓋平台數",
        "m_views": "已知觀看總數",
        "m_likes": "互動數（按讚）",
        # results
        "r_kpi": "關鍵效能指標",
        "r_filter_platform": "篩選平台",
        "r_sort": "排序方式",
        "r_cards": "顯示卡片數",
        "r_chart_platform": "各平台互動聲量",
        "r_chart_keyword": "各關鍵字觸及聲量（觀看／讚遞補）",
        "r_table": "內容明細表",
        "sort_views_or_likes": "觀看數（無則以讚遞補）",
        "sort_likes": "按讚數",
        "sort_comments": "留言數",
        "sort_publishedAt": "發布時間",
        # card
        "c_views": "觀看 {v}",
        "c_views_na": "觀看 —",
        "c_likes": "讚 {v}",
        "c_comments": "留言 {v}",
        "c_reposts": "轉發 {v}",
        "c_open": "開啟原文 ↗",
        # report
        "rp_header": "AI 深度洞察與推播",
        "rp_need_data": "請先在「情報採集」分頁完成數據抓取。",
        "rp_sample": "將以 {n} 筆跨平台內容樣本進行分析。",
        "rp_instruction": "分析指令（例如：聚焦特定品牌、調整報告語氣）",
        "rp_generate": "生成情報分析報告",
        "rp_report_title": "市場情報報告",
        "rp_md_src": "檢視 Markdown 原始碼",
        "rp_send_line": "透過 LINE 發送推播",
        "rp_sent": "已成功發送 {n} 則 LINE 訊息。",
        # automation
        "au_header": "背景自動化排程",
        "au_desc": "背景自動執行：跨平台抓取 → AI 報告生成 → LINE 自動推播。",
        "au_keywords": "目標監控關鍵字",
        "au_platforms": "目標監控平台",
        "au_weekday": "每週執行日",
        "au_hour": "時 (24h)",
        "au_minute": "分",
        "au_enable": "啟用自動化排程",
        "au_disable": "停用自動化排程",
        "au_scheduled": "已設定排程：每{weekday} {time} 自動執行。",
        "au_disabled": "自動化排程已停用。",
        "au_run_now_title": "手動強制執行",
        "au_run_now_desc": "立即於背景執行一次完整工作流。",
        "au_run_now": "立即執行",
        "au_run_done": "手動執行完畢。",
        # history
        "h_header": "歷史知識庫",
        "h_not_configured": "尚未設定 Supabase（SUPABASE_URL / SUPABASE_KEY），歷史功能不可用。",
        "h_days": "查詢近幾天",
        "h_trend": "關鍵字觀看趨勢",
        "h_no_data": "目前尚無歷史資料，請先執行抓取。",
        "h_reports": "歷史報告",
        "h_no_reports": "尚無報告記錄。",
    },
    "en": {
        "app_title": "Cross-platform Social Intelligence & AI Analysis",
        "app_caption": "UniversalContentModel feed · Asia/Taipei · {time}",
        "app_subtitle": "Trending content intelligence across YouTube, Instagram, Facebook and Threads, with seamless AI insight reports.",
        "lang_label": "語言 / Language",
        "tab_search": "Collect",
        "tab_report": "AI Insights",
        "tab_auto": "Automation",
        "tab_history": "History",
        "sb_env": "Settings & Status",
        "sb_key_status": "API key integration",
        "sb_configured": "configured",
        "sb_missing": "missing",
        "sb_automation": "Automation status",
        "sb_next_run": "Next run: {time}",
        "sb_no_job": "No scheduled job",
        "sb_model": "Model",
        "sc_header": "Cross-platform collection",
        "sc_settings": "Fetch settings",
        "sc_keywords": "Keywords (from keywords.csv)",
        "sc_extra": "Extra keywords, comma separated",
        "sc_platform_hint": "Facebook currently expects public page/profile URLs; Instagram and Threads use keyword/hashtag search.",
        "sc_platforms": "Platforms",
        "sc_days": "YouTube lookback days",
        "sc_max_sec": "YouTube max seconds",
        "sc_limit": "Apify result limit per platform",
        "sc_fetch": "Fetch content",
        "sc_fetching": "Fetching content…",
        "sc_fetching_one": "Fetching: {label}",
        "sc_fail": "{platform} failed: {message}",
        "sc_empty": "Run a search to populate the cross-platform feed.",
        "sc_kw_table": "View keyword table (keywords.csv)",
        "sc_done": "Done! Collected {n} items.",
        "m_items": "Items",
        "m_platforms": "Platforms",
        "m_views": "Known views",
        "m_likes": "Likes",
        "r_kpi": "Key metrics",
        "r_filter_platform": "Filter platforms",
        "r_sort": "Sort by",
        "r_cards": "Cards",
        "r_chart_platform": "Engagement by platform",
        "r_chart_keyword": "Reach proxy by keyword (views/likes)",
        "r_table": "Content table",
        "sort_views_or_likes": "Views (likes fallback)",
        "sort_likes": "Likes",
        "sort_comments": "Comments",
        "sort_publishedAt": "Published",
        "c_views": "views {v}",
        "c_views_na": "views —",
        "c_likes": "likes {v}",
        "c_comments": "comments {v}",
        "c_reposts": "reposts {v}",
        "c_open": "Open source ↗",
        "rp_header": "AI insights & push",
        "rp_need_data": "Fetch content first in the Collect tab.",
        "rp_sample": "Analyzing {n} cross-platform samples.",
        "rp_instruction": "Report instruction (brand focus, tone, etc.)",
        "rp_generate": "Generate report",
        "rp_report_title": "Market intelligence report",
        "rp_md_src": "View Markdown source",
        "rp_send_line": "Send to LINE",
        "rp_sent": "Sent {n} LINE message(s).",
        "au_header": "Background automation",
        "au_desc": "Runs in background: cross-platform fetch → AI report → LINE push.",
        "au_keywords": "Keywords",
        "au_platforms": "Platforms",
        "au_weekday": "Weekday",
        "au_hour": "Hour (24h)",
        "au_minute": "Minute",
        "au_enable": "Enable weekly job",
        "au_disable": "Disable job",
        "au_scheduled": "Scheduled: every {weekday} at {time}.",
        "au_disabled": "Automation disabled.",
        "au_run_now_title": "Run now",
        "au_run_now_desc": "Run one full workflow in the background immediately.",
        "au_run_now": "Run now",
        "au_run_done": "Manual run finished.",
        "h_header": "History",
        "h_not_configured": "Supabase is not configured (SUPABASE_URL / SUPABASE_KEY); history is unavailable.",
        "h_days": "History days",
        "h_trend": "Keyword view trend",
        "h_no_data": "No history yet. Run a fetch first.",
        "h_reports": "Saved reports",
        "h_no_reports": "No reports yet.",
    },
}

WEEKDAY_LABELS = {
    "zh": ["週一", "週二", "週三", "週四", "週五", "週六", "週日"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}


def lang() -> str:
    return st.session_state.get("lang", "zh")


def t(key: str, **kwargs: Any) -> str:
    table = I18N.get(lang(), I18N["zh"])
    text = table.get(key) or I18N["zh"].get(key, key)
    return text.format(**kwargs) if kwargs else text


# ---------------------------------------------------------------------------
# CSS（品牌樣式：Playfair + Inter，金色主題）
# ---------------------------------------------------------------------------
def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap');
        :root {
            --bg: #FCFBFA;
            --surface: #FFFFFF;
            --border: #EBEBEB;
            --text: #1A1A1A;
            --muted: #6B7280;
            --accent: #C5A880;
        }
        html, body, [class*="css"], .stApp {
            font-family: 'Inter', sans-serif !important;
            color: var(--text) !important;
        }
        h1, h2, h3, h4 {
            font-family: 'Playfair Display', serif !important;
            font-weight: 500 !important;
            color: var(--text) !important;
        }
        .stApp { background: var(--bg) !important; }
        .block-container { max-width: 1280px; padding-top: 1.4rem; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 4px !important;
            border-color: var(--border) !important;
            background: var(--surface) !important;
        }
        button[data-testid="baseButton-primary"] {
            background: #1A1A1A !important;
            border-color: #1A1A1A !important;
            color: #fff !important;
            border-radius: 2px !important;
        }
        button[data-testid="baseButton-primary"]:hover {
            background: var(--accent) !important;
            border-color: var(--accent) !important;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin: 14px 0 22px;
        }
        .metric-card {
            border: 1px solid var(--border);
            background: var(--surface);
            border-radius: 4px;
            padding: 16px;
        }
        .metric-label { color: var(--muted); font-size: 0.78rem; margin-bottom: 6px; }
        .metric-value { font-family: 'Playfair Display', serif; font-size: 1.7rem; font-weight: 500; }
        .platform-badge {
            display: inline-flex; align-items: center;
            border-radius: 999px; padding: 2px 10px;
            color: #fff; font-size: 0.72rem; font-weight: 600;
            text-transform: capitalize; margin-right: 8px;
        }
        .muted { color: var(--muted); }
        .thread-content { font-size: 1.05rem; line-height: 1.7; margin: 10px 0 12px; }
        .content-title { font-size: 1rem; font-weight: 600; line-height: 1.4; margin: 8px 0; }
        .content-link { color: var(--accent); text-decoration: none; font-weight: 600; }
        @media (max-width: 768px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            .metric-value { font-size: 1.4rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.start()
    return scheduler


def load_keywords() -> pd.DataFrame:
    if os.path.exists(KEYWORDS_CSV):
        try:
            return pd.read_csv(KEYWORDS_CSV)
        except Exception:
            return pd.DataFrame({"keyword": [], "category": [], "note": []})
    return pd.DataFrame({"keyword": [], "category": [], "note": []})


def number(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def compact_number(value: Any) -> str:
    value = number(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value.startswith("["):
        try:
            import ast

            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item]
        except Exception:
            return []
    return []


def image_like(url: str) -> bool:
    clean = url.lower().split("?")[0]
    return clean.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


def video_like(url: str) -> bool:
    clean = url.lower().split("?")[0]
    return clean.endswith((".mp4", ".mov", ".m3u8", ".webm"))


# ---------------------------------------------------------------------------
# 側邊欄
# ---------------------------------------------------------------------------
def select_language() -> None:
    options = {"中文": "zh", "English": "en"}
    choice = st.sidebar.radio(
        I18N["zh"]["lang_label"],
        list(options.keys()),
        index=0 if lang() == "zh" else 1,
        horizontal=True,
        key="lang_radio",
    )
    st.session_state["lang"] = options[choice]


def render_sidebar() -> None:
    st.sidebar.divider()
    st.sidebar.subheader(t("sb_env"))

    st.sidebar.caption(t("sb_key_status"))
    keys = {
        "YouTube": "YOUTUBE_API_KEY",
        "Apify": "APIFY_API_TOKEN",
        "OpenRouter": "OPENROUTER_API_KEY",
        "LINE": "LINE_CHANNEL_ACCESS_TOKEN",
        "Supabase": "SUPABASE_URL",
    }
    for label, env_key in keys.items():
        ok = bool(os.getenv(env_key))
        icon = "●" if ok else "○"
        state = t("sb_configured") if ok else t("sb_missing")
        st.sidebar.markdown(
            f'<div style="display:flex;justify-content:space-between;font-size:0.85rem;">'
            f'<span class="muted">{label}</span>'
            f'<span style="color:{"#1A1A1A" if ok else "#9CA3AF"};">{icon} {state}</span></div>',
            unsafe_allow_html=True,
        )

    st.sidebar.divider()
    st.sidebar.subheader(t("sb_automation"))
    jobs = get_scheduler().get_jobs()
    if jobs:
        next_run = jobs[0].next_run_time
        st.sidebar.caption(t("sb_next_run", time=next_run.strftime("%Y-%m-%d %H:%M") if next_run else "N/A"))
    else:
        st.sidebar.caption(t("sb_no_job"))
    st.sidebar.caption(f'{t("sb_model")}: {os.getenv("OPENROUTER_MODEL", "—")}')


# ---------------------------------------------------------------------------
# 結果呈現
# ---------------------------------------------------------------------------
def render_metrics(df: pd.DataFrame) -> None:
    known_views = df["metrics_views"].dropna().sum() if "metrics_views" in df else 0
    likes = df["metrics_likes"].sum() if "metrics_likes" in df else 0
    html = f"""
    <div class="metric-grid">
        <div class="metric-card"><div class="metric-label">{t('m_items')}</div><div class="metric-value">{len(df)}</div></div>
        <div class="metric-card"><div class="metric-label">{t('m_platforms')}</div><div class="metric-value">{df['platform'].nunique()}</div></div>
        <div class="metric-card"><div class="metric-label">{t('m_views')}</div><div class="metric-value" style="color:var(--accent);">{compact_number(known_views)}</div></div>
        <div class="metric-card"><div class="metric-label">{t('m_likes')}</div><div class="metric-value">{compact_number(likes)}</div></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_content_card(row: pd.Series) -> None:
    platform = str(row.get("platform", ""))
    author = str(row.get("authorName") or row.get("author_name") or "Unknown")
    title = row.get("title")
    content = str(row.get("content") or "")
    url = str(row.get("url") or "")
    media_urls = as_list(row.get("mediaUrls")) or as_list(row.get("media_urls"))
    views = row.get("metrics_views")

    metrics = [
        t("c_views", v=compact_number(views)) if pd.notna(views) else t("c_views_na"),
        t("c_likes", v=compact_number(row.get("metrics_likes"))),
        t("c_comments", v=compact_number(row.get("metrics_comments"))),
    ]
    reposts = row.get("metrics_reposts")
    if pd.notna(reposts):
        metrics.append(t("c_reposts", v=compact_number(reposts)))

    color = PLATFORM_COLORS.get(platform, "#6B7280")
    with st.container(border=True):
        st.markdown(
            f'<span class="platform-badge" style="background:{color};">{platform}</span>'
            f'<span class="muted">{author} · {row.get("fetchedKeyword", "")}</span>',
            unsafe_allow_html=True,
        )

        # Threads 採類 X 圖文排版（大字內文），其餘平台採標題優先。
        if platform != "threads" and title:
            st.markdown(f'<div class="content-title">{title}</div>', unsafe_allow_html=True)
        if content:
            css_class = "thread-content" if platform == "threads" else "muted"
            st.markdown(f'<div class="{css_class}">{content}</div>', unsafe_allow_html=True)

        if media_urls:
            cols = st.columns(min(2, len(media_urls)))
            for index, media_url in enumerate(media_urls[:4]):
                with cols[index % len(cols)]:
                    if image_like(media_url):
                        st.image(media_url, width='stretch')
                    elif video_like(media_url):
                        st.video(media_url)

        st.caption(" · ".join(metrics))
        if url:
            st.markdown(f'<a class="content-link" href="{url}" target="_blank">{t("c_open")}</a>', unsafe_allow_html=True)


def render_results(df: pd.DataFrame) -> None:
    with st.container(border=True):
        st.markdown(f"#### {t('r_kpi')}")
        render_metrics(df)

        controls = st.columns([1, 1, 1])
        with controls[0]:
            platforms = sorted(df["platform"].dropna().unique().tolist())
            selected_platforms = st.multiselect(t("r_filter_platform"), platforms, default=platforms)
        with controls[1]:
            sort_keys = ["views_or_likes", "likes", "comments", "publishedAt"]
            sort_by = st.selectbox(t("r_sort"), sort_keys, format_func=lambda k: t(f"sort_{k}"))
        with controls[2]:
            max_cards = st.slider(t("r_cards"), 5, 100, 30)

    filtered = df[df["platform"].isin(selected_platforms)].copy()
    if filtered.empty:
        return
    filtered["views_or_likes"] = filtered["metrics_views"].fillna(filtered["metrics_likes"])
    sort_column = {
        "views_or_likes": "views_or_likes",
        "likes": "metrics_likes",
        "comments": "metrics_comments",
        "publishedAt": "publishedAt",
    }[sort_by]
    filtered = filtered.sort_values(sort_column, ascending=False).head(max_cards)

    chart_cols = st.columns(2)
    with chart_cols[0]:
        with st.container(border=True):
            st.markdown(f"##### {t('r_chart_platform')}")
            platform_agg = filtered.groupby("platform", as_index=False)["metrics_likes"].sum()
            fig = px.bar(platform_agg, x="platform", y="metrics_likes",
                         color="platform", color_discrete_map=PLATFORM_COLORS, text_auto=".2s")
            fig.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
                              margin={"t": 20, "b": 30, "l": 30, "r": 10})
            st.plotly_chart(fig, width='stretch')
    with chart_cols[1]:
        with st.container(border=True):
            st.markdown(f"##### {t('r_chart_keyword')}")
            keyword_agg = filtered.groupby("fetchedKeyword", as_index=False)["views_or_likes"].sum()
            fig2 = px.bar(keyword_agg, x="fetchedKeyword", y="views_or_likes",
                          text_auto=".2s", color_discrete_sequence=["#C5A880"])
            fig2.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                               plot_bgcolor="rgba(0,0,0,0)",
                               margin={"t": 20, "b": 30, "l": 30, "r": 10})
            st.plotly_chart(fig2, width='stretch')

    with st.expander(t("r_table")):
        table_cols = [c for c in ["platform", "fetchedKeyword", "authorName", "title",
                                  "metrics_views", "metrics_likes", "metrics_comments", "url"]
                      if c in filtered.columns]
        st.dataframe(
            filtered[table_cols],
            width='stretch',
            column_config={"url": st.column_config.LinkColumn("URL")},
        )

    for _, row in filtered.iterrows():
        render_content_card(row)


# ---------------------------------------------------------------------------
# 分頁：情報採集
# ---------------------------------------------------------------------------
def render_scraper_tab() -> None:
    st.markdown(f"## {t('sc_header')}")
    kw_df = load_keywords()
    keyword_options = kw_df["keyword"].dropna().tolist() if not kw_df.empty else []

    with st.container(border=True):
        st.markdown(f"##### {t('sc_settings')}")
        cols = st.columns([2, 1, 1])
        with cols[0]:
            selected = st.multiselect(
                t("sc_keywords"),
                options=keyword_options,
                default=keyword_options[: min(4, len(keyword_options))],
                key="sc_keywords",
            )
            extra = st.text_input(t("sc_extra"), key="sc_extra")
            if extra.strip():
                selected += [item.strip() for item in extra.split(",") if item.strip()]
            st.caption(t("sc_platform_hint"))
        with cols[1]:
            platforms = st.multiselect(
                t("sc_platforms"),
                options=list(SUPPORTED_PLATFORMS),
                default=["youtube", "threads"],
                format_func=str.capitalize,
                key="sc_platforms",
            )
            days = st.slider(t("sc_days"), 1, 90, 14, key="sc_days")
        with cols[2]:
            max_seconds = st.slider(t("sc_max_sec"), 15, 180, 120, key="sc_max_sec")
            result_limit = st.slider(t("sc_limit"), 5, 100, 50, key="sc_limit")

        if st.button(t("sc_fetch"), type="primary", disabled=not selected or not platforms):
            progress = st.progress(0.0, text=t("sc_fetching"))

            def progress_callback(done: int, total: int, label: str) -> None:
                progress.progress(min(done / max(total, 1), 1.0), text=t("sc_fetching_one", label=label))

            try:
                df, errors = fetch_content_dataframe(
                    selected,
                    platforms=platforms,
                    days=days,
                    max_seconds=max_seconds,
                    result_limit=result_limit,
                    progress_callback=progress_callback,
                )
            except DataRouterError as exc:
                progress.empty()
                st.error(str(exc))
                return
            progress.empty()
            st.session_state["df_results"] = df
            st.session_state["fetch_errors"] = errors
            st.session_state["run_id"] = str(uuid.uuid4())

            if not df.empty:
                st.success(t("sc_done", n=len(df)))
                db_service.upsert_shorts(df, st.session_state["run_id"])

    if not kw_df.empty:
        with st.expander(t("sc_kw_table")):
            st.dataframe(kw_df, width='stretch')

    errors = st.session_state.get("fetch_errors", {})
    for platform, message in errors.items():
        st.warning(t("sc_fail", platform=platform, message=message))

    df = st.session_state.get("df_results")
    if isinstance(df, pd.DataFrame) and not df.empty:
        render_results(df)
    else:
        st.info(t("sc_empty"))


# ---------------------------------------------------------------------------
# 分頁：AI 報告
# ---------------------------------------------------------------------------
def render_report_tab() -> None:
    st.markdown(f"## {t('rp_header')}")
    df = st.session_state.get("df_results")
    if not isinstance(df, pd.DataFrame) or df.empty:
        st.info(t("rp_need_data"))
        return

    with st.container(border=True):
        st.write(t("rp_sample", n=len(df)))
        extra = st.text_input(t("rp_instruction"))
        if st.button(t("rp_generate"), type="primary"):
            placeholder = st.empty()
            report = ""
            try:
                for delta in stream_report(df, extra_instruction=extra or None):
                    report += delta
                    placeholder.markdown(report)
            except LLMAgentError as exc:
                st.error(str(exc))
                return
            st.session_state["report"] = report
            db_service.save_report(
                st.session_state.get("run_id", "manual"),
                df["fetchedKeyword"].dropna().unique().tolist(),
                os.getenv("OPENROUTER_MODEL", "unknown"),
                report,
            )

    report = st.session_state.get("report")
    if report:
        with st.container(border=True):
            st.markdown(f"##### {t('rp_report_title')}")
            st.markdown(report)
            with st.expander(t("rp_md_src")):
                st.code(report, language="markdown")
            if st.button(t("rp_send_line")):
                try:
                    sent = push_report(report)
                    st.success(t("rp_sent", n=sent))
                except LineServiceError as exc:
                    st.error(str(exc))


# ---------------------------------------------------------------------------
# 自動化排程
# ---------------------------------------------------------------------------
def automation_job(keywords: list[str], platforms: list[str], days: int,
                   max_seconds: int, result_limit: int) -> None:
    df, errors = fetch_content_dataframe(
        keywords,
        platforms=platforms,
        days=days,
        max_seconds=max_seconds,
        result_limit=result_limit,
    )
    if df.empty:
        raise RuntimeError(f"No content fetched. Errors: {errors}")
    report, run_id = generate_report(df)
    db_service.upsert_shorts(df, run_id)
    db_service.save_report(
        run_id,
        df["fetchedKeyword"].dropna().unique().tolist(),
        os.getenv("OPENROUTER_MODEL", "unknown"),
        report,
    )
    push_report(report)


def render_automation_tab() -> None:
    st.markdown(f"## {t('au_header')}")
    scheduler = get_scheduler()
    kw_df = load_keywords()
    keyword_options = kw_df["keyword"].dropna().tolist() if not kw_df.empty else []
    weekday_labels = WEEKDAY_LABELS[lang()]

    with st.container(border=True):
        st.caption(t("au_desc"))
        keywords = st.multiselect(t("au_keywords"), keyword_options,
                                  default=keyword_options[: min(4, len(keyword_options))],
                                  key="au_keywords")
        platforms = st.multiselect(t("au_platforms"), list(SUPPORTED_PLATFORMS),
                                   default=["youtube", "threads"], format_func=str.capitalize,
                                   key="au_platforms")
        c1, c2, c3 = st.columns(3)
        with c1:
            weekday_idx = st.selectbox(t("au_weekday"), range(7),
                                       format_func=lambda i: weekday_labels[i], key="au_weekday")
        with c2:
            hour = st.number_input(t("au_hour"), 0, 23, 9, key="au_hour")
        with c3:
            minute = st.number_input(t("au_minute"), 0, 59, 0, key="au_minute")
        days = st.slider(t("sc_days"), 1, 90, 7, key="au_days")
        max_seconds = st.slider(t("sc_max_sec"), 15, 180, 120, key="auto_max_seconds")
        result_limit = st.slider(t("sc_limit"), 5, 100, 50, key="auto_result_limit")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(t("au_enable"), type="primary", disabled=not keywords or not platforms):
                scheduler.remove_all_jobs()
                scheduler.add_job(
                    automation_job,
                    trigger="cron",
                    day_of_week=int(weekday_idx),
                    hour=int(hour),
                    minute=int(minute),
                    args=[keywords, platforms, days, max_seconds, result_limit],
                    id="weekly_report",
                    replace_existing=True,
                )
                st.success(t("au_scheduled", weekday=weekday_labels[weekday_idx],
                             time=f"{int(hour):02d}:{int(minute):02d}"))
                st.rerun()
        with col_b:
            if st.button(t("au_disable"), disabled=not scheduler.get_jobs()):
                scheduler.remove_all_jobs()
                st.info(t("au_disabled"))
                st.rerun()

    with st.container(border=True):
        st.markdown(f"##### {t('au_run_now_title')}")
        st.caption(t("au_run_now_desc"))
        if st.button(t("au_run_now")):
            with st.spinner(t("au_run_now")):
                automation_job(keywords, platforms, days, max_seconds, result_limit)
            st.success(t("au_run_done"))


# ---------------------------------------------------------------------------
# 歷史知識庫
# ---------------------------------------------------------------------------
def render_history_tab() -> None:
    st.markdown(f"## {t('h_header')}")
    if not db_service.is_configured():
        st.warning(t("h_not_configured"))
        return

    days = st.slider(t("h_days"), 1, 90, 30)
    with st.container(border=True):
        st.markdown(f"##### {t('h_trend')}")
        hist_df = db_service.get_history(days=days)
        if hist_df.empty:
            st.info(t("h_no_data"))
        else:
            agg = hist_df.copy()
            agg["fetched_at"] = pd.to_datetime(agg["fetched_at"]).dt.date
            agg = agg.groupby(["fetched_at", "keyword"], as_index=False)["view_count"].sum()
            fig = px.line(agg, x="fetched_at", y="view_count", color="keyword", markers=True)
            fig.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)",
                              margin={"t": 20, "b": 30, "l": 40, "r": 20})
            st.plotly_chart(fig, width='stretch')

    reports = db_service.get_reports(limit=20)
    with st.container(border=True):
        st.markdown(f"##### {t('h_reports')}")
        if not reports:
            st.info(t("h_no_reports"))
        else:
            for report in reports:
                label = f"{str(report.get('generated_at', ''))[:16].replace('T', ' ')}　{report.get('keywords', '')}"
                with st.expander(label):
                    st.markdown(report.get("content", ""))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> None:
    inject_custom_css()
    select_language()

    st.markdown(
        f"""
        <div style="border-bottom:1px solid #EBEBEB;padding-bottom:20px;margin-bottom:24px;">
            <h1 style="margin:0;font-size:clamp(1.7rem,4vw,2.6rem);">{t('app_title')}</h1>
            <p class="muted" style="margin:10px 0 0;font-size:clamp(0.85rem,2vw,1rem);max-width:640px;line-height:1.6;">{t('app_subtitle')}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(t("app_caption", time=datetime.now().strftime("%Y-%m-%d %H:%M")))

    render_sidebar()

    tabs = st.tabs([t("tab_search"), t("tab_report"), t("tab_auto"), t("tab_history")])
    with tabs[0]:
        render_scraper_tab()
    with tabs[1]:
        render_report_tab()
    with tabs[2]:
        render_automation_tab()
    with tabs[3]:
        render_history_tab()


if __name__ == "__main__":
    main()
