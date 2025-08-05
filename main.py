# main.py (包含翻譯功能)
import os
import requests
import feedparser
import logging
from datetime import datetime
from dateutil import parser as date_parser
from deep_translator import GoogleTranslator # NEW: 引入翻譯函式庫

# --- 設定 ---
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

# 您可以自由擴充這個列表
RSS_FEEDS = {
    "Bloomberg": "https://www.bloomberg.com/opinion/authors/ARbTQlRLRjE/matthew-s-levine.rss",
    "SupplyChainDive": "https://www.supplychaindive.com/rss/",
    "CFODive": "https://www.cfodive.com/rss/",
    "Hacker News": "https://news.ycombinator.com/rss",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Harvard Business Review": "https://hbr.org/rss/regular",
    "Wall Street Journal": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

NOTION_API_URL = "https://api.notion.com/v1/"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# --- 核心函式 ---

def check_env_vars():
    if not NOTION_TOKEN or not DATABASE_ID:
        logging.error("🚫 缺少環境變數：NOTION_TOKEN 或 NOTION_DATABASE_ID")
        return False
    return True

def get_existing_urls_from_notion() -> set:
    existing_urls = set()
    query_url = f"{NOTION_API_URL}databases/{DATABASE_ID}/query"
    try:
        response = requests.post(query_url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        for page in data.get("results", []):
            properties = page.get("properties", {})
            url_property = properties.get("URL", {})
            if url_property and url_property.get("url"):
                existing_urls.add(url_property["url"])
        logging.info(f"✅ 成功從 Notion 取得 {len(existing_urls)} 筆已存在的 URL")
        return existing_urls
    except requests.exceptions.RequestException as e:
        logging.error(f"🛑 查詢 Notion 資料庫失敗: {e}")
        return set()

def add_entry_to_notion(source: str, entry: dict):
    create_page_url = f"{NOTION_API_URL}pages"
    
    title = entry.get("title", "無標題")
    link = entry.get("link", "")
    published_str = entry.get("published", datetime.now().isoformat())
    published_dt = date_parser.parse(published_str)

    # NEW: 翻譯標題
    translated_title = ""
    try:
        # 將英文標題翻譯成繁體中文
        translated_title = GoogleTranslator(source='auto', target='zh-TW').translate(title)
        logging.info(f"  翻譯成功: '{title}' -> '{translated_title}'")
    except Exception as e:
        # 如果翻譯失敗，就使用原標題，並記錄警告
        logging.warning(f"  ⚠️ 翻譯失敗: {title} | 錯誤: {e}")
        translated_title = title # 翻譯失敗時，中文標題欄位就填入原文

    # MODIFIED: 更新 Payload，加入新的 "中文標題" 屬性
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "標題": { # 原本的標題欄位 (Title 類型)
                "title": [{"text": {"content": title}}]
            },
            "中文標題": { # 新增的中文標題欄位 (Text 類型)
                "rich_text": [{"text": {"content": translated_title}}]
            },
            "URL": {
                "url": link
            },
            "來源": {
                "select": {"name": source}
            },
            "發布時間": {
                "date": {"start": published_dt.isoformat()}
            }
        }
    }

    try:
        response = requests.post(create_page_url, headers=HEADERS, json=payload)
        response.raise_for_status()
        logging.info(f"✅ 成功新增文章到 Notion: {title}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"🛑 新增文章到 Notion 失敗: {title} | 錯誤: {e.response.text}")
        return False

def main():
    logging.info("🚀 開始執行 RSS to Notion 腳本 (含翻譯功能)...")
    if not check_env_vars():
        return
    existing_urls = get_existing_urls_from_notion()
    new_entries_count = 0
    for source_name, feed_url in RSS_FEEDS.items():
        logging.info(f"📡 正在處理來源: {source_name} ({feed_url})")
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            logging.warning(f"⚠️ 解析來源 {source_name} 時可能發生問題: {feed.bozo_exception}")
        entries = feed.entries
        logging.info(f"🔍 從 {source_name} 取得 {len(entries)} 筆資料")
        for entry in entries:
            if entry.link not in existing_urls:
                if add_entry_to_notion(source_name, entry):
                    new_entries_count += 1
                    existing_urls.add(entry.link)
            else:
                logging.info(f"🔄 跳過已存在文章: {entry.title}")
    logging.info(f"🎉 任務完成！本次共新增 {new_entries_count} 筆新文章。")

if __name__ == "__main__":
    main()
