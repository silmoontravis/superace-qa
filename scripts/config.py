# SUPERACE QA Test Configuration

BASE_URL = "https://dev-superace-original-api.fuyuit.tw"
GAME_URL = "https://dev-superace-original.fuyuit.tw"

SSO_KEYS = ["test002"]
SSO_KEY  = SSO_KEYS[0]

BET         = 1.2   # standard test bet (minimum valid value)
INVALID_BET = 1.0   # BUG-005: defaultBet:1 is NOT in betList

# ── Paytable (multiplier of bet) ──────────────────────────────────────────────
PAYTABLE = {
    8: {3: 0.5,  4: 1.5,  5: 2.5 },  # Ace
    7: {3: 0.4,  4: 1.2,  5: 2.0 },  # King
    6: {3: 0.3,  4: 0.9,  5: 1.5 },  # Queen
    5: {3: 0.2,  4: 0.6,  5: 1.0 },  # Jack
    3: {3: 0.1,  4: 0.3,  5: 0.5 },  # Spades
    4: {3: 0.1,  4: 0.3,  5: 0.5 },  # Hearts
    1: {3: 0.05, 4: 0.15, 5: 0.25},  # Diamonds
    2: {3: 0.05, 4: 0.15, 5: 0.25},  # Clubs
}

# ── Multipliers ───────────────────────────────────────────────────────────────
MG_MULTIPLIERS = [1, 2, 3, 5]   # cascade index 0,1,2,3+
FG_MULTIPLIERS = [2, 4, 6, 10]

# ── Symbol codes ──────────────────────────────────────────────────────────────
SCATTER      = 9
WILDS        = {10, 11}              # 10=BigJoker, 11=LittleJoker
GOLD_SYMBOLS = set(range(101, 109))  # 101-108
GOLD_REELS   = {1, 2, 3}            # 0-indexed (reels 2,3,4 in 1-indexed)

# ── Free Game ─────────────────────────────────────────────────────────────────
FG_INITIAL_SPINS   = 10
FG_RETRIGGER_SPINS = 5
FG_SEARCH_MAX_SPINS = 200  # max spins to search for FG trigger

# ── Statistical test thresholds (used in test_stats.py) ───────────────────────
GOLDEN_RATE         = 0.05   # ~5% observed per cell in gold reels
BIG_JOKER_RATE      = 0.15   # ~15% of gold conversions → BigJoker (observed)
SCATTER_RATE        = 0.03   # ~3% per cell (spec target)
FG_TRIGGER_RATE_MIN = 0.005  # minimum 0.5% FG trigger rate expected

RTP_MIN = 0.40   # generous lower bound (small sample, high variance)
RTP_MAX = 1.20   # generous upper bound

STAT_SPIN_COUNT = 100  # spins for statistical tests
