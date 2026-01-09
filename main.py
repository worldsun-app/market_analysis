import os
import asyncio
import datetime
import argparse
import time
import tempfile
import shutil
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from playwright.async_api import async_playwright
from telegram import Bot
import json

from fmp_client import FMPClient
from scraper import get_market_recap_content
from generate import summarize_market_recap
from ghost_client import GhostClient

# 取得專案根目錄 (確保在任何位置執行都能以此為基準)
BASE_DIR = Path(__file__).resolve().parent

# 載入環境變數
load_dotenv(BASE_DIR / ".env")

# 設定 API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.getenv("FMP_API_KEY")

# 引入 FMP Client
fmp_client = FMPClient(api_key=FMP_API_KEY)

# 市場指數與商品對照表
MARKET_SYMBOLS = {
    "S&P 500": "^GSPC",
    "Dow Jones": "^DJI",
    "NASDAQ": "^IXIC",
    "Russell 2000": "^RUT",
    "VIX": "^VIX",
    "Gold": "xauusd"
}
SECTOR_ETF_MAP = {
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Technology": "XLK",
    "Utilities": "XLU"
}

# 設定 Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)
grounding_tool = types.Tool(
    google_search=types.GoogleSearch()
)

config = types.GenerateContentConfig(
    tools=[grounding_tool]
)

# 使用使用者指定的模型
MODEL_NAME = "gemini-3-flash-preview"

def fetch_market_data():
    """獲取 FMP 市場數據"""
    print("[*] 開始從 FMP 獲取市場數據...")
    market_data_lines = []
    
    # 1. 獲取市場指數
    print("   - 正在獲取主要指數...")
    for name, symbol in MARKET_SYMBOLS.items():
        try:
            price, change = fmp_client.get_stock_inf(symbol)
            market_data_lines.append(f"{name}: Price {price}, Change {change}%")
        except Exception as e:
            print(f"   [!] 無法獲取 {name} ({symbol}): {e}")
            market_data_lines.append(f"{name}: N/A")

    # 2. 獲取板塊 ETF
    print("   - 正在獲取板塊 ETF...")
    sector_results = []
    for name, symbol in SECTOR_ETF_MAP.items():
        try:
            price, change = fmp_client.get_stock_inf(symbol)
            sector_results.append({'name': name, 'symbol': symbol, 'price': price, 'change': change})
        except Exception as e:
            print(f"   [!] 無法獲取 {name} ({symbol}): {e}")
    
    if sector_results:
        sector_results.sort(key=lambda x: x['change'], reverse=True)

        selected_sectors = []
        if len(sector_results) <= 6:
            selected_sectors = sector_results
        else:
            top_3 = [x for x in sector_results if x['change'] > 0][:3]
            bottom_3 = [x for x in sector_results if x['change'] < 0][:3]
            selected_sectors = top_3 + bottom_3
            
        for s in selected_sectors:
            market_data_lines.append(f"{s['name']}: Price {s['price']}, Change {s['change']}%")

    market_data_str = "\n".join(market_data_lines)
    
    # 3. 獲取債券利率
    print("   - 正在獲取債券利率...")
    try:
        treasury_result = fmp_client.get_treasury_rates()
    except Exception as e:
        print(f"   [!] 無法獲取債券利率: {e}")
        treasury_result = {}

    print("[+] FMP 數據獲取完成")

    return market_data_str, treasury_result

async def analyze_market(target_date, market_data_str, treasury_result, output_dir=None):
    """第一步：取得市場分析數據"""
    prompt_path = BASE_DIR / "prompts/US_market_analysis.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"找不到 {prompt_path}")
    
    base_prompt = prompt_path.read_text(encoding="utf-8")
    final_prompt = base_prompt.replace("使用者輸入日期 ( 如 2025 / 12 / 01 ) ", target_date)
    
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=final_prompt,
        config=config
    )
    
    report_text = response.text
    if output_dir:
        report_file = output_dir / f"market_report_{target_date.replace('/', '').replace(' ', '')}.md"
        report_file.write_text(report_text, encoding="utf-8")

    return report_text

