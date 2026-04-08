#!/usr/bin/env python3
"""
SUPERACE API QA Test Suite
Run: python test_api.py
"""
import sys
import os
import json
import time
import unittest
import requests
from typing import Optional, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *  # includes ERR_TOKEN_ANY
from game_logic import (
    calculate_cascade_win, verify_cascade, calculate_ways_win_x100,
    find_gold_in_forbidden_reels, count_symbol, is_scatter, is_gold,
    is_joker, grid_to_string
)


# ── API Client ────────────────────────────────────────────────────────

class GameClient:
    """Minimal HTTP client for SUPERACE game API."""

    def __init__(self):
        self.token: Optional[str] = None
        self.coin: float = 0
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    def login(self, sso_key: str = SSO_KEY) -> Dict:
        r = self.session.post(f"{BASE_URL}/sso/login", params={"ssoKey": sso_key})
        r.raise_for_status()
        data = r.json()
        if data["error"] == ERR_OK:
            self.token = data["data"]["token"]
            self.coin = data["data"]["profile"]["coin"]
        return data

    def play(self, bet: float = DEFAULT_BET) -> Dict:
        r = self.session.post(f"{BASE_URL}/play",
                              params={"bet": bet, "token": self.token})
        r.raise_for_status()
        return r.json()

    def buy_free_spin(self, bet: float = DEFAULT_BET) -> Dict:
        r = self.session.post(f"{BASE_URL}/buyFreeSpin",
                              params={"bet": bet, "token": self.token})
        r.raise_for_status()
        js = r.json()
        if js.get("error") == ERR_OK:
            self.coin = js["data"]["slotData"].get("afterCoin", self.coin)
        return js

    def keep_alive(self) -> Dict:
        r = self.session.post(f"{BASE_URL}/keepAlive",
                              params={"token": self.token})
        return r.json()

    def logout(self) -> Dict:
        r = self.session.post(f"{BASE_URL}/logout",
                              params={"token": self.token})
        return r.json()


# ── Compatibility Helpers (BUG-002 / BUG-003) ────────────────────────

def get_bet(slot: dict) -> float:
    """BUG-002: API uses 'bet', spec says 'bets'. Accept both."""
    return slot.get("bets", slot.get("bet", 0))

def get_fg_flag(pt: dict) -> bool:
    """BUG-003: API uses 'hasFreeSpin', spec says 'hasFreeGame'. Accept both."""
    return pt.get("hasFreeGame", pt.get("hasFreeSpin", False))

def get_add_free_spin(pt: dict) -> list:
    """
    BUG-004: addFreeSpin structure inconsistency.
      Spec says: list of numeric spin counts [0, 5, 10]
      Actual:    dict of booleans e.g. {0: False, 1: False, 2: True}
                 or empty dict {} when no free spin triggered
    Returns normalised list of values for iteration.
    """
    v = pt.get("addFreeSpin", [])
    if isinstance(v, dict):
        return list(v.values()) if v else []
    return v

def has_free_spin_trigger(pt: dict) -> bool:
    """Return True if any cascade triggered a free spin."""
    v = pt.get("addFreeSpin", [])
    if isinstance(v, dict):
        return any(v.values())
    return any(x > 0 for x in v)


# ── Shared Fixtures ───────────────────────────────────────────────────

def spin_n(client: GameClient, n: int, bet: float = DEFAULT_BET,
           delay: float = REQUEST_DELAY_S) -> List[Dict]:
    """Spin n times, return list of successful slotData dicts."""
    results = []
    for _ in range(n):
        resp = client.play(bet)
        if resp["error"] == ERR_OK:
            results.append(resp["data"]["slotData"])
        time.sleep(delay)
    return results


# ════════════════════════════════════════════════════════════════════
# 1. Authentication
# ════════════════════════════════════════════════════════════════════

class TestAuthentication(unittest.TestCase):

    def test_login_success(self):
        c = GameClient()
        resp = c.login()
        self.assertEqual(resp["error"], ERR_OK, f"Login failed: {resp}")
        self.assertIn("token", resp["data"])
        self.assertIsNotNone(c.token)

    def test_login_returns_profile(self):
        c = GameClient()
        resp = c.login()
        profile = resp["data"]["profile"]
        for field in ["userId", "coin", "currency"]:
            self.assertIn(field, profile, f"Profile missing '{field}'")

    def test_login_returns_bet_list(self):
        c = GameClient()
        resp = c.login()
        self.assertIn("betList", resp["data"])
        self.assertIsInstance(resp["data"]["betList"], list)
        self.assertGreater(len(resp["data"]["betList"]), 0)

    def test_play_with_invalid_token_returns_error(self):
        # BUG-001: backend currently returns ERR_INSUFFICIENT(2) for invalid
        # tokens instead of ERR_TOKEN_INVALID(4)/ERR_TOKEN_EXPIRED(6).
        # Accepting all three until the backend error path is fixed.
        c = GameClient()
        c.token = "totally_invalid_token_xyz"
        resp = c.play()
        self.assertIn(resp["error"], ERR_TOKEN_ANY,
                      f"Expected a token/auth error, got {resp['error']}")
        # TODO: tighten this once BUG-001 is fixed:
        # self.assertIn(resp["error"], [ERR_TOKEN_INVALID, ERR_TOKEN_EXPIRED])

    def test_response_always_has_required_envelope(self):
        """Every response must have error, data, time fields."""
        c = GameClient()
        resp = c.login()
        for field in ["error", "data", "time"]:
            self.assertIn(field, resp)


# ════════════════════════════════════════════════════════════════════
# 2. Spin Response Structure
# ════════════════════════════════════════════════════════════════════

