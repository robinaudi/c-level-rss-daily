# 🧠 C-Level RSS Daily Digest

使用 GitHub Actions 自動整理各大 RSS 財經/科技新聞，並依照職位分類（CEO, COO, CFO, CTO, CIO）每日寫入 Notion 資料庫，協助高階主管快速掌握重要趨勢。

## 📌 專案特色

- ⏰ 每日 09:00 自動排程執行
- 🌐 擷取多個 RSS 來源（Bloomberg, SupplyChainDive, CFO Dive, InfoQ, CIO.com）
- 🔎 自動過濾過去 7 天內的新聞
- 🧠 支援重複檢查避免寫入重複內容
- 📝 寫入 Notion 時自動分類、標註日期與職位
- ⚠️ 執行錯誤時提供日誌輸出與例外處理

## 🔧 環境變數（GitHub Secrets）

請前往 GitHub Repository → `Settings > Secrets and variables > Actions`，新增以下變數：

| 名稱               | 說明                         |
|--------------------|------------------------------|
| `NOTION_TOKEN`      | Notion 整合的 internal token（[取得方式點我](https://www.notion.com/my-integrations)） |
| `NOTION_DATABASE_ID`| Notion 資料庫 ID，來自資料庫頁面網址中 |

## 🧪 手動觸發更新

1. 點選上方選單「Actions」
2. 選擇左側 `Auto Update News Digest`
3. 點選右上角 `Run workflow` 執行測試

## 🗂️ 資料結構（Notion）

| 欄位             | 說明                                 |
|------------------|--------------------------------------|
| 登錄日期         | 新聞進入 Notion 的日期                |
| 事件發生日期     | 新聞發布時間                         |
| 標題             | 新聞標題                             |
| 摘要             | 新聞內容節錄（前 500 字）             |
| 分類             | 依照 RSS 類別自動歸類                |
| 適合主管         | CEO、COO、CFO、CTO、CIO               |
| 連結             | 原始新聞網址                         |
| 該注意哪些？     | 預留給使用者摘要 AI 自動判斷或手動編輯 |

## ⚙️ 自動排程時間

目前設定為每日台北時間 09:00 執行：

```yaml
schedule:
  - cron: '0 1 * * *'  # UTC+0 等同於台灣時間早上 09:00