async def generate_html(target_date, market_data, output_dir):
    template_path = BASE_DIR / "prompts/tg_template.html"
    if not template_path.exists():
        raise FileNotFoundError(f"找不到 {template_path}")
    
    html_template = template_path.read_text(encoding="utf-8")
    
    # 建立生成 HTML 的指令
    generation_prompt = f"""
你是一位專業的前端工程師與金融設計師。
請根據提供的「市場數據」填入隨附的「HTML版型」中，生成一份完整的市場分析報告（繁體中文）。

### 任務要求：
1. **嚴格遵守版型**：請勿更改 HTML 的 CSS 樣式、結構、class 名稱。
2. **數據準確性**：將報告中的指數數值、漲跌幅、新聞內容填入對應的模塊。
(針對「最大變動個股」與「板塊」區域，請務必根據提供的資料數量，動態生成對應數量的 HTML 卡片或行 (例如：如果有 6 支上漲股，就必須生成 6 個 .mover-card))
3. **動態判斷**：
   - **顏色規則**：針對所有漲跌幅、變動率或利率變動數值 (包含指數、債券、板塊、個股)：
     - **數值 > 0**：必須使用 `text-green` class，並搭配向上箭頭 `<i class="fa-solid fa-caret-up"></i>`，卡片背景/邊框若有相關設定請設為 `up` 或 `bg-green-soft`。
     - **數值 < 0**：必須使用 `text-red` class，並搭配向下箭頭 `<i class="fa-solid fa-caret-down"></i>`，卡片背景/邊框若有相關設定請設為 `down` 或 `bg-red-soft`。
     - **數值 = 0**：維持中性色。
4. **日期更新**：將版型中的日期更新為 {target_date}。
5. **僅輸出 HTML**：不要輸出任何解釋文字，僅輸出完整的 <html>...</html> 程式碼。

### [數據來源]

**1. 市場指數與板塊數據 (Indices & Sectors):**
{market_data.get('market_data_str', 'N/A')}

**2. 債券利率 (Treasury Rates):**
{market_data.get('treasury_result', 'N/A')}

**3. 市場回顧重點 (Market Recap):**
{json.dumps(market_data.get('recap_summary', []), indent=2, ensure_ascii=False)}

**4. 最大變動個股 (Biggest Movers):**
{json.dumps(market_data.get('biggest_change_sp500_stock', []), indent=2, ensure_ascii=False)}

**5. 個股新聞總結 (Symbol News Summaries):**
{json.dumps(market_data.get('symbol_news_summary', {}), indent=2, ensure_ascii=False)}

### [HTML 原始版型]
{html_template}
"""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=generation_prompt
        )
        html_content = response.text.strip()
        if html_content.startswith("```html"):
            html_content = html_content[7:]
        if html_content.endswith("```"):
            html_content = html_content[:-3]
        html_content = html_content.strip()

        html_file = output_dir / f"market_report_{target_date.replace('/', '').replace(' ', '')}.html"
        html_file.write_text(html_content, encoding="utf-8")
        return html_file
    except Exception as e:
        print(f"[!] 生成 HTML 時發生錯誤: {e}")
        raise

