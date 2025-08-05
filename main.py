# ✅ 直接寫入 token 和 database ID（⚠️ 僅限測試）
# NOTION_TOKEN = "ntn_Eq42642401088NbxGGoTVevHnW4eOJ94SCEkrBwOtjy9gQ"  
# NOTION_DATABASE_ID = "2450196ab6ca8037b2e4c4f6f1537649"  # 請替換為你的資料庫 ID
# main.py
import os
import requests
import feedparser
import logging
from datetime import datetime
from dateutil import parser as date_parser

# --- 設定 ---
# 從環境變數讀取機敏資訊
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

# 要訂閱的 RSS Feed 列表
RSS_FEEDS = {
    "Bloomberg": "https://www.bloomberg.com/opinion/authors/ARbTQlRLRjE/matthew-s-levine.rss",
    "SupplyChainDive": "https://www.supplychaindive.com/rss/",
    "CFODive": "https://www.cfodive.com/rss/",
}

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Notion API 的基本設定
NOTION_API_URL = "https://api.notion.com/v1/"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# --- 核心函式 ---

def check_env_vars():
    """檢查必要的環境變數是否存在"""
    if not NOTION_TOKEN:
        logging.error("🚫 缺少環境變數：NOTION_TOKEN")
        return False
    if not DATABASE_ID:
        logging.error("🚫 缺少環境變數：NOTION_DATABASE_ID")
        return False
    return True

def get_existing_urls_from_notion() -> set:
    """從 Notion Database 取得所有已存在的 URL，用於防止重複寫入"""
    existing_urls = set()
    query_url = f"{NOTION_API_URL}databases/{DATABASE_ID}/query"
    
    try:
        response = requests.post(query_url, headers=HEADERS)
        response.raise_for_status()  # 如果請求失敗 (如 401, 404), 會拋出例外
        
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
        # 如果無法連接Notion，返回一個空集合，避免後續流程完全中斷，但會失去防重功能
        return set()

def add_entry_to_notion(source: str, entry: dict):
    """將單筆 RSS 項目新增至 Notion Database"""
    create_page_url = f"{NOTION_API_URL}pages"
    
    # 從 entry 中提取資訊
    title = entry.get("title", "無標題")
    link = entry.get("link", "")
    # 使用 date_parser 處理多種日期格式
    published_str = entry.get("published", datetime.now().isoformat())
    published_dt = date_parser.parse(published_str)

    # 建立 Notion Page 的資料結構 (Payload)
    # **請確保您的 Notion Database 屬性名稱與這裡的 key 一致**
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "標題": {
                "title": [{"text": {"content": title}}]
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
    """主執行函式"""
    logging.info("🚀 開始執行 RSS to Notion 腳本...")
    
    if not check_env_vars():
        return # 如果缺少環境變數，直接結束

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
                    # 將新增成功的 url 加入集合，避免同一次運行中重複添加
                    existing_urls.add(entry.link)
            else:
                logging.info(f"🔄 跳過已存在文章: {entry.title}")

    logging.info(f"🎉 任務完成！本次共新增 {new_entries_count} 筆新文章。")

if __name__ == "__main__":
    main()
