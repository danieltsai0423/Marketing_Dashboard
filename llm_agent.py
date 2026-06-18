"""LLM Agent：把 YouTube Shorts 數據轉成醫美市場情報報告。

統一走 OpenRouter（OpenAI 相容介面），用 openai SDK：
  - base_url = OPENROUTER_BASE_URL
  - api_key  = OPENROUTER_API_KEY
  - model    = OPENROUTER_MODEL

提供兩種呼叫：
  - generate_report()        一次回傳完整 Markdown 報告。
  - stream_report()          產生器，逐段 yield 文字，供 UI 打字機效果。
"""

from __future__ import annotations

import logging
import os
import uuid

import pandas as pd
from openai import OpenAI

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("llm_agent")

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
# 每個關鍵字最多取幾支送進 Prompt，避免某單一關鍵字佔滿樣本。
TOP_PER_KEYWORD = 5
# 送進 Prompt 的影片總筆數上限（分層後再截）。
MAX_ROWS_IN_PROMPT = 25

SYSTEM_PROMPT = (
    "你是專精『醫美 / 美容診所』的短影音市場分析師，"
    "服務對象是台灣診所行銷團隊。"
    "分析時聚焦台灣繁體中文受眾市場，簡體中文或中國市場的影片僅供參考，不要特別強調。"
    "請用繁體中文、條理清晰的 Markdown 輸出，數據導向、可執行。"
    "【重要格式規定】禁止使用 Markdown 表格（| 欄位 | 格式），"
    "所有數據一律改用條列式清單（- 或數字序號）呈現。"
)


class LLMAgentError(Exception):
    """LLM Agent 相關錯誤。"""


def _get_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    base_url = base_url or os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)
    if not api_key:
        raise LLMAgentError(
            "缺少 OPENROUTER_API_KEY，請在 .env 設定或以參數傳入。"
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def _select_samples(df: pd.DataFrame, top_per_kw: int = TOP_PER_KEYWORD, max_total: int = MAX_ROWS_IN_PROMPT) -> pd.DataFrame:
    """分層抽樣：每個關鍵字取觀看數 top N，再全體截到 max_total。"""
    if "keyword" not in df.columns:
        return df.sort_values("view_count", ascending=False).head(max_total)
    frames = [
        grp.sort_values("view_count", ascending=False).head(top_per_kw)
        for _, grp in df.groupby("keyword")
    ]
    sampled = pd.concat(frames).sort_values("view_count", ascending=False)
    return sampled.head(max_total)


def _dataframe_to_context(df: pd.DataFrame) -> str:
    """把 DataFrame 摘要成餵給 LLM 的文字脈絡。"""
    if df is None or df.empty:
        return "（沒有任何影片資料）"

    cols = [c for c in ["keyword", "title", "channel", "view_count",
                        "like_count", "duration_sec", "published_at", "url"]
            if c in df.columns]
    selected = _select_samples(df)

    lines = []
    # 各關鍵字觀看數加總概況
    if "keyword" in df.columns:
        agg = (
            df.groupby("keyword")["view_count"]
            .agg(["count", "sum"])
            .sort_values("sum", ascending=False)
        )
        lines.append("## 各關鍵字概況（影片數 / 總觀看數）")
        for kw, row in agg.iterrows():
            lines.append(f"- {kw}：{int(row['count'])} 支，總觀看 {int(row['sum']):,}")
        lines.append("")

    lines.append(f"## 精選影片樣本（共 {len(selected)} 筆，每關鍵字 top {TOP_PER_KEYWORD}，依觀看數排序）")
    for _, r in selected[cols].iterrows():
        parts = []
        if "keyword" in cols:
            parts.append(f"[{r['keyword']}]")
        parts.append(str(r.get("title", "")))
        parts.append(f"觀看 {int(r.get('view_count', 0)):,}")
        if "like_count" in cols:
            parts.append(f"讚 {int(r.get('like_count', 0)):,}")
        if "duration_sec" in cols:
            parts.append(f"{int(r.get('duration_sec', 0))}s")
        if "channel" in cols:
            parts.append(f"頻道:{r.get('channel', '')}")
        if "url" in cols:
            parts.append(f"url:{r.get('url', '')}")
        lines.append("- " + " | ".join(parts))

    return "\n".join(lines)


def _build_messages(df: pd.DataFrame, extra_instruction: str | None = None) -> list[dict]:
    context = _dataframe_to_context(df)
    user_prompt = f"""以下是過去一段期間，醫美相關關鍵字在 YouTube Shorts 的數據：

{context}

請產出一份「醫美短影音市場情報報告」，結構如下：

# 醫美短影音市場情報報告

## 一、本期趨勢摘要
（3-5 點，點出哪些主題/關鍵字最熱、整體聲量觀察）

## 二、爆款影片解析
（挑 3-5 支高觀看影片，分析它們的標題鉤子、題材、為何會紅；每支影片末尾必須附上影片連結，格式為「🔗 影片連結」，連結從數據中的 url 欄位取得）

## 三、診所選題建議
（給 5-8 個可直接執行的短影音選題方向，附一句切角說明，聚焦台灣市場受眾）

## 四、風險與注意事項
（醫美廣告法規、誇大療效用語等需避免的點）
"""
    if extra_instruction:
        user_prompt += f"\n額外要求：{extra_instruction}\n"

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def generate_report(
    df: pd.DataFrame,
    model: str | None = None,
    extra_instruction: str | None = None,
    api_key: str | None = None,
) -> tuple[str, str]:
    """一次產生完整 Markdown 報告。

    Returns:
        (report_content, run_id) — 報告內文與本次執行 UUID。
    """
    client = _get_client(api_key)
    model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
    messages = _build_messages(df, extra_instruction)
    run_id = str(uuid.uuid4())
    logger.info("呼叫 LLM（model=%s, run_id=%s）產生報告...", model, run_id)
    try:
        resp = client.chat.completions.create(model=model, messages=messages)
    except Exception as exc:
        logger.error("LLM 呼叫失敗：%s", exc)
        raise LLMAgentError(str(exc)) from exc
    return resp.choices[0].message.content or "", run_id


def stream_report(
    df: pd.DataFrame,
    model: str | None = None,
    extra_instruction: str | None = None,
    api_key: str | None = None,
):
    """串流產生報告，逐段 yield 文字（供 Streamlit 打字機效果）。"""
    client = _get_client(api_key)
    model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
    messages = _build_messages(df, extra_instruction)
    logger.info("呼叫 LLM（model=%s）串流產生報告...", model)
    try:
        stream = client.chat.completions.create(
            model=model, messages=messages, stream=True
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as exc:
        logger.error("LLM 串流失敗：%s", exc)
        raise LLMAgentError(str(exc)) from exc


if __name__ == "__main__":
    # 用真實抓取資料實測：python llm_agent.py
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.INFO)

    from youtube_service import fetch_shorts

    print("抓取測試資料（線雕/音波拉提/電波拉皮，過去 30 天）...")
    df = fetch_shorts(["線雕", "音波拉提", "電波拉皮"], days=30)
    print(f"抓到 {len(df)} 支 Shorts，開始產生報告...\n")

    try:
        report = generate_report(df)
    except LLMAgentError as e:
        print(f"\n[錯誤] {e}")
        raise SystemExit(1)

    print(report)
