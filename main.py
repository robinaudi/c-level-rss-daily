# main.py (最終版：含翻譯、完整防重、30天篩選、數量限制)
import os
import requests
import feedparser
import logging
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from deep_translator import GoogleTranslator

# --- 設定 ---
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
# NEW: 新增可設定的單次最大執行數量，預設為 100
MAX_ENTRIES_PER_RUN = int(os.getenv('MAX_ENTRIES_PER_RUN', '100'))


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

# --- 核心函式 (後面不變的函式省略了重複的註解) ---

def check_env_vars():
    if not NOTION_TOKEN or not DATABASE_ID:
        logging.error("🚫 缺少環境變數：NOTION_TOKEN 或 NOTION_DATABASE_ID")
        return False
    return True

def get_existing_urls_from_notion() -> set:
    existing_urls = set()
    query_url = f"{NOTION_API_URL}databases/{DATABASE_ID}/query"
    has_more = True
    next_cursor = None
    while has_more:
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        try:
            response = requests.post(query_url, headers=HEADERS, json=payload)
            response.raise_for_status()
            data = response.json()
            for page in data.get("results", []):
                properties = page.get("properties", {})
                url_property = properties.get("URL", {})
                if url_property and url_property.get("url"):
                    existing_urls.add(url_property["url"])
            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")
        except requests.exceptions.RequestException as e:
            logging.error(f"🛑 查詢 Notion 資料庫失敗: {e}")
            return existing_urls
    logging.info(f"✅ 成功從 Notion 取得全部分頁，共 {len(existing_urls)} 筆已存在的 URL")
    return existing_urls

def add_entry_to_notion(source: str, entry: dict):
    create_page_url = f"{NOTION_API_URL}pages"
    title = entry.get("title", "無標題")
    link = entry.get("link", "")
    published_str = entry.get("published", datetime.now(timezone.utc).isoformat())
    published_dt = date_parser.parse(published_str)
    translated_title = ""
    try:
        translated_title = GoogleTranslator(source='auto', target='zh-TW').translate(title)
        logging.info(f"  翻譯成功: '{title}' -> '{translated_title}'")
    except Exception as e:
        logging.warning(f"  ⚠️ 翻譯失敗: {title} | 錯誤: {e}")
        translated_title = title
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "標題": {"title": [{"text": {"content": title}}]},
            "中文標題": {"rich_text": [{"text": {"content": translated_title}}]},
            "URL": {"url": link},
            "來源": {"select": {"name": source}},
            "發布時間": {"date": {"start": published_dt.isoformat()}}
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

# MODIFIED: 主函式邏輯大幅更新
def main():
    logging.info(f"🚀 開始執行 RSS to Notion 腳本 (單次上限: {MAX_ENTRIES_PER_RUN} 筆)...")
    if not check_env_vars():
        return

    # NEW: 設定 30 天的時間篩選條件
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    existing_urls = get_existing_urls_from_notion()
    new_entries_count = 0
    
    all_new_entries = []

    # NEW: 第一輪迴圈，先收集所有來源的、30天內的新文章
    logging.info("--- 階段一: 收集所有來源的近期新文章 ---")
    for source_name, feed_url in RSS_FEEDS.items():
        logging.info(f"📡 正在處理來源: {source_name}")
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            logging.warning(f"⚠️ 解析來源 {source_name} 時可能發生問題: {feed.bozo_exception}")
        
        for entry in feed.entries:
            # 檢查 URL 是否重複
            if entry.link in existing_urls:
                continue

            # 檢查發布時間是否在 30 天內
            published_dt = date_parser.parse(entry.get("published", datetime.now(timezone.utc).isoformat()))
            # 如果解析出的時間沒有時區資訊，預設其為 UTC
            if published_dt.tzinfo is None:
                published_dt = published_dt.replace(tzinfo=timezone.utc)

            if published_dt >= thirty_days_ago:
                # 將來源名稱和發布時間附加到 entry 物件中，方便後續排序
                entry.source_name = source_name
                entry.published_datetime = published_dt
                all_new_entries.append(entry)

    logging.info(f"🔍 收集完成，共找到 {len(all_new_entries)} 筆 30 天內的新文章。")

    # NEW: 第二階段，將所有收集到的新文章按時間倒序排列（最新的在最前面）
    logging.info("--- 階段二: 排序並寫入資料庫 ---")
    all_new_entries.sort(key=lambda e: e.published_datetime, reverse=True)

    for entry in all_new_entries:
        # 檢查是否已達到單次執行的上限
        if new_entries_count >= MAX_ENTRIES_PER_RUN:
            logging.info(f"🏁 已達到單次執行上限 ({MAX_ENTRIES_PER_RUN} 筆)，提前結束任務。")
            break

        logging.info(f"✍️ 正在處理文章: {entry.title} (發布於: {entry.published_datetime.strftime('%Y-%m-%d')})")
        if add_entry_to_notion(entry.source_name, entry):
            new_entries_count += 1
            # 即時將 URL 加入集合，以防萬一 RSS 中有完全重複的項目
            existing_urls.add(entry.link)
    
    logging.info(f"🎉 任務完成！本次共新增 {new_entries_count} 筆新文章。")

if __name__ == "__main__":
    main()
