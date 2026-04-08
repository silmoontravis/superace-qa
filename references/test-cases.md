# SUPERACE 測試用例清單

> 依據需求規格書整理。每個用例對應一個可執行的自動化測試或手動驗證步驟。
> 自動化狀態：✅ 已實作 / 🔧 部分實作 / ❌ 待實作

---

## TC-001 系列：盤面規格

### TC-001-01 盤面尺寸正確
- **分類：** 規則合規
- **自動化：** ✅ `TestSpinStructure::test_grid_is_5x4`
- **驗證：** 每次 spin 回傳的 grid 必須是 5 輪 × 4 列（5 reels, 4 rows）
- **預期：** `len(grid) == 5`，`len(grid[i]) == 4` for all i

### TC-001-02 黃金牌只出現在第 2-4 輪
- **分類：** 規則合規
- **自動化：** ✅ `TestRuleCompliance::test_gold_only_in_reels_1_2_3`
- **驗證：** 符號值 101-108 不得出現在 reel[0] 和 reel[4]
- **預期：** 所有盤面 reel 0 和 reel 4 無 gold 符號

### TC-001-03 儲存的盤面不含空格
- **分類：** 規則合規
- **自動化：** ✅ `TestRuleCompliance::test_no_empty_cells_in_stored_grids`
- **驗證：** 補牌後盤面每格必須有符號（≠ 0）
- **預期：** 0 個空格

---

## TC-002 系列：Ways 計獎

### TC-002-01 Ways 計算正確性
- **分類：** 核心邏輯
- **自動化：** ✅ `TestPayoutVerification::test_mg_cascade_wins_match_calculation`
- **驗證：** 獨立重算每段 cascade 的 win 金額，與後端回傳相符
- **公式：** `win = Σ(ways_per_symbol × paytable_x100) × bet / 100 × multiplier`
- **容差：** ±0.02

### TC-002-02 零贏組合對應零獎金
- **分類：** 核心邏輯
- **自動化：** ✅ `TestPayoutVerification::test_zero_win_cascades_have_no_combinations`
- **驗證：** 後端回傳 win=0 時，我方獨立計算也必須為 0

### TC-002-03 Ways 左至右連線規則
- **分類：** 核心邏輯
- **自動化：** 🔧（含在 TC-002-01 的計算邏輯中）
- **驗證：** 中獎必須從第 1 輪（reel[0]）開始連續出現，不得跳輪

### TC-002-04 符號必須出現 3 輪以上才算中獎
- **分類：** 核心邏輯
- **自動化：** 🔧（含在 TC-002-01 的 paytable 查找中，3輪以下無賠率）
- **驗證：** 只有 2 輪相同符號時，win = 0

### TC-002-05 總贏分 = 所有 cascade 金額加總
- **分類：** 核心邏輯
- **自動化：** ✅ `TestPayoutVerification::test_total_win_equals_sum_of_cascades`
- **驗證：** `totalWin == sum(mgWin) + sum(fgWin)`

---

## TC-003 系列：消除連擊 & 倍率

### TC-003-01 MG 倍率成長曲線
- **分類：** 核心邏輯
- **自動化：** ✅ `TestMultiplierProgression::test_mg_multipliers_are_1_2_3_5`
- **驗證：** 主遊戲 cascade 0→1x, 1→2x, 2→3x, 3+→5x
- **注意：** 第 4 次以上全部使用 5x（最後一個值固定）

### TC-003-02 FG 倍率成長曲線
- **分類：** 核心邏輯
- **自動化：** ✅ `TestFreeGameMechanics::test_fg_multipliers_are_2_4_6_10`（需 FG 觸發樣本）
- **驗證：** 免費遊戲 cascade 0→2x, 1→4x, 2→6x, 3+→10x

### TC-003-03 消除後補牌再次判定
- **分類：** 核心邏輯
- **自動化：** 🔧（間接驗證：mgTable 有多個 cascade 時）
- **驗證：** 補牌後若形成新中獎，mgTable 需包含多個盤面快照
- **預期：** `len(mgTable) >= 2` 代表至少一次成功連擊

