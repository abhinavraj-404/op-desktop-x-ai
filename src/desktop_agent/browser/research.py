"""Web research engine — structured data extraction from the web.

Uses Playwright for JS-rendered pages, with fallback to curl for simple APIs.
Integrates with Wikipedia, GitHub, and other structured data sources.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from urllib.parse import quote_plus

from desktop_agent.browser.manager import BrowserManager
from desktop_agent.log import get_logger

log = get_logger(__name__)


class ResearchEngine:
    """Structured web research with API-first strategy."""

    def __init__(self, browser: BrowserManager) -> None:
        self._browser = browser

    async def search(self, query: str, *, source: str = "google") -> str:
        """Search the web and return extracted results."""
        if source == "wikipedia":
            return await self._wikipedia_api(query)
        elif source == "github":
            return await self._github_api(query)
        else:
            return await self._google_search(query)

    async def fetch_url(self, url: str) -> str:
        """Fetch a URL and return the visible text content."""
        result = await self._browser.navigate(url)
        if "failed" in result.lower():
            return result
        text = await self._browser.extract_text()
        return text

    async def extract_structured_data(self, url: str) -> dict:
        """Navigate to URL and extract structured data (tables, links)."""
        await self._browser.navigate(url)
        return {
            "text": await self._browser.extract_text(),
            "links": await self._browser.extract_links(),
            "tables": await self._browser.extract_tables(),
        }

    # ── API-first data sources ────────────────────────────────────

    async def _wikipedia_api(self, query: str) -> str:
        """Fetch data from Wikipedia REST API (faster & more reliable than browsing)."""
        encoded = quote_plus(query.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["curl", "-sL", "--max-time", "10", url],
                capture_output=True,
                text=True,
                timeout=15,
            )
            data = json.loads(result.stdout)
            title = data.get("title", query)
            extract = data.get("extract", "No summary available.")
            return f"Wikipedia — {title}:\n{extract}"
        except Exception as e:
            return f"Wikipedia API failed: {e}"

    async def _github_api(self, query: str) -> str:
        """Search GitHub API for repository information."""
        search_url = f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&per_page=3"
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["curl", "-sL", "--max-time", "10", search_url],
                capture_output=True,
                text=True,
                timeout=15,
            )
            data = json.loads(result.stdout)
            items = data.get("items", [])
            if not items:
                return f"No GitHub repos found for: {query}"

            lines = []
            for repo in items:
                lines.append(
                    f"- {repo['full_name']}: ★{repo['stargazers_count']} "
                    f"| {repo.get('language', 'N/A')} "
                    f"| {repo.get('description', '')[:100]}"
                )
            return "GitHub results:\n" + "\n".join(lines)
        except Exception as e:
            return f"GitHub API failed: {e}"

    async def _google_search(self, query: str) -> str:
        """Search Google using Playwright (JS-rendered results)."""
        result = await self._browser.search_google(query)
        if "failed" in result.lower():
            # Fallback to curl
            return await self._curl_search(query)

        await asyncio.sleep(1.0)  # Wait for results to render
        text = await self._browser.extract_text("div#search")
        if not text or len(text) < 50:
            text = await self._browser.extract_text("body")
        return text[:3000] if text else "No search results found."

    async def _curl_search(self, query: str) -> str:
        """Fallback: curl-based search when browser is unavailable."""
        import re

        url = f"https://www.google.com/search?q={quote_plus(query)}"
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["curl", "-sL", "-A", "Mozilla/5.0", "--max-time", "15", url],
                capture_output=True,
                text=True,
                timeout=20,
            )
            text = re.sub(r"<script[^>]*>.*?</script>", "", result.stdout, flags=re.DOTALL | re.I)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:3000] if text else "No results."
        except Exception as e:
            return f"Search failed: {e}"
