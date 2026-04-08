#!/usr/bin/env python3
"""
SUPERACE Visual QA Tests — Playwright
Tests page load, canvas render, FPS, console errors, and UI elements.

Setup:
    pip install playwright
    playwright install chromium

Run:
    python test_visual.py
    python test_visual.py --show   # open visible browser
"""
import sys
import os
import time
import asyncio
import argparse
from dataclasses import dataclass, field
from typing import List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import GAME_URL

try:
    from playwright.async_api import async_playwright, Page
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False


@dataclass
class VResult:
    name: str
    passed: bool = False
    detail: str = ""
    ms: float = 0

    def ok(self, msg: str = "") -> "VResult":
        self.passed = True
        self.detail = msg
        return self

    def fail(self, msg: str) -> "VResult":
        self.passed = False
        self.detail = msg
        return self


class VisualQA:
    """Playwright-based visual QA for SUPERACE."""

    LOAD_TIMEOUT_MS  = 30_000
    GAME_BOOT_MS     = 12_000   # wait for Cocos2D to initialise
    FPS_SAMPLE_MS    = 2_000

    def __init__(self, url: str = GAME_URL, headless: bool = True):
        self.url = url
        self.headless = headless
        self.results: List[VResult] = []

    # ── Runner ────────────────────────────────────────────────────────

    async def run(self) -> List[VResult]:
        if not PLAYWRIGHT_OK:
            print("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True,
            )
            page = await ctx.new_page()

            console_errors: List[str] = []
            js_exceptions: List[str] = []
            page.on("console",       lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror",     lambda e: js_exceptions.append(str(e)))

            # Navigate once; all tests share the same page
            await self._test_page_load(page)
            # Only continue if page loaded
            if self.results[-1].passed:
                await self._test_canvas_renders(page)
                await self._test_fps(page)
                await self._test_no_critical_console_errors(page, console_errors)
                await self._test_no_js_exceptions(page, js_exceptions)
                await self._test_game_boot(page)

            await browser.close()

        return self.results

    # ── Individual Tests ──────────────────────────────────────────────

    async def _test_page_load(self, page: Page):
        r = VResult("Page Load")
        t0 = time.time()
        try:
            resp = await page.goto(self.url, timeout=self.LOAD_TIMEOUT_MS,
                                   wait_until="domcontentloaded")
            ms = (time.time() - t0) * 1000
            r.ms = ms
            if resp and resp.status == 200:
                r.ok(f"HTTP 200 in {ms:.0f}ms")
            else:
                status = resp.status if resp else "no response"
                r.fail(f"HTTP {status}")
        except Exception as e:
            r.fail(f"Navigation error: {e}")
        self.results.append(r)

    async def _test_canvas_renders(self, page: Page):
        r = VResult("Canvas Renders")
        try:
            canvas = await page.wait_for_selector("#GameCanvas", timeout=10_000)
            if canvas:
                box = await canvas.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    r.ok(f"{int(box['width'])}×{int(box['height'])}px")
                else:
                    r.fail("Canvas has zero dimensions")
            else:
                r.fail("#GameCanvas not found in DOM")
        except Exception as e:
            r.fail(str(e))
        self.results.append(r)

    async def _test_fps(self, page: Page):
        r = VResult("FPS ≥ 30")
        try:
            fps = await page.evaluate(f"""
                () => new Promise(resolve => {{
                    let frames = 0;
                    const start = performance.now();
                    const dur = {self.FPS_SAMPLE_MS};
                    function tick() {{
                        frames++;
                        if (performance.now() - start < dur) {{
                            requestAnimationFrame(tick);
                        }} else {{
                            resolve(frames / (dur / 1000));
                        }}
                    }}
                    requestAnimationFrame(tick);
                }})
            """)
            fps = float(fps)
            r.ms = fps
            if fps >= 30:
                r.ok(f"{fps:.1f} FPS")
            elif fps >= 15:
                r.fail(f"Low FPS: {fps:.1f} (expected ≥ 30)")
            else:
                r.fail(f"Very low FPS: {fps:.1f}")
        except Exception as e:
            r.fail(str(e))
        self.results.append(r)

    async def _test_no_critical_console_errors(self, page: Page, errors: List[str]):
        r = VResult("No Console Errors")
        await page.wait_for_timeout(2000)   # flush deferred errors

        # Filter acceptable non-critical errors
        IGNORE = [
            "favicon.ico",
            "ERR_BLOCKED_BY_CLIENT",
            "log.service.com",          # logging server not available in dev env
            "ERR_NAME_NOT_RESOLVED",    # expected in isolated dev environments
        ]
        critical = [e for e in errors if not any(ign in e for ign in IGNORE)]

        if not critical:
            r.ok(f"{len(errors)} total (all non-critical)")
        else:
            snippet = "; ".join(e[:80] for e in critical[:3])
            r.fail(f"{len(critical)} critical errors: {snippet}")
        self.results.append(r)

    async def _test_no_js_exceptions(self, page: Page, exceptions: List[str]):
        r = VResult("No JS Exceptions")
        if not exceptions:
            r.ok("0 exceptions")
        else:
            r.fail(f"{len(exceptions)} exception(s): {exceptions[0][:120]}")
        self.results.append(r)

    async def _test_game_boot(self, page: Page):
        r = VResult("Game Boots (Cocos2D init)")
        try:
            # Check AppConfig loaded (from config.js)
            app_config = await page.evaluate("() => window.AppConfig || null")
            if app_config:
                env    = app_config.get("env", "?")
                gameid = app_config.get("gameId", "?")
                r.ok(f"AppConfig found — env={env}, gameId={gameid}")
            else:
                # AppConfig may not be exposed; just check canvas still alive
                canvas = await page.query_selector("#GameCanvas")
                r.ok("Canvas present (AppConfig not exposed)") if canvas else r.fail("Canvas gone after boot wait")
        except Exception as e:
            r.fail(str(e))
        self.results.append(r)


# ── Pretty Print ──────────────────────────────────────────────────────

def print_results(results: List[VResult]):
    print("\n── Visual Tests ─────────────────────────────────")
    passed = sum(1 for r in results if r.passed)
    for r in results:
        icon = "✅" if r.passed else "❌"
        print(f"  {icon}  {r.name:<30}  {r.detail}")
    print(f"  Result: {passed}/{len(results)} passed\n")


# ── Entry Point ───────────────────────────────────────────────────────

def run(headless: bool = True) -> List[VResult]:
    qa = VisualQA(headless=headless)
    return asyncio.run(qa.run())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="Open visible browser")
    args = parser.parse_args()

    if not PLAYWRIGHT_OK:
        print("ERROR: Playwright not installed.")
        print("Run:  pip install playwright && playwright install chromium")
        sys.exit(1)

    results = run(headless=not args.show)
    print_results(results)
    sys.exit(0 if all(r.passed for r in results) else 1)
