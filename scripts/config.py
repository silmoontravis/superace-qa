"""
SUPERACE QA Configuration
Edit these values to match your environment.
"""

# ── API ──────────────────────────────────────────────────────────────
BASE_URL   = "https://dev-superace-original-api.fuyuit.tw"
GAME_URL   = "https://dev-superace-original.fuyuit.tw/?ssoKey=test002"
SSO_KEY    = "test002"
SSO_KEYS   = ["test001", "test002", "test003"]  # all available test accounts
DEFAULT_BET = 1.2   # must be from the server's betList
# betList from /sso/login: [0.6, 1.2, 3, 6, 9, 15, 30, 45, 60, 90, 120, 300, 600, 888, 960]
BET_LIST    = [0.6, 1.2, 3, 6, 9, 15, 30, 45, 60, 90, 120, 300, 600, 888, 960]

# ── Board ─────────────────────────────────────────────────────────────
REELS = 5
ROWS  = 4

# ── Symbols ──────────────────────────────────────────────────────────
EMPTY        = 0
BIG_JOKER    = 10
LITTLE_JOKER = 11
SCATTER      = 9    # ← was 12 (BUG-NEW-002 root cause; confirmed from office version)
# Gold symbols = base symbol + 100  (101=Gold_Clubs … 108=Gold_Ace)
WILDS        = {BIG_JOKER, LITTLE_JOKER}          # for test_stats.py compatibility
GOLD_SYMBOLS = set(range(101, 109))               # 101-108
GOLD_REELS   = {1, 2, 3}                          # 0-indexed (same as GOLD_ALLOWED_REELS)

# ── Paytable (values × 100, divide by 100 for actual ratio) ──────────
PAYTABLE_X100 = {
    8: {3: 50,  4: 150, 5: 250},  # Ace
    7: {3: 40,  4: 120, 5: 200},  # King
    6: {3: 30,  4:  90, 5: 150},  # Queen
    5: {3: 20,  4:  60, 5: 100},  # Jack
    4: {3: 10,  4:  30, 5:  50},  # Spades
    3: {3: 10,  4:  30, 5:  50},  # Hearts
    2: {3:  5,  4:  15, 5:  25},  # Diamonds
    1: {3:  5,  4:  15, 5:  25},  # Clubs
}

# ── Multipliers (index = cascade number, last value repeats) ─────────
MG_MULTIPLIERS = [1, 2, 3, 5]
FG_MULTIPLIERS = [2, 4, 6, 10]

# ── Free Game ─────────────────────────────────────────────────────────
FG_INITIAL_SPINS   = 10
FG_RETRIGGER_SPINS = 5
FG_TRIGGER_SCATTERS = 3

# ── Gold reel constraint (0-indexed) ─────────────────────────────────
GOLD_ALLOWED_REELS   = [1, 2, 3]   # reels 2,3,4 in 1-indexed (game spec)
GOLD_FORBIDDEN_REELS = [0, 4]

# ── Slot Config (mirrors backend config.ts) ───────────────────────────
# Updated 2026-04-07 after git pull (commit 6f2652f)
GOLDEN_RATE   = 0.05   # was 0.18 in old version
BIG_JOKER_RATE = 0.15  # was 0.25 in old version
# BigJoker copy count: min 2, max 5 (cloneWeights: [2,3,4,5])
BIG_JOKER_COPY_MIN = 2
BIG_JOKER_COPY_MAX = 5

# ── Error Codes ───────────────────────────────────────────────────────
ERR_OK            = 0
ERR_INSUFFICIENT  = 2
ERR_TOKEN_INVALID = 4
ERR_TOKEN_EXPIRED = 6
ERR_IN_PROGRESS   = 15

# ⚠️  Known Issue: invalid token sometimes returns ERR_INSUFFICIENT (2)
#     instead of ERR_TOKEN_INVALID (4) / ERR_TOKEN_EXPIRED (6).
#     Root cause: token lookup failure falls through to wrong error path.
#     Filed as BUG-001 — see references/known-issues.md
ERR_TOKEN_ANY = [ERR_TOKEN_INVALID, ERR_TOKEN_EXPIRED, ERR_INSUFFICIENT]

# ── Test Settings ─────────────────────────────────────────────────────
WIN_TOLERANCE       = 0.02   # max acceptable diff in win amount (float precision)
STAT_SAMPLE_SIZE    = 100    # spins for distribution tests
STAT_SPIN_COUNT     = 100    # alias for test_stats.py compatibility
FG_SEARCH_MAX_SPINS = 200    # max spins to search for a free-game trigger
REQUEST_DELAY_S     = 0.1    # seconds between requests

# ── test_stats.py aliases ─────────────────────────────────────────────
BET         = DEFAULT_BET   # standard test bet
INVALID_BET = 1.0           # BUG-005: defaultBet:1 not in betList
SCATTER_RATE        = 0.03
FG_TRIGGER_RATE_MIN = 0.005
RTP_MIN             = 0.40
RTP_MAX             = 1.20
