"""
One-time setup: opens a visible Chrome browser, waits for you to log in to
LinkedIn (including any 2FA/verification), then auto-saves the session to
session.json when it detects your feed. Run this once locally.

Usage:
    python setup_session.py
"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

SESSION_FILE = Path("session.json")
TIMEOUT_SECONDS = 300  # 5 minutes to complete login


async def main():
    print("\n=== LinkedIn Session Setup ===")
    print("A Chrome browser window will open.")
    print("Log in to LinkedIn normally — including any 2FA or verification steps.")
    print(f"The session will be saved automatically once your feed loads.")
    print(f"(You have {TIMEOUT_SECONDS // 60} minutes to complete login)\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await ctx.new_page()
        await page.goto("https://www.linkedin.com/login")

        print("Waiting for you to log in to LinkedIn...")

        # Poll until we see a logged-in URL or timeout
        logged_in_markers = ("/feed", "/mynetwork", "/jobs", "/messaging", "/notifications")
        deadline = asyncio.get_event_loop().time() + TIMEOUT_SECONDS

        while asyncio.get_event_loop().time() < deadline:
            current = page.url
            if any(m in current for m in logged_in_markers):
                break
            await asyncio.sleep(1)
        else:
            print("\nTimed out waiting for login. Please try again.")
            await browser.close()
            sys.exit(1)

        print(f"Logged in detected at: {page.url}")
        await ctx.storage_state(path=str(SESSION_FILE))
        print(f"Session saved to {SESSION_FILE}")
        print("\nSetup complete. You can now run:  python agent.py --dry-run\n")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
