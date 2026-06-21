from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("db_service")

DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")
CONTENT_JSONL = DATA_DIR / "content_runs.jsonl"


def _get_secret(key: str) -> str | None:
    try:
        import streamlit as st

        return st.secrets.get(key) or os.getenv(key)
    except Exception:
        return os.getenv(key)


def is_configured() -> bool:
    return bool(_get_secret("SUPABASE_URL") and _get_secret("SUPABASE_KEY"))


def _get_client():
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY.")
    from supabase import create_client

    return create_client(url, key)


def _json_safe(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.isna(value) if not isinstance(value, (list, dict, tuple, set)) else False:
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def _records(df: pd.DataFrame, run_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in df.assign(run_id=run_id).to_dict(orient="records"):
        records.append({key: _json_safe(value) for key, value in record.items()})
    return records


def _legacy_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "video_id": record.get("video_id") or record.get("id"),
        "keyword": record.get("keyword") or record.get("fetchedKeyword"),
        "title": record.get("title") or record.get("content"),
        "channel": record.get("channel") or record.get("authorName") or record.get("author_name"),
        "published_at": record.get("published_at") or record.get("publishedAt"),
        "duration_sec": record.get("duration_sec"),
        "view_count": record.get("view_count") or record.get("metrics_views") or 0,
        "like_count": record.get("like_count") or record.get("metrics_likes") or 0,
        "comment_count": record.get("comment_count") or record.get("metrics_comments") or 0,
        "url": record.get("url"),
        "run_id": record.get("run_id"),
    }


def _save_content_jsonl(records: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with CONTENT_JSONL.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def upsert_shorts(df: pd.DataFrame, run_id: str) -> int:
    if df.empty:
        return 0

    records = _records(df, run_id)
    try:
        _save_content_jsonl(records)
    except Exception as exc:
        logger.error("Local content JSONL save failed: %s", exc)

    if not is_configured():
        return len(records)

    legacy_records = [_legacy_record(record) for record in records]
    try:
        client = _get_client()
        client.table("shorts").upsert(legacy_records, on_conflict="video_id").execute()
        logger.info("upserted %d content rows to Supabase shorts", len(legacy_records))
        return len(legacy_records)
    except Exception as exc:
        logger.error("upsert_shorts failed: %s", exc)
        return 0


def save_report(run_id: str, keywords: list[str], model: str, content: str) -> bool:
    kw_str = ", ".join(keywords)
    now = datetime.now(timezone(timedelta(hours=8)))
    ok = False

    if is_configured():
        try:
            client = _get_client()
            client.table("reports").insert(
                {
                    "run_id": run_id,
                    "keywords": kw_str,
                    "model": model,
                    "content": content,
                }
            ).execute()
            ok = True
        except Exception as exc:
            logger.error("Supabase report save failed: %s", exc)

    try:
        REPORTS_DIR.mkdir(exist_ok=True)
        filename = now.strftime("%Y-%m-%d_%H-%M") + ".md"
        markdown = (
            f"---\n"
            f"run_id: {run_id}\n"
            f"generated_at: {now.isoformat()}\n"
            f"keywords: [{kw_str}]\n"
            f"model: {model}\n"
            f"---\n\n"
            f"{content}"
        )
        (REPORTS_DIR / filename).write_text(markdown, encoding="utf-8")
    except Exception as exc:
        logger.error("Local report save failed: %s", exc)

    return ok


def get_history(days: int = 30) -> pd.DataFrame:
    if not is_configured():
        return pd.DataFrame()
    try:
        client = _get_client()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        response = (
            client.table("shorts")
            .select("keyword,view_count,like_count,comment_count,fetched_at,title,url,channel,duration_sec")
            .gte("fetched_at", since)
            .order("fetched_at", desc=True)
            .limit(2000)
            .execute()
        )
        df = pd.DataFrame(response.data)
        if not df.empty:
            df["fetched_at"] = pd.to_datetime(df["fetched_at"])
            df["view_count"] = pd.to_numeric(df["view_count"], errors="coerce").fillna(0).astype(int)
        return df
    except Exception as exc:
        logger.error("get_history failed: %s", exc)
        return pd.DataFrame()


def get_reports(limit: int = 20) -> list[dict]:
    if not is_configured():
        return []
    try:
        client = _get_client()
        response = (
            client.table("reports")
            .select("id,run_id,generated_at,keywords,model,content")
            .order("generated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        logger.error("get_reports failed: %s", exc)
        return []
