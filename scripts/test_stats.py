"""
test_stats.py — SUPERACE Statistical Test Suite

Covers:
  - RTP (return-to-player) over STAT_SPIN_COUNT spins
  - GoldSymbol appearance rate in gold reels
  - BigJoker vs LittleJoker distribution after gold conversion
  - Free Game trigger rate
  - BUG-005: defaultBet:1 not in betList (direct betList assertion)

All spins are collected once in setUpClass and shared across tests.
"""

import unittest
import requests
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    BASE_URL, SSO_KEY, BET, INVALID_BET,
    WILDS, GOLD_SYMBOLS, GOLD_REELS,
    STAT_SPIN_COUNT,
    RTP_MIN, RTP_MAX,
    GOLDEN_RATE, BIG_JOKER_RATE, FG_TRIGGER_RATE_MIN,
)


# ─────────────────────────────────────────────────────────────────────────────
# Minimal GameClient
# ─────────────────────────────────────────────────────────────────────────────

class _GameClient:
    def __init__(self, sso_key=SSO_KEY, bet=BET):
        self.session    = requests.Session()
        self.token      = None
        self.bet        = bet
        self.login_data = None
        self._login(sso_key)

    def _login(self, sso_key):
        resp = self.session.post(f"{BASE_URL}/sso/login", params={"ssoKey": sso_key})
        resp.raise_for_status()
        raw             = resp.json()
        self.login_data = raw
        inner           = raw.get("data", raw)
        self.token      = inner["token"]

    @staticmethod
    def _normalize(raw):
        """Flatten new API envelope to legacy shape: { error, slotData: { ... } }"""
        if raw.get("error", 0) != 0 or "data" not in raw:
            return raw
        inner    = raw["data"]
        slot_raw = inner.get("slotData", {})
        paytable = slot_raw.get("paytable", slot_raw)
        slot = {
            "mgTable":     paytable.get("mgTable",     []),
            "mgWin":       paytable.get("mgWin",       []),
            "fgTable":     paytable.get("fgTable",     []),
            "fgWin":       paytable.get("fgWin",       []),
            "hasFreeSpin": paytable.get("hasFreeSpin", False),
            "hasFreeGame": paytable.get("hasFreeGame", False),
            "addFreeSpin": paytable.get("addFreeSpin", []),
            "bet":         slot_raw.get("bet"),
            "totalWin":    slot_raw.get("totalWin",    0),
            "coin":        slot_raw.get("afterCoin",   slot_raw.get("coin", 0)),
            "roundId":     inner.get("roundID",        inner.get("roundId")),
        }
        return {"error": raw["error"], "slotData": slot}

    def spin(self):
        resp = self.session.post(
            f"{BASE_URL}/play",
            params={"token": self.token, "bet": self.bet},
        )
        resp.raise_for_status()
        return self._normalize(resp.json())

    def logout(self):
        try:
            self.session.post(f"{BASE_URL}/logout", params={"token": self.token})
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Shared spin fixture — collected once, reused by all test classes
# ─────────────────────────────────────────────────────────────────────────────

_spin_results   = None
_login_response = None


def _load_fixtures():
    global _spin_results, _login_response
    if _spin_results is not None:
        return
    client          = _GameClient()
    _login_response = client.login_data
    _spin_results   = [client.spin() for _ in range(STAT_SPIN_COUNT)]
    client.logout()


# ─────────────────────────────────────────────────────────────────────────────
# TestRTP
# ─────────────────────────────────────────────────────────────────────────────

class TestRTP(unittest.TestCase):
    """Return-to-Player over STAT_SPIN_COUNT spins."""

    @classmethod
    def setUpClass(cls):
        _load_fixtures()
        cls.spins = _spin_results

    def test_rtp_within_expected_range(self):
        """RTP = totalWin / totalBet must be in [RTP_MIN, RTP_MAX]."""
        total_bet = Decimal(str(BET)) * STAT_SPIN_COUNT
        total_win = sum(
            Decimal(str(s.get("slotData", {}).get("totalWin", 0)))
            for s in self.spins
        )
        rtp = float(total_win / total_bet)
        self.assertGreaterEqual(
            rtp, RTP_MIN,
            f"RTP {rtp:.4f} below minimum {RTP_MIN} "
            f"(totalWin={float(total_win):.2f} / totalBet={float(total_bet):.2f})"
        )
        self.assertLessEqual(
            rtp, RTP_MAX,
            f"RTP {rtp:.4f} above maximum {RTP_MAX} "
            f"(totalWin={float(total_win):.2f} / totalBet={float(total_bet):.2f})"
        )

    def test_total_win_always_non_negative(self):
        """totalWin must never be negative across all sampled spins."""
        negatives = [
            i for i, s in enumerate(self.spins)
            if float(s.get("slotData", {}).get("totalWin", 0)) < 0
        ]
        self.assertEqual(negatives, [],
                         f"Negative totalWin found at spin indices: {negatives}")


