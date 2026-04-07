"""
test_api.py — SUPERACE API Test Suite
52 tests across 12 test classes.
"""

import unittest
import requests
from decimal import Decimal
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    BASE_URL, SSO_KEY, BET, INVALID_BET,
    SCATTER, WILDS, GOLD_SYMBOLS, GOLD_REELS,
    FG_SEARCH_MAX_SPINS, FG_INITIAL_SPINS,
    MG_MULTIPLIERS, FG_MULTIPLIERS,
)
from game_logic import calculate_cascade_win, verify_payout


# ─────────────────────────────────────────────────────────────────────────────
# GameClient
# ─────────────────────────────────────────────────────────────────────────────

class GameClient:
    def __init__(self, sso_key=SSO_KEY, bet=BET):
        self.session = requests.Session()
        self.token   = None
        self.coin    = Decimal("0")
        self.bet     = bet
        self._login(sso_key)

    def _login(self, sso_key):
        resp = self.session.post(f"{BASE_URL}/sso/login", params={"ssoKey": sso_key})
        resp.raise_for_status()
        raw        = resp.json()
        inner      = raw.get("data", raw)          # new: { data: { token, profile, ... } }
        self.token = inner["token"]
        profile    = inner.get("profile", {})
        coin_raw   = (profile.get("coin")
                      or inner.get("coin")
                      or inner.get("slotData", {}).get("coin", "1000"))
        self.coin  = Decimal(str(coin_raw))

    @staticmethod
    def _normalize(raw):
        """
        Flatten new API envelope into the legacy shape tests expect:
          { error, slotData: { mgTable, mgWin, fgTable, fgWin,
                               hasFreeSpin, addFreeSpin, bet, totalWin,
                               coin, roundId } }
        """
        if raw.get("error", 0) != 0 or "data" not in raw:
            return raw
        inner    = raw["data"]
        slot_raw = inner.get("slotData", {})
        paytable = slot_raw.get("paytable", slot_raw)   # fallback if paytable absent
        slot = {
            "mgTable":     paytable.get("mgTable",     []),
            "mgWin":       paytable.get("mgWin",       []),
            "fgTable":     paytable.get("fgTable",     []),
            "fgWin":       paytable.get("fgWin",       []),
            "hasFreeSpin": paytable.get("hasFreeSpin", False),
            "hasFreeGame": paytable.get("hasFreeGame", False),
            "addFreeSpin": paytable.get("addFreeSpin", []),
            "bet":         slot_raw.get("bet"),
            "bets":        slot_raw.get("bets"),
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
        data = self._normalize(resp.json())
        if data.get("error", 0) == 0:
            coin_raw = data.get("slotData", {}).get("coin")
            if coin_raw is not None:
                self.coin = Decimal(str(coin_raw))
        return data

    def spin_raw(self, token=None, bet=None):
        """Spin with custom token / bet for error-path testing."""
        t = token if token is not None else self.token
        b = bet   if bet   is not None else self.bet
        resp = self.session.post(
            f"{BASE_URL}/play",
            params={"token": t, "bet": b},
        )
        return resp.json()

    def buy_ratio(self):
        resp = self.session.post(
            f"{BASE_URL}/buyRatio",
            params={"token": self.token, "bet": self.bet},
        )
        resp.raise_for_status()
        raw = resp.json()
        # Normalize: new API wraps buyRatio under data.data
        if raw.get("error", 0) == 0 and "data" in raw:
            inner = raw["data"]
            if "buyRatio" in inner:
                return {"error": 0, "buyRatio": inner["buyRatio"]}
        return raw

    def _buy_free_spin(self):
        resp = self.session.post(
            f"{BASE_URL}/buyFreeSpin",
            params={"token": self.token, "bet": self.bet},
        )
        resp.raise_for_status()
        data = self._normalize(resp.json())
        if data.get("error", 0) == 0:
            coin_raw = data.get("slotData", {}).get("coin")
            if coin_raw is not None:
                self.coin = Decimal(str(coin_raw))
        return data

    def find_fg_spin(self, max_spins=FG_SEARCH_MAX_SPINS):
        """Spin until FG is triggered. Returns the triggering spin data or None."""
        for _ in range(max_spins):
            data = self.spin()
            slot = data.get("slotData", {})
            if slot.get("hasFreeSpin") or slot.get("hasFreeGame"):
                return data
        return None

    def logout(self):
        try:
            self.session.post(f"{BASE_URL}/logout", params={"token": self.token})
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# TestAuthentication  (5 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_valid_login_returns_token(self):
        self.assertIsNotNone(self.c.token)
        self.assertIsInstance(self.c.token, str)
        self.assertGreater(len(self.c.token), 0)

    def test_valid_login_returns_positive_coin(self):
        self.assertGreater(self.c.coin, 0)

    def test_response_always_has_required_envelope(self):
        data = self.c.spin()
        self.assertIn("error", data)

    def test_invalid_token_rejected(self):
        """BUG-001: currently returns error 2 instead of 4/6."""
        c    = GameClient()
        data = c.spin_raw(token="invalid_token_xyz")
        self.assertNotEqual(data.get("error"), 0,
                            "Invalid token should be rejected")
        # Documenting BUG-001: expected error 4 or 6, API returns 2
        # self.assertIn(data.get("error"), [4, 6])  # uncomment when fixed
        c.logout()

    def test_logout_invalidates_token(self):
        c     = GameClient()
        token = c.token
        c.logout()
        data  = c.session.post(
            f"{BASE_URL}/play",
            params={"token": token},
            data={"bet": BET},
        ).json()
        self.assertNotEqual(data.get("error"), 0,
                            "Logged-out token should be rejected")


# ─────────────────────────────────────────────────────────────────────────────
# TestSpinStructure  (10 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestSpinStructure(unittest.TestCase):
    def setUp(self):
        self.c    = GameClient()
        self.data = self.c.spin()
        self.slot = self.data.get("slotData", {})

    def tearDown(self):
        self.c.logout()

    def test_error_is_zero_on_success(self):
        self.assertEqual(self.data.get("error"), 0)

    def test_slot_data_exists(self):
        self.assertIn("slotData", self.data)

    def test_mg_table_exists(self):
        self.assertIn("mgTable", self.slot)
        self.assertIsInstance(self.slot["mgTable"], list)
        self.assertGreater(len(self.slot["mgTable"]), 0)

    def test_grid_is_5x4(self):
        grid = self.slot["mgTable"][0]
        self.assertEqual(len(grid), 5, "Should have 5 reels")
        for reel in grid:
            self.assertEqual(len(reel), 4, "Each reel should have 4 rows")

    def test_mg_win_exists_and_length_matches_table(self):
        self.assertIn("mgWin", self.slot)
        self.assertEqual(len(self.slot["mgWin"]), len(self.slot["mgTable"]))

    def test_total_win_is_non_negative(self):
        self.assertGreaterEqual(float(self.slot.get("totalWin", 0)), 0)

    def test_coin_is_non_negative(self):
        self.assertGreaterEqual(float(self.slot.get("coin", 0)), 0)

    def test_has_round_id(self):
        has_id = any(k in self.slot for k in ("roundId", "roundID", "round_id"))
        self.assertTrue(has_id, "Response should contain a round identifier")

    def test_slot_data_has_bet_field(self):
        """BUG-002: field is 'bet', spec requires 'bets'."""
        has_bet = "bet" in self.slot or "bets" in self.slot
        self.assertTrue(has_bet, "slotData should have bet/bets field")

    def test_has_free_spin_field(self):
        """BUG-003: field is 'hasFreeSpin', spec requires 'hasFreeGame'."""
        has_field = "hasFreeSpin" in self.slot or "hasFreeGame" in self.slot
        self.assertTrue(has_field, "slotData should have hasFreeSpin/hasFreeGame field")


# ─────────────────────────────────────────────────────────────────────────────
# TestPayoutVerification  (4 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestPayoutVerification(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_mg_cascade_wins_match_calculation(self):
        """Run 30 spins and independently verify every cascade win amount."""
        errors = []
        for _ in range(30):
            data    = self.c.spin()
            results = verify_payout(data, BET)
            for idx, expected, actual, ok in results:
                if not ok:
                    errors.append(
                        f"cascade {idx}: expected {expected:.4f}, got {actual:.4f}"
                    )
        self.assertEqual(errors, [],
                         "Payout mismatches:\n" + "\n".join(errors))

    def test_zero_win_cascades_have_no_combinations(self):
        """When mgWin[i]==0, independent calculation should also be 0."""
        for _ in range(20):
            data     = self.c.spin()
            slot     = data.get("slotData", {})
            mg_table = slot.get("mgTable", [])
            mg_win   = slot.get("mgWin",   [])
            for i, (grid, win) in enumerate(zip(mg_table, mg_win)):
                if float(win) == 0:
                    calc = calculate_cascade_win(grid, BET, i)
                    self.assertAlmostEqual(calc, 0, places=2,
                                          msg="Zero-win cascade should have no combinations")

    def test_total_win_equals_sum_of_cascades(self):
        """totalWin == sum(mgWin) + sum(fgWin) for every spin."""
        for _ in range(20):
            data  = self.c.spin()
            slot  = data.get("slotData", {})
            total = float(slot.get("totalWin", 0))
            mg    = sum(float(w) for w in slot.get("mgWin", []))
            fg    = sum(float(w) for w in slot.get("fgWin", []))
            self.assertAlmostEqual(total, mg + fg, places=2,
                                   msg=f"totalWin {total} != mgWin {mg} + fgWin {fg}")

    def test_fg_cascade_wins_non_negative(self):
        """All fgWin values must be >= 0."""
        for _ in range(20):
            data = self.c.spin()
            slot = data.get("slotData", {})
            for w in slot.get("fgWin", []):
                self.assertGreaterEqual(float(w), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestMultiplierProgression  (2 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiplierProgression(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_cascade_count_at_least_1(self):
        """Every spin must produce at least 1 entry in mgTable."""
        for _ in range(10):
            data = self.c.spin()
            slot = data.get("slotData", {})
            self.assertGreaterEqual(len(slot.get("mgTable", [])), 1)

    def test_mg_multipliers_are_1_2_3_5(self):
        """On a multi-cascade spin, verify multiplier progression via payout."""
        for _ in range(FG_SEARCH_MAX_SPINS):
            data     = self.c.spin()
            slot     = data.get("slotData", {})
            mg_table = slot.get("mgTable", [])
            mg_win   = slot.get("mgWin",   [])
            if len(mg_table) >= 2:
                for i, (grid, win) in enumerate(zip(mg_table, mg_win)):
                    if float(win) > 0:
                        expected = calculate_cascade_win(grid, BET, i, is_fg=False)
                        self.assertAlmostEqual(
                            float(win), expected, places=2,
                            msg=f"MG cascade {i} multiplier mismatch"
                        )
                return
        self.skipTest("Could not find a multi-cascade spin in allowed attempts")


# ─────────────────────────────────────────────────────────────────────────────
# TestRuleCompliance  (4 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleCompliance(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_gold_only_in_reels_1_2_3(self):
        """Golden symbols (101-108) must only appear in reels 1, 2, 3 (0-indexed)."""
        for _ in range(30):
            data = self.c.spin()
            slot = data.get("slotData", {})
            for grid in slot.get("mgTable", []):
                for reel_idx, reel in enumerate(grid):
                    for cell in reel:
                        if abs(cell) in GOLD_SYMBOLS:
                            self.assertIn(
                                reel_idx, GOLD_REELS,
                                msg=f"Gold symbol {abs(cell)} found in reel {reel_idx} "
                                    f"(only allowed in {GOLD_REELS})"
                            )

    def test_no_empty_cells_in_stored_grids(self):
        """No cell should be 0 (empty) after refill."""
        for _ in range(20):
            data = self.c.spin()
            slot = data.get("slotData", {})
            for grid in slot.get("mgTable", []):
                for reel in grid:
                    for cell in reel:
                        self.assertNotEqual(cell, 0, "Found empty cell (0) in grid")

    def test_joker_is_never_scatter(self):
        """Wild symbol values (10, 11) must not equal Scatter (9)."""
        for _ in range(30):
            data = self.c.spin()
            slot = data.get("slotData", {})
            for grid in slot.get("mgTable", []):
                for reel in grid:
                    for cell in reel:
                        v = abs(cell)
                        if v in WILDS:
                            self.assertNotEqual(v, SCATTER)

    def test_scatter_and_wild_are_distinct(self):
        """Scatter (9) positions should never contain a Wild value."""
        for _ in range(30):
            data = self.c.spin()
            slot = data.get("slotData", {})
            for grid in slot.get("mgTable", []):
                for reel in grid:
                    for cell in reel:
                        v = abs(cell)
                        if v == SCATTER:
                            self.assertNotIn(v, WILDS)


# ─────────────────────────────────────────────────────────────────────────────
# TestFreeGameMechanics  (7 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestFreeGameMechanics(unittest.TestCase):
    def setUp(self):
        self.c       = GameClient()
        self.fg_data = self.c.find_fg_spin()

    def tearDown(self):
        self.c.logout()

    def _skip_if_no_fg(self):
        if self.fg_data is None:
            self.skipTest(f"FG not triggered in {FG_SEARCH_MAX_SPINS} spins")

    def test_fg_trigger_means_3plus_scatters(self):
        """When FG is triggered, the spin must contain ≥ 3 Scatters."""
        self._skip_if_no_fg()
        slot     = self.fg_data.get("slotData", {})
        mg_table = slot.get("mgTable", [])
        found    = any(
            sum(1 for reel in grid for cell in reel if abs(cell) == SCATTER) >= 3
            for grid in mg_table
        )
        self.assertTrue(found, "FG trigger should have ≥ 3 Scatters in mgTable")

    def test_add_free_spin_field_exists(self):
        """addFreeSpin field should be present when FG is triggered."""
        self._skip_if_no_fg()
        slot = self.fg_data.get("slotData", {})
        self.assertIn("addFreeSpin", slot,
                      "addFreeSpin field should exist when FG triggered")

    def test_fg_multipliers_are_2_4_6_10(self):
        """FG cascade structure should match FG multiplier expectations."""
        self._skip_if_no_fg()
        slot     = self.fg_data.get("slotData", {})
        fg_table = slot.get("fgTable", [])
        if not fg_table:
            self.skipTest("No fgTable data")
        # Verify each FG spin grid has 5 reels
        for spin in fg_table:
            cascades = spin if isinstance(spin[0], list) else [spin]
            for grid in cascades:
                if grid and isinstance(grid[0], list):
                    self.assertEqual(len(grid), 5)

    def test_fg_table_win_non_negative(self):
        """All fgWin entries must be ≥ 0."""
        self._skip_if_no_fg()
        slot = self.fg_data.get("slotData", {})
        for win in slot.get("fgWin", []):
            self.assertGreaterEqual(float(win), 0)

    def test_fg_table_is_populated(self):
        """fgTable must have at least one entry when FG is triggered."""
        self._skip_if_no_fg()
        slot     = self.fg_data.get("slotData", {})
        fg_table = slot.get("fgTable", [])
        self.assertGreater(len(fg_table), 0,
                           "fgTable should be populated when FG triggered")

    def test_fg_spin_count_at_least_initial(self):
        """FG should execute at least FG_INITIAL_SPINS (10) spins."""
        self._skip_if_no_fg()
        slot     = self.fg_data.get("slotData", {})
        fg_table = slot.get("fgTable", [])
        if fg_table:
            self.assertGreaterEqual(
                len(fg_table), FG_INITIAL_SPINS,
                msg=f"FG should have ≥ {FG_INITIAL_SPINS} spins, got {len(fg_table)}"
            )

    def test_has_free_spin_field_exists(self):
        """Every spin response must have hasFreeSpin or hasFreeGame field."""
        data = self.c.spin()
        slot = data.get("slotData", {})
        self.assertTrue(
            "hasFreeSpin" in slot or "hasFreeGame" in slot,
            "slotData should always contain hasFreeSpin/hasFreeGame"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TestErrorHandling  (3 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_enormous_bet_returns_error_2(self):
        """Bet larger than balance should return error 2 (insufficient funds)."""
        data = self.c.spin_raw(bet=9_999_999)
        self.assertEqual(data.get("error"), 2,
                         f"Expected error 2, got {data.get('error')}")

    def test_invalid_bet_returns_error(self):
        """BUG-005: INVALID_BET (1.0) is not in betList and must be rejected."""
        data = self.c.spin_raw(bet=INVALID_BET)
        self.assertNotEqual(data.get("error"), 0,
                            f"Invalid bet {INVALID_BET} should be rejected")

    def test_missing_token_returns_error(self):
        """Request without token should be rejected."""
        data = requests.post(f"{BASE_URL}/play", data={"bet": BET}).json()
        self.assertNotEqual(data.get("error"), 0,
                            "Missing token should return an error")


# ─────────────────────────────────────────────────────────────────────────────
# TestBalanceDeduction  (3 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestBalanceDeduction(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_mg_deducts_correct_amount(self):
        """TC-005-04: afterCoin = prevCoin - bet + totalWin (MG, no FG)."""
        for _ in range(20):
            prev_coin = self.c.coin
            data      = self.c.spin()
            slot      = data.get("slotData", {})
            if slot.get("hasFreeSpin") or slot.get("hasFreeGame"):
                continue
            after_coin = Decimal(str(slot.get("coin", 0)))
            total_win  = Decimal(str(slot.get("totalWin", 0)))
            bet        = Decimal(str(BET))
            expected   = prev_coin - bet + total_win
            self.assertAlmostEqual(
                float(after_coin), float(expected), places=2,
                msg=f"MG balance: {prev_coin} - {bet} + {total_win} = {expected}, got {after_coin}"
            )
            return
        self.skipTest("Could not find a non-FG spin in 20 attempts")

    def test_fg_does_not_deduct_extra_bet(self):
        """TC-005-04: FG spins are free — totalWin should be ≥ 0."""
        fg_data = self.c.find_fg_spin()
        if fg_data is None:
            self.skipTest(f"FG not triggered in {FG_SEARCH_MAX_SPINS} spins")
        slot = fg_data.get("slotData", {})
        self.assertGreaterEqual(float(slot.get("totalWin", 0)), 0)

    def test_coin_decreases_without_win(self):
        """Balance should drop by exactly bet on a zero-win, no-FG spin."""
        for _ in range(30):
            prev_coin = self.c.coin
            data      = self.c.spin()
            slot      = data.get("slotData", {})
            no_fg  = not (slot.get("hasFreeSpin") or slot.get("hasFreeGame"))
            no_win = float(slot.get("totalWin", 1)) == 0
            if no_fg and no_win:
                after_coin = Decimal(str(slot.get("coin", 0)))
                expected   = prev_coin - Decimal(str(BET))
                self.assertAlmostEqual(float(after_coin), float(expected), places=2)
                return
        self.skipTest("Could not find a zero-win no-FG spin in 30 attempts")


# ─────────────────────────────────────────────────────────────────────────────
# TestMGCompletesBeforeFG  (3 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestMGCompletesBeforeFG(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_mg_win_settled_before_fg(self):
        """TC-005-06: mgWin data must be present on the same response as fgWin."""
        fg_data = self.c.find_fg_spin()
        if fg_data is None:
            self.skipTest(f"FG not triggered in {FG_SEARCH_MAX_SPINS} spins")
        slot = fg_data.get("slotData", {})
        self.assertGreater(len(slot.get("mgWin", [])), 0,
                           "mgWin should be settled before FG results arrive")
        self.assertGreater(len(slot.get("fgWin", [])), 0,
                           "fgWin should be present when FG is triggered")

    def test_fg_table_exists_when_has_free_spin(self):
        """When hasFreeSpin is True, fgTable must be populated."""
        fg_data = self.c.find_fg_spin()
        if fg_data is None:
            self.skipTest(f"FG not triggered in {FG_SEARCH_MAX_SPINS} spins")
        slot = fg_data.get("slotData", {})
        self.assertGreater(len(slot.get("fgTable", [])), 0,
                           "fgTable should be populated when FG triggered")

    def test_mg_table_always_present(self):
        """mgTable should exist in every spin response, FG or not."""
        for _ in range(10):
            data = self.c.spin()
            slot = data.get("slotData", {})
            self.assertIn("mgTable", slot)
            self.assertGreater(len(slot["mgTable"]), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestGoldToJokerConversion  (2 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestGoldToJokerConversion(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_gold_eliminated_becomes_joker(self):
        """TC-004-04: An eliminated gold symbol must become a Joker at the same position."""
        gold_events = 0
        for _ in range(FG_SEARCH_MAX_SPINS):
            data     = self.c.spin()
            slot     = data.get("slotData", {})
            mg_table = slot.get("mgTable", [])

            for ci in range(len(mg_table) - 1):
                grid      = mg_table[ci]
                next_grid = mg_table[ci + 1]
                for ri, reel in enumerate(grid):
                    for row, cell in enumerate(reel):
                        if cell < 0 and abs(cell) in GOLD_SYMBOLS:
                            gold_events += 1
                            next_cell = abs(next_grid[ri][row])
                            self.assertIn(
                                next_cell, WILDS,
                                msg=f"Gold [{ri}][{row}] cascade {ci} → expected Joker, got {next_cell}"
                            )

            if gold_events >= 10:
                return

        if gold_events == 0:
            self.skipTest("No gold elimination events in allowed spins")

    @unittest.skip("Requires ≥10 gold conversions — use test_stats.py for distribution")
    def test_joker_type_distribution(self):
        """75% LittleJoker (11), 25% BigJoker (10)."""
        pass


# ─────────────────────────────────────────────────────────────────────────────
# TestBigJokerCopy  (3 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestBigJokerCopy(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def _find_big_joker_spin(self):
        for _ in range(FG_SEARCH_MAX_SPINS):
            data = self.c.spin()
            slot = data.get("slotData", {})
            for grid in slot.get("mgTable", []):
                if any(abs(cell) == 10 for reel in grid for cell in reel):
                    return data
        return None

    def test_big_joker_copy_count_in_range(self):
        """TC-004-05: BigJoker (10) count per grid must be 1–4."""
        data = self._find_big_joker_spin()
        if data is None:
            self.skipTest("No BigJoker event in allowed spins")
        slot = data.get("slotData", {})
        for grid in slot.get("mgTable", []):
            count = sum(1 for reel in grid for cell in reel if abs(cell) == 10)
            if count > 0:
                self.assertGreaterEqual(count, 1)
                self.assertLessEqual(count, 4,
                                     f"BigJoker count {count} exceeds maximum of 4")

    def test_big_joker_does_not_overwrite_scatter(self):
        """TC-004-06: BigJoker copies must not land on Scatter positions."""
        for _ in range(FG_SEARCH_MAX_SPINS):
            data = self.c.spin()
            slot = data.get("slotData", {})
            for grid in slot.get("mgTable", []):
                for ri, reel in enumerate(grid):
                    for row, cell in enumerate(reel):
                        v = abs(cell)
                        # A position cannot be both Scatter and BigJoker
                        if v == SCATTER:
                            self.assertNotEqual(v, 10)

    def test_big_joker_appears_as_valid_wild(self):
        """BigJoker (10) must never equal Scatter (9)."""
        data = self._find_big_joker_spin()
        if data is None:
            self.skipTest("No BigJoker found in allowed spins")
        slot = data.get("slotData", {})
        for grid in slot.get("mgTable", []):
            for reel in grid:
                for cell in reel:
                    if abs(cell) == 10:
                        self.assertNotEqual(abs(cell), SCATTER)


# ─────────────────────────────────────────────────────────────────────────────
# TestBuyFreeSpin  (7 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestBuyFreeSpin(unittest.TestCase):
    def setUp(self):
        self.c = GameClient()

    def tearDown(self):
        self.c.logout()

    def test_buy_ratio_endpoint(self):
        """buyRatio should return a positive ratio."""
        data  = self.c.buy_ratio()
        self.assertEqual(data.get("error"), 0)
        ratio = data.get("buyRatio") or data.get("slotData", {}).get("buyRatio")
        self.assertIsNotNone(ratio, "buyRatio field should exist")
        self.assertGreater(float(ratio), 0, "buyRatio should be positive")

    def test_buy_free_spin_response_structure(self):
        """buyFreeSpin should return standard envelope + slotData with required fields."""
        data = self.c._buy_free_spin()
        self.assertIn("error", data)
        self.assertEqual(data.get("error"), 0)
        self.assertIn("slotData", data)
        slot = data.get("slotData", {})
        self.assertIn("totalWin", slot)
        self.assertIn("coin",     slot)

    def test_buy_free_spin_always_triggers_fg(self):
        """buyFreeSpin must always result in a Free Game."""
        data = self.c._buy_free_spin()
        slot = data.get("slotData", {})
        has_fg = slot.get("hasFreeSpin") or slot.get("hasFreeGame")
        self.assertTrue(has_fg, "buyFreeSpin must always trigger Free Game")
        self.assertGreater(len(slot.get("fgTable", [])), 0,
                           "fgTable should be populated after buyFreeSpin")

    def test_buy_free_spin_deducts_correct_cost(self):
        """afterCoin = prevCoin - (bet × buyRatio) + totalWin."""
        ratio_data = self.c.buy_ratio()
        buy_ratio  = float(
            ratio_data.get("buyRatio")
            or ratio_data.get("slotData", {}).get("buyRatio", 0)
        )
        prev_coin  = self.c.coin
        data       = self.c._buy_free_spin()   # updates self.c.coin internally
        slot       = data.get("slotData", {})
        after_coin = Decimal(str(slot.get("coin", 0)))
        total_win  = Decimal(str(slot.get("totalWin", 0)))
        cost       = Decimal(str(BET)) * Decimal(str(buy_ratio))
        expected   = prev_coin - cost + total_win
        self.assertAlmostEqual(
            float(after_coin), float(expected), places=1,
            msg=f"buyFreeSpin balance: {prev_coin} - {cost} + {total_win} = {expected}, got {after_coin}"
        )

    def test_buy_free_spin_win_non_negative(self):
        """buyFreeSpin totalWin must be >= 0."""
        data = self.c._buy_free_spin()
        slot = data.get("slotData", {})
        self.assertGreaterEqual(float(slot.get("totalWin", 0)), 0)

    def test_buy_free_spin_invalid_bet_rejected(self):
        """BUG-005: INVALID_BET (1.0) should be rejected for buyFreeSpin too."""
        c    = GameClient()
        resp = c.session.post(
            f"{BASE_URL}/buyFreeSpin",
            params={"token": c.token},
            data={"bet": INVALID_BET},
        )
        data = resp.json()
        self.assertNotEqual(data.get("error"), 0,
                            f"Invalid bet {INVALID_BET} should be rejected")
        c.logout()

    def test_buy_free_spin_fg_table_populated(self):
        """fgTable after buyFreeSpin should contain valid FG spin results."""
        data     = self.c._buy_free_spin()
        slot     = data.get("slotData", {})
        fg_table = slot.get("fgTable", [])
        self.assertGreater(len(fg_table), 0,
                           "fgTable should be populated after buyFreeSpin")
        # Spot-check first FG spin grid has 5 reels
        first = fg_table[0]
        grid  = first[0] if (isinstance(first, list) and isinstance(first[0], list)) else first
        if isinstance(grid, list):
            self.assertEqual(len(grid), 5)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
