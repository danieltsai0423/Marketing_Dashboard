"""Supabase 持久化服務：影片數據與報告的存取層。

本機讀 .env，Streamlit Cloud 讀 st.secrets，介面統一。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("db_service")

REPORTS_DIR = Path("reports")


def _get_client():
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL 或 SUPABASE_KEY，請設定 .env 或 Streamlit Secrets。")
    from supabase import create_client
    return create_client(url, key)


def _get_secret(key: str) -> str | None:
    """優先從 Streamlit secrets 讀，fallback 到環境變數。"""
    try:
        import streamlit as st
        return st.secrets.get(key) or os.getenv(key)
    except Exception:
        return os.getenv(key)


def is_configured() -> bool:
    """回傳 Supabase 是否已設定（供 UI 顯示狀態用）。"""
    return bool(_get_secret("SUPABASE_URL") and _get_secret("SUPABASE_KEY"))


def upsert_shorts(df: pd.DataFrame, run_id: str) -> int:
    """將 DataFrame upsert 到 Supabase shorts table，依 video_id 去重。

    Returns:
        成功寫入的筆數。
    """
    if df.empty:
        return 0
    try:
        client = _get_client()
        records = df.assign(run_id=run_id).to_dict(orient="records")
        # 確保欄位型態可序列化
        for r in records:
            for k, v in r.items():
                if hasattr(v, "item"):  # numpy scalar
                    r[k] = v.item()
        client.table("shorts").upsert(records, on_conflict="video_id").execute()
        logger.info("upsert %d 筆到 Supabase shorts", len(records))
        return len(records)
    except Exception as exc:
        logger.error("upsert_shorts 失敗：%s", exc)
        return 0


def save_report(run_id: str, keywords: list[str], model: str, content: str) -> bool:
    """存報告到 Supabase reports table，並在本機寫入 Markdown 檔。

    Returns:
        True 表示 Supabase 寫入成功。
    """
    kw_str = "、".join(keywords)
    now = datetime.now(timezone(timedelta(hours=8)))  # Asia/Taipei

    # 寫入 Supabase
    ok = False
    try:
        client = _get_client()
        client.table("reports").insert({
            "run_id": run_id,
            "keywords": kw_str,
            "model": model,
            "content": content,
        }).execute()
        logger.info("報告已存入 Supabase reports（run_id=%s）", run_id)
        ok = True
    except Exception as exc:
        logger.error("save_report Supabase 失敗：%s", exc)

    # 本機 Markdown 備份（Obsidian 相容）
    try:
        REPORTS_DIR.mkdir(exist_ok=True)
        fname = now.strftime("%Y-%m-%d_%H-%M") + ".md"
        md = (
            f"---\n"
            f"run_id: {run_id}\n"
            f"generated_at: {now.isoformat()}\n"
            f"keywords: [{kw_str}]\n"
            f"model: {model}\n"
            f"---\n\n"
            f"{content}"
        )
        (REPORTS_DIR / fname).write_text(md, encoding="utf-8")
        logger.info("報告已存至本機 reports/%s", fname)
    except Exception as exc:
        logger.error("save_report 本機備份失敗：%s", exc)

    return ok


def get_history(days: int = 30) -> pd.DataFrame:
    """查詢過去 N 天的歷史 shorts 資料。"""
    try:
        client = _get_client()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (
            client.table("shorts")
            .select("keyword,view_count,like_count,fetched_at,title,url,channel,duration_sec")
            .gte("fetched_at", since)
            .order("fetched_at", desc=True)
            .limit(2000)
            .execute()
        )
        df = pd.DataFrame(resp.data)
        if not df.empty:
            df["fetched_at"] = pd.to_datetime(df["fetched_at"])
            df["view_count"] = pd.to_numeric(df["view_count"], errors="coerce").fillna(0).astype(int)
        return df
    except Exception as exc:
        logger.error("get_history 失敗：%s", exc)
        return pd.DataFrame()


def get_reports(limit: int = 20) -> list[dict]:
    """取得歷史報告清單（時間倒序）。"""
    try:
        client = _get_client()
        resp = (
            client.table("reports")
            .select("id,run_id,generated_at,keywords,model,content")
            .order("generated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.error("get_reports 失敗：%s", exc)
        return []