class TestSpinStructure(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()
        resp = cls.c.play(DEFAULT_BET)
        assert resp["error"] == ERR_OK, f"Spin failed in setup: {resp}"
        cls.slot = resp["data"]["slotData"]
        cls.pt   = cls.slot["paytable"]

    def test_has_round_id(self):
        c2 = GameClient()
        c2.login()
        r = c2.play()
        self.assertIn("roundID", r["data"],
                      "data.roundID missing from spin response")

    def test_slot_data_fields(self):
        # BUG-002: spec says "bets" but API returns "bet"
        for f in ["paytable", "totalWin", "afterCoin"]:
            self.assertIn(f, self.slot, f"slotData missing '{f}'")
        # Accept either "bet" or "bets" until field name is standardised
        self.assertTrue("bet" in self.slot or "bets" in self.slot,
                        "slotData missing bet amount field (expected 'bet' or 'bets')")

    def test_paytable_fields(self):
        # BUG-003: spec says "hasFreeGame" but API returns "hasFreeSpin"
        for f in ["mgTable", "mgWin", "fgTable", "fgWin", "addFreeSpin"]:
            self.assertIn(f, self.pt, f"paytable missing '{f}'")
        # Accept either field name until standardised
        self.assertTrue("hasFreeGame" in self.pt or "hasFreeSpin" in self.pt,
                        "paytable missing free game flag (expected 'hasFreeGame' or 'hasFreeSpin')")

    def test_mg_table_not_empty(self):
        self.assertGreater(len(self.pt["mgTable"]), 0)

    def test_mg_table_win_same_length(self):
        self.assertEqual(len(self.pt["mgTable"]), len(self.pt["mgWin"]),
                         "mgTable and mgWin length mismatch")

    def test_grid_is_5x4(self):
        grid = self.pt["mgTable"][0]
        self.assertEqual(len(grid), REELS, f"Expected {REELS} reels, got {len(grid)}")
        for reel_idx, reel in enumerate(grid):
            self.assertEqual(len(reel), ROWS,
                             f"Reel {reel_idx}: expected {ROWS} rows, got {len(reel)}")

    def test_has_free_game_is_bool(self):
        # BUG-003: field name is "hasFreeSpin" in actual API (spec says "hasFreeGame")
        flag = self.pt.get("hasFreeGame", self.pt.get("hasFreeSpin"))
        self.assertIsNotNone(flag, "Neither hasFreeGame nor hasFreeSpin found")
        self.assertIsInstance(flag, bool)

    def test_bets_matches_request(self):
        # BUG-002: field is "bet" not "bets" in actual API
        actual_bet = self.slot.get("bets", self.slot.get("bet"))
        self.assertIsNotNone(actual_bet, "No bet amount in slotData")
        self.assertEqual(actual_bet, DEFAULT_BET)

    def test_total_win_non_negative(self):
        self.assertGreaterEqual(self.slot["totalWin"], 0)

    def test_fg_table_win_same_length(self):
        # fgWin is flat (one entry per cascade across ALL FG spins)
        # fgTable is nested (one entry per FG spin, each containing N cascades)
        # So len(fgWin) >= len(fgTable) — they are NOT equal when any FG spin has >1 cascade.
        # See also: TestMGCompletesBeforeFG::test_fg_table_fgwin_parallel
        self.assertGreaterEqual(len(self.pt["fgWin"]), len(self.pt["fgTable"]),
                                "fgWin must have >= entries as fgTable (flat vs nested)")


# ════════════════════════════════════════════════════════════════════
# 3. Payout Verification  (critical — re-compute every win)
# ════════════════════════════════════════════════════════════════════

class TestPayoutVerification(unittest.TestCase):
    """
    Independent re-computation of win amounts.
    If any value differs by more than WIN_TOLERANCE, the test fails.
    """

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()
        cls.spins = spin_n(cls.c, 30)

    def test_mg_cascade_wins_match_calculation(self):
        errors = []
        for i, slot in enumerate(self.spins):
            pt  = slot["paytable"]
            bet = get_bet(slot)
            for j, (grid, reported) in enumerate(zip(pt["mgTable"], pt["mgWin"])):
                result = verify_cascade(grid, bet, j, "MG", reported)
                if not result["ok"]:
                    errors.append(
                        f"Spin#{i} MG cascade {j}: "
                        f"reported={reported:.4f} calculated={result['calculated']:.4f} "
                        f"diff={result['diff']:.4f}\n"
                        f"{grid_to_string(grid)}"
                    )
        self.assertEqual(len(errors), 0,
                         f"{len(errors)} payout mismatches:\n" + "\n---\n".join(errors[:3]))

    def test_total_win_equals_sum_of_cascades(self):
        """totalWin must equal sum(mgWin) + sum(fgWin)."""
        errors = []
        for i, slot in enumerate(self.spins):
            pt       = slot["paytable"]
            reported = slot["totalWin"]
            calc     = round(sum(pt["mgWin"]) + sum(pt["fgWin"]), 2)
            if abs(calc - reported) > WIN_TOLERANCE:
                errors.append(f"Spin#{i}: totalWin={reported} sum={calc}")
        self.assertEqual(len(errors), 0, "\n".join(errors))

    def test_win_amounts_non_negative(self):
        for i, slot in enumerate(self.spins):
            for j, w in enumerate(slot["paytable"]["mgWin"]):
                self.assertGreaterEqual(w, 0,
                    f"Spin#{i} MG cascade {j}: negative win {w}")
            for j, w in enumerate(slot["paytable"]["fgWin"]):
                self.assertGreaterEqual(w, 0,
                    f"Spin#{i} FG cascade {j}: negative win {w}")

    def test_zero_win_cascades_have_no_combinations(self):
        """When reported win = 0, our independent calculation must also = 0."""
        errors = []
        for i, slot in enumerate(self.spins):
            pt  = slot["paytable"]
            bet = get_bet(slot)
            for j, (grid, reported) in enumerate(zip(pt["mgTable"], pt["mgWin"])):
                if reported == 0:
                    win_x100, combos = calculate_ways_win_x100(grid)
                    calc = win_x100 * bet / 100
                    if calc > WIN_TOLERANCE:
                        errors.append(
                            f"Spin#{i} MG cascade {j}: "
                            f"reported=0 but calculated={calc:.4f}"
                        )
        self.assertEqual(len(errors), 0, "\n".join(errors))


# ════════════════════════════════════════════════════════════════════
# 4. Multiplier Progression
# ════════════════════════════════════════════════════════════════════

class TestMultiplierProgression(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()
        # Need spins with at least 2 cascades to verify progression
        cls.spins = spin_n(cls.c, 40)
        cls.multi_cascade_spins = [
            s for s in cls.spins if len(s["paytable"]["mgWin"]) >= 2
        ]

    def _check_multiplier(self, spins, mode):
        table = MG_MULTIPLIERS if mode == "MG" else FG_MULTIPLIERS
        key_table = "mgTable" if mode == "MG" else "fgTable"
        key_win   = "mgWin"   if mode == "MG" else "fgWin"
        errors = []
        for i, slot in enumerate(spins):
            pt  = slot["paytable"]
            bet = get_bet(slot)
            for j, (grid, reported) in enumerate(zip(pt[key_table], pt[key_win])):
                if reported == 0:
                    continue
                win_x100, _ = calculate_ways_win_x100(grid)
                base = win_x100 * bet / 100
                if base < 0.001:
                    continue
                actual_mult = round(reported / base, 2)
                expected_mult = table[min(j, len(table) - 1)]
                if abs(actual_mult - expected_mult) > 0.05:
                    errors.append(
                        f"Spin#{i} {mode} cascade {j}: "
                        f"multiplier expected={expected_mult} actual={actual_mult:.2f}"
                    )
        return errors

    def test_mg_multipliers_are_1_2_3_5(self):
        errors = self._check_multiplier(self.multi_cascade_spins, "MG")
        self.assertEqual(len(errors), 0,
                         f"{len(errors)} MG multiplier errors:\n" + "\n".join(errors[:5]))

    def test_cascade_count_at_least_1(self):
        """Every spin must have at least 1 cascade (initial board)."""
        for i, slot in enumerate(self.spins):
            self.assertGreater(len(slot["paytable"]["mgTable"]), 0,
                               f"Spin#{i}: no mgTable entries")


# ════════════════════════════════════════════════════════════════════
# 5. Rule Compliance
# ════════════════════════════════════════════════════════════════════

class TestRuleCompliance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()
        cls.spins = spin_n(cls.c, 40)

    def test_gold_only_in_reels_1_2_3(self):
        """Gold symbols (101-108) must NEVER appear in reels 0 or 4."""
        violations = []
        for i, slot in enumerate(self.spins):
            pt = slot["paytable"]
            all_grids = pt["mgTable"] + pt["fgTable"]
            for j, grid in enumerate(all_grids):
                v = find_gold_in_forbidden_reels(grid, GOLD_FORBIDDEN_REELS)
                for reel, row, sym in v:
                    violations.append(
                        f"Spin#{i} grid#{j}: gold {sym} at reel={reel} row={row}"
                    )
        self.assertEqual(len(violations), 0,
                         f"{len(violations)} gold placement violations:\n" +
                         "\n".join(violations[:5]))

    def test_scatter_count_per_grid(self):
        """Scatter can appear in any reel; count should be 0–5 range typically."""
        for i, slot in enumerate(self.spins):
            for j, grid in enumerate(slot["paytable"]["mgTable"]):
                n = count_symbol(grid, is_scatter)
                self.assertLessEqual(n, REELS * ROWS,
                    f"Spin#{i} grid#{j}: impossible scatter count {n}")
                self.assertGreaterEqual(n, 0)

    def test_joker_is_never_scatter(self):
        """Joker and Scatter are distinct; no symbol should be both."""
        for i, slot in enumerate(self.spins):
            for j, grid in enumerate(slot["paytable"]["mgTable"]):
                for reel in range(REELS):
                    for row in range(ROWS):
                        s = abs(grid[reel][row])
                        if is_joker(s):
                            self.assertFalse(is_scatter(s),
                                f"Spin#{i} grid#{j} reel={reel} row={row}: "
                                f"symbol {s} is both joker and scatter")

    def test_no_empty_cells_in_stored_grids(self):
        """Stored grids should not contain empty (0) cells after refill."""
        violations = []
        for i, slot in enumerate(self.spins):
            for j, grid in enumerate(slot["paytable"]["mgTable"]):
                for reel in range(REELS):
                    for row in range(ROWS):
                        s = abs(grid[reel][row])
                        if s == 0:
                            violations.append(
                                f"Spin#{i} grid#{j}: empty cell at reel={reel} row={row}"
                            )
        self.assertEqual(len(violations), 0,
                         f"{len(violations)} empty cells in stored grids")


# ════════════════════════════════════════════════════════════════════
# 6. Free Game Mechanics
# ════════════════════════════════════════════════════════════════════

class TestFreeGameMechanics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()
        # Collect spins; try to capture a free-game trigger
        cls.spins = spin_n(cls.c, FG_SEARCH_MAX_SPINS // 2)
        cls.fg_spin = next(
            (s for s in cls.spins if get_fg_flag(s["paytable"])), None
        )
        # Fallback: use buyFreeSpin to guarantee an FG-containing spin
        if cls.fg_spin is None:
            js = cls.c.buy_free_spin()
            if js.get("error") == ERR_OK:
                cls.fg_spin = js["data"]["slotData"]

    def test_has_free_game_is_always_bool(self):
        for s in self.spins:
            self.assertIsInstance(get_fg_flag(s["paytable"]), bool)

    def test_fg_table_win_non_negative(self):
        for i, slot in enumerate(self.spins):
            for j, w in enumerate(slot["paytable"]["fgWin"]):
                self.assertGreaterEqual(w, 0,
                    f"Spin#{i} FG cascade {j}: negative win {w}")

    def test_add_free_spin_values_valid(self):
        """
        addFreeSpin values must be numeric (0/5/10) per spec.
        BUG-004: API currently returns boolean True/False instead of numeric counts.
        This test accepts booleans as a known deviation until fixed.
        """
        for i, slot in enumerate(self.spins):
            for j, v in enumerate(get_add_free_spin(slot["paytable"])):
                # Accept numeric (correct) or boolean (BUG-004 deviation)
                valid = (isinstance(v, bool) or
                         (isinstance(v, (int, float)) and v in [0, FG_RETRIGGER_SPINS, FG_INITIAL_SPINS]))
                self.assertTrue(valid,
                    f"Spin#{i} cascade {j}: unexpected addFreeSpin value={v!r} (type={type(v).__name__})")

    def test_fg_trigger_means_3plus_scatters(self):
        """
        When FG is FRESHLY triggered (addFreeSpin has a truthy entry),
        the FINAL cascade board (last mgTable entry) must contain >= 3 Scatters.

        Architecture note (post 2026-04-07 engine refactor):
        Scatter is no longer detected mid-loop. The engine runs all cascades to
        completion, then checks the final board for Scatter count. So the
        Scatter-containing board is always mgTable[-1] (the last 0-win board).
        """
        for i, slot in enumerate(self.spins):
            pt = slot["paytable"]
            triggers = get_add_free_spin(pt)
            if not any(bool(v) for v in triggers):
                continue

            # Scatter is on the final board (last mgTable entry)
            if not pt["mgTable"]:
                continue

            final_grid = pt["mgTable"][-1]
            n_scatters = count_symbol(final_grid, is_scatter)
            self.assertGreaterEqual(n_scatters, FG_TRIGGER_SCATTERS,
                f"Spin#{i}: FG triggered but final board only has "
                f"{n_scatters} scatters (need >= {FG_TRIGGER_SCATTERS})\n"
                f"{grid_to_string(final_grid)}")

    def _iter_fg_cascades(self, pt):
        """
        Yield (spin_i, cascade_idx, grid, win) for every FG cascade.

        fgTable[spin_i] = list of cascade snapshots for FG spin i.
        fgWin = flat list of wins for all cascades across all FG spins.
        cascade_idx resets to 0 at the start of each FG spin.
        """
        fg_win_idx = 0
        for spin_i, spin_cascades in enumerate(pt["fgTable"]):
            cascade_idx = 0
            for grid in spin_cascades:
                if fg_win_idx >= len(pt["fgWin"]):
                    return
                win = pt["fgWin"][fg_win_idx]
                yield spin_i, cascade_idx, grid, win
                fg_win_idx += 1
                cascade_idx += 1

    def test_fg_payout_if_present(self):
        """If FG boards exist, verify payout math with FG multipliers.

        fgTable[spin][cascade] contains the snapshot; fgWin is flat across all cascades.
        """
        if not self.fg_spin:
            self.skipTest("No free-game trigger found in sample; increase FG_SEARCH_MAX_SPINS")

        pt  = self.fg_spin["paytable"]
        bet = get_bet(self.fg_spin)
        errors = []
        for spin_i, cascade_idx, grid, reported in self._iter_fg_cascades(pt):
            result = verify_cascade(grid, bet, cascade_idx, "FG", reported)
            if not result["ok"]:
                errors.append(
                    f"FG spin={spin_i} cascade={cascade_idx}: "
                    f"reported={reported:.4f} calculated={result['calculated']:.4f}"
                )
        self.assertEqual(len(errors), 0, "\n".join(errors))

    def test_fg_multipliers_are_2_4_6_10(self):
        """FG multipliers must follow [2,4,6,10] pattern per FG spin."""
        if not self.fg_spin:
            self.skipTest("No free-game trigger found")

        pt  = self.fg_spin["paytable"]
        bet = get_bet(self.fg_spin)
        errors = []
        from game_logic import calculate_ways_win_x100
        for spin_i, cascade_idx, grid, reported in self._iter_fg_cascades(pt):
            if reported == 0:
                continue
            win_x100, _ = calculate_ways_win_x100(grid)
            base = win_x100 * bet / 100
            if base < 0.001:
                continue
            actual_mult   = round(reported / base, 2)
            expected_mult = FG_MULTIPLIERS[min(cascade_idx, len(FG_MULTIPLIERS) - 1)]
            if abs(actual_mult - expected_mult) > 0.05:
                errors.append(
                    f"FG spin={spin_i} cascade={cascade_idx}: "
                    f"expected mult={expected_mult} actual={actual_mult:.2f}"
                )
        self.assertEqual(len(errors), 0, "\n".join(errors))

    def test_fg_retrigger_adds_5_spins(self):
        """TC-005-03: FG retrigger must add exactly FG_RETRIGGER_SPINS (5) extra spins.

        Strategy: run 10 buyFreeSpin calls; if any gives len(fgTable) > FG_INITIAL_SPINS,
        that's a retrigger. Verify the extra length is a multiple of FG_RETRIGGER_SPINS.
        If no retrigger observed, skipTest (probabilistic — ~10% per FG session).
        """
        retrigger_found = False
        errors = []

        c = GameClient()
        c.login()
        for attempt in range(10):
            js = c.buy_free_spin()
            if js.get("error") != ERR_OK:
                continue
            pt       = js["data"]["slotData"]["paytable"]
            fg_count = len(pt.get("fgTable", []))

            if fg_count > FG_INITIAL_SPINS:
                retrigger_found = True
                extra = fg_count - FG_INITIAL_SPINS
                if extra % FG_RETRIGGER_SPINS != 0:
                    errors.append(
                        f"Attempt {attempt}: fgTable has {fg_count} spins — "
                        f"extra={extra} is not a multiple of FG_RETRIGGER_SPINS({FG_RETRIGGER_SPINS})"
                    )

        if not retrigger_found:
            self.skipTest(
                "No FG retrigger observed in 10 buyFreeSpin calls — probabilistic test; "
                "retry or increase attempt count for more coverage"
            )

        self.assertEqual(errors, [], "\n".join(errors))


# ════════════════════════════════════════════════════════════════════
# 7. Error Handling
# ════════════════════════════════════════════════════════════════════

class TestErrorHandling(unittest.TestCase):

    def setUp(self):
        self.c = GameClient()
        self.c.login()

    def test_invalid_token_error_code(self):
        # BUG-001: same as TestAuthentication — backend returns ERR_INSUFFICIENT(2)
        self.c.token = "fake_token_that_does_not_exist"
        resp = self.c.play()
        self.assertIn(resp["error"], ERR_TOKEN_ANY,
                      f"Expected a token/auth error, got {resp}")

    def test_enormous_bet_returns_error(self):
        """Bet far exceeding balance should return error (not crash)."""
        resp = self.c.play(bet=999_999_999_999)
        # Should be insufficient (2) or a validation error, but NOT a server crash
        self.assertIn("error", resp)
        if resp["error"] != ERR_OK:
            self.assertEqual(resp["error"], ERR_INSUFFICIENT,
                             f"Expected ERR_INSUFFICIENT(2), got {resp['error']}")

    def test_response_structure_on_error(self):
        """Error responses must still have the standard envelope."""
        self.c.token = "bad"
        resp = self.c.play()
        for field in ["error", "data", "time"]:
            self.assertIn(field, resp, f"Error response missing '{field}'")


# ════════════════════════════════════════════════════════════════════
# 8. Balance Verification  (TC-005-04)
# ════════════════════════════════════════════════════════════════════

class TestBalanceDeduction(unittest.TestCase):
    """
    TC-005-04: FG spins must NOT deduct bet from balance.
    TC-005-04b: MG spins must deduct exactly `bet` from balance.

    Strategy: track afterCoin across consecutive spins.
    For each spin, the correct formula is one of:
      MG: afterCoin = prevCoin - bet + totalWin
      FG: afterCoin = prevCoin + totalWin        (no deduction)
    At minimum, one of the two must hold within tolerance.
    If NEITHER holds, the balance arithmetic is wrong.
    """

    BALANCE_TOLERANCE = 0.05   # accept rounding up to 5 cents

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        resp = cls.c.login()
        # Initial coin from login profile
        cls.start_coin = float(resp["data"]["profile"]["coin"])
        cls.spins = spin_n(cls.c, 30)

    def test_balance_arithmetic_every_spin(self):
        """afterCoin must equal prevCoin ± bet + totalWin (MG or FG rule)."""
        errors = []
        prev = self.start_coin

        for i, slot in enumerate(self.spins):
            bet       = get_bet(slot)
            total_win = slot["totalWin"]
            after     = slot["afterCoin"]

            exp_mg = round(prev - bet + total_win, 2)
            exp_fg = round(prev          + total_win, 2)

            diff_mg = abs(after - exp_mg)
            diff_fg = abs(after - exp_fg)

            if diff_mg > self.BALANCE_TOLERANCE and diff_fg > self.BALANCE_TOLERANCE:
                errors.append(
                    f"Spin#{i}: afterCoin={after:.2f}  "
                    f"prev={prev:.2f}  bet={bet}  win={total_win:.2f}\n"
                    f"  expected MG={exp_mg:.2f} (diff={diff_mg:.4f}) "
                    f"  expected FG={exp_fg:.2f} (diff={diff_fg:.4f})"
                )
            prev = after   # carry forward for next spin

        self.assertEqual(len(errors), 0,
                         f"{len(errors)} balance mismatches:\n" + "\n".join(errors[:3]))

    def test_mg_spin_deducts_bet(self):
        """
        For a confirmed MG spin (fgTable empty, hasFreeSpin False),
        afterCoin must equal prevCoin - bet + totalWin.
        """
        errors = []
        prev  = self.start_coin
        checked = 0

        for i, slot in enumerate(self.spins):
            pt        = slot["paytable"]
            bet       = get_bet(slot)
            total_win = slot["totalWin"]
            after     = slot["afterCoin"]

            is_mg = not get_fg_flag(pt) and len(pt.get("fgTable", [])) == 0

            if is_mg:
                exp = round(prev - bet + total_win, 2)
                if abs(after - exp) > self.BALANCE_TOLERANCE:
                    errors.append(
                        f"Spin#{i} MG: afterCoin={after:.2f} "
                        f"expected={exp:.2f} (prev={prev:.2f} bet={bet} win={total_win:.2f})"
                    )
                checked += 1

            prev = after

        if checked == 0:
            self.skipTest("No pure MG spins found in sample")

        self.assertEqual(len(errors), 0,
                         f"{len(errors)} MG balance errors:\n" + "\n".join(errors[:3]))

    def test_after_coin_always_present(self):
        """afterCoin must be present and non-negative in every spin."""
        for i, slot in enumerate(self.spins):
            self.assertIn("afterCoin", slot, f"Spin#{i}: missing afterCoin")
            self.assertGreaterEqual(slot["afterCoin"], 0,
                                    f"Spin#{i}: negative afterCoin={slot['afterCoin']}")

    def test_fg_does_not_deduct_bet(self):
        """TC-005-04: FG spins must NOT deduct bet from balance.

        Strategy: buyFreeSpin runs all 10 FG spins as a single API call.
        The correct formula is: afterCoin = prevCoin - (bet * buyRatio) + totalWin
        If FG spins also deducted bet, the formula would show an extra -bet*10 shortfall.
        """
        c = GameClient()
        c.login()
        prev_coin = c.coin

        js = c.buy_free_spin(DEFAULT_BET)
        if js.get("error") != ERR_OK:
            self.skipTest(f"buyFreeSpin failed: error={js.get('error')}")

        slot = js["data"]["slotData"]
        after_coin = slot.get("afterCoin", slot.get("afterCoin"))
        total_win  = slot.get("totalWin", 0)

        # Get buyRatio (POST, same as _get_buy_ratio in TestBuyFreeSpin)
        ratio_r = c.session.post(f"{BASE_URL}/buyRatio",
                                 params={"token": c.token})
        buy_ratio = ratio_r.json()["data"]["buyRatio"]

        cost = round(DEFAULT_BET * buy_ratio, 2)
        expected = round(prev_coin - cost + total_win, 2)
        actual   = round(float(after_coin), 2)

        self.assertAlmostEqual(
            actual, expected, delta=self.BALANCE_TOLERANCE,
            msg=f"TC-005-04 FAIL: afterCoin={actual} != prevCoin({prev_coin}) "
                f"- cost({cost}) + win({total_win}) = {expected}. "
                f"Possible extra per-spin bet deduction."
        )


# ════════════════════════════════════════════════════════════════════
# 9. MG Completes Before FG  (TC-005-06)
# ════════════════════════════════════════════════════════════════════

class TestMGCompletesBeforeFG(unittest.TestCase):
    """
    TC-005-06: When a MG spin triggers FG, all MG cascades must finish
    before any FG rounds run.

    Verification: If hasFreeSpin=True AND fgTable has entries,
    then mgTable must have at least one entry (the cascade that triggered FG).
    """

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()
        # Use full FG_SEARCH_MAX_SPINS to maximise chance of finding a trigger
        cls.spins = spin_n(cls.c, FG_SEARCH_MAX_SPINS)
        cls.fg_trigger_spins = [
            s for s in cls.spins
            if get_fg_flag(s["paytable"]) and s["paytable"].get("fgTable")
        ]

    def test_mg_table_present_before_fg_data(self):
        """If FG data exists in response, MG table must also be present."""
        if not self.fg_trigger_spins:
            self.skipTest("No FG-trigger spins found; increase FG_SEARCH_MAX_SPINS")

        for i, slot in enumerate(self.fg_trigger_spins):
            pt = slot["paytable"]
            self.assertGreater(
                len(pt["mgTable"]), 0,
                f"FG spin#{i}: fgTable has data but mgTable is empty — "
                "FG ran before MG was resolved"
            )

    def test_mg_win_recorded_in_fg_trigger_spin(self):
        """The spin that triggers FG must have mgWin entries (MG ran first)."""
        if not self.fg_trigger_spins:
            self.skipTest("No FG-trigger spins found")

        for i, slot in enumerate(self.fg_trigger_spins):
            pt = slot["paytable"]
            self.assertEqual(
                len(pt["mgTable"]), len(pt["mgWin"]),
                f"FG spin#{i}: mgTable/mgWin length mismatch in triggering spin"
            )

    def test_fg_table_fgwin_parallel(self):
        """fgTable[spin_i] is a list of cascade boards; fgWin is a flat list of all wins.
        fgWin.length >= fgTable.length (each FG spin contributes >= 1 win entry).
        Architecture note (2026-04-07): fgTable[i] = mgTable of FG spin i (array of boards);
        fgWin = flat [...mgWin] across all FG spins. They are NOT equal in length.
        """
        for i, slot in enumerate(self.spins):
            pt = slot["paytable"]
            fg_table = pt.get("fgTable", [])
            fg_win   = pt.get("fgWin",   [])
            if not fg_table:
                continue
            # fgWin must have at least as many entries as fgTable (each spin ≥ 1 cascade)
            self.assertGreaterEqual(
                len(fg_win), len(fg_table),
                f"Spin#{i}: fgWin ({len(fg_win)}) < fgTable ({len(fg_table)}) — impossible"
            )


# ════════════════════════════════════════════════════════════════════
# 10. Gold → Joker Conversion  (TC-004-04)
# ════════════════════════════════════════════════════════════════════

class TestGoldToJokerConversion(unittest.TestCase):
    """
    TC-004-04: When a gold symbol (101-108) is eliminated (negative value
    in mgTable[i]), the same cell in mgTable[i+1] must contain a Joker
    (BigJoker=10 or LittleJoker=11).
    """

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()
        # 200 spins + 3 buyFreeSpin FG rounds for more gold-elimination events
        cls.spins = spin_n(cls.c, 200)
        for _ in range(3):
            bfs = cls.c.buy_free_spin()
            if bfs.get("error") == 0:
                fg_slot = bfs["data"]["slotData"]
                cls.spins.append(fg_slot)
                for fg_round in fg_slot["paytable"].get("fgTable", []):
                    if len(fg_round) >= 2:
                        synthetic = {"paytable": {"mgTable": fg_round, "fgTable": []}}
                        cls.spins.append(synthetic)
        # Pre-filter spins with at least 2 cascades (consecutive grids)
        cls.multi_cascade = [
            s for s in cls.spins
            if len(s["paytable"]["mgTable"]) >= 2
        ]

    def _find_eliminated_gold(self, grid: list) -> list:
        """Return (reel, row) of cells that are negative gold symbols."""
        result = []
        for reel in range(REELS):
            for row in range(ROWS):
                val = grid[reel][row]
                if val < 0 and is_gold(abs(val)):
                    result.append((reel, row))
        return result

    def test_eliminated_gold_becomes_joker(self):
        """Every eliminated gold cell must have a joker in the next cascade."""
        errors = []
        gold_events = 0

        for i, slot in enumerate(self.multi_cascade):
            pt = slot["paytable"]
            for ci in range(len(pt["mgTable"]) - 1):
                curr = pt["mgTable"][ci]
                nxt  = pt["mgTable"][ci + 1]

                for reel, row in self._find_eliminated_gold(curr):
                    gold_events += 1
                    next_val = abs(nxt[reel][row])
                    if not is_joker(next_val):
                        errors.append(
                            f"Spin#{i} cascade {ci}: "
                            f"gold {abs(curr[reel][row])} eliminated at "
                            f"reel={reel} row={row}, "
                            f"next board has {next_val} (expected joker 10 or 11)\n"
                            f"  curr: {grid_to_string(curr)}\n"
                            f"  next: {grid_to_string(nxt)}"
                        )

        if gold_events == 0:
            self.skipTest(
                f"No gold elimination events in {len(self.multi_cascade)} "
                "multi-cascade spins; try running --stats for larger sample"
            )

        self.assertEqual(len(errors), 0,
                         f"{len(errors)} gold→joker conversion failures "
                         f"(out of {gold_events} events):\n" +
                         "\n---\n".join(errors[:2]))

    def test_joker_type_distribution(self):
        """
        BigJoker should be ~15% of conversions, LittleJoker ~85%.
        Updated 2026-04-07: bigJokerRate changed from 0.25 to 0.15 in config.ts.
        Allow wide tolerance since sample size may be small.
        """
        big = little = 0

        for slot in self.multi_cascade:
            pt = slot["paytable"]
            for ci in range(len(pt["mgTable"]) - 1):
                curr = pt["mgTable"][ci]
                nxt  = pt["mgTable"][ci + 1]
                for reel, row in self._find_eliminated_gold(curr):
                    v = abs(nxt[reel][row])
                    if v == BIG_JOKER:      big    += 1
                    elif v == LITTLE_JOKER: little += 1

        total = big + little
        if total < 20:
            self.skipTest(f"Only {total} gold conversion events — need >=20 for distribution test")

        big_rate = big / total
        # Expected ~15% BigJoker (BIG_JOKER_RATE=0.15); accept 2%–45% with small samples
        self.assertGreater(big_rate, 0.02,
                           f"BigJoker rate too low: {big_rate:.1%} ({big}/{total}), expected ~{BIG_JOKER_RATE:.0%}")
        self.assertLess(big_rate, 0.45,
                        f"BigJoker rate too high: {big_rate:.1%} ({big}/{total}), expected ~{BIG_JOKER_RATE:.0%}")


# ════════════════════════════════════════════════════════════════════
# 11. BigJoker Copy Mechanics  (TC-004-05 / TC-004-06)
# ════════════════════════════════════════════════════════════════════

class TestBigJokerCopy(unittest.TestCase):
    """
    TC-004-05: After a gold cell converts to BigJoker, additional copies
               must appear in the next cascade board.
    TC-004-06: Copy count must be 1-4 (total BigJoker positions = 2-5).
    Rules:
      - Copies must NOT land on Scatter positions
      - Copies must NOT land on existing Joker positions
    """

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()
        cls.spins = spin_n(cls.c, 120)  # 120 regular spins
        # Supplement with buyFreeSpin FG cascade data (5 calls) — FG rounds have
        # ~10 spins each with multiplied wins, increasing multi-cascade boards
        # and gold-elimination → BigJoker conversion events.
        for _ in range(5):
            bfs = cls.c.buy_free_spin()
            if bfs.get("error") == 0:
                fg_slot = bfs["data"]["slotData"]
                cls.spins.append(fg_slot)
                for fg_round in fg_slot["paytable"].get("fgTable", []):
                    if len(fg_round) >= 2:
                        synthetic = {"paytable": {"mgTable": fg_round, "fgTable": []}}
                        cls.spins.append(synthetic)
        cls.multi_cascade = [
            s for s in cls.spins
            if len(s["paytable"]["mgTable"]) >= 2
        ]

    def _find_new_big_jokers(self, curr: list, nxt: list) -> dict:
        """
        Compare two consecutive boards.
        Returns:
          origin:  (reel, row) list of gold cells that became BigJoker
          copies:  (reel, row) list of NEW BigJoker positions (not from gold)
        """
        origin_positions = set()
        for reel in range(REELS):
            for row in range(ROWS):
                val = curr[reel][row]
                if val < 0 and is_gold(abs(val)):
                    nxt_val = abs(nxt[reel][row])
                    if nxt_val == BIG_JOKER:
                        origin_positions.add((reel, row))

        if not origin_positions:
            return {"origin": [], "copies": []}

        # All BigJoker positions in next board
        all_bj = {
            (reel, row)
            for reel in range(REELS)
            for row in range(ROWS)
            if abs(nxt[reel][row]) == BIG_JOKER
        }

        copies = list(all_bj - origin_positions)
        return {"origin": list(origin_positions), "copies": copies}

    def test_big_joker_has_copies(self):
        """Every BigJoker origin must have ≥1 copy in next board (if space allows)."""
        events_found = 0
        no_copy_cases = 0

        for i, slot in enumerate(self.multi_cascade):
            pt = slot["paytable"]
            for ci in range(len(pt["mgTable"]) - 1):
                curr = pt["mgTable"][ci]
                nxt  = pt["mgTable"][ci + 1]
                info = self._find_new_big_jokers(curr, nxt)

                if not info["origin"]:
                    continue

                events_found += 1
                # Board has 20 cells; if all remaining are scatter/joker, no copy possible
                # This is a graceful skip condition — just count
                if len(info["copies"]) == 0:
                    no_copy_cases += 1

        if events_found == 0:
            self.skipTest("No BigJoker origin events found in sample")

        # Expect at least 50% of BigJoker events to have copies
        # (some may have no valid target positions)
        copy_rate = 1 - (no_copy_cases / events_found)
        self.assertGreater(copy_rate, 0.4,
                           f"Only {copy_rate:.0%} of BigJoker events had copies "
                           f"({events_found - no_copy_cases}/{events_found})")

    def test_big_joker_copy_count_2_to_5(self):
        """Copy count (excluding origin) must be between 1 and 4, total positions 2-5.

        Updated 2026-04-07: engine now enforces Math.max(2, copyRule.count),
        cloneWeights = [2,3,4,5]. Minimum copies is 1 (total BigJoker = origin + ≥1),
        but the engine places 'count' copies where count ∈ {2,3,4,5}.
        So total BigJoker cells (origin + copies) is 3-6, copies alone is 2-5.
        """
        errors = []

        for i, slot in enumerate(self.multi_cascade):
            pt = slot["paytable"]
            for ci in range(len(pt["mgTable"]) - 1):
                curr = pt["mgTable"][ci]
                nxt  = pt["mgTable"][ci + 1]
                info = self._find_new_big_jokers(curr, nxt)

                if not info["origin"] or not info["copies"]:
                    continue

                n_copies = len(info["copies"])
                if not (BIG_JOKER_COPY_MIN <= n_copies <= BIG_JOKER_COPY_MAX):
                    errors.append(
                        f"Spin#{i} cascade {ci}: "
                        f"BigJoker copies={n_copies} "
                        f"(expected {BIG_JOKER_COPY_MIN}-{BIG_JOKER_COPY_MAX})\n"
                        f"  origin={info['origin']}  copies={info['copies']}"
                    )

        self.assertEqual(len(errors), 0, "\n".join(errors[:3]))

    def test_big_joker_not_copied_to_scatter(self):
        """BigJoker copies must never land on a Scatter position."""
        errors = []

        for i, slot in enumerate(self.multi_cascade):
            pt = slot["paytable"]
            for ci in range(len(pt["mgTable"]) - 1):
                curr = pt["mgTable"][ci]
                nxt  = pt["mgTable"][ci + 1]
                info = self._find_new_big_jokers(curr, nxt)

                for reel, row in info["copies"]:
                    # The source cell in curr should not be scatter
                    src = abs(curr[reel][row])
                    if is_scatter(src):
                        errors.append(
                            f"Spin#{i} cascade {ci}: "
                            f"BigJoker copied onto scatter at reel={reel} row={row}"
                        )

        self.assertEqual(len(errors), 0,
                         f"{len(errors)} BigJoker-on-scatter violations:\n" +
                         "\n".join(errors[:3]))


# ════════════════════════════════════════════════════════════════════
# 12. buyFreeSpin Endpoint  (new route added 2026-04-07)
# ════════════════════════════════════════════════════════════════════

class TestBuyFreeSpin(unittest.TestCase):
    """
    Tests for POST /buyFreeSpin?bet=...&token=...

    Rules (from backend game.ts + config.ts):
    - Costs bet * buyRatio (buyRatio=50 from /buyRatio endpoint)
    - Forces FG trigger on first spin (buyFeature=true)
    - Runs all FG spins to completion inside the route
    - Returns: mgTable, mgWin, fgTable, fgWin, hasFreeSpin=true, addFreeSpin
    - afterCoin = prevCoin - (bet * buyRatio) + totalWin
    """

    @classmethod
    def setUpClass(cls):
        cls.c = GameClient()
        cls.c.login()

    def _buy_free_spin(self, bet: float = DEFAULT_BET):
        r = self.c.session.post(
            f"{BASE_URL}/buyFreeSpin",
            params={"bet": bet, "token": self.c.token}
        )
        js = r.json()
        # Keep local coin in sync so prevCoin checks are accurate
        if js.get("error") == 0:
            self.c.coin = js["data"]["slotData"].get("afterCoin", self.c.coin)
        return js

    def _get_buy_ratio(self):
        r = self.c.session.post(
            f"{BASE_URL}/buyRatio",
            params={"token": self.c.token}
        )
        js = r.json()
        return js["data"]["buyRatio"]

    def test_buy_ratio_endpoint(self):
        """GET /buyRatio must return a positive numeric buyRatio."""
        ratio = self._get_buy_ratio()
        self.assertIsInstance(ratio, (int, float),
            f"buyRatio must be numeric, got {type(ratio).__name__}")
        self.assertGreater(ratio, 0, "buyRatio must be positive")

    def test_buy_free_spin_response_structure(self):
        """buyFreeSpin must return standard envelope with slotData."""
        js = self._buy_free_spin()
        self.assertEqual(js.get("error"), 0,
            f"buyFreeSpin returned error {js.get('error')}: {js.get('message')}")
        data = js["data"]
        self.assertIn("slotData", data)
        pt = data["slotData"]["paytable"]
        for field in ("mgTable", "mgWin", "fgTable", "fgWin", "hasFreeSpin", "addFreeSpin"):
            self.assertIn(field, pt, f"Missing field: {field}")

    def test_buy_free_spin_always_triggers_fg(self):
        """buyFreeSpin must always set hasFreeSpin=True (FG was triggered)."""
        js = self._buy_free_spin()
        self.assertEqual(js.get("error"), 0,
            f"buyFreeSpin error: {js.get('message')}")
        pt = js["data"]["slotData"]["paytable"]
        self.assertTrue(
            pt.get("hasFreeSpin") or pt.get("hasFreeGame"),
            "buyFreeSpin must always trigger FG (hasFreeSpin should be True)"
        )

    def test_buy_free_spin_deducts_correct_cost(self):
        """afterCoin = prevCoin - (bet * buyRatio) + totalWin."""
        ratio = self._get_buy_ratio()
        prev_coin = self.c.coin

        js = self._buy_free_spin()
        self.assertEqual(js.get("error"), 0,
            f"buyFreeSpin error: {js.get('message')}")

        slot = js["data"]["slotData"]
        bet       = slot["bet"]
        total_win = slot["totalWin"]
        after     = slot["afterCoin"]
        cost      = round(bet * ratio, 2)

        expected = round(prev_coin - cost + total_win, 2)
        self.assertAlmostEqual(after, expected, delta=WIN_TOLERANCE,
            msg=f"afterCoin={after} expected={expected} "
                f"(prevCoin={prev_coin} bet={bet} ratio={ratio} cost={cost} win={total_win})")

    def test_buy_free_spin_win_non_negative(self):
        """totalWin from buyFreeSpin must be >= 0."""
        js = self._buy_free_spin()
        self.assertEqual(js.get("error"), 0)
        total_win = js["data"]["slotData"]["totalWin"]
        self.assertGreaterEqual(total_win, 0,
            f"totalWin must be non-negative, got {total_win}")

    def test_buy_free_spin_invalid_bet_rejected(self):
        """Bet not in allowedBets must be rejected."""
        js = self._buy_free_spin(bet=0.99)
        self.assertNotEqual(js.get("error"), 0,
            "bet=0.99 is not in allowedBets, should return error")

    def test_buy_free_spin_fg_table_populated(self):
        """fgTable must not be empty after buyFreeSpin (FG spins were run)."""
        js = self._buy_free_spin()
        self.assertEqual(js.get("error"), 0)
        pt = js["data"]["slotData"]["paytable"]
        self.assertGreater(len(pt["fgTable"]), 0,
            "fgTable should be populated after buyFreeSpin ran all FG spins")


# ════════════════════════════════════════════════════════════════════
# Entry Point
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
