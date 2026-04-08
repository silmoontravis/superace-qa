# Known Issues / Bug Tracker

## BUG-001 — Invalid token returns wrong error code
- **Status:** Open
- **Severity:** Medium
- **Found:** First QA run
- **Test:** `TestAuthentication::test_play_with_invalid_token_returns_error`

### Symptom
Calling `POST /play` with an invalid token returns `error: 2` (ERR_INSUFFICIENT)
instead of `error: 4` (ERR_TOKEN_INVALID) or `error: 6` (ERR_TOKEN_EXPIRED).

### Expected
```json
{ "error": 4, "message": "token invalid" }
```

### Actual
```json
{ "error": 2, "message": "..." }
```

### Root Cause (suspected)
In `src/routes/game.ts`, the `requireUserId()` call throws a `GameError`,
but the catch block or error middleware may not be mapping it correctly —
it falls through to the "insufficient balance" branch instead of propagating
the token error code.

### Fix Direction
Check `src/common/errorMiddleware.ts` and `src/routes/game.ts` error handling order.
Ensure `ERR.TOKEN_EXPIRED` and `ERR.TOKEN_INVALID` are caught before
balance deduction logic runs.

---

## BUG-002 — Field name `bets` vs `bet` inconsistency
- **Status:** Open
- **Severity:** Low (functional, but breaks spec contract)
- **Found:** First QA run

### Symptom
`slotData` response uses field name `"bet"` but the spec and backend comments say `"bets"`.

### Expected
```json
{ "bets": 1.2 }
```

### Actual
```json
{ "bet": 1.2 }
```

### Fix
Standardise field name in `src/routes/game.ts` response builder.

---

## BUG-003 — Field name `hasFreeSpin` vs `hasFreeGame` inconsistency
- **Status:** Open
- **Severity:** Low
- **Found:** First QA run

### Symptom
`paytable` uses `"hasFreeSpin"` but spec says `"hasFreeGame"`.

### Fix
Rename field in `src/modules/slot/types.ts` and route response.

---

## BUG-004 — `addFreeSpin` returns boolean dict instead of numeric array
- **Status:** Open
- **Severity:** Medium (frontend may break if expecting numbers)
- **Found:** First QA run

### Symptom
`addFreeSpin` should indicate HOW MANY spins were added per cascade.

### Expected (per spec)
```json
{ "addFreeSpin": [0, 0, 10] }   // cascade 2 added 10 spins
```

### Actual
```json
{ "addFreeSpin": { "2": true } }   // boolean, not numeric
```

### Fix Direction
Return `0` or the actual spin count (5 or 10) instead of `true/false`.

---

## BUG-005 — DEFAULT_BET=1 not in allowed betList
- **Status:** Open (config issue)
- **Severity:** Medium
- **Found:** First QA run

### Symptom
Calling `/play?bet=1` returns:
```
invalid bet amount, allowed: 0.6, 1.2, 3, 6, 9, 15, 30, 45, 60, 90, 120, 300, 600, 888, 960
```
The minimum bet is `0.6`, not `1`. The betList should be clearly documented.

---

## BUG-006 🔴 High — JS 變數重複宣告（前端 SyntaxError）
- **Status:** Open
- **Severity:** High（可能導致特定瀏覽器/版本崩潰）
- **Found:** 視覺測試（Playwright）
- **Test:** `test_visual.py::No JS Exceptions`

### Symptom
瀏覽器 console 拋出 JS 例外：
```
Identifier 'LOG_ENDPOINT_SUFFIX' has already been declared
```

### 原因分析
某個 JS 檔案使用 `const` 或 `let` 宣告 `LOG_ENDPOINT_SUFFIX`，但同一 scope 中已經有同名宣告（可能來自兩個不同腳本都宣告了同一個 global const）。

### 影響
- Chrome 嚴格模式下會拋出 SyntaxError
- 可能導致後續 JS 邏輯中斷，影響 log 功能或遊戲初始化
- 在舊版或容錯較低的環境下可能造成遊戲無法啟動

### 根本原因（已確認）
兩支檔案各自宣告了完全相同的 const：

**entry_env_log.01bf5.js：**
```javascript
const LOG_ENDPOINT_SUFFIX = "/logger.php";  // ← 第一次宣告
```

**client_env_helper.fcf49.js：**
```javascript
const LOG_ENDPOINT_SUFFIX = "/logger.php";  // ← 重複宣告 → SyntaxError
```

兩個檔案都在同一 global scope 載入，`const` 不允許重複宣告。

### 修復方式（選一）
**方案A（推薦）：** 只保留其中一支的宣告，另一支改為直接使用字串 `"/logger.php"` 或抽成共用模組。

**方案B（快速）：** 把其中一支改成 `var`（var 允許重複宣告，不會拋錯）。

### 修復後驗證
```bash
python test_visual.py
# 預期：No JS Exceptions ✅
```

---

*Add new bugs in the format above.*