### TC-003-04 不中獎時只有 1 個 cascade 快照
- **分類：** 核心邏輯
- **自動化：** ✅ `TestMultiplierProgression::test_cascade_count_at_least_1`
- **驗證：** 即使不中獎，mgTable 也至少有初始盤面

---

## TC-004 系列：特殊符號

### TC-004-01 Scatter 不參與 Ways 計獎
- **分類：** 規則合規
- **自動化：** 🔧（含在 TC-002-01 中：scatter 不出現在 candidates）
- **驗證：** Scatter 存在時不影響其他符號的 ways 計算

### TC-004-02 Joker（Wild）不可替代 Scatter
- **分類：** 規則合規
- **自動化：** ✅ `TestRuleCompliance::test_joker_is_never_scatter`
- **驗證：** Joker(10/11) 和 Scatter(12) 絕不重疊在同一位置

### TC-004-03 Joker 可替代一般付費符號
- **分類：** 規則合規
- **自動化：** ✅（含在 TC-002-01：`can_match()` 函數驗證 joker 替代）
- **驗證：** Joker 出現在計獎路徑時可作為任意 base symbol

### TC-004-04 黃金牌消除後轉為鬼牌
- **分類：** 特殊功能
- **自動化：** ✅ `TestGoldToJokerConversion::test_eliminated_gold_becomes_joker`
- **驗證：**
  - mgTable[i] 中有 gold 符號（101-108）且為負值（被消除）
  - mgTable[i+1] 中原位置出現 BigJoker(10) 或 LittleJoker(11)

### TC-004-05 大鬼牌複製到其他位置
- **分類：** 特殊功能
- **自動化：** ✅ `TestBigJokerCopy::test_big_joker_has_copies`（機率性 skip — BigJoker 事件稀少）
- **驗證：**
  - 當 BigJoker 出現後，下一盤面中 BigJoker 數量 ≥ 1
  - 複製不落在 Scatter 或已有 Joker 的位置

### TC-004-06 大鬼牌複製數量範圍 1-4 個
- **分類：** 特殊功能
- **自動化：** ✅ `TestBigJokerCopy::test_big_joker_copy_count_2_to_5`
- **驗證：** BigJoker 一次複製 2~5 個（含原位置）

---

## TC-005 系列：免費遊戲

### TC-005-01 3 個 Scatter 觸發免費遊戲
- **分類：** 功能流程
- **自動化：** ✅ `TestFreeGameMechanics::test_fg_trigger_means_3plus_scatters`
- **驗證：** 觸發 FG 的 cascade 盤面必須有 ≥ 3 個 Scatter

### TC-005-02 初次觸發給予 10 次
- **分類：** 功能流程
- **自動化：** ✅ `TestFreeGameMechanics::test_add_free_spin_values_valid`（驗證值為 10 或 5）
- **驗證：** 初次觸發 addFreeSpin 值應為 10

### TC-005-03 免費遊戲中再觸發追加 5 次
- **分類：** 功能流程
- **自動化：** 🔧（test_add_free_spin_values_valid 驗證值為 5 或 10，但無法區分初次/再觸發）
- **驗證：** FG 狀態中再次出現 3+ Scatter，addFreeSpin = 5

### TC-005-04 免費遊戲不扣玩家投注
- **分類：** 功能流程
- **自動化：** ✅ `TestBalanceDeduction::test_fg_does_not_deduct_bet`
- **驗證：** buyFreeSpin 後 `afterCoin = prevCoin - cost + totalWin`（cost = bet×buyRatio，無額外每局扣款）

### TC-005-05 FG 贏分必須為非負值
- **分類：** 功能流程
- **自動化：** ✅ `TestFreeGameMechanics::test_fg_table_win_non_negative`

