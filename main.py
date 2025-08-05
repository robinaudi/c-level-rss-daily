# main.py
import feedparser
import requests
from datetime import datetime, timedelta
import os

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 設定要讀取的 RSS 清單（職位對應分類）
RSS_FEEDS = [
    {"職位": "CEO", "分類": "全球財經", "url": "https://www.bloomberg.com/feed"},
    {"職位": "COO", "分類": "供應鏈動態", "url": "https://www.supplychaindive.com/rss/"},
    {"職位": "CFO", "分類": "財務與會計策略", "url": "https://www.cfodive.com/rss/"},
    {"職位": "CTO", "分類": "技術策略", "url": "https://feed.infoq.com/"},
    {"職位": "CIO", "分類": "資安治理", "url": "https://www.cio.com/index.rss"},
]

# 日期範圍：過去 7 天
now = datetime.utcnow()
seven_days_ago = now - timedelta(days=7)

# 檢查 Notion 是否已經有該條目（用 URL 當唯一鍵）
def is_duplicate(url):
    search_url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "filter": {
            "property": "連結",
            "url": {
                "equals": url
            }
        }
    }
    response = requests.post(search_url, headers=HEADERS, json=payload)
    data = response.json()
    return len(data.get("results", [])) > 0

# 將資料寫入 Notion

def create_page(item, 職位, 分類):
    pub_date = datetime(*item.published_parsed[:6]).strftime("%Y.%m.%d")
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "登錄日期": {"date": {"start": now.strftime("%Y-%m-%d")}},
            "事件發生日期": {"date": {"start": datetime(*item.published_parsed[:6]).strftime("%Y-%m-%d")}},
            "摘要": {"rich_text": [{"text": {"content": item.get("summary", "")[:500]}}]},
            "標題": {"title": [{"text": {"content": item.title}}]},
            "分類": {"select": {"name": 分類}},
            "適合主管": {"select": {"name": 職位}},
            "連結": {"url": item.link},
            "該注意哪些？": {"rich_text": [{"text": {"content": "待補充（可用 AI 自動摘要生成）"}}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=payload)
    return res.status_code == 200

# 執行主邏輯
for feed in RSS_FEEDS:
    d = feedparser.parse(feed["url"])
    for entry in d.entries:
        if hasattr(entry, "published_parsed"):
            pub_dt = datetime(*entry.published_parsed[:6])
            if pub_dt >= seven_days_ago:
                if not is_duplicate(entry.link):
                    print("新增：", entry.title)
                    create_page(entry, feed["職位"], feed["分類"])
                else:
                    print("跳過重複：", entry.title)
