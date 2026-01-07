import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3-flash-preview"

def summarize_company_news(symbol: str, news_items: list[dict]) -> str:
    if not news_items:
        return "無相關新聞資料。"

    combined_text = ""
    for item in news_items:
        title = item.get('title', 'No Title')
        text = item.get('text', 'No Content')
        combined_text += f"Title: {title}\nContent: {text}\n---\n"

    prompt = f"""
    你是一位專業的金融分析師。請閱讀以下關於 {symbol} 的新聞內容，並將其整理統整。
    請用「繁體中文」寫出總結，用 1 到 2 句話概括這間公司的新聞大部分都在說什麼 (例如：財報表現優異、推出了新產品、面臨法律訴訟等)。
    請注意，請不要包含任何自我介紹以及提到"該新聞"等文字的內容，僅輸出對該公司的總結。

    新聞內容集合：
    {combined_text}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return f"生成總結時發生錯誤: {e}"

def summarize_market_recap(recap_content: str) -> list[dict]:
    if not recap_content:
        return []

    prompt = f"""
    你是一位專業的金融分析師。請閱讀以下「每日市場回顧」的原文內容。
    請找出其中的重點（通常原文會有類似標題或強調的部分），並將每個重點轉化為一項結構化數據。
    請注意，請不要包含任何自我介紹以及提到"該新聞"等文字的內容，僅輸出對該公司的總結。
    
    **輸出格式要求**：
    請輸出一個 JSON 格式的列表 (List of Dicts)，不要有 markdown code block，直接輸出 JSON 字串即可，格式如下：
    [
        {{
            "topic": "重點標題 (例如：股市表現、能源板塊、債券市場等)",
            "summary": "開頭寫出公司全名，用 3 到 4 句繁體中文總結這個重點的內容。"
        }},
        ...
    ]

    原文內容：
    {recap_content}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        import json
        return json.loads(response.text)
    except Exception as e:
        print(f"生成市場回顧總結時發生錯誤: {e}")
        return []