async def convert_to_images(html_file_path):
    """第三步：將 HTML 轉換為兩張 PNG 圖片 (Part 1 & Part 2)"""
    image_paths = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(device_scale_factor=3)
        abs_path = f"file:///{html_file_path.absolute()}"
        
        await page.set_viewport_size({"width": 1000, "height": 2000}) # Height increased just in case
        await page.goto(abs_path, wait_until="networkidle", timeout=120000)
        
        content_locator = page.locator(".infographic-container")
        await page.evaluate("""
            () => {
                document.querySelector('.section:nth-of-type(4)').style.display = 'none';
                document.querySelector('.section:nth-of-type(5)').style.display = 'none';
                document.querySelector('.section:nth-of-type(6)').style.display = 'none';
                document.querySelector('.footer').style.display = 'none';
            }
        """)
        
        part1_path = html_file_path.with_name(f"{html_file_path.stem}_part1.png")
        await content_locator.screenshot(path=str(part1_path))
        image_paths.append(part1_path)
        print(f"[+] 截圖完成 Part 1: {part1_path.name}")

        await page.evaluate("""
            () => {
                // Show clean slate (reset) or just toggle
                document.querySelector('.section:nth-of-type(4)').style.display = 'block';
                document.querySelector('.section:nth-of-type(5)').style.display = 'block';
                document.querySelector('.section:nth-of-type(6)').style.display = 'block';
                document.querySelector('.footer').style.display = 'block';

                // Hide Part 1 elements
                document.querySelector('.header').style.display = 'none';
                document.querySelector('.section:nth-of-type(1)').style.display = 'none';
                document.querySelector('.section:nth-of-type(2)').style.display = 'none';
                document.querySelector('.section:nth-of-type(3)').style.display = 'none';
            }
        """)

        part2_path = html_file_path.with_name(f"{html_file_path.stem}_part2.png")
        await content_locator.screenshot(path=str(part2_path))
        image_paths.append(part2_path)
        print(f"[+] 截圖完成 Part 2: {part2_path.name}")
        
        await browser.close()
        
    return image_paths

async def send_to_telegram(image_paths, html_path):
    """第四步：發送 圖片(多張) 和 HTML 到 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] 錯誤：未設定 Telegram Token 或 Chat ID，略過發送步驟。")
        return
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    async with bot:
        # 發送圖片 (Loop)
        for i, img_path in enumerate(image_paths):
            caption = f"📊 美股日報 Part {i+1}"
            with open(img_path, 'rb') as f:
                await bot.send_photo(
                    chat_id=TELEGRAM_CHAT_ID, 
                    photo=f, 
                    caption=caption,
                    read_timeout=60, 
                    write_timeout=60, 
                    connect_timeout=60
                )
            print(f"[+] 圖片已發送: {img_path.name}")
        
        # # 發送 HTML (維持 send_document)
        # with open(html_path, 'rb') as f:
        #     await bot.send_document(
        #         chat_id=TELEGRAM_CHAT_ID, 
        #         document=f, 
        #         caption=f"{html_path.name}",
        #         read_timeout=60, 
        #         write_timeout=60, 
        #         connect_timeout=60
        #     )
        # print(f"[+] HTML 已發送: {html_path.name}")

async def generate_email_html(target_date, market_data, output_dir=None):
    """第二步(B)：將數據填入 Email 版型 (Table Layout)"""
    print("[*] 執行 Step 2B: 生成 Email HTML (Ghost)...")
    
    template_path = BASE_DIR / "prompts/email_template.html"
    if not template_path.exists():
        print(f"[!] 找不到 {template_path}，跳過 Ghost 生成。")
        return None
    
    html_template = template_path.read_text(encoding="utf-8")
    
    generation_prompt = f"""
你是一位專業的 Email 行銷人員與前端工程師。
請將下方的市場數據填入「Email HTML 版型」中。

