# main.py (V5: 最終優化版 - 加入延遲以符合 API 頻率限制)
import os
import requests
import feedparser
import logging
import json
import time # NEW: 引入 time 函式庫
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from deep_translator import GoogleTranslator
import google.generativeai as genai

# ... (所有設定和除了 main 以外的函式都維持不變，此處省略以保持簡潔)
# --- 設定 ---
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
MAX_ENTRIES_PER_RUN = int(os.getenv('MAX_ENTRIES_PER_RUN', '50'))

RSS_FEEDS = {
    "Harvard Business Review": "https://hbr.org/rss/regular",
    "Bloomberg": "https://www.bloomberg.com/opinion/authors/ARbTQlRLRjE/matthew-s-levine.rss",
    "TechCrunch": "https://techcrunch.com/feed/",
    
}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
NOTION_API_URL = "https://api.notion.com/v1/"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28",
}

# --- 核心函式 ---
def analyze_article_with_ai(title: str, summary: str) -> dict:
    if not GOOGLE_API_KEY:
        logging.warning("⚠️ 未設定 GOOGLE_API_KEY，跳過 AI 分析功能。")
        return {}
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
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
        cleaned_json_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        analysis_result = json.loads(cleaned_json_text)
        logging.info("  ✅ AI 分析完成。")
        return analysis_result
    except Exception as e:
        logging.error(f"  🛑 AI 分析失敗: {title} | 錯誤: {e}")
        return {}
        
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
    logging.info(f"✅ 成功從 Notion 取得全部分頁，共 {len(existing_urls)} 筆已存在的 URL")
    return existing_urls

def add_entry_to_notion(source: str, entry: dict, analysis: dict, reading_time: int):
    # 此函式內容完全不變
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

# --- MODIFIED: 主函式加入了 time.sleep() ---
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
                entry.source_name, entry.published_datetime = source_name, published_dt
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
        
        # NEW: 在處理完一筆文章後，不論成功失敗，都休息 2 秒鐘
        logging.info("--- 休息 2 秒，避免觸及 API 頻率上限 ---")
        time.sleep(2)

    logging.info(f"🎉 任務完成！本次共新增 {new_entries_count} 筆新文章。")

if __name__ == "__main__":
    main()