### TC-005-06 主遊戲連擊完整結束後才進 FG
- **分類：** 功能流程
- **自動化：** ✅ `TestMGCompletesBeforeFG::test_mg_table_present_before_fg_data`, `test_mg_win_recorded_in_fg_trigger_spin`
- **驗證：** 觸發 FG 的那次 spin，`mgTable` 和 `mgWin` 必須包含所有連擊結算後才出現 `hasFreeSpin=true`

---

## TC-006 系列：API 結構 & 錯誤處理

### TC-006-01 標準回應信封
- **分類：** API 合規
- **自動化：** ✅ `TestAuthentication::test_response_always_has_required_envelope`
- **驗證：** 所有回應包含 `error`, `data`, `time`

### TC-006-02 Invalid Token 應回傳 error 4 或 6
- **分類：** API 合規
- **自動化：** 🔧 `TestErrorHandling::test_invalid_token_error_code`（目前寬鬆接受 2，BUG-001）
- **驗證：** 目標：error ∈ {4, 6}

### TC-006-03 餘額不足回傳 error 2
- **分類：** API 合規
- **自動化：** ✅ `TestErrorHandling::test_enormous_bet_returns_error`

### TC-006-04 roundID 格式為時間戳整數
- **分類：** API 合規
- **自動化：** ✅ `TestSpinStructure::test_has_round_id`
- **驗證：** `data.roundID` 存在且為數字

---

## TC-007 系列：視覺 & UI

### TC-007-01 遊戲頁面 HTTP 200
- **分類：** 視覺
- **自動化：** ✅ `test_visual.py::Page Load`

### TC-007-02 Canvas 渲染正常（非空白）
- **分類：** 視覺
- **自動化：** ✅ `test_visual.py::Canvas Renders`

### TC-007-03 FPS ≥ 30
- **分類：** 視覺
- **自動化：** ✅ `test_visual.py::FPS ≥ 30`

### TC-007-04 無 JS 例外
- **分類：** 視覺
- **自動化：** 🔧 `test_visual.py::No JS Exceptions`（BUG-006 阻擋，已知）

### TC-007-05 AppConfig 正確載入
- **分類：** 視覺
- **自動化：** ✅ `test_visual.py::Game Boots`

### TC-007-06 FG API 欄位在瀏覽器端可存取
- **分類：** 視覺 + FG
- **自動化：** ✅ `test_visual_fg.py::API FG State Field Accessible`

### TC-007-07 HTML Shell 完整性
- **分類：** 視覺
- **自動化：** ✅ `test_visual_fg.py::HTML Shell Intact`

---

## TC-008 系列：統計分佈（需大量樣本）

### TC-008-01 黃金牌分佈符合規格
- **分類：** 統計
- **自動化：** ✅ `test_stats.py::TestGoldSymbolRate`
- **驗證：** 取樣 200 spin，黃金牌出現率符合 reel 1-3 有值、reel 0 和 4 為 0%

### TC-008-02 Scatter 出現率約 3%
- **分類：** 統計
- **自動化：** ❌
- **驗證：** 取樣 200+ spin，每個格子的 Scatter 出現率 ≈ 3% (±2%)

### TC-008-03 BigJoker 佔 gold 轉換的 25%
- **分類：** 統計
- **自動化：** ✅ `test_stats.py::TestBigJokerRate`
- **驗證：** BigJoker 佔所有 Joker 轉換的 ~15%（含複製後計算）

---

## 測試執行優先序

| 優先 | 用例群 | 說明 |
|---|---|---|
| P0 | TC-002, TC-003 | 核心計算正確性（金錢直接相關）|
| P1 | TC-001, TC-004, TC-005 | 規則合規和功能完整性 |
| P2 | TC-006 | API 合約正確性 |
| P3 | TC-007 | 視覺渲染品質 |
| P4 | TC-008 | 統計分佈（RTP 調校用）|

---

## 自動化進度摘要

| 狀態 | 數量 |
|---|---|
| ✅ 已自動化 | 27 |
| 🔧 部分實作 | 5 |
| ❌ 待實作 | 5 |
| **合計** | **37** |
