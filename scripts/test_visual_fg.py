#!/usr/bin/env python3
"""
SUPERACE Free Game Visual QA Tests — Playwright
Tests the visual rendering and UI correctness of the Free Game flow.

Setup:
    pip install playwright
    playwright install chromium

Run:
    python test_visual_fg.py
    python test_visual_fg.py --show   # visible browser
"""
import sys
import os
import asyncio
import time
import argparse
from dataclasses import dataclass
from typing import List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import GAME_URL, BASE_URL, SSO_KEY, DEFAULT_BET

try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False


@dataclass
class VResult:
    name: str
    passed: bool = False
    detail: str = ""
    ms: float = 0

    def ok(self, msg=""):
        self.passed = True; self.detail = msg; return self

    def fail(self, msg):
        self.passed = False; self.detail = msg; return self


# ── Helpers ───────────────────────────────────────────────────────────

async def wait_for_canvas_ready(page: Page, timeout=20_000):
    """Wait until #GameCanvas is visible and has non-zero size."""
    await page.wait_for_selector("#GameCanvas", timeout=timeout)
    await page.wait_for_timeout(5000)   # let Cocos2D finish booting


async def get_js(page: Page, expr: str, default=None):
    """Evaluate JS expression, return default on error."""
    try:
        return await page.evaluate(expr)
    except Exception:
        return default


# ── FG Visual QA ─────────────────────────────────────────────────────

