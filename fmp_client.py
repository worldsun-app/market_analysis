import requests
import logging
from typing import Optional, Dict
import os
import pandas as pd
from collections import Counter
from pathlib import Path
from datetime import datetime, date, timedelta
from generate import summarize_company_news

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

class FMPClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("FMP API key is required.")
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com"

    def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if not data:
                logger.warning(f"No data found for endpoint {url} with params {params}")
                return None
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching from {url}: {e}")
            return None
    
    def get_sp500(self):
        endpoint = "api/v3/sp500_constituent"
        sp500_data = self._request(endpoint)
        return sp500_data
    
    def get_stock_inf(self, symbol: str):
        endpoint = f"api/v3/quote/{symbol}"
        price_data = self._request(endpoint)
        price = price_data[0]['price']
        change_rate = price_data[0]['changesPercentage']
        return price, change_rate
    
    def get_treasury_rates(self):
        excel_file = BASE_DIR / "resource/treasury.xlsx"
        endpoint = "stable/treasury-rates"
        treasury_data = self._request(endpoint)
        new_data = treasury_data[0]
        new_df = pd.DataFrame([new_data])
        new_df['date'] = pd.to_datetime(new_df['date'])
        try:
            old_df = pd.read_excel(excel_file)
            old_df['date'] = pd.to_datetime(old_df['date'])
            combined_df = pd.concat([old_df, new_df])
        except Exception as e:
            logger.warning(f"Could not read existing treasury data: {e}")
            combined_df = new_df
        
        combined_df = combined_df.drop_duplicates(subset=['date'], keep='first')
        combined_df = combined_df.sort_values('date', ascending=False).reset_index(drop=True)

        try:
            output_df = combined_df.copy()
            output_df['date'] = output_df['date'].dt.strftime('%Y-%m-%d')
            output_df.to_excel(excel_file, index=False)
        except Exception as e:
            logger.error(f"Error saving treasury data to Excel: {e}")

        def get_val(row_idx, col_name):
            if row_idx < len(combined_df):
                val = combined_df.at[row_idx, col_name]
                if pd.isna(val):
                    return "N/A"
                return val
            return get_val
        
        idx_current = 0
        idx_prev = 1
        idx_5d = 5
        idx_lm = 21
        if not combined_df.empty:
            current_date = combined_df.iloc[0]['date']
            found = False
            for days_back in range(30, 0, -1):
                target_date = current_date - pd.Timedelta(days=days_back)
                matches = combined_df.index[combined_df['date'] == target_date].tolist()
                if matches:
                    idx_lm = matches[0]
                    found = True
                    break

        result = {
            "US 2Y": {
                "current": get_val(idx_current, 'year2'),
                "prev": get_val(idx_prev, 'year2'),
                "5d": get_val(idx_5d, 'year2'),
                "lm": get_val(idx_lm, 'year2'),
            },
            "US 10Y": {
                "current": get_val(idx_current, 'year10'),
                "prev": get_val(idx_prev, 'year10'),
                "5d": get_val(idx_5d, 'year10'),
                "lm": get_val(idx_lm, 'year10'),
            },
            "US 30Y": {
                "current": get_val(idx_current, 'year30'),
                "prev": get_val(idx_prev, 'year30'),
                "5d": get_val(idx_5d, 'year30'),
                "lm": get_val(idx_lm, 'year30'),
            },
        }
        return result

    def get_biggest_change_sp500_stock(self):
        endpoint = "api/v3/quote-short"
        try:
            sp500_df = pd.read_excel(BASE_DIR / "resource/sp500_stock.xlsx")
            if 'Symbol' in sp500_df.columns:
                sp500_symbols = sp500_df['Symbol'].astype(str).tolist()
            else:
                sp500_symbols = sp500_df.iloc[:, 0].astype(str).tolist()
            all_quotes = []
            
            for i in range(0, len(sp500_symbols), 500):
                chunk = sp500_symbols[i:i + 500]
                symbols_string = ",".join(chunk)
                batch_endpoint = f"api/v3/quote/{symbols_string}"
                data = self._request(batch_endpoint)
                if data:
                    all_quotes.extend(data)
            if not all_quotes:
                return []
            valid_quotes = [q for q in all_quotes if q.get('changesPercentage') is not None]
            sorted_quotes = sorted(valid_quotes, key=lambda x: x['changesPercentage'], reverse=True)
            top_6 = sorted_quotes[:6]
            bottom_6 = sorted_quotes[-6:]
            result_list = []
            
            for item in top_6:
                result_list.append({
                    'symbol': item.get('symbol'),
                    'changesPercentage': item.get('changesPercentage'),
                    'price': item.get('price'),
                    'type': 'Top Gainer'
                })
                
            for item in bottom_6:
                result_list.append({
                    'symbol': item.get('symbol'),
                    'changesPercentage': item.get('changesPercentage'),
                    'price': item.get('price'),
                    'type': 'Top Loser'
                })
                
            return result_list

        except Exception as e:
            logger.error(f"Error processing S&P 500 stock data: {e}")
            return []

    def get_most_news_symbols(self):
        endpoint = "stable/news/stock-latest"
        news_data = self._request(endpoint)
        symbols = [news.get('symbol') for news in news_data if news.get('symbol') and news.get('symbol') != 'null']
        count = Counter(symbols)
        top_3_symbols = [symbol for symbol, num in count.most_common(3)]
        return top_3_symbols
    
    def get_symbol_news(self, symbols: list[str]):
        today = date.today()
        yesterday = today - timedelta(days=1)
        results = {}
        
        endpoint = "api/v3/stock_news"
        
        for symbol in symbols:
            params = {'symbols': symbol}
            news_data = self._request(endpoint, params=params)
            
            symbol_news_items = []
            if news_data:
                for news in news_data:
                    pub_date_str = news.get('publishedDate')
                    if not pub_date_str:
                        continue
                        
                    try:
                        pub_datetime = datetime.strptime(pub_date_str, "%Y-%m-%d %H:%M:%S")
                        pub_date = pub_datetime.date()
                        
                        if pub_date >= yesterday:
                            symbol_news_items.append({
                                'title': news.get('title'),
                                'text': news.get('text'),
                                'publishedDate': pub_date_str,
                            })
                    except (ValueError, TypeError):
                        continue
            
            summary = summarize_company_news(symbol, symbol_news_items)
            results[symbol] = summary
            
        return results

    def get_sp500_change_news(self, symbols: list[str]):
        today = date.today()
        befor_yesterday = today - timedelta(days=2)
        results = {}
        
        endpoint = "stable/news/stock"
        for symbol in symbols:
            params = {'symbols': symbol}
            news_data = self._request(endpoint, params=params)
            
            symbol_news_items = []
            if news_data:
                for news in news_data:
                    pub_date_str = news.get('publishedDate')
                    if not pub_date_str:
                        continue
                        
                    try:
                        pub_datetime = datetime.strptime(pub_date_str, "%Y-%m-%d %H:%M:%S")
                        pub_date = pub_datetime.date()
                        
                        if pub_date >= befor_yesterday:
                            symbol_news_items.append({
                                'title': news.get('title'),
                                'text': news.get('text'),
                                'publishedDate': pub_date_str,
                            })
                    except (ValueError, TypeError):
                        continue
            
            summary = summarize_company_news(symbol, symbol_news_items)
            results[symbol] = summary
            
        return results
