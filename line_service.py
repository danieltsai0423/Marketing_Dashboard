"""LINE 推播服務：把報告以 Broadcast Message 發送到 LINE OA 所有追蹤者。

使用 line-bot-sdk v3。LINE 單則文字訊息上限 5000 字，
且單次 broadcast 最多 5 則訊息，因此長報告會自動分段。
"""

from __future__ import annotations

import logging
import os
import re

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    BroadcastRequest,
    TextMessage,
)
from linebot.v3.messaging.exceptions import ApiException

logger = logging.getLogger("line_service")

# LINE 單則文字訊息字數上限（保守抓 4900）。
LINE_TEXT_LIMIT = 4900
# 單次 broadcast 最多訊息則數。
LINE_MAX_MESSAGES = 5


class LineServiceError(Exception):
    """LINE 服務相關錯誤。"""


def _convert_table(match: re.Match) -> str:
    """把 Markdown 表格轉成條列式文字。"""
    lines = [l.strip() for l in match.group(0).strip().splitlines()]
    # 第一行是標題列，第二行是分隔線（跳過）
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        parts = [f"{headers[i]}：{cells[i]}" for i in range(min(len(headers), len(cells)))]
        rows.append("  • " + "｜".join(parts))
    return "\n".join(rows)


def _markdown_to_line(text: str) -> str:
    """把 Markdown 轉成 LINE 易讀的純文字格式。"""
    # Markdown 表格 → 條列式
    table_pattern = re.compile(
        r"(\|.+\|\n\|[-| :]+\|\n(?:\|.+\|\n?)+)", re.MULTILINE
    )
    text = table_pattern.sub(_convert_table, text)
    # H1 → 標題加框線
    text = re.sub(r"^# (.+)$", r"📊 \1\n" + "─" * 20, text, flags=re.MULTILINE)
    # H2 → 粗體區塊標題
    text = re.sub(r"^## (.+)$", r"\n▌ \1", text, flags=re.MULTILINE)
    # H3 → 小標題
    text = re.sub(r"^### (.+)$", r"\n◆ \1", text, flags=re.MULTILINE)
    # 粗體 **text** → 全形【text】
    text = re.sub(r"\*\*(.+?)\*\*", r"【\1】", text)
    # 斜體 *text* → 保留原文
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # 水平線
    text = re.sub(r"^---+$", "─" * 20, text, flags=re.MULTILINE)
    # 移除反引號
    text = re.sub(r"`(.+?)`", r"\1", text)
    # 條列符號 - / * 開頭 → 縮排純文字（去掉符號）
    text = re.sub(r"^[ \t]*[-*] (.+)$", r"  \1", text, flags=re.MULTILINE)
    # 多餘空行壓縮
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_text(text: str, limit: int = LINE_TEXT_LIMIT) -> list[str]:
    """依字數上限分段，盡量在換行處切，避免切斷句子。"""
    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks


def push_report(
    report: str,
    access_token: str | None = None,
    **_kwargs,
) -> int:
    """把報告 Broadcast 到 LINE OA 所有追蹤者。

    Args:
        report: 要發送的文字。
        access_token: Channel access token；省略時讀 .env 的 LINE_CHANNEL_ACCESS_TOKEN。

    Returns:
        實際發送的訊息則數。

    Raises:
        LineServiceError: 缺金鑰、分段超過上限或 API 失敗。
    """
    access_token = access_token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        raise LineServiceError("缺少 LINE_CHANNEL_ACCESS_TOKEN。")

    report = _markdown_to_line(report)
    chunks = _split_text(report)
    if len(chunks) > LINE_MAX_MESSAGES:
        logger.warning("報告過長（%d 段），將截斷為 %d 則。", len(chunks), LINE_MAX_MESSAGES)
        head = chunks[: LINE_MAX_MESSAGES - 1]
        tail = "（報告過長，後續內容已截斷，請至儀表板查看完整版）"
        chunks = head + [tail]

    messages = [TextMessage(text=c) for c in chunks]

    configuration = Configuration(access_token=access_token)
    try:
        with ApiClient(configuration) as api_client:
            api = MessagingApi(api_client)
            api.broadcast(BroadcastRequest(messages=messages))
    except ApiException as exc:
        logger.error("LINE broadcast 失敗：status=%s body=%s", exc.status, exc.body)
        raise LineServiceError(f"LINE API 錯誤 {exc.status}: {exc.body}") from exc
    except Exception as exc:
        logger.error("LINE broadcast 失敗：%s", exc)
        raise LineServiceError(str(exc)) from exc

    logger.info("已 broadcast %d 則訊息至 OA 所有追蹤者", len(messages))
    return len(messages)


if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.INFO)

    test_msg = "【測試推播】跨平台社群情報系統 LINE OA Broadcast 測試 ✅"
    try:
        n = push_report(test_msg)
        print(f"成功 broadcast {n} 則訊息。")
    except LineServiceError as e:
        print(f"[錯誤] {e}")
        raise SystemExit(1)