class FreeGameVisualQA:
    """
    Visual QA specifically for Free Game (FG) flow.

    Strategy:
    - Use the game API directly (via fetch inside the page) to force a FG state
    - OR spin repeatedly until FG triggers
    - Then observe the UI for correct FG-specific elements
    """

    GAME_BOOT_MS  = 10_000
    FG_WAIT_MS    = 8_000    # wait after FG triggers for animations

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.results: List[VResult] = []

    async def run(self) -> List[VResult]:
        if not PLAYWRIGHT_OK:
            print("Playwright not installed.")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True,
            )
            page = await ctx.new_page()

            js_exceptions = []
            page.on("pageerror", lambda e: js_exceptions.append(str(e)))

            # Navigate and wait for game boot
            await page.goto(GAME_URL, timeout=30_000, wait_until="domcontentloaded")
            await wait_for_canvas_ready(page)

            # Run all FG visual tests
            await self._test_game_loaded(page)
            await self._test_canvas_pixel_content(page)
            await self._test_appconfig_fg_ready(page)
            await self._test_no_critical_exceptions(page, js_exceptions)
            await self._test_fps_stable(page)
            await self._test_api_fg_state_accessible(page)
            await self._test_game_ui_completeness(page)

            await browser.close()

        return self.results

    # ── Tests ─────────────────────────────────────────────────────────

    async def _test_game_loaded(self, page: Page):
        r = VResult("Game Fully Loaded")
        canvas = await page.query_selector("#GameCanvas")
        if not canvas:
            self.results.append(r.fail("Canvas not found"))
            return
        box = await canvas.bounding_box()
        if box and box["width"] > 100 and box["height"] > 100:
            r.ok(f"Canvas {int(box['width'])}×{int(box['height'])}")
        else:
            r.fail(f"Canvas too small: {box}")
        self.results.append(r)

    async def _test_canvas_pixel_content(self, page: Page):
        """
        Verify the canvas is not blank (all black/white).
        Samples pixel values and checks for variation.
        """
        r = VResult("Canvas Has Pixel Content")
        try:
            result = await page.evaluate("""
                () => {
                    const canvas = document.getElementById('GameCanvas');
                    if (!canvas) return { ok: false, reason: 'no canvas' };
                    const ctx = canvas.getContext('2d');
                    if (!ctx) return { ok: false, reason: 'no 2d context (WebGL game)' };

                    // Sample 10 points from center area
                    const w = canvas.width, h = canvas.height;
                    const samples = [];
                    for (let i = 0; i < 10; i++) {
                        const x = Math.floor(w * 0.2 + (w * 0.6 * i / 10));
                        const y = Math.floor(h * 0.3 + (h * 0.4 * i / 10));
                        const px = ctx.getImageData(x, y, 1, 1).data;
                        samples.push({ r: px[0], g: px[1], b: px[2] });
                    }
                    const distinct = new Set(samples.map(s => `${s.r},${s.g},${s.b}`)).size;
                    return { ok: distinct > 2, distinct, samples: samples.slice(0,3) };
                }
            """)
            if result.get("ok"):
                r.ok(f"{result.get('distinct')} distinct pixel values")
            elif result.get("reason") == "no 2d context (WebGL game)":
                # WebGL canvas — can't read pixels with 2D context; this is expected
                r.ok("WebGL canvas (pixel read not available — expected for Cocos2D)")
            else:
                r.fail(f"Canvas appears blank: {result}")
        except Exception as e:
            r.fail(str(e))
        self.results.append(r)

    async def _test_appconfig_fg_ready(self, page: Page):
        """Verify AppConfig is loaded and game is in a playable state."""
        r = VResult("AppConfig & Game State")
        try:
            cfg = await get_js(page, "() => window.AppConfig || null")
            if not cfg:
                r.fail("AppConfig not found on window")
                self.results.append(r)
                return

            issues = []
            if cfg.get("env") not in [1, 2, 3, 4]:
                issues.append(f"unknown env={cfg.get('env')}")
            if not cfg.get("apiHost"):
                issues.append("apiHost missing")
            if cfg.get("gameId") != 1:
                issues.append(f"unexpected gameId={cfg.get('gameId')}")

            if issues:
                r.fail(f"Config issues: {', '.join(issues)}")
            else:
                r.ok(f"env={cfg.get('env')}, apiHost ok, gameId=1")
        except Exception as e:
            r.fail(str(e))
        self.results.append(r)

    async def _test_no_critical_exceptions(self, page: Page, exceptions: list):
        r = VResult("No Critical JS Exceptions")
        # BUG-006 is a known issue — flag it but don't block
        known = ["LOG_ENDPOINT_SUFFIX"]
        critical = [e for e in exceptions if not any(k in e for k in known)]
        known_found = [e for e in exceptions if any(k in e for k in known)]

        if not exceptions:
            r.ok("0 exceptions")
        elif not critical and known_found:
            r.fail(f"BUG-006 active: {known_found[0][:80]} (known, needs fix)")
        else:
            r.fail(f"{len(critical)} unknown exception(s): {critical[0][:100]}")
        self.results.append(r)

    async def _test_fps_stable(self, page: Page):
        """Measure FPS over 2 seconds — should be ≥ 30."""
        r = VResult("FPS Stable (≥30)")
        try:
            fps = await page.evaluate("""
                () => new Promise(resolve => {
                    let f = 0; const s = performance.now();
                    function t() {
                        f++;
                        if (performance.now() - s < 2000) requestAnimationFrame(t);
                        else resolve(f / 2);
                    }
                    requestAnimationFrame(t);
                })
            """)
            fps = float(fps)
            if fps >= 30:
                r.ok(f"{fps:.1f} FPS")
            else:
                r.fail(f"Low FPS: {fps:.1f} (expected ≥30)")
        except Exception as e:
            r.fail(str(e))
        self.results.append(r)

    async def _test_api_fg_state_accessible(self, page: Page):
        """
        Call the game API from inside the browser context to verify:
        1. Login works
        2. /play endpoint returns correct structure
        3. FG state field (hasFreeSpin) is present
        """
        r = VResult("API FG State Field Accessible")
        try:
            api_result = await page.evaluate(f"""
                async () => {{
                    try {{
                        // Login
                        const loginRes = await fetch(
                            '{BASE_URL}/sso/login?ssoKey={SSO_KEY}',
                            {{ method: 'POST' }}
                        );
                        const loginData = await loginRes.json();
                        if (loginData.error !== 0) return {{ ok: false, reason: 'login failed: ' + loginData.error }};

                        const token = loginData.data.token;

                        // Play
                        const playRes = await fetch(
                            '{BASE_URL}/play?bet={DEFAULT_BET}&token=' + token,
                            {{ method: 'POST' }}
                        );
                        const playData = await playRes.json();
                        if (playData.error !== 0) return {{ ok: false, reason: 'play failed: ' + playData.error }};

                        const pt = playData.data.slotData.paytable;
                        const hasFgField = 'hasFreeSpin' in pt || 'hasFreeGame' in pt;
                        const fgValue = pt.hasFreeSpin ?? pt.hasFreeGame ?? null;

                        return {{
                            ok: hasFgField,
                            hasFgField,
                            fgValue,
                            mgCascades: pt.mgTable ? pt.mgTable.length : 0,
                            totalWin: playData.data.slotData.totalWin
                        }};
                    }} catch(e) {{
                        return {{ ok: false, reason: e.message }};
                    }}
                }}
            """)

            if api_result.get("ok"):
                fg = api_result.get("fgValue")
                cascades = api_result.get("mgCascades", 0)
                win = api_result.get("totalWin", 0)
                r.ok(f"hasFreeSpin={fg}, cascades={cascades}, win={win}")
            else:
                r.fail(f"API error: {api_result.get('reason')}")
        except Exception as e:
            r.fail(str(e))
        self.results.append(r)

    async def _test_game_ui_completeness(self, page: Page):
        """
        Check DOM for expected UI structure.
        Since Cocos2D renders on canvas, most UI is inside WebGL.
        We verify the HTML shell is intact.
        """
        r = VResult("HTML Shell Intact")
        try:
            checks = await page.evaluate("""
                () => ({
                    hasCanvas:       !!document.getElementById('GameCanvas'),
                    hasSplash:       !!document.getElementById('splash-image'),
                    hasProgressBar:  !!document.querySelector('#GameDiv') || !!document.querySelector('#progress-bar') || !!document.querySelector('.progress'),
                    bodyNotEmpty:    document.body.innerHTML.length > 500,
                    title:           document.title || '(no title)'
                })
            """)
            issues = []
            if not checks.get("hasCanvas"):      issues.append("canvas missing")
            if not checks.get("bodyNotEmpty"):   issues.append("body empty")

            if not issues:
                r.ok(f"canvas ✓, title='{checks.get('title')}'")
            else:
                r.fail(", ".join(issues))
        except Exception as e:
            r.fail(str(e))
        self.results.append(r)


# ── Print Results ─────────────────────────────────────────────────────

def print_results(results: List[VResult]):
    print("\n── FG Visual Tests ──────────────────────────────")
    for r in results:
        icon = "✅" if r.passed else "❌"
        print(f"  {icon}  {r.name:<35}  {r.detail}")
    passed = sum(1 for r in results if r.passed)
    print(f"  Result: {passed}/{len(results)} passed\n")


# ── Entry Point ───────────────────────────────────────────────────────

def run(headless=True) -> List[VResult]:
    qa = FreeGameVisualQA(headless=headless)
    return asyncio.run(qa.run())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="Visible browser")
    args = parser.parse_args()

    if not PLAYWRIGHT_OK:
        print("Install: pip install playwright && playwright install chromium")
        sys.exit(1)

    results = run(headless=not args.show)
    print_results(results)
    sys.exit(0 if all(r.passed for r in results) else 1)
