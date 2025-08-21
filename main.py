# main.py (V6: 整合 API 日誌儀表板功能)
import os
import requests
import feedparser
import logging
import json
import time
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from deep_translator import GoogleTranslator
import google.generativeai as genai

# --- 設定 ---
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
LOG_DATABASE_ID = os.getenv('LOG_DATABASE_ID') # NEW: 新增日誌資料庫 ID
MAX_ENTRIES_PER_RUN = int(os.getenv('MAX_ENTRIES_PER_RUN', '100'))

# ... (RSS_FEEDS, logging, NOTION_API_URL, HEADERS 的設定維持不變)
RSS_FEEDS = {
    "Bloomberg": "https://www.bloomberg.com/opinion/authors/ARbTQlRLRjE/matthew-s-levine.rss", "Hacker News": "https://news.ycombinator.com/rss", "TechCrunch": "https://techcrunch.com/feed/", "Harvard Business Review": "https://hbr.org/rss/regular",
}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
NOTION_API_URL = "https://api.notion.com/v1/"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28",
}

# --- 核心函式 ---

# MODIFIED: AI 分析函式現在會回傳 token 使用量
def analyze_article_with_ai(title: str, summary: str) -> tuple[dict, int]:
    """使用 Google Gemini API 分析文章，並回傳分析結果與 token 用量"""
    if not GOOGLE_API_KEY:
        logging.warning("⚠️ 未設定 GOOGLE_API_KEY，跳過 AI 分析功能。")
        return {}, 0

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = f"""
        你是一位頂尖的商業與科技分析師。請簡潔地閱讀以下文章的標題與摘要，並嚴格按照下面的 JSON 格式回傳分析結果。
        你的回傳必須是一個可被直接解析的 JSON 物件，不要包含任何額外的解釋或 Markdown 語法。
        JSON 格式範本如下:
        {{
          "summary": "一個包含 3 個重點的繁體中文條列式摘要",
          "keywords": ["核心關鍵字1", "核心關鍵字2"],
          "sentiment": "正面 | 負面 | 中性",
          "entities": ["提及的公司或人物1"]
        }}
        ---
        文章標題: "{title}"
        文章摘要: "{summary}"
        ---
        """
        logging.info(f"  🤖 正在發送至 Google AI (Gemini) 進行分析: {title}")
        response = model.generate_content(prompt)
        
        # 取得 token 用量
        token_usage = response.usage_metadata.total_token_count
        
        cleaned_json_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        analysis_result = json.loads(cleaned_json_text)
        logging.info(f"  ✅ AI 分析完成 (使用 {token_usage} tokens)。")
        return analysis_result, token_usage
    except Exception as e:
        logging.error(f"  🛑 AI 分析失敗: {title} | 錯誤: {e}")
        return {}, 0

# NEW: 全新的日誌寫入函式
def write_log_to_notion(log_data: dict):
    """將單次運行的日誌寫入指定的 Notion 資料庫"""
    if not LOG_DATABASE_ID:
        logging.warning("⚠️ 未設定 LOG_DATABASE_ID，跳過寫入日誌。")
        return

    page_title = f"API Log: {log_data['source_name']} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    payload = {
        "parent": {"database_id": LOG_DATABASE_ID},
        "properties": {
            # **請確保這裡的屬性名稱與您 Notion 日誌資料庫中的完全一致**
            "新頁面": {"title": [{"text": {"content": page_title}}]},
            "新聞來源": {"select": {"name": log_data["source_name"]}},
            "成功分析數": {"number": log_data["success_count"]},
            "Gemini Tokens": {"number": log_data["gemini_tokens"]},
            "代理服務 (次)": {"number": log_data["api_calls"]}
        }
    }
    
    try:
        response = requests.post(f"{NOTION_API_URL}pages", headers=HEADERS, json=payload)
        response.raise_for_status()
        logging.info(f"📋 成功寫入日誌到 Notion: {log_data['source_name']}")
    except requests.exceptions.RequestException as e:
        logging.error(f"🛑 寫入日誌到 Notion 失敗 | 錯誤: {e.response.text}")

# ... (其他函式維持不變)
def calculate_reading_time(text: str) -> int:
    if not text: return 0
    return max(1, round(len(text) / 300))

def check_env_vars():
    if not NOTION_TOKEN or not DATABASE_ID: return False
    return True

