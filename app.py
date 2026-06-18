"""醫美短影音市場情報儀表板（Streamlit）。

區塊 A：側邊欄 — 金鑰狀態與排程指示器
區塊 B：分頁1 — 關鍵字與數據抓取
區塊 C：分頁2 — AI 分析報告與 LINE 發送
區塊 D：分頁3 — 每週自動化排程

啟動：py -m streamlit run app.py
"""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from youtube_service import fetch_shorts, YouTubeServiceError
from llm_agent import stream_report, generate_report, LLMAgentError
from line_service import push_report, LineServiceError
import db_service

KEYWORDS_CSV = "keywords.csv"
WEEKDAYS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

st.set_page_config(page_title="醫美情報與分析系統", page_icon="✧", layout="wide")


# ---------------------------------------------------------------------------
# CSS 注入與 UI 美化 (Clinical Precision & Elegance)
# ---------------------------------------------------------------------------
def inject_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

        /* 全域字型套用 */
        html, body, [class*="css"], .stApp {
            font-family: 'Inter', sans-serif !important;
            color: #1A1A1A !important;
        }
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Playfair Display', serif !important;
            font-weight: 500 !important;
            letter-spacing: 0.02em;
            color: #1A1A1A !important;
        }

        /* 顏色變數 */
        :root {
            --color-primary: #C5A880;
            --color-primary-hover: #B0926A;
            --color-background: #FCFBFA;
            --color-surface: #FFFFFF;
            --color-border: #EBEBEB;
            --color-text: #1A1A1A;
            --color-text-muted: #6B7280;
        }

        .stApp {
            background-color: var(--color-background) !important;
        }

        header[data-testid="stHeader"] {
            background-color: transparent !important;
        }

        /* 卡片容器 */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background-color: var(--color-surface) !important;
            border: 1px solid var(--color-border) !important;
            border-radius: 2px !important;
            padding: 1.5rem !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
            margin-bottom: 1.25rem !important;
            transition: box-shadow 0.3s ease !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.04) !important;
        }

        /* 標籤頁 (Tabs) 樣式優化 */
        div[data-testid="stTabBar"] {
            background-color: transparent !important;
            border-bottom: 1px solid var(--color-border) !important;
            gap: 16px !important;
            padding-bottom: 4px !important;
            overflow-x: auto !important;
            flex-wrap: nowrap !important;
        }
        button[data-testid="stTabBar-trigger"] {
            font-family: 'Inter', sans-serif !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.03em !important;
            color: var(--color-text-muted) !important;
            border: none !important;
            background: none !important;
            padding: 8px 4px !important;
            white-space: nowrap !important;
            transition: color 0.3s ease !important;
        }
        button[data-testid="stTabBar-trigger"]:hover {
            color: var(--color-text) !important;
        }
        button[data-testid="stTabBar-trigger"][aria-selected="true"] {
            color: var(--color-text) !important;
            font-weight: 600 !important;
            border-bottom: 2px solid var(--color-primary) !important;
        }

        /* 主要按鈕樣式 */
        button[data-testid="baseButton-primary"] {
            background-color: #1A1A1A !important;
            border: 1px solid #1A1A1A !important;
            border-radius: 2px !important;
            color: #FFFFFF !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
            letter-spacing: 0.05em !important;
            font-size: 0.85rem !important;
            padding: 0.65rem 1.25rem !important;
            min-height: 44px !important;
            width: 100% !important;
            transition: all 0.3s ease !important;
        }
        button[data-testid="baseButton-primary"]:hover {
            background-color: var(--color-primary) !important;
            border-color: var(--color-primary) !important;
        }

        /* 次要按鈕樣式 */
        button[data-testid="baseButton-secondary"] {
            background-color: transparent !important;
            border: 1px solid var(--color-border) !important;
            border-radius: 2px !important;
            color: var(--color-text) !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
            letter-spacing: 0.05em !important;
            font-size: 0.85rem !important;
            padding: 0.65rem 1.25rem !important;
            min-height: 44px !important;
            width: 100% !important;
            transition: all 0.3s ease !important;
        }
        button[data-testid="baseButton-secondary"]:hover {
            border-color: #1A1A1A !important;
        }

        /* 輸入框優化 */
        div[data-baseweb="select"] {
            border-radius: 2px !important;
        }
        input, select, textarea {
            border-radius: 2px !important;
            font-size: 16px !important; /* 防止 iOS 自動縮放 */
        }

        /* KPI 指標卡片 */
        .metric-card {
            background-color: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: 2px;
            padding: 1.25rem;
            text-align: left;
            transition: border-color 0.3s ease;
        }
        .metric-card:hover {
            border-color: var(--color-primary);
        }
        .metric-title {
            font-family: 'Inter', sans-serif;
            font-size: 0.78rem;
            letter-spacing: 0.05em;
            color: var(--color-text-muted);
            margin-bottom: 0.5rem;
            font-weight: 500;
        }
        .metric-value {
            font-family: 'Playfair Display', serif;
            font-size: 1.9rem;
            font-weight: 400;
            color: var(--color-text);
            line-height: 1.1;
        }

        /* ── RWD：手機版 ── */
        @media (max-width: 768px) {
            div[data-testid="stVerticalBlockBorderWrapper"] {
                padding: 1rem !important;
            }
            .metric-value {
                font-size: 1.5rem;
            }
            /* 側邊欄收合時主內容滿版 */
            .main .block-container {
                padding-left: 1rem !important;
                padding-right: 1rem !important;
                max-width: 100% !important;
            }
            /* Dataframe 橫向捲動 */
            div[data-testid="stDataFrameResizable"] {
                overflow-x: auto !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 排程器（用 cache_resource 確保整個 app 生命週期只建立一次）
# ---------------------------------------------------------------------------
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
            pass
    return pd.DataFrame({"keyword": [], "category": [], "note": []})


def automation_job(keywords: list[str], days: int):
    """排程觸發時的完整流程：抓取 → 報告 → LINE。靜默執行，結果寫入 log。"""
    import logging

    log = logging.getLogger("automation")
    try:
        log.info("自動化流程啟動：%s", keywords)
        df = fetch_shorts(keywords, days=days)
        if df.empty:
            log.warning("自動化：未抓到資料，跳過。")
            return
        report = generate_report(df)
        push_report(report)
        log.info("自動化流程完成，已推播 LINE。")
    except Exception as exc:  # 背景任務不可讓例外逸出
        log.error("自動化流程失敗：%s", exc)


# ---------------------------------------------------------------------------
# 區塊 A：側邊欄
# ---------------------------------------------------------------------------
def render_sidebar():
    st.sidebar.markdown(
        '<h2 style="font-family: \'Inter\', sans-serif; font-size: 1rem; letter-spacing: 0.05em; color: #1A1A1A; border-bottom: 1px solid #EBEBEB; padding-bottom: 8px; margin-bottom: 20px;">系統設定與狀態</h2>',
        unsafe_allow_html=True
    )

    st.sidebar.markdown(
        '<div style="font-family: \'Inter\', sans-serif; font-size: 0.8rem; letter-spacing: 0.05em; color: #6B7280; margin-bottom: 12px;">API 金鑰整合</div>',
        unsafe_allow_html=True
    )
    keys = {
        "YouTube API": "YOUTUBE_API_KEY",
        "OpenRouter": "OPENROUTER_API_KEY",
        "LINE Token": "LINE_CHANNEL_ACCESS_TOKEN",
        "LINE 推播對象": "LINE_USER_ID",
    }
    
    status_html = '<div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px;">'
    for label, env in keys.items():
        ok = bool(os.getenv(env))
        color = "#1A1A1A" if ok else "#9CA3AF"
        icon = "●" if ok else "○"
        status_text = "已啟用" if ok else "待設定"
        status_html += f'<div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; font-family: \'Inter\', sans-serif;"><span style="color: #4B5563;">{label}</span><span style="color: {color}; font-size: 0.8rem;">{icon} {status_text}</span></div>'
    status_html += '</div>'
    st.sidebar.markdown(status_html, unsafe_allow_html=True)
    st.sidebar.caption("請於專案根目錄 `.env` 更新金鑰並重啟系統。")

    st.sidebar.markdown(
        '<div style="font-family: \'Inter\', sans-serif; font-size: 0.8rem; letter-spacing: 0.05em; color: #6B7280; margin-bottom: 12px; margin-top: 10px;">自動化排程狀態</div>',
        unsafe_allow_html=True
    )
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    if jobs:
        job = jobs[0]
        nxt = job.next_run_time
        nxt_str = nxt.strftime('%Y-%m-%d %H:%M') if nxt else 'N/A'
        sched_html = f"""
        <div style="border-left: 2px solid #C5A880; padding-left: 12px; margin-bottom: 24px;">
            <div style="color: #1A1A1A; font-family: 'Inter', sans-serif; font-size: 0.85rem; font-weight: 500;">排程已啟用</div>
            <div style="color: #6B7280; font-size: 0.8rem; margin-top: 4px;">下次執行：{nxt_str}</div>
        </div>
        """
        st.sidebar.markdown(sched_html, unsafe_allow_html=True)
    else:
        sched_html = """
        <div style="border-left: 2px solid #EBEBEB; padding-left: 12px; margin-bottom: 24px;">
            <div style="color: #9CA3AF; font-family: 'Inter', sans-serif; font-size: 0.85rem;">排程未啟用</div>
        </div>
        """
        st.sidebar.markdown(sched_html, unsafe_allow_html=True)

    st.sidebar.markdown(
        f'<div style="font-family: \'Inter\', sans-serif; font-size: 0.8rem; color: #6B7280;">模型：<span style="color: #1A1A1A;">{os.getenv("OPENROUTER_MODEL", "未設定")}</span></div>',
        unsafe_allow_html=True
    )


# ---------------------------------------------------------------------------
# 輔助 UI 元件：指標卡片
# ---------------------------------------------------------------------------
def render_metrics_cards(df: pd.DataFrame):
    total_shorts = len(df)
    total_views = df["view_count"].sum()
    avg_views = int(df["view_count"].mean()) if total_shorts > 0 else 0
    total_likes = df["like_count"].sum()
    
    def format_num(num):
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num / 1_000:.1f}K"
        return str(num)
        
    metrics_html = f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px;">
        <div class="metric-card">
            <div class="metric-title">採集影片總數</div>
            <div class="metric-value">{total_shorts}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">總曝光觀看數</div>
            <div class="metric-value" style="color: #C5A880;">{format_num(total_views)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">平均觀看次數</div>
            <div class="metric-value">{format_num(avg_views)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">互動數 (按讚)</div>
            <div class="metric-value">{format_num(total_likes)}</div>
        </div>
    </div>
    """
    st.markdown(metrics_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 區塊 B：關鍵字與數據抓取
# ---------------------------------------------------------------------------
def render_scraper_tab():
    st.markdown(
        '<h2 style="font-size: 1.8rem; color: #1A1A1A; margin-bottom: 24px;">市場情報採集</h2>',
        unsafe_allow_html=True
    )

    kw_df = load_keywords()
    all_keywords = kw_df["keyword"].dropna().tolist() if not kw_df.empty else []

    with st.container(border=True):
        st.markdown(
            '<h3 style="font-family: \'Inter\', sans-serif; font-size: 0.95rem; letter-spacing: 0.05em; color: #6B7280; margin-bottom: 20px;">數據抓取設定</h3>',
            unsafe_allow_html=True
        )
        col1, col2 = st.columns([2, 1])
        with col1:
            selected = st.multiselect(
                "監控關鍵字（讀自 keywords.csv）",
                options=all_keywords,
                default=all_keywords[: min(4, len(all_keywords))],
            )
            extra = st.text_input("額外自訂關鍵字（請以逗號分隔）", "")
            if extra.strip():
                selected = selected + [k.strip() for k in extra.split(",") if k.strip()]
        with col2:
            days = st.slider("數據回溯天數", min_value=1, max_value=90, value=14)
            max_sec = st.slider("影片時長上限（秒）", 15, 120, 120)

        st.write("")
        if st.button("開始掃描抓取", type="primary", disabled=not selected):
            progress = st.progress(0.0, text="初始化中...")

            def cb(done, total, keyword):
                progress.progress(done / total, text=f"正在掃描：{keyword} ({done}/{total})")

            try:
                df = fetch_shorts(selected, days=days, max_seconds=max_sec,
                                  progress_callback=cb)
            except YouTubeServiceError as e:
                progress.empty()
                st.error(f"數據抓取失敗：{e}")
                return
            progress.empty()
            st.session_state["df_results"] = df
            if df.empty:
                st.warning("未找到符合目前條件的數據。")
            else:
                st.success(f"數據抓取完成！共取得 {len(df)} 筆紀錄。")
                import uuid as _uuid
                run_id = str(_uuid.uuid4())
                st.session_state["run_id"] = run_id
                db_service.upsert_shorts(df, run_id)

    if not kw_df.empty:
        st.write("")
        with st.expander("檢視關鍵字分類表 (keywords.csv)"):
            st.dataframe(kw_df, use_container_width=True)

    # 顯示結果
    df = st.session_state.get("df_results")
    if df is not None and not df.empty:
        st.write("")
        with st.container(border=True):
            st.markdown(
                '<h3 style="font-family: \'Inter\', sans-serif; font-size: 0.95rem; letter-spacing: 0.05em; color: #6B7280; margin-bottom: 20px;">關鍵效能指標</h3>',
                unsafe_allow_html=True
            )
            # 渲染 KPI 數字小卡
            render_metrics_cards(df)

            st.dataframe(
                df[["keyword", "title", "view_count", "like_count",
                    "duration_sec", "published_at", "url"]],
                use_container_width=True,
                column_config={"url": st.column_config.LinkColumn("連結")},
            )

        st.write("")
        # 圖表展示區
        plotly_layout_updates = {
            "template": "plotly_white",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"family": "Inter, sans-serif", "color": "#1A1A1A"},
            "margin": {"t": 40, "b": 30, "l": 40, "r": 20},
        }

        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown(
                    '<h3 style="font-family: \'Inter\', sans-serif; font-size: 0.95rem; font-weight: 500; letter-spacing: 0.05em; color: #1A1A1A; margin-bottom: 20px;">各關鍵字曝光聲量</h3>',
                    unsafe_allow_html=True
                )
                agg = (df.groupby("keyword")["view_count"].sum()
                       .sort_values(ascending=False).reset_index())
                fig = px.bar(
                    agg, 
                    x="keyword", 
                    y="view_count",
                    text_auto=".2s",
                    color_discrete_sequence=["#C5A880"]
                )
                fig.update_layout(**plotly_layout_updates)
                fig.update_traces(
                    marker_line_width=0,
                    textposition="outside",
                    textfont_color="#1A1A1A"
                )
                st.plotly_chart(fig, use_container_width=True)
                
        with c2:
            with st.container(border=True):
                st.markdown(
                    '<h3 style="font-family: \'Inter\', sans-serif; font-size: 0.95rem; font-weight: 500; letter-spacing: 0.05em; color: #1A1A1A; margin-bottom: 20px;">前 10 熱門內容分佈</h3>',
                    unsafe_allow_html=True
                )
                top = df.nlargest(10, "view_count").copy()
                top["short_title"] = top["title"].apply(lambda x: str(x) if len(str(x)) <= 30 else str(x)[:27] + "...")
                
                fig2 = px.pie(
                    top, 
                    names="short_title", 
                    values="view_count",
                    hole=0.45,
                    color_discrete_sequence=["#C5A880", "#D4AF37", "#E0A96D", "#8D99AE", "#2B2D42", "#A3B18A", "#D4A373", "#CCD5AE", "#E9EDC9", "#FAEDCD"],
                    custom_data=["title"]
                )
                fig2.update_layout(**plotly_layout_updates)
                fig2.update_layout(showlegend=False)
                fig2.update_traces(
                    textposition="inside", 
                    textinfo="percent",
                    hovertemplate="<b>%{customdata[0]}</b><br><br>觀看數: %{value:,}<br>佔比: %{percent}<extra></extra>"
                )
                st.plotly_chart(fig2, use_container_width=True)


# ---------------------------------------------------------------------------
# 區塊 C：AI 報告與 LINE
# ---------------------------------------------------------------------------
def render_report_tab():
    st.markdown(
        '<h2 style="font-size: 1.8rem; color: #1A1A1A; margin-bottom: 24px;">AI 深度洞察與推播</h2>',
        unsafe_allow_html=True
    )

    df = st.session_state.get("df_results")
    if df is None or df.empty:
        st.info("請先在「市場情報採集」分頁中完成數據抓取。")
        return

    with st.container(border=True):
        st.markdown(
            '<h3 style="font-family: \'Inter\', sans-serif; font-size: 0.95rem; letter-spacing: 0.05em; color: #6B7280; margin-bottom: 20px;">分析報告設定</h3>',
            unsafe_allow_html=True
        )
        st.write(f"將以 **{len(df)}** 支短影音樣本進行分析。")
        extra = st.text_input("分析指令（例如：聚焦特定品牌、調整報告語氣）", "")
        
        st.write("")
        if st.button("生成情報分析報告", type="primary"):
            placeholder = st.empty()
            acc = ""
            try:
                for delta in stream_report(df, extra_instruction=extra or None):
                    acc += delta
                    placeholder.markdown(acc)
            except LLMAgentError as e:
                st.error(f"報告生成失敗：{e}")
                return
            st.session_state["report"] = acc
            run_id = st.session_state.get("run_id", "manual")
            model = os.getenv("OPENROUTER_MODEL", "unknown")
            keywords = df["keyword"].unique().tolist() if "keyword" in df.columns else []
            db_service.save_report(run_id, keywords, model, acc)

    report = st.session_state.get("report")
    if report:
        st.write("")
        with st.container(border=True):
            st.markdown(
                '<h3 style="font-family: \'Inter\', sans-serif; font-size: 0.95rem; letter-spacing: 0.05em; color: #6B7280; margin-bottom: 20px;">市場情報報告</h3>',
                unsafe_allow_html=True
            )
            st.markdown(report)
            
            st.write("")
            with st.expander("檢視 Markdown 原始碼"):
                st.code(report, language="markdown")
            
            st.write("")
            if st.button("透過 LINE 發送推播", type="secondary"):
                with st.spinner("正在發送推播..."):
                    try:
                        n = push_report(report)
                        st.success(f"已成功發送至 {n} 個 LINE 群組。")
                    except LineServiceError as e:
                        st.error(f"推播發送失敗：{e}")


# ---------------------------------------------------------------------------
# 區塊 D：自動化排程
# ---------------------------------------------------------------------------
def render_automation_tab():
    st.markdown(
        '<h2 style="font-size: 1.8rem; color: #1A1A1A; margin-bottom: 24px;">背景自動化排程</h2>',
        unsafe_allow_html=True
    )

    scheduler = get_scheduler()
    kw_df = load_keywords()
    all_keywords = kw_df["keyword"].dropna().tolist() if not kw_df.empty else []

    with st.container(border=True):
        st.markdown(
            '<h3 style="font-family: \'Inter\', sans-serif; font-size: 0.95rem; letter-spacing: 0.05em; color: #6B7280; margin-bottom: 16px;">自動化工作流設定</h3>',
            unsafe_allow_html=True
        )
        st.markdown("<p style='color: #6B7280; font-size: 0.9em; margin-bottom: 24px;'>背景自動執行：數據抓取 → AI 報告生成 → LINE 自動推播。</p>", unsafe_allow_html=True)
        
        auto_keywords = st.multiselect("目標監控關鍵字", options=all_keywords,
                                       default=all_keywords[: min(4, len(all_keywords))])
        c1, c2, c3 = st.columns(3)
        with c1:
            weekday = st.selectbox("每週執行日", WEEKDAYS, index=0)
        with c2:
            hour = st.number_input("時 (24h)", 0, 23, 9)
        with c3:
            minute = st.number_input("分", 0, 59, 0)
        days = st.slider("數據回溯天數", 1, 90, 7)

        jobs = scheduler.get_jobs()
        enabled = bool(jobs)

        st.write("")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("啟用自動化排程", type="primary", disabled=not auto_keywords):
                scheduler.remove_all_jobs()
                scheduler.add_job(
                    automation_job,
                    trigger="cron",
                    day_of_week=WEEKDAYS.index(weekday),  # 0=Mon
                    hour=int(hour),
                    minute=int(minute),
                    args=[auto_keywords, days],
                    id="weekly_report",
                    replace_existing=True,
                )
                st.success(f"已設定排程：每{weekday} {int(hour):02d}:{int(minute):02d} 自動執行。")
                st.rerun()
        with col_b:
            if st.button("停用自動化排程", type="secondary", disabled=not enabled):
                scheduler.remove_all_jobs()
                st.info("自動化排程已停用。")
                st.rerun()

    st.write("")
    
    with st.container(border=True):
        st.markdown(
            '<h3 style="font-family: \'Inter\', sans-serif; font-size: 0.95rem; letter-spacing: 0.05em; color: #6B7280; margin-bottom: 16px;">手動強制執行</h3>',
            unsafe_allow_html=True
        )
        st.markdown("<p style='color: #6B7280; font-size: 0.9em; margin-bottom: 24px;'>立即於背景執行一次完整的自動化工作流。</p>", unsafe_allow_html=True)
        if st.button("立即執行", type="secondary"):
            with st.spinner("正在執行自動化流程..."):
                automation_job(auto_keywords, days)
            st.success("手動執行測試完畢。")


# ---------------------------------------------------------------------------
# 區塊 E：歷史知識庫
# ---------------------------------------------------------------------------
def render_history_tab():
    st.markdown(
        '<h2 style="font-size: 1.8rem; font-weight: 700; margin-bottom: 20px;">📚 歷史知識庫</h2>',
        unsafe_allow_html=True
    )

    if not db_service.is_configured():
        st.warning("尚未設定 Supabase（SUPABASE_URL / SUPABASE_KEY），歷史功能不可用。")
        return

    col1, col2 = st.columns([1, 3])
    with col1:
        history_days = st.slider("查詢近幾天", 1, 90, 30)

    with st.container(border=True):
        st.markdown(
            '<h3 style="font-size: 1.1rem; font-weight: 600; margin-bottom: 15px; color: #EC4899;">關鍵字觀看趨勢</h3>',
            unsafe_allow_html=True
        )
        hist_df = db_service.get_history(days=history_days)
        if hist_df.empty:
            st.info("目前尚無歷史資料，請先執行抓取。")
        else:
            agg = (
                hist_df.groupby(["fetched_at", "keyword"])["view_count"]
                .sum()
                .reset_index()
            )
            agg["fetched_at"] = agg["fetched_at"].dt.date
            agg = agg.groupby(["fetched_at", "keyword"])["view_count"].sum().reset_index()
            fig = px.line(
                agg, x="fetched_at", y="view_count", color="keyword",
                labels={"fetched_at": "日期", "view_count": "總觀看數", "keyword": "關鍵字"},
                color_discrete_sequence=["#EC4899", "#2563EB", "#8B5CF6", "#10B981", "#F59E0B"],
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(30,41,59,0.4)",
                plot_bgcolor="rgba(0,0,0,0)",
                font={"family": "Figtree, Noto Sans, sans-serif"},
                margin={"t": 20, "b": 30, "l": 40, "r": 20},
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"共 {len(hist_df)} 筆歷史紀錄")

    st.write("")
    with st.container(border=True):
        st.markdown(
            '<h3 style="font-size: 1.1rem; font-weight: 600; margin-bottom: 15px; color: #EC4899;">歷史報告</h3>',
            unsafe_allow_html=True
        )
        reports = db_service.get_reports(limit=20)
        if not reports:
            st.info("尚無報告記錄。")
        else:
            for r in reports:
                ts = r.get("generated_at", "")[:16].replace("T", " ")
                kw = r.get("keywords", "")
                label = f"{ts}　{kw}"
                with st.expander(label):
                    st.markdown(r.get("content", ""))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    # 注入 Custom CSS
    inject_custom_css()
    
    # 頂部 Hero Banner (Clinical Elegance)
    hero_html = """
    <div style="border-bottom: 1px solid #EBEBEB; padding-bottom: 24px; margin-bottom: 32px; margin-top: 12px;">
        <h1 style="margin: 0; font-size: clamp(1.8rem, 5vw, 3rem); font-weight: 500; font-family: 'Playfair Display', serif; color: #1A1A1A; line-height: 1.1;">
            醫美情報與 AI 分析
        </h1>
        <p style="margin: 12px 0 0 0; color: #6B7280; font-family: 'Inter', sans-serif; font-size: clamp(0.85rem, 2.5vw, 1rem); font-weight: 400; max-width: 600px; line-height: 1.6;">
            專為醫美產業打造的精準市場情報與 AI 分析系統。追蹤 YouTube Shorts 趨勢，並無縫推送洞察報告。
        </p>
    </div>
    """
    st.markdown(hero_html, unsafe_allow_html=True)
    
    render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs(
        ["市場情報採集", "AI 深度洞察", "自動化排程", "歷史知識庫"]
    )
    with tab1:
        render_scraper_tab()
    with tab2:
        render_report_tab()
    with tab3:
        render_automation_tab()
    with tab4:
        render_history_tab()


if __name__ == "__main__":
    main()
