# 跨平台社群內容情報儀表板

**繁體中文** | [English](./README.en.md)

> 整合 **YouTube、Instagram、Facebook、Threads** 的熱門短影音／貼文，正規化為統一資料模型，透過 LLM 自動生成市場分析報告，並可推播至 LINE —— 一個本地部署的 Streamlit 應用。

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white">
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white">
  <img alt="Tests" src="https://img.shields.io/badge/tests-24%20passing-brightgreen">
  <img alt="i18n" src="https://img.shields.io/badge/i18n-繁中%20%2F%20EN-blue">
</p>

---

## 專案概述

一套本地部署的社群內容市場情報系統。使用者輸入關鍵字並勾選平台後，系統會**平行**從四個社群平台抓取表現最佳的貼文／影片，將格式迥異的回應正規化為統一的 `UniversalContentModel`，再透過 LLM Agent 產出可執行的繁體中文市場分析報告，並支援每週自動化排程與 LINE 推播。

本儀表板原為單一平台的 YouTube Shorts 監測工具，後重構為**通用型、跨平台**架構，可套用於任何內容領域（美食、旅遊、健身、美妝……）。

## 功能特色

- **四平台、混合資料源** —— YouTube 走官方 Data API v3；Instagram／Facebook／Threads 走 Apify Actor。
- **統一資料模型** —— 跨平台共用單一 schema（`UniversalContentModel`），並保留向後相容欄位別名，讓 UI、報告與儲存層與任一資料源解耦。
- **平行請求路由** —— 資料路由中樞以 `ThreadPoolExecutor` 同時對選定平台發送請求；單一平台失敗會被隔離並回報，不會中斷整體。
- **包容性 UI 元件** —— 影片平台以直式縮圖呈現，Threads 以類 X 的大字圖文卡片呈現；統一排序會處理「無觀看數」內容（置底／以按讚數遞補）。
- **雙語介面** —— 預設繁體中文，可於側邊欄即時切換英文。
- **AI 報告** —— 透過 OpenRouter（OpenAI 相容）串流輸出 Markdown 報告（趨勢摘要、爆款解析、選題建議、風險提醒）。
- **自動化與推播** —— `APScheduler` 每週排程 + LINE 廣播。
- **優雅降級** —— 未設定 Supabase 時自動退回本地 JSONL／Markdown 落地；缺少金鑰會於側邊欄顯示狀態而不影響其他功能。

## 系統架構

```
[ 關鍵字 & 平台選擇 ]
              │
              ▼
[ 資料路由中樞 ] ── ThreadPoolExecutor（平行 fan-out）
      ├── YouTube   ─► YouTube Data API v3
      ├── Instagram ─► Apify instagram-scraper
      ├── Facebook  ─► Apify facebook-videos-scraper
      └── Threads   ─► Apify threads-scraper
              │
              ▼
[ UniversalContentModel ] ◄── 跨平台清洗與正規化
              │
              ▼
[ Streamlit UI ]  /  [ LLM 報告 Agent ]  /  [ LINE 推播 ]  /  [ Supabase 知識庫 ]
```

## 技術棧

`Python` · `Streamlit` · `pandas` · `Plotly` · `YouTube Data API v3` · `Apify` · `OpenRouter (LLM)` · `APScheduler` · `Supabase` · `pytest`

## 快速開始

### 環境需求

- 建議 Python 3.12 或 3.13（建議使用 virtualenv）。
- 欲使用之服務的 API 金鑰（見[環境變數](#環境變數)）。

### 安裝

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 設定

```bash
cp .env.example .env             # 接著填入你的金鑰
```

### 執行

```bash
streamlit run app.py
```

開啟後位於 `http://localhost:8501`。

> 提醒：介面、分頁、語言切換與卡片版型在沒有任何金鑰時即可完整瀏覽；實際抓取資料才需要下列對應金鑰。

## 環境變數

複製 `.env.example` 為 `.env` 並依需求填入：

| 變數 | 用途 | 必填於 |
| --- | --- | --- |
| `YOUTUBE_API_KEY` | YouTube Data API v3 | YouTube 抓取 |
| `APIFY_API_TOKEN` | Apify Actor | Instagram／Facebook／Threads 抓取 |
| `APIFY_*_ACTOR` | 覆寫 Actor id | 可選（已有合理預設） |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | LLM 報告生成 | AI 報告 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API | LINE 推播（可選） |
| `SUPABASE_URL` / `SUPABASE_KEY` | 歷史知識庫 | 可選（退回本地 JSONL） |

`.env` 已被 gitignore，不會進版控。

## 專案結構

```
app.py              # Streamlit UI：分頁、i18n、卡片、圖表、排程
data_router.py      # 跨平台平行路由 → UniversalContentModel
content_model.py    # UniversalContentModel 與解析輔助
youtube_service.py  # YouTube Data API v3（兩階段抓取、Shorts 篩選）
apify_service.py    # IG / FB / Threads 的 Apify Actor + 防禦式轉換
llm_agent.py        # DataFrame → prompt → 串流 Markdown 報告（OpenRouter）
line_service.py     # LINE 廣播（5000 字分段）
db_service.py       # Supabase 持久化 + 本地 JSONL／Markdown 落地
keywords.csv        # 預設關鍵字清單（可編輯）
tests/              # pytest 測試套件（單元 + Streamlit AppTest）
```

## 測試

```bash
pip install -r requirements-dev.txt
pytest
```

24 項測試涵蓋資料模型、Apify 轉換、路由排序與錯誤隔離、LLM prompt 組裝，以及端到端的 Streamlit `AppTest` 冒煙測試（雙語渲染 + 跨平台卡片渲染）。關鍵迴歸（英文模式重複 widget id、`NaN` 標題處理、無觀看數排序）皆由測試鎖定。

## 注意事項

- Apify Actor 的 input schema 為防禦式預設；尤其 Facebook 關鍵字搜尋路徑可能需依你實際使用的 Actor 調整。
- LLM 報告無論 UI 語言為何，皆以繁體中文產出。
