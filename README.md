# 🇺🇸 美股市場自動化分析系統 (U.S. Market Analysis Automation)

這是一個自動化的美股市場分析與報告生成工具。它整合了多個數據來源與 AI 模型，每天自動生成市場回顧、可視化報告，並推送到 Telegram 頻道。

## ✨ 主要功能

1.  **多源數據獲取**：
    *   **Financial Modeling Prep (FMP)**：獲取即時股價、指數、板塊表現、債券利率 (2Y/10Y/30Y) 及個股新聞。
    *   **Web Scraping (Playwright)**：自動抓取每日市場回顧 (Market Recap) 文章。
2.  **AI 智能分析**：
    *   使用 **Google Gemini API** (Gemini 2.0 Flash) 針對市場數據、新聞與文章進行摘要與趨勢分析。
3.  **自動化報告生成**：
    *   **Telegram 圖片報告**：將數據填入 HTML 版型，利用 Playwright 自動截圖成高品質圖表，分段發送至 Telegram。
    *   **Email / Blog 草稿 (Ghost)**：(可選) 生成適合 Email 行銷的 HTML 格式，並透過 API 自動在 Ghost Blog 建立草稿。
4.  **排程執行**：
    *   支援單次執行或每日定時 (06:00) 自動運作。
5.  **雲端友善**：
    *   支援雲端部署 (如 Zeabur)，自動處理暫存檔案與路徑問題。

## 🛠️ 安裝與設定

### 1. 環境需求
*   Python 3.10+
*   Google Chrome / Chromium (Playwright 用)

### 2. 安裝依賴套件
```bash
pip install -r requirements.txt
playwright install chromium
```
*(若無 requirements.txt，主要套件包括：`google-genai`, `playwright`, `python-dotenv`, `requests`, `pandas`, `openpyxl`, `python-telegram-bot`, `pyjwt`, `beautifulsoup4`)*

### 3. 設定環境變數 (.env)
請在專案根目錄建立 `.env` 檔案，並填入以下資訊：

```ini
# Google Gemini AI
GEMINI_API_KEY=your_gemini_api_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Financial Modeling Prep (FMP)
FMP_API_KEY=your_fmp_api_key

# Ghost Blog (Optional)
API_URL=https://your-blog.ghost.io
ADMIN_API=your_ghost_admin_api_key
```

## 🚀 使用方法

### 單次執行 (手動觸發)
執行一次完整的流程，適合測試或手動生成報告。
```bash
python main.py
```

### 排程模式 (Daemon)
程式會持續運行，並在每天早上 06:00 自動執行任務。
```bash
python main.py --schedule
```

## 📂 專案結構

*   `main.py`: 程式主入口，負責流程控制與排程。
*   `fmp_client.py`: 負責與 FMP API 互動，獲取金融數據。
*   `scraper.py`: 使用 Playwright 爬取市場回顧文章。
*   `generate.py`: 封裝 Google Gemini API，負責生成文本摘要與報告內容。
*   `ghost_client.py`: Ghost Blog API 客戶端。
*   `prompts/`: 存放 Prompt 模板與 HTML 版型。
    *   `US_market_analysis.txt`: AI 分析用的 Prompt。
    *   `tg_template.html`: Telegram 圖片報告用的 HTML 版型。
    *   `email_template.html`: Email / Blog 用的 HTML 版型。
*   `resource/`: 存放靜態資源 (如債券歷史數據 Excel)。

## ⚠️ 注意事項
*   **雲端部署**：程式已優化路徑處理 (使用 `BASE_DIR`) 與暫存檔案 (`tempfile`)，可直接部署於 Zeabur 等平台。
*   **字型**：HTML 截圖依賴系統字型，若在 Linux 容器中執行，中文可能需要安裝對應字型檔 (如 `fonts-noto-cjk`)。

---
Developed for automated financial insights.
