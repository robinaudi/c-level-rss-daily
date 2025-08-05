# ✅ 直接寫入 token 和 database ID（⚠️ 僅限測試）
# NOTION_TOKEN = "secret_ntn_Eq42642401088NbxGGoTVevHnW4eOJ94SCEkrBwOtjy9gQ"  
# NOTION_DATABASE_ID = "2460196ab6ca80b6b556000cac086c6d"  # 請替換為你的資料庫 ID

# main.py
import feedparser
import requests
from datetime import datetime, timedelta
import sys

# ✅ 直接寫入 token 和 database ID（⚠️ 僅限測試）
NOTION_TOKEN = "secret_ntn_Eq42642401088NbxGGoTVevHnW4eOJ94SCEkrBwOtjy9gQ"  # 請替換為你的 token
NOTION_DATABASE_ID = "2460196ab6ca80b6b556000cac086c6d"  # 請替換為你的資料庫 ID

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

now = datetime.utcnow()
seven_days_ago = now - timedelta(days=30)

# 寫入 log 到 Notion 表格
def write_log_to_notion(message):
    try:
        payload = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "標題": {"title": [{"text": {"content": f"📋 Log: {message[:50]}"}}]},
                "摘要": {"rich_text": [{"text": {"content": message}}]},
                "分類": {"select": {"name": "log"}},
                "適合主管": {"select": {"name": "System"}},
                "連結": {"url": "https://example.com/log"},
                "登錄日期": {"date": {"start": now.strftime("%Y-%m-%d")}},
                "事件發生日期": {"date": {"start": now.strftime("%Y-%m-%d")}},
                "該注意哪些？": {"rich_text": [{"text": {"content": "系統自動記錄"}}]}
            }
        }
        res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=payload)
        res.raise_for_status()
        print(f"🪵 寫入 log 至 Notion 成功：{message}")
    except Exception as e:
        print(f"🛑 log 寫入失敗：{e}")

# 檢查 Notion 是否已經有該條目（用 URL 當唯一鍵）
def is_duplicate(url):
    try:
        search_url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
        payload = {
            "filter": {
                "property": "連結",
                "url": {"equals": url}
            }
        }
        response = requests.post(search_url, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        return len(data.get("results", [])) > 0
    except Exception as e:
        msg = f"⚠️ 查重失敗: {e}"
        print(msg)
        write_log_to_notion(msg)
        return False

# 將資料寫入 Notion
def create_page(item, 職位, 分類):
    try:
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
        res.raise_for_status()
        print(f"✅ 寫入成功：{item.title}")
        return True
    except Exception as e:
        msg = f"❌ 寫入失敗：{item.title}，錯誤：{e}"
        print(msg)
        write_log_to_notion(msg)
        return False

# 測試是否能寫入 Notion
try:
    test_payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "標題": {"title": [{"text": {"content": "✅ 測試：Notion 寫入測試"}}]},
            "摘要": {"rich_text": [{"text": {"content": f"執行於 {now.strftime('%Y-%m-%d %H:%M:%S')} UTC"}}]},
            "分類": {"select": {"name": "技術策略"}},
            "適合主管": {"select": {"name": "CTO"}},
            "連結": {"url": "https://example.com/test-log"},
            "登錄日期": {"date": {"start": now.strftime("%Y-%m-%d")}},
            "事件發生日期": {"date": {"start": now.strftime("%Y-%m-%d")}},
            "該注意哪些？": {"rich_text": [{"text": {"content": "僅供測試用途"}}]}
        }
    }
    test_res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=test_payload)
    test_res.raise_for_status()
    print("📝 成功寫入測試 log 至 Notion")
except Exception as e:
    msg = f"🚫 測試 log 寫入失敗：{e}"
    print(msg)
    write_log_to_notion(msg)

# 執行主邏輯
for feed in RSS_FEEDS:
    try:
        print(f"📡 處理來源：{feed['url']}")
        d = feedparser.parse(feed["url"])
        print(f"🔍 共取得 {len(d.entries)} 筆資料")
        for entry in d.entries:
            if hasattr(entry, "published_parsed"):
                pub_dt = datetime(*entry.published_parsed[:6])
                print(f"  • ⏰ 發布時間：{pub_dt.strftime('%Y-%m-%d')}, 標題：{entry.title}")
                if pub_dt >= seven_days_ago:
                    if not is_duplicate(entry.link):
                        create_page(entry, feed["職位"], feed["分類"])
                    else:
                        print("🔁 跳過重複：", entry.title)
    except Exception as e:
        msg = f"❌ RSS 來源處理失敗：{feed['url']}，錯誤：{e}"
        print(msg)
        write_log_to_notion(msg)
