# main.py (V4: 全面升級至 Google AI - Gemini)
import os
import requests
import feedparser
import logging
import json
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from deep_translator import GoogleTranslator
import google.generativeai as genai # NEW: 引入 Google AI 函式庫

# --- 設定 ---
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY') # MODIFIED: 讀取 Google API Key
MAX_ENTRIES_PER_RUN = int(os.getenv('MAX_ENTRIES_PER_RUN', '100'))

# ... (RSS_FEEDS, logging, NOTION_API_URL, HEADERS 的設定維持不變)
RSS_FEEDS = {
    "Bloomberg": "https://www.bloomberg.com/opinion/authors/ARbTQlRLRjE/matthew-s-levine.rss",
    "Hacker News": "https://news.ycombinator.com/rss",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Harvard Business Review": "https://hbr.org/rss/regular",
}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
NOTION_API_URL = "https://api.notion.com/v1/"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28",
}

# --- NEW: 全新改寫的 AI 分析函式 (for Gemini) ---
def analyze_article_with_ai(title: str, summary: str) -> dict:
    """使用 Google Gemini API 分析文章，一次取得多項資訊"""
    if not GOOGLE_API_KEY:
        logging.warning("⚠️ 未設定 GOOGLE_API_KEY，跳過 AI 分析功能。")
        return {}

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        # Gemini 1.5 Flash 是速度快、成本效益高的最新模型
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        # 我們的魔法指令
        prompt = f"""
        你是一位頂尖的商業與科技分析師。請簡潔地閱讀以下文章的標題與摘要，並嚴格按照下面的 JSON 格式回傳分析結果。

        你的回傳必須是一個可被直接解析的 JSON 物件，不要包含任何額外的解釋或 Markdown 語法 (例如 ```json ```)。

        JSON 格式範本如下:
        {{
          "summary": "一個包含 3 個重點的繁體中文條列式摘要",
          "keywords": ["核心關鍵字1", "核心關鍵字2", "核心關鍵字3"],
          "sentiment": "正面 | 負面 | 中性",
          "entities": ["提及的公司或人物1", "提及的公司或人物2"]
        }}

        ---
        文章標題: "{title}"
        文章摘要: "{summary}"
        ---
        """

        logging.info(f"  🤖 正在發送至 Google AI (Gemini) 進行分析: {title}")
        response = model.generate_content(prompt)
        
        # 解析 AI 回傳的 JSON 字串
        # Gemini 有時會在回傳的 JSON 前後加上 ```json ... ```，我們需要先清理掉
        cleaned_json_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        analysis_result = json.loads(cleaned_json_text)

        logging.info("  ✅ AI 分析完成。")
        return analysis_result
    except Exception as e:
        logging.error(f"  🛑 AI 分析失敗: {title} | 錯誤: {e}")
        return {} # 即使失敗，也回傳空字典，不中斷主流程

# ... (其他函式維持不變)
def calculate_reading_time(text: str) -> int:
    if not text: return 0
    word_count = len(text)
    reading_minutes = round(word_count / 300)
    return max(1, reading_minutes)

def check_env_vars():
    if not NOTION_TOKEN or not DATABASE_ID:
        logging.error("🚫 缺少環境變數：NOTION_TOKEN 或 NOTION_DATABASE_ID")
        return False
    return True

def get_existing_urls_from_notion():
    existing_urls = set()
    query_url = f"{NOTION_API_URL}databases/{DATABASE_ID}/query"
    has_more, next_cursor = True, None
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
        except requests.exceptions.RequestException as e:
            logging.error(f"🛑 查詢 Notion 資料庫失敗: {e}")
            return existing_urls
    logging.info(f"✅ 成功從 Notion 取得全部分頁，共 {len(existing_urls)} 筆已存在的 URL")
    return existing_urls

def add_entry_to_notion(source: str, entry: dict, analysis: dict, reading_time: int):
    create_page_url = f"{NOTION_API_URL}pages"
    title = entry.get("title", "無標題")
    link = entry.get("link", "")
    published_dt = date_parser.parse(entry.get("published", datetime.now(timezone.utc).isoformat()))
    try:
        translated_title = GoogleTranslator(source='auto', target='zh-TW').translate(title)
    except Exception:
        translated_title = title
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "標題": {"title": [{"text": {"content": title}}]},
            "中文標題": {"rich_text": [{"text": {"content": translated_title}}]},
            "URL": {"url": link},
            "來源": {"select": {"name": source}},
            "發布時間": {"date": {"start": published_dt.isoformat()}},
            "AI 摘要": {"rich_text": [{"text": {"content": analysis.get("summary", "N/A")}}]},
            "關鍵字": {"multi_select": [{"name": kw} for kw in analysis.get("keywords", [])]},
            "閱讀時間(分)": {"number": reading_time},
            "情緒": {"select": {"name": analysis.get("sentiment", "N/A")} if analysis.get("sentiment") else None},
            "提及實體": {"multi_select": [{"name": entity} for entity in analysis.get("entities", [])]}
        }
    }
    try:
        response = requests.post(create_page_url, headers=HEADERS, json=payload)
        response.raise_for_status()
        logging.info(f"✅ 成功新增並分析文章到 Notion: {title}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"🛑 新增文章到 Notion 失敗: {title} | 錯誤: {e.response.text}")
        return False

def main():
    logging.info(f"🚀 開始執行 RSS to Notion 腳本 (AI引擎: Google Gemini)...")
    if not check_env_vars(): return
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    existing_urls = get_existing_urls_from_notion()
    new_entries_count = 0
    all_new_entries = []
    logging.info("--- 階段一: 收集所有來源的近期新文章 ---")
    for source_name, feed_url in RSS_FEEDS.items():
        logging.info(f"📡 正在處理來源: {source_name}")
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            if entry.link in existing_urls: continue
            published_dt = date_parser.parse(entry.get("published", datetime.now(timezone.utc).isoformat()))
            if published_dt.tzinfo is None: published_dt = published_dt.replace(tzinfo=timezone.utc)
            if published_dt >= thirty_days_ago:
                entry.source_name = source_name
                entry.published_datetime = published_dt
                all_new_entries.append(entry)
    logging.info(f"🔍 收集完成，共找到 {len(all_new_entries)} 筆 30 天內的新文章。")
    all_new_entries.sort(key=lambda e: e.published_datetime, reverse=True)
    logging.info(f"--- 階段二: 分析並寫入資料庫 (單次上限: {MAX_ENTRIES_PER_RUN} 筆) ---")
    for entry in all_new_entries:
        if new_entries_count >= MAX_ENTRIES_PER_RUN:
            logging.info(f"🏁 已達到單次執行上限，提前結束任務。")
            break
        content_to_analyze = entry.get("summary", "")
        reading_time = calculate_reading_time(content_to_analyze)
        analysis_results = analyze_article_with_ai(entry.get("title", ""), content_to_analyze)
        logging.info(f"✍️ 正在處理文章: {entry.title}")
        if add_entry_to_notion(entry.source_name, entry, analysis_results, reading_time):
            new_entries_count += 1
            existing_urls.add(entry.link)
    logging.info(f"🎉 任務完成！本次共新增 {new_entries_count} 筆新文章。")

if __name__ == "__main__":
    main()
