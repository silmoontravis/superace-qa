#!/usr/bin/env python3
"""
SUPERACE QA Runner
Orchestrates all QA tests and prints a final report.

Usage:
    python qa_runner.py              # API tests only (fast, ~30s)
    python qa_runner.py --visual     # API + visual (requires Playwright)
    python qa_runner.py --stats      # API + statistical distribution
    python qa_runner.py --all        # Everything
    python qa_runner.py --show       # Open visible browser for visual tests
"""
import sys
import os
import time
import unittest
import argparse
from datetime import datetime

# Windows: force UTF-8 output to avoid cp950 emoji encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Helpers ───────────────────────────────────────────────────────────

def separator(label: str = "", width: int = 60):
    if label:
        print(f"\n{'─' * 4}  {label}  {'─' * (width - len(label) - 7)}")
    else:
        print("─" * width)


def print_api_summary(result: unittest.TestResult):
    total   = result.testsRun
    failed  = len(result.failures)
    errored = len(result.errors)
    passed  = total - failed - errored
    icon    = "✅" if failed == 0 and errored == 0 else "❌"
    print(f"  {icon}  {passed}/{total} passed", end="")
    if failed:  print(f"  |  {failed} failures", end="")
    if errored: print(f"  |  {errored} errors",   end="")
    print()

    for label, items in [("Failures", result.failures), ("Errors", result.errors)]:
        if items:
            print(f"\n  {label}:")
            for test, tb in items:
                last_line = tb.strip().split("\n")[-1]
                print(f"    ✗  {test}")
                print(f"       {last_line}")


# ── API Test Runner ───────────────────────────────────────────────────

def run_api_tests(include_stats: bool = False) -> unittest.TestResult:
    import test_api

    test_classes = [
        test_api.TestAuthentication,
        test_api.TestSpinStructure,
        test_api.TestPayoutVerification,
        test_api.TestMultiplierProgression,
        test_api.TestRuleCompliance,
        test_api.TestFreeGameMechanics,
        test_api.TestErrorHandling,
        test_api.TestBalanceDeduction,
        test_api.TestMGCompletesBeforeFG,
        test_api.TestGoldToJokerConversion,
        test_api.TestBigJokerCopy,
        test_api.TestBuyFreeSpin,
    ]

    if include_stats:
        try:
            import test_stats
            for cls in [
                test_stats.TestRTP,
                test_stats.TestGoldSymbolRate,
                test_stats.TestBigJokerRate,
                test_stats.TestFGTriggerRate,
                test_stats.TestBetListBUG005,
            ]:
                test_classes.append(cls)
        except ImportError:
            print("  (stats module not found, skipping)")

    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    return runner.run(suite)


# ── Visual Test Runner ────────────────────────────────────────────────

def run_visual_tests(show_browser: bool = False):
    try:
        from test_visual import run, print_results
        results = run(headless=not show_browser)
        print_results(results)
        return results
    except ImportError as e:
        print(f"  Playwright not available: {e}")
        return []

def run_visual_fg_tests(show_browser: bool = False):
    try:
        from test_visual_fg import run, print_results
        results = run(headless=not show_browser)
        print_results(results)
        return results
    except ImportError as e:
        print(f"  Playwright FG tests not available: {e}")
        return []


# ── Report ────────────────────────────────────────────────────────────

def final_report(api_result, visual_results, elapsed: float):
    separator("SUPERACE QA REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  {elapsed:.1f}s")
    separator()

    api_ok = True
    if api_result:
        api_ok = api_result.testsRun > 0 and not api_result.failures and not api_result.errors

    visual_ok = True
    if visual_results:
        visual_ok = all(r.passed for r in visual_results)

    overall = api_ok and visual_ok
    status  = "✅  ALL TESTS PASSED" if overall else "❌  SOME TESTS FAILED"
    print(f"\n  {status}\n")
    separator()
    return overall


# ── Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SUPERACE QA Runner")
    parser.add_argument("--visual",  action="store_true", help="Run visual tests")
    parser.add_argument("--stats",   action="store_true", help="Run statistical tests")
    parser.add_argument("--all",     action="store_true", help="Run everything")
    parser.add_argument("--show",    action="store_true", help="Visible browser (visual tests only)")
    args = parser.parse_args()

    run_visual  = args.visual or args.all
    run_stats   = args.stats  or args.all
    show        = args.show

    t0 = time.time()

    # ── API Tests ──────────────────────────────────────────────────
    separator("API Tests")
    api_result = run_api_tests(include_stats=run_stats)
    print()
    print_api_summary(api_result)

    # ── Visual Tests ───────────────────────────────────────────────
    visual_results = []
    if run_visual:
        separator("Visual Tests")
        visual_results = run_visual_tests(show_browser=show)
        separator("FG Visual Tests")
        visual_results += run_visual_fg_tests(show_browser=show)

    # ── Final Report ───────────────────────────────────────────────
    ok = final_report(api_result, visual_results, time.time() - t0)
    sys.exit(0 if ok else 1)