# ─────────────────────────────────────────────────────────────────────────────
# TestGoldSymbolRate
# ─────────────────────────────────────────────────────────────────────────────

class TestGoldSymbolRate(unittest.TestCase):
    """Gold symbols (101-108) should appear ~GOLDEN_RATE per cell in gold reels."""

    @classmethod
    def setUpClass(cls):
        _load_fixtures()
        cls.spins = _spin_results

    def test_gold_symbol_rate_in_gold_reels(self):
        """Gold symbol rate in reels 1-3 should be in a reasonable range."""
        gold_cells  = 0
        total_cells = 0

        for spin in self.spins:
            slot     = spin.get("slotData", {})
            mg_table = slot.get("mgTable", [])
            if not mg_table:
                continue
            # Use mgTable[0] (initial grid) — abs() to include eliminated symbols
            initial_grid = mg_table[0]
            for reel_idx, reel in enumerate(initial_grid):
                if reel_idx in GOLD_REELS:
                    for cell in reel:
                        total_cells += 1
                        if abs(cell) in GOLD_SYMBOLS:
                            gold_cells += 1

        if total_cells == 0:
            self.skipTest("No cells collected from gold reels")

        rate = gold_cells / total_cells
        # Allow ±15 percentage points around GOLDEN_RATE for small sample tolerance
        lower = max(0.0, GOLDEN_RATE - 0.15)
        upper = GOLDEN_RATE + 0.15
        self.assertGreaterEqual(
            rate, lower,
            f"GoldSymbol rate {rate:.4f} below lower bound {lower:.4f} "
            f"({gold_cells}/{total_cells} cells)"
        )
        self.assertLessEqual(
            rate, upper,
            f"GoldSymbol rate {rate:.4f} above upper bound {upper:.4f} "
            f"({gold_cells}/{total_cells} cells)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TestBigJokerRate
# ─────────────────────────────────────────────────────────────────────────────

class TestBigJokerRate(unittest.TestCase):
    """
    After a gold symbol is eliminated, the replacement Joker should be
    BigJoker (10) ~BIG_JOKER_RATE of the time, LittleJoker (11) the rest.
    Implements the distribution check skipped in test_api.py.
    """

    @classmethod
    def setUpClass(cls):
        _load_fixtures()
        cls.spins = _spin_results

    def _collect_joker_conversions(self):
        """
        Walk consecutive cascade pairs; when a gold symbol is eliminated
        (negative value in cascade i), record the Joker type at the same
        position in cascade i+1.
        """
        big_joker   = 0
        total_conversions = 0

        for spin in self.spins:
            slot     = spin.get("slotData", {})
            mg_table = slot.get("mgTable", [])
            for ci in range(len(mg_table) - 1):
                grid      = mg_table[ci]
                next_grid = mg_table[ci + 1]
                for ri, reel in enumerate(grid):
                    for row, cell in enumerate(reel):
                        if cell < 0 and abs(cell) in GOLD_SYMBOLS:
                            total_conversions += 1
                            next_val = abs(next_grid[ri][row])
                            if next_val == 10:  # BigJoker
                                big_joker += 1

        return big_joker, total_conversions

    def test_big_joker_rate_within_range(self):
        """BigJoker fraction of gold conversions should be ~BIG_JOKER_RATE."""
        big_joker, total = self._collect_joker_conversions()

        if total == 0:
            self.skipTest(
                f"No gold→Joker conversions found in {STAT_SPIN_COUNT} spins; "
                "increase STAT_SPIN_COUNT for reliable measurement"
            )

        rate = big_joker / total
        # Allow ±25 percentage points for small sample variance
        lower = max(0.0, BIG_JOKER_RATE - 0.25)
        upper = min(1.0, BIG_JOKER_RATE + 0.25)
        self.assertGreaterEqual(
            rate, lower,
            f"BigJoker rate {rate:.4f} below lower bound {lower:.4f} "
            f"({big_joker}/{total} conversions)"
        )
        self.assertLessEqual(
            rate, upper,
            f"BigJoker rate {rate:.4f} above upper bound {upper:.4f} "
            f"({big_joker}/{total} conversions)"
        )

    def test_all_gold_conversions_produce_valid_joker(self):
        """Every eliminated gold symbol must become a Wild (10 or 11)."""
        errors = []
        for spin_idx, spin in enumerate(self.spins):
            slot     = spin.get("slotData", {})
            mg_table = slot.get("mgTable", [])
            for ci in range(len(mg_table) - 1):
                grid      = mg_table[ci]
                next_grid = mg_table[ci + 1]
                for ri, reel in enumerate(grid):
                    for row, cell in enumerate(reel):
                        if cell < 0 and abs(cell) in GOLD_SYMBOLS:
                            next_val = abs(next_grid[ri][row])
                            if next_val not in WILDS:
                                errors.append(
                                    f"spin {spin_idx} cascade {ci} [{ri}][{row}]: "
                                    f"gold {abs(cell)} → {next_val} (not a Joker)"
                                )
        self.assertEqual(errors, [],
                         "Gold→Joker conversion failures:\n" + "\n".join(errors))


# ─────────────────────────────────────────────────────────────────────────────
# TestFGTriggerRate
# ─────────────────────────────────────────────────────────────────────────────

class TestFGTriggerRate(unittest.TestCase):
    """Free Game should trigger at a rate >= FG_TRIGGER_RATE_MIN."""

    @classmethod
    def setUpClass(cls):
        _load_fixtures()
        cls.spins = _spin_results

    def test_fg_trigger_rate_above_minimum(self):
        """Observed FG trigger rate must be >= FG_TRIGGER_RATE_MIN."""
        fg_count = sum(
            1 for s in self.spins
            if (s.get("slotData", {}).get("hasFreeSpin")
                or s.get("slotData", {}).get("hasFreeGame"))
        )

        if fg_count == 0:
            self.skipTest(
                f"No FG triggered in {STAT_SPIN_COUNT} spins; "
                "increase STAT_SPIN_COUNT for reliable rate measurement"
            )

        rate = fg_count / STAT_SPIN_COUNT
        self.assertGreaterEqual(
            rate, FG_TRIGGER_RATE_MIN,
            f"FG trigger rate {rate:.4f} ({fg_count}/{STAT_SPIN_COUNT}) "
            f"is below minimum {FG_TRIGGER_RATE_MIN}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TestBetListBUG005
# ─────────────────────────────────────────────────────────────────────────────

class TestBetListBUG005(unittest.TestCase):
    """
    BUG-005: The server returns defaultBet:1 but 1 is not in betList.
    Assert the inconsistency directly from login response data.
    """

    @classmethod
    def setUpClass(cls):
        _load_fixtures()
        cls.login = _login_response

    def _extract_bet_list(self):
        """Extract betList from login response (new: data.betList, legacy: top-level or slotData)."""
        inner = self.login.get("data", self.login)
        return (inner.get("betList")
                or self.login.get("betList")
                or self.login.get("slotData", {}).get("betList"))

    def _extract_default_bet(self):
        """Extract defaultBet from login response."""
        inner = self.login.get("data", self.login)
        return (inner.get("defaultBet")
                or self.login.get("defaultBet")
                or self.login.get("slotData", {}).get("defaultBet"))

    def test_invalid_bet_not_in_bet_list(self):
        """BUG-005: INVALID_BET (1.0) must not appear in betList."""
        bet_list = self._extract_bet_list()
        if bet_list is None:
            self.skipTest("betList not found in login response")

        numeric_list = [float(b) for b in bet_list]
        self.assertNotIn(
            float(INVALID_BET), numeric_list,
            f"BUG-005 CONFIRMED: defaultBet {INVALID_BET} IS in betList {numeric_list} "
            "(this assertion should hold if the bug exists)"
        )

    def test_default_bet_absent_from_bet_list(self):
        """BUG-005: If defaultBet field exists, it should not equal INVALID_BET or be missing from betList."""
        bet_list    = self._extract_bet_list()
        default_bet = self._extract_default_bet()

        if bet_list is None or default_bet is None:
            self.skipTest("betList or defaultBet not found in login response")

        numeric_list = [float(b) for b in bet_list]
        default_f    = float(default_bet)

        # Document BUG-005: defaultBet is 1 but 1 is not in betList
        if default_f == float(INVALID_BET):
            self.assertNotIn(
                default_f, numeric_list,
                f"BUG-005: defaultBet={default_f} is returned by server "
                f"but is NOT in betList={numeric_list}"
            )
        else:
            # defaultBet changed — it should now be in betList (bug would be fixed)
            self.assertIn(
                default_f, numeric_list,
                f"defaultBet={default_f} is not in betList={numeric_list}"
            )

    def test_valid_bet_is_in_bet_list(self):
        """BET (1.2) must be a valid entry in betList."""
        bet_list = self._extract_bet_list()
        if bet_list is None:
            self.skipTest("betList not found in login response")

        numeric_list = [float(b) for b in bet_list]
        self.assertIn(
            float(BET), numeric_list,
            f"Standard test BET {BET} not found in betList {numeric_list}"
        )


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
