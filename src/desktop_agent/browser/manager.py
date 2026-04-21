"""Playwright browser session manager.

Provides a persistent browser with cookie/session persistence,
DOM access, JS rendering, and structured data extraction.
Replaces the old curl-based web research approach.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from desktop_agent.config import get_settings
from desktop_agent.log import get_logger

log = get_logger(__name__)


class BrowserManager:
    """Manages a persistent Playwright browser session."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def start(self) -> None:
        """Launch the browser (lazy — only starts when first needed)."""
        if self._page is not None:
            return

        from playwright.async_api import async_playwright

        settings = get_settings()

        self._playwright = await async_playwright().start()

        browser_type = getattr(self._playwright, settings.browser.default_browser)

        # Persistent context for cookies/sessions
        user_data = Path(settings.browser.user_data_dir)
        user_data.mkdir(parents=True, exist_ok=True)

        self._context = await browser_type.launch_persistent_context(
            user_data_dir=str(user_data),
            headless=settings.browser.headless,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )

        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

        log.info("browser_started", browser=settings.browser.default_browser)

    async def stop(self) -> None:
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._playwright = None
        log.info("browser_stopped")

    @property
    def page(self):
        return self._page

    async def navigate(self, url: str) -> str:
        """Navigate to a URL and wait for load."""
        await self.start()
        settings = get_settings()
        try:
            await self._page.goto(
                url, wait_until="domcontentloaded", timeout=settings.browser.page_load_timeout
            )
            title = await self._page.title()
            return f"Navigated to: {title} ({url})"
        except Exception as e:
            return f"Navigation failed: {e}"

    async def extract_text(self, selector: str = "body") -> str:
        """Extract visible text from the page or a specific element."""
        await self.start()
        try:
            element = await self._page.query_selector(selector)
            if element:
                text = await element.inner_text()
                if len(text) > 5000:
                    text = text[:5000] + "\n… [truncated]"
                return text
            return "(element not found)"
        except Exception as e:
            return f"Extract failed: {e}"

    async def extract_links(self, selector: str = "a") -> list[dict[str, str]]:
        """Extract all links from the page."""
        await self.start()
        try:
            links = await self._page.eval_on_selector_all(
                selector,
                """els => els.map(e => ({
                    text: e.innerText.trim().substring(0, 100),
                    href: e.href
                })).filter(l => l.href && l.text)""",
            )
            return links[:100]
        except Exception as e:
            log.warning("link_extraction_failed", error=str(e))
            return []

    async def extract_tables(self) -> list[list[list[str]]]:
        """Extract all HTML tables as lists of rows."""
        await self.start()
        try:
            tables = await self._page.eval_on_selector_all(
                "table",
                """tables => tables.map(t =>
                    Array.from(t.rows).map(r =>
                        Array.from(r.cells).map(c => c.innerText.trim())
                    )
                )""",
            )
            return tables
        except Exception as e:
            log.warning("table_extraction_failed", error=str(e))
            return []

    async def click_element(self, selector: str) -> str:
        """Click an element by CSS selector."""
        await self.start()
        try:
            await self._page.click(selector, timeout=5000)
            return f"Clicked: {selector}"
        except Exception as e:
            return f"Click failed ({selector}): {e}"

    async def type_in_element(
        self, selector: str, text: str, *, press_enter: bool = False
    ) -> str:
        """Type text into an input element."""
        await self.start()
        try:
            await self._page.fill(selector, text)
            if press_enter:
                await self._page.press(selector, "Enter")
            return f"Typed into {selector}: {text[:50]}"
        except Exception as e:
            return f"Type failed ({selector}): {e}"

    async def screenshot(self) -> bytes:
        """Take a screenshot of the current page."""
        await self.start()
        return await self._page.screenshot(type="png")

    async def evaluate(self, js: str) -> Any:
        """Evaluate JavaScript in the page context."""
        await self.start()
        try:
            return await self._page.evaluate(js)
        except Exception as e:
            return f"JS eval failed: {e}"

    async def get_page_info(self) -> dict:
        """Get current page URL, title, and meta info."""
        await self.start()
        return {
            "url": self._page.url,
            "title": await self._page.title(),
        }

    async def search_google(self, query: str) -> str:
        """Navigate to Google search results for a query."""
        from urllib.parse import quote_plus

        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return await self.navigate(url)

    async def wait_for_selector(self, selector: str, *, timeout: int = 10000) -> bool:
        """Wait for an element to appear on the page."""
        await self.start()
        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False
