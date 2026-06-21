# 跨平台社群資料整合規格書 v2 (YouTube + Apify 混合方案)
## 適用對象：Claude Code (系統架構/總指揮) & Codex (API/爬蟲實作)

本文件定義如何將原本單一的 YouTube Shorts 儀表板，升級為支援 **YouTube, Instagram, Facebook, 以及 Threads** 的通用型社群熱門內容儀表板。

---

## 1. 系統架構與資料路由 (Data Routing)

因為我們採用了混合資料源（官方 API + 爬蟲 API），後端架構必須具備「請求路由（Router）」的能力。

```text
[使用者輸入關鍵字 & 選擇平台] 
       │
       ▼
[Backend: 資料路由中樞 (Data Router)]
       ├── (若包含 YouTube) ──> [YouTube Data API v3]
       ├── (若包含 IG) ───────> [Apify: Instagram Actor]
       ├── (若包含 FB) ───────> [Apify: Facebook Actor]
       └── (若包含 Threads) ──> [Apify: Threads Actor]
                                       │
[標準化資料模型 (UniversalContentModel)] <──(資料清洗與正規化)
       │
       ▼
[Frontend: 通用儀表板 UI] (由 Claude Code 負責動態渲染)
```

---

## 2. 資料獲取策略與 API/Actor 配置

### A. YouTube (保留官方 API)
* **策略：** 使用原本的 YouTube Data API v3。
* **重點：** 確保搜尋參數加上 `videoDuration=short` 來精準抓取 Shorts。

### B. Instagram & Facebook (Apify 方案)
* **Instagram Actor:** `apify/instagram-scraper` (透過 hashtag 或關鍵字)。
* **Facebook Actor:** `apify/facebook-videos-scraper` (指定 `videoType: shorts`)。

### C. Threads (Apify 新增方案)
* **建議 Actor:** `apify/threads-scraper` 或社群高頻使用的 Threads 爬蟲。
* **重點特性：** Threads 偏向圖文與短影音混合。抓取時需特別注意解析 `text` (內文) 與 `attachments` (媒體附件，可能是圖片或影片)。
* **輸入參數範例 (JSON):**
    ```json
    {
      "searchQueries": ["關鍵字"],
      "resultsLimit": 50,
      "proxy": { "useApifyProxy": true }
    }
    ```

---

## 3. 介面協議：升級版通用資料模型 (Schema)

由於加入了 Threads（可能沒有標題、且可能為純圖文），我們的資料模型需要升級，使其包容性更強。**Codex 必須將四個平台的差異化 JSON，轉為以下標準格式：**

```typescript
export interface UniversalContentModel {
  id: string;               // 唯一識別碼 (Platform_ID)
  platform: 'youtube' | 'instagram' | 'facebook' | 'threads'; 
  authorName: string;       // 創作者/帳號名稱 (Threads 必備)
  title: string | null;     // 影片標題 (Threads 可能為 null)
  content: string;          // 完整內文/描述 (Threads 主要文字內容)
  url: string;              // 貼文/影片原始連結
  mediaUrls: string[];      // 媒體資源陣列 (影片 URL 或 圖片 URL，支援 Threads 多圖)
  thumbnail: string | null; // 預覽圖 URL
  metrics: {
    views: number | null;   // 觀看次數 (Threads 可能抓不到準確觀看數)
    likes: number;          // 按讚數
    comments: number;       // 評論數
    reposts: number | null; // 轉發數 (針對 Threads/FB)
  };
  publishedAt: string;      // ISO 8601 時間字串
  fetchedKeyword: string;   // 觸發此抓取的關鍵字
}
```

---

## 4. Agent 開發分工更新指引

### 🥷 Codex 任務：API 路由與多源對接 (`feature/multi-platform-integration`)
1.  **實作 API Router：** 撰寫一個 Facade 或 Controller，根據前端傳來的平台陣列（例如 `['youtube', 'threads']`），**平行發送 (Promise.all)** 請求到 YouTube API 和 Apify Service。
2.  **Threads Apify 實作：** 新增 Threads 的 Apify 呼叫邏輯。
3.  **Data Transformer 升級：** 確保四種不同來源的資料，都能穩健地 Map 到 `UniversalContentModel`。特別注意處理 Threads 可能缺少的 `title` 和 `views` 欄位（給予 `null` 或預設值，不能報錯）。

### 🧑‍💻 Claude Code 任務：前端包容性重構 (`feature/core-refactor`)
1.  **UI 支援圖文排版：** 原本的儀表板可能只針對「直式短影音」設計。現在需擴充卡片組件 (Card Component)：
    * 若是 YT/IG/FB：顯示直立縮圖與播放按鈕。
    * 若是 Threads：排版需類似 Twitter/X，以大字體的 `content` 為主，下方搭配縮圖網格 (`mediaUrls`)。
2.  **搜尋過濾器 (Filter) 更新：** 新增 Threads 選項，並在前端實作統一的排序邏輯（例如：如果以「觀看數」排序，Threads 貼文若無觀看數則應置底或依按讚數遞補）。
3.  **總代理 Review：** 審查 Codex 提交的 API Router PR，確保 `UniversalContentModel` 的型別在整個專案中被嚴格遵守。
