"""
SUPERACE Game Logic Helpers
Re-implements the backend calculation in Python for independent verification.
"""
from config import (
    REELS, ROWS, PAYTABLE_X100, MG_MULTIPLIERS, FG_MULTIPLIERS,
    EMPTY, BIG_JOKER, LITTLE_JOKER, SCATTER, WIN_TOLERANCE
)


# ── Symbol Helpers ────────────────────────────────────────────────────

def to_base(s: int) -> int:
    """Gold symbol → base symbol. e.g. 108 (Gold_Ace) → 8 (Ace)."""
    s = abs(s)
    return s - 100 if 101 <= s <= 108 else s

def is_scatter(s: int) -> bool:
    return abs(s) == SCATTER

def is_joker(s: int) -> bool:
    return abs(s) in (BIG_JOKER, LITTLE_JOKER)

def is_gold(s: int) -> bool:
    return 101 <= abs(s) <= 108

def is_empty(s: int) -> bool:
    return abs(s) == EMPTY

def can_match(sym: int, candidate: int) -> bool:
    """
    Can `sym` count as `candidate` in a Ways evaluation?
    Rules:
      - Scatter never matches anything
      - Empty never matches
      - Joker matches any non-scatter base symbol
      - Gold matches as its base equivalent
    """
    sym = abs(sym)
    if is_scatter(sym) or is_empty(sym):
        return False
    if is_joker(sym):
        return True          # Joker = Wild, matches any base symbol
    return to_base(sym) == candidate


# ── Ways Calculation ──────────────────────────────────────────────────

def ensure_2d_grid(grid: list) -> list:
    """
    Normalise a grid to 2D: grid[reel][row] = int.
    mgTable[i] is already 2D: [[r0c0,r0c1,...], [r1c0,...], ...]
    fgTable[i] is wrapped one extra level: [[[r0c0,...], [r1c0,...], ...]]
    Detect and unwrap the extra level when present.
    """
    if not grid:
        return grid
    first_cell = grid[0][0] if grid[0] else None
    if isinstance(first_cell, (list, tuple)):
        # fgTable format: [actual_5x4_grid] — unwrap one level
        return grid[0]
    return grid


def calculate_ways_win_x100(grid: list) -> tuple:
    """
    Re-compute win (×100, before bet & multiplier) from a raw grid.

    Args:
        grid: grid[reel][row]  — values may be negative (= eliminated cell,
              treat as positive for win calculation)

    Returns:
        (total_win_x100, list_of_combinations)
    """
    grid = ensure_2d_grid(grid)
    # Use ALL base symbols as candidates.
    # Restricting to reel-0 symbols misses combinations where reel 0 only has a
    # Joker (Wild): the Joker can substitute for any base symbol, so every base
    # symbol that continues left-to-right through subsequent reels should count.
    # (BUG-007 fix: original code restricted to reel-0 symbols, causing mismatch
    # when BigJoker in reel 0 acted as Wild for a symbol absent from reel 0.)
    candidates = set(PAYTABLE_X100.keys())

    total_x100 = 0
    combinations = []

    for candidate in candidates:
        counts = []
        for reel in range(REELS):
            cnt = sum(
                1 for row in range(ROWS)
                if can_match(grid[reel][row], candidate)
            )
            if cnt == 0:
                break
            counts.append(cnt)

        if len(counts) < 3:
            continue

        ways = 1
        for c in counts:
            ways *= c

        n_reels = len(counts)
        if candidate in PAYTABLE_X100 and n_reels in PAYTABLE_X100[candidate]:
            pay_x100 = PAYTABLE_X100[candidate][n_reels]
            win_x100 = ways * pay_x100
            total_x100 += win_x100
            combinations.append({
                "symbol": candidate,
                "reels": n_reels,
                "ways": ways,
                "pay_x100": pay_x100,
                "win_x100": win_x100,
            })

    return total_x100, combinations


def get_multiplier(cascade_idx: int, mode: str) -> int:
    """Return the multiplier for cascade_idx in MG or FG mode."""
    table = MG_MULTIPLIERS if mode == "MG" else FG_MULTIPLIERS
    return table[min(cascade_idx, len(table) - 1)]


def calculate_cascade_win(grid: list, bet: float, cascade_idx: int, mode: str) -> float:
    """
    Expected win = (winX100 * bet / 100) * multiplier, rounded to 2 dp.
    """
    win_x100, _ = calculate_ways_win_x100(grid)
    multiplier = get_multiplier(cascade_idx, mode)
    return round(win_x100 * bet / 100 * multiplier, 2)


def verify_cascade(grid: list, bet: float, cascade_idx: int,
                   mode: str, reported_win: float) -> dict:
    """
    Verify a single cascade's reported win against our calculation.
    Returns a result dict with 'ok', 'diff', 'calculated', 'reported'.
    """
    calc = calculate_cascade_win(grid, bet, cascade_idx, mode)
    diff = abs(calc - reported_win)
    return {
        "ok": diff <= WIN_TOLERANCE,
        "calculated": calc,
        "reported": reported_win,
        "diff": diff,
        "multiplier": get_multiplier(cascade_idx, mode),
    }


# ── Grid Inspection Helpers ───────────────────────────────────────────

def count_symbol(grid: list, sym_fn) -> int:
    """Count cells matching a predicate function."""
    return sum(
        1 for reel in range(len(grid))
        for row in range(len(grid[reel]))
        if sym_fn(grid[reel][row])
    )

def find_gold_in_forbidden_reels(grid: list, forbidden: list) -> list:
    grid = ensure_2d_grid(grid)
    """Return list of (reel, row) where gold appears in forbidden reels."""
    violations = []
    for reel in forbidden:
        if reel >= len(grid):
            continue
        for row in range(len(grid[reel])):
            if is_gold(grid[reel][row]):
                violations.append((reel, row, grid[reel][row]))
    return violations

def grid_to_string(grid: list) -> str:
    """Pretty-print a 5×4 grid (columns = reels, rows = rows)."""
    SYM_MAP = {
        0: "  ", 1: "♣ ", 2: "♦ ", 3: "♥ ", 4: "♠ ",
        5: "J ", 6: "Q ", 7: "K ", 8: "A ",
        9: "$$",  # Scatter (corrected from 12, 2026-04-07)
        10: "BJ", 11: "LJ",
        101: "G♣", 102: "G♦", 103: "G♥", 104: "G♠",
        105: "GJ", 106: "GQ", 107: "GK", 108: "GA",
    }
    lines = []
    for row in range(ROWS):
        cells = []
        for reel in range(REELS):
            s = grid[reel][row]
            prefix = "-" if s < 0 else " "
            label = SYM_MAP.get(abs(s), f"{abs(s):2d}")
            cells.append(f"{prefix}{label}")
        lines.append("  ".join(cells))
    return "\n".join(lines)
