"""
game_logic.py — Independent payout verification logic for SUPERACE QA.

Grid convention: grid[reel_idx][row_idx], 5 reels × 4 rows.
mgTable values:
  - positive  → symbol currently on the board
  - negative  → symbol that was eliminated in this cascade (abs = symbol code)
Payout formula: win = ways × paytable[symbol][reel_count] × bet × cascade_multiplier
"""

from config import PAYTABLE, MG_MULTIPLIERS, FG_MULTIPLIERS, SCATTER, WILDS, GOLD_SYMBOLS


def _abs_grid(grid):
    """Return a copy of the grid with all values as absolute integers."""
    return [[abs(cell) for cell in reel] for reel in grid]


def calculate_ways_for_symbol(grid, symbol):
    """
    Count Ways for a paying symbol across the 5-reel grid.
    Wild (10, 11) substitutes for any non-Scatter paying symbol.

    Returns:
        (ways: int, reel_count: int) — both 0 if chain is < 3 reels.
    """
    counts = []
    for reel in grid:
        cnt = sum(1 for cell in reel if cell == symbol or cell in WILDS)
        if cnt == 0:
            break
        counts.append(cnt)

    if len(counts) < 3:
        return 0, 0

    ways = 1
    for c in counts:
        ways *= c
    return ways, len(counts)


def calculate_cascade_win(grid, bet, cascade_index, is_fg=False):
    """
    Independently calculate the expected win for one cascade.

    Args:
        grid         : raw grid from mgTable (negative values OK — abs() applied)
        bet          : bet amount (float)
        cascade_index: 0-based cascade index for multiplier lookup
        is_fg        : use FG multipliers if True

    Returns:
        float: expected win amount, rounded to 2 decimal places.
    """
    multipliers = FG_MULTIPLIERS if is_fg else MG_MULTIPLIERS
    multiplier  = multipliers[min(cascade_index, len(multipliers) - 1)]

    abs_grid  = _abs_grid(grid)
    total_win = 0.0

    for symbol in PAYTABLE:
        ways, reel_count = calculate_ways_for_symbol(abs_grid, symbol)
        if ways > 0:
            payout     = PAYTABLE[symbol][reel_count]
            total_win += ways * payout * bet * multiplier

    return round(total_win, 2)


def verify_payout(spin_data, bet, tolerance=0.02):
    """
    Verify every MG cascade win against independent calculation.

    Returns:
        list of (cascade_idx, expected, actual, ok) tuples.
    """
    slot     = spin_data.get("slotData", {})
    mg_table = slot.get("mgTable", [])
    mg_win   = slot.get("mgWin",   [])

    results = []
    for i, (grid, reported) in enumerate(zip(mg_table, mg_win)):
        expected = calculate_cascade_win(grid, bet, i, is_fg=False)
        actual   = float(reported)
        ok       = abs(expected - actual) <= tolerance
        results.append((i, expected, actual, ok))
    return results


def ensure_2d_grid(table):
    """
    Normalize mgTable / fgTable to a consistent list-of-grids format.
    Handles the extra nesting that BUG-008 introduced in fgTable.
    """
    if not table:
        return []
    first = table[0]
    if (isinstance(first, list) and first and
            isinstance(first[0], list) and first[0] and
            isinstance(first[0][0], list)):
        return [item for sublist in table for item in sublist]
    return table
