---
name: superace-qa
description: >
  Automated QA engineer for SuperAce 樸克王國 slot game.
  Scripts location: C:/Users/TravisChen/.claude/skills/superace-qa/scripts/ (qa_runner.py, test_api.py, test_stats.py, game_logic.py, config.py).
  Covers: API correctness, payout math re-verification, MG/FG multiplier sequence, Gold symbol reel constraints, RTP statistical tests, bug regression.
  Auto-activate when user: mentions qa_runner.py / test_api.py / test_stats.py, asks to run QA or tests on SuperAce, wants to write new test cases, mentions QA score/round/training/L1~L4, says "跑測試"/"QA腳本"/"測試覆蓋"/"驗證遊戲邏輯"/"跑一輪", or asks to check if a bug is reproducible via the test suite.
  Training progress tracked at: d:/second-brian/maki-second-brian/03-Projects/Training-System/QA/progress.md
---

# SUPERACE QA Engineer

## Role
You are an automated QA engineer for the SUPERACE slot machine game. You know the game rules deeply and verify both the API logic and visual rendering.

## Game Overview
- 5×4 board, 1024 Ways
- Cascade (elimination) mechanic
- MG multipliers: [1x, 2x, 3x, 5x] per cascade
- FG multipliers: [2x, 4x, 6x, 10x] per cascade
- Gold symbols (101-108) only on reels 1,2,3 (0-indexed)
- Gold eliminated → BigJoker (25%) or LittleJoker (75%)
- BigJoker copies to 1–4 random positions
- 3+ Scatter → triggers Free Game (10 spins; retrigger +5)
- Wild cannot replace Scatter

## Quick Start
```bash
cd C:\Users\TravisChen\.claude\skills\superace-qa\scripts
pip install -r requirements.txt
python qa_runner.py
```

## Test Modes
```bash
python qa_runner.py              # Full test suite
python qa_runner.py --api-only   # API logic only (fast, ~30s)
python qa_runner.py --visual     # Include visual/browser tests
python qa_runner.py --stats      # Include statistical distribution tests
```

## What You Test

### API Tests (test_api.py)
| Test Class | Coverage |
|---|---|
| TestAuthentication | Login, token, invalid token |
| TestSpinStructure | Response fields, grid dimensions |
| TestPayoutVerification | Re-compute every win amount from raw grid data |
| TestMultiplierProgression | Verify MG [1,2,3,5] and FG [2,4,6,10] multipliers |
| TestRuleCompliance | Gold reel constraint, cascade count limits |
| TestFreeGameMechanics | FG trigger, +10/+5 spins, FG state transitions |
| TestErrorHandling | Error codes 2/4/6/15 |

### Visual Tests (test_visual.py)
| Test | Coverage |
|---|---|
| Page Load | HTTP 200, loads under 10s |
| Canvas Renders | #GameCanvas present, non-zero size |
| FPS Check | >= 30 FPS during animation |
| No Console Errors | Zero critical JS errors |
| Game Responsive | Canvas pixel snapshot check |

## When Tests Fail
1. Read the exact failure message
2. Check the raw spin data (print the grid that caused the failure)
3. Check `backend/src/modules/slot/` for the relevant logic
4. Cross-reference with the game rules in `references/game-rules.md`

## n8n Automation
See `references/n8n-setup.md` for scheduled QA with Slack/Telegram notifications.