### 任務要求：
1.  **Email 相容性**：這個版型使用 Table 排版以相容各類信箱，**請勿更改結構** (如 `<table>`, `<tr>`, `<td>`)，僅在註解標示處填入內容或複製 `<tr>` 行。
2.  **內容填入**：
    *   **主要指數**：填入 `.indices-table` 中。請複製 `<tr>` 來增加指數項目，每一個 `<tr>` 代表一個指數行。
        - 格式：`<tr>` 內含三個 `<td>`，務必加入 `width` 與 `style` 以確保對齊：
          1. **指數名稱**：(靠左) `<td width="50%" style="width: 50%; padding: 12px 10px; color: #555; text-align: left;"><strong class="index-name" style="font-size: 14px;">指數名稱</strong></td>`
          2. **數值**：(靠右) `<td width="25%" style="width: 25%; padding: 12px 10px; text-align: right; font-size: 14px;">數值</td>`
          3. **漲跌幅**：(靠右) `<td width="25%" style="width: 25%; padding: 12px 10px; text-align: right; font-weight: bold; font-size: 14px;">漲跌幅</td>` (請依照漲跌變色)
          - **注意**：`<tr>` 請加上 `style="border-bottom: 1px solid #eee;"` 以做分隔。
    *   **板塊**：填入 `.sector-strong` (強勢) 與 `.sector-weak` (弱勢) 表格中。
        - 格式：與主要指數相同，使用 3 欄位 `<tr>`，**務必保持欄位寬度一致**：
          1. **板塊名稱**：`<td width="50%" style="width: 50%; padding: 12px 10px; color: #555; text-align: left; font-size: 14px;">板塊名稱</td>`
          2. **數值**：`<td width="25%" style="width: 25%; padding: 12px 10px; text-align: right; font-size: 14px;">數值</td>`
          3. **漲跌幅**：`<td width="25%" style="width: 25%; padding: 12px 10px; text-align: right; font-weight: bold; font-size: 14px;">漲跌幅</td>`
          - **注意**：`<tr>` 請加上 `style="border-bottom: 1px solid #eee;"` 以做分隔。
    *   **債券**：填入 `.treasury-row` 中，格式完全相同 (50%, 25%, 25%)。
    *   **焦點個股**：填入 `.movers-table` 中。每一個個股是一個 `<tr>`，內含新聞摘要。
    *   **市場回顧**：填入 `.recap-list` 中，使用 `<li>`。
3.  **樣式與顏色**：
    *   **Inline Style**：請務必保持 `style="..."` 屬性。
    *   **顏色**：正數請加入/保留 `color: #00c853;` (綠)，負數請加入/保留 `color: #ff1744;` (紅)。
4.  **僅輸出 HTML**。

### [數據來源]
**1. 指數 & 板塊:**
{market_data.get('market_data_str', 'N/A')}

**2. 債券:**
{market_data.get('treasury_result', 'N/A')}

**3. 市場回顧:**
{json.dumps(market_data.get('recap_summary', []), indent=2, ensure_ascii=False)}

**4. 焦點個股:**
{json.dumps(market_data.get('biggest_change_sp500_stock', []), indent=2, ensure_ascii=False)}

**5. 新聞摘要:**
{json.dumps(market_data.get('symbol_news_summary', {}), indent=2, ensure_ascii=False)}

