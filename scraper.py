from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

async def get_market_recap_content() -> str:
    url = "https://www.edwardjones.com/us-en/market-news-insights/stock-market-news/daily-market-recap"
    content = ""
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            selector = ".rich-text.relative"
            try:
                await page.wait_for_selector(selector, timeout=10000)
            except Exception:
                logger.warning(f"Selector {selector} not found on page.")
                await browser.close()
                return ""
            elements = await page.query_selector_all(selector)
            
            full_text = []
            for element in elements:
                text = await element.inner_text()
                if text.strip():
                   full_text.append(text)
            
            content = "\n\n".join(full_text)
            
            await browser.close()
            
    except Exception as e:
        logger.error(f"Error scraping market recap: {e}")
        return ""

    return content