def get_existing_urls_from_notion():
    existing_urls = set()
    query_url, has_more, next_cursor = f"{NOTION_API_URL}databases/{DATABASE_ID}/query", True, None
    while has_more:
        payload = {"start_cursor": next_cursor} if next_cursor else {}
        try:
            response = requests.post(query_url, headers=HEADERS, json=payload)
            response.raise_for_status()
            data = response.json()
            for page in data.get("results", []):
                url_prop = page.get("properties", {}).get("URL", {})
                if url_prop.get("url"): existing_urls.add(url_prop["url"])
            has_more, next_cursor = data.get("has_more", False), data.get("next_cursor")
        except requests.exceptions.RequestException: return existing_urls
    logging.info(f"✅ 成功從主資料庫取得 {len(existing_urls)} 筆已存在的 URL")
    return existing_urls

def add_entry_to_notion(source: str, entry: dict, analysis: dict, reading_time: int):
    # 此函式內容完全不變
    create_page_url = f"{NOTION_API_URL}pages"
    title, link = entry.get("title", "無標題"), entry.get("link", "")
    published_dt = date_parser.parse(entry.get("published", datetime.now(timezone.utc).isoformat()))
    try: translated_title = GoogleTranslator(source='auto', target='zh-TW').translate(title)
    except Exception: translated_title = title
    payload = {"parent": {"database_id": DATABASE_ID}, "properties": {
            "標題": {"title": [{"text": {"content": title}}]}, "中文標題": {"rich_text": [{"text": {"content": translated_title}}]}, "URL": {"url": link}, "來源": {"select": {"name": source}}, "發布時間": {"date": {"start": published_dt.isoformat()}}, "AI 摘要": {"rich_text": [{"text": {"content": analysis.get("summary", "N/A")}}]}, "關鍵字": {"multi_select": [{"name": kw} for kw in analysis.get("keywords", [])]}, "閱讀時間(分)": {"number": reading_time}, "情緒": {"select": {"name": analysis.get("sentiment", "N/A")} if analysis.get("sentiment") else None}, "提及實體": {"multi_select": [{"name": entity} for entity in analysis.get("entities", [])]}
        }}
    try:
        response = requests.post(create_page_url, headers=HEADERS, json=payload)
        response.raise_for_status()
        logging.info(f"✅ 成功新增並分析文章: {title}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"🛑 新增文章失敗: {title} | 錯誤: {e.response.text}")
        return False

# --- MODIFIED: 主函式邏輯重構以支援分來源日誌記錄 ---
def main():
    logging.info(f"🚀 開始執行 RSS to Notion 腳本 (含日誌記錄)...")
    if not check_env_vars(): return
    
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    existing_urls = get_existing_urls_from_notion()
    total_new_entries_count = 0

    # MODIFIED: 現在是逐一處理每個來源，並在處理完畢後寫入日誌
    for source_name, feed_url in RSS_FEEDS.items():
        logging.info(f"--- 開始處理來源: {source_name} ---")
        
        # 初始化當前來源的日誌數據
        log_data = {
            "source_name": source_name, "success_count": 0, "gemini_tokens": 0, "api_calls": 0
        }

        # 收集當前來源的新文章
        source_new_entries = []
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            if entry.link in existing_urls: continue
            published_dt = date_parser.parse(entry.get("published", datetime.now(timezone.utc).isoformat()))
            if published_dt.tzinfo is None: published_dt = published_dt.replace(tzinfo=timezone.utc)
            if published_dt >= thirty_days_ago:
                entry.published_datetime = published_dt
                source_new_entries.append(entry)
        
        logging.info(f"🔍 來源 {source_name} 找到 {len(source_new_entries)} 筆新文章。")
        source_new_entries.sort(key=lambda e: e.published_datetime, reverse=True)

        # 處理當前來源的新文章
        for entry in source_new_entries:
            if total_new_entries_count >= MAX_ENTRIES_PER_RUN:
                logging.info(f"🏁 已達到單次運行總上限 ({MAX_ENTRIES_PER_RUN} 筆)，停止處理此來源。")
                break
            
            content_to_analyze = entry.get("summary", "")
            reading_time = calculate_reading_time(content_to_analyze)
            
            analysis_results, tokens_used = analyze_article_with_ai(entry.get("title", ""), content_to_analyze)
            log_data["api_calls"] += 1
            log_data["gemini_tokens"] += tokens_used

            logging.info(f"✍️ 正在寫入文章: {entry.title}")
            if add_entry_to_notion(source_name, entry, analysis_results, reading_time):
                log_data["success_count"] += 1
                total_new_entries_count += 1
                existing_urls.add(entry.link)
            
            logging.info("--- 休息 2 秒 ---")
            time.sleep(2)
        
        # 處理完一個來源後，如果進行了任何 API 呼叫，就寫入日誌
        if log_data["api_calls"] > 0:
            write_log_to_notion(log_data)
        
        logging.info(f"--- 來源 {source_name} 處理完畢 ---")

    logging.info(f"🎉 任務完成！本次共新增 {total_new_entries_count} 筆新文章。")

if __name__ == "__main__":
    main()
