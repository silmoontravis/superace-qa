# n8n 自動化 QA 流程設定指南

## 目標
每次部署或定時執行 SUPERACE QA，失敗時自動通知你。

---

## 步驟一：安裝 n8n（本地 Docker）

```bash
docker run -d \
  --name n8n \
  -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  n8nio/n8n
```

開啟瀏覽器：http://localhost:5678

---

## 步驟二：建立 QA Workflow

在 n8n 介面中建立一個新 Workflow，加入以下節點：

### 節點 1 — Schedule Trigger（定時觸發）
- 類型：**Schedule Trigger**
- 設定：每隔 1 小時（或每天上午 9:00）
- 或改用 **Webhook** 節點讓 CI/CD 部署後主動觸發

```
Cron 範例：
  每小時    → 0 * * * *
  每天 9AM  → 0 9 * * *
  每次部署  → 改用 Webhook
```

---

### 節點 2 — Execute Command（執行 QA）
- 類型：**Execute Command**
- Command：
```bash
cd C:\Users\TravisChen\.claude\skills\superace-qa\scripts && python qa_runner.py --api-only 2>&1
```
- 勾選 `Return exit code`

> Windows 上的 n8n 請確認 Python 在系統 PATH 中

---

### 節點 3 — IF（判斷是否失敗）
- 類型：**IF**
- 條件：`{{ $json.exitCode }}` **不等於** `0`
  - True → 下一步發送通知
  - False → 結束（通過）

---

### 節點 4a — Telegram 通知（推薦）
- 類型：**Telegram**
- 需要先建立 Telegram Bot：
  1. 找 @BotFather → `/newbot` → 取得 Bot Token
  2. 找 @userinfobot → 取得你的 Chat ID
- Message：
```
🚨 SUPERACE QA Failed!
Time: {{ $now.format('YYYY-MM-DD HH:mm') }}
Output:
{{ $json.stdout.slice(0, 3000) }}
```

---

### 節點 4b — Slack 通知（替代方案）
- 類型：**Slack**
- Credential：Slack Bot Token（需在 Slack App 取得）
- Channel：`#qa-alerts`
- Message：
```
:rotating_light: *SUPERACE QA Failed*
```
附上 `stdout` 前 500 字

---

### 節點 4c — Email 通知（最簡單）
- 類型：**Send Email**
- 設定 Gmail SMTP 或任何 SMTP
- Subject：`[SUPERACE QA] FAILED - {{ $now }}`
- Body：`{{ $json.stdout }}`

---

## 步驟三：部署後自動觸發（Webhook 模式）

在 CI/CD pipeline 最後加一行：

```bash
# GitHub Actions / GitLab CI 最後一步
curl -X POST http://your-server:5678/webhook/superace-qa
```

把 n8n 的 **Webhook** 節點改成 POST 觸發器即可。

---

## 完整 Workflow JSON（可直接匯入 n8n）

```json
{
  "name": "SUPERACE QA",
  "nodes": [
    {
      "name": "Schedule",
      "type": "n8n-nodes-base.scheduleTrigger",
      "parameters": {
        "rule": { "interval": [{ "field": "hours", "hoursInterval": 1 }] }
      }
    },
    {
      "name": "Run QA",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "cd C:\\Users\\TravisChen\\.claude\\skills\\superace-qa\\scripts && python qa_runner.py --api-only 2>&1"
      }
    },
    {
      "name": "Check Result",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "number": [{ "value1": "={{ $json.exitCode }}", "operation": "notEqual", "value2": 0 }]
        }
      }
    },
    {
      "name": "Notify Telegram",
      "type": "n8n-nodes-base.telegram",
      "parameters": {
        "text": "🚨 SUPERACE QA Failed!\n\n{{ $json.stdout.slice(0,2000) }}"
      }
    }
  ]
}
```

---

## 推薦監控項目

| 觸發時機 | 建議測試 | 通知對象 |
|---|---|---|
| 每小時 | `--api-only` (快速) | Telegram 靜音通知 |
| 每天 8AM | `--all` (完整) | Telegram 一般通知 |
| 每次部署 | `--api-only --visual` | Slack #deploy 頻道 |
| 失敗累積 3 次 | 停止部署 + 緊急通知 | 打電話 (Twilio) |

---

## 常見問題

**Python 找不到？**
```bash
# Windows n8n Docker 內呼叫外部 Python 需要 volume 掛載
# 或改用 HTTP Request 節點呼叫一個包裝成 API 的 QA service
```

**想要測試結果的詳細報告？**
修改 `qa_runner.py` 輸出 JSON，n8n 用 **Function** 節點解析後格式化。