---
### [Email版型]
{html_template}
"""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=generation_prompt
        )
        html_content = response.text.strip()
        if html_content.startswith("```html"):
            html_content = html_content[7:]
        if html_content.endswith("```"):
            html_content = html_content[:-3]
        html_content = html_content.strip()
        
        if output_dir:
            email_html_path = output_dir / f"email_report_{target_date.replace('/', '').replace(' ', '')}.html"
            email_html_path.write_text(html_content, encoding="utf-8")
            print(f"[+] Step 2B 完成，Email HTML 已存至 {email_html_path}")
        
        return html_content
    except Exception as e:
        print(f"[!] 生成 Email HTML 失敗: {e}")
        return None

async def run_automation(target_date=None):
    if not target_date:
        target_date = datetime.datetime.now().strftime("%Y / %m / %d")
    try:
        # 0. 獲取 FMP 數據
        print("======== [Step 0: Fetching Data] ========")
        market_data_str, treasury_result = fetch_market_data()
        
        print("[*] Fetching biggest movers...")
        biggest_change_sp500_stock = fmp_client.get_biggest_change_sp500_stock()
        
        movers_symbols = [item['symbol'] for item in biggest_change_sp500_stock] if biggest_change_sp500_stock else []
        symbol_news_summary = {}
        if movers_symbols:
            symbol_news_summary = fmp_client.get_sp500_change_news(movers_symbols)
        # print(symbol_news_summary)
        
        print("[*] Scraping Market Recap...")
        recap_content = await get_market_recap_content()
        recap_summary = []
        if recap_content:
            recap_summary = summarize_market_recap(recap_content)
        else:
            print("[!] Market recap scraping failed or empty.")

        # 彙整所有數據
        all_market_data = {
            'market_data_str': market_data_str,
            'treasury_result': treasury_result,
            'biggest_change_sp500_stock': biggest_change_sp500_stock,
            'symbol_news_summary': symbol_news_summary,
            'recap_summary': recap_summary
        }
        print("======== [Data Collection Complete] ========")

        # 1. 使用 tempfile 處理中間產物
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            print(f"[*] 使用暫存目錄: {temp_dir}")

            # (Optional) 這裡可以選擇是否要將 md 存檔，或只是為了 debug
            # await analyze_market(target_date, market_data_str, treasury_result, output_dir=temp_dir)

            # 生成 Telegram 用 HTML (Grid Layout) -> Images (Split)
            tg_html_file = await generate_html(target_date, all_market_data, output_dir=temp_dir)
            image_files = await convert_to_images(tg_html_file)
            await send_to_telegram(image_files, tg_html_file)
            
            # 2. 生成 Ghost 用 HTML (Table Layout) -> Post
            # email_html_content = await generate_email_html(target_date, all_market_data, output_dir=temp_dir)
            
            # if email_html_content:
            #     ghost_url = os.getenv("API_URL")
            #     # ghost_url path is handled in GhostClient
            #     ghost_key = os.getenv("ADMIN_API")
                
            #     if ghost_url and ghost_key:
            #         print(f"[*] 發送至 Ghost (URL: {ghost_url})...")
            #         ghost = GhostClient(ghost_url, ghost_key)
            #         title = f"美國市場收盤報告 {target_date}"
                    
            #         # Create Post (Status='draft')
            #         result = ghost.create_post(
            #             title, 
            #             email_html_content, 
            #             status='draft', 
            #             tags=['Market Report']
            #         )
            #         if result:
            #             print(f"[+] Ghost 文章發布成功: {result.get('posts', [{}])[0].get('title')}")
            #         else:
            #             print("[!] Ghost 文章發布失敗")
            #     else:
            #         print("[!] 未設定 API_URL 或 ADMIN_API，跳過 Ghost 發送。")

        print("\n 全流程執行成功！(暫存檔案已清除)")
        
    except Exception as e:
        print(f"\n[❌] 執行過程中發生錯誤: {e}")
        import traceback
        traceback.print_exc()

async def scheduler():
    """排程模式：每天 06:00 執行"""
    
    while True:
        now = datetime.datetime.now()
        # 設定目標時間為今天的 06:00
        target_time = now.replace(hour=5, minute=55, second=0, microsecond=0)
        
        # 如果現在已經過了 06:00，目標設為明天 06:00
        if now >= target_time:
            target_time += datetime.timedelta(days=1)
            
        wait_seconds = (target_time - now).total_seconds()
        hours = int(wait_seconds // 3600)
        minutes = int((wait_seconds % 3600) // 60)
        
        print(f"\n[*] 目前時間: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[*] 下次執行: {target_time.strftime('%Y-%m-%d %H:%M:%S')} (還有 {hours} 小時 {minutes} 分鐘)")
        
        # 等待直到目標時間
        await asyncio.sleep(wait_seconds)
        
        print(f"\n[⏰] 時間到！開始執行任務: {datetime.datetime.now().strftime('%Y-%m-%d')}")
        await run_automation()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="美股分析自動化機器人")
    parser.add_argument("--schedule", action="store_true", help="啟用排程模式 (每天早上 6:00 執行)")
    args = parser.parse_args()

    try:
        if args.schedule:
            asyncio.run(scheduler())
        else:
            print("[*] 執行單次任務模式...")
            asyncio.run(run_automation())
    except KeyboardInterrupt:
        print("\n[!] 程式已手動停止。 bye bye!")
