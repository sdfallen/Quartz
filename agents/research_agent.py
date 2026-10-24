"""
agents/research_agent.py  —  JARVIS Research Agent
Fixed:
  - Interruptible HTTP requests
  - Rate limiting between requests
  - Result caching
  - Proper stop handling
"""

import hashlib
import threading
import time
import urllib.parse
from datetime import datetime
from agents.base_agent import BaseAgent
from logger import get_logger

log = get_logger(__name__)

try:
    import requests as _requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    log.warning("requests library not installed")


class ResearchAgent(BaseAgent):

    _cache: dict = {}
    _CACHE_TTL   = 3600  # 1 hour

    def __init__(self, jarvis_tools: dict):
        super().__init__(
            "ResearchAgent", jarvis_tools)
        self.max_sources = 3

    # ── Main ──────────────────────────────────────────

    def run(self, goal: str = ""):
        if not goal:
            self._log_step(
                "No research topic given.")
            self.is_running = False
            self._status    = "idle"
            return

        self._log_step(
            f"Starting research: {goal}")

        try:
            result = self._research(goal)
            if result:
                self._add_result(
                    result, level="success")
                self._use_tool(
                    "add_note",
                    f"Research: {goal}\n\n"
                    f"{result[:300]}",
                    "research")
                self._log_step(
                    "Research complete. "
                    "Saved to notes.")
        except Exception as exc:
            self._log_step(
                f"Research error: {exc}")

        self.is_running = False
        self._status    = "completed"

    # ── Research logic ────────────────────────────────

    def _research(self, topic: str) -> str:
        lines = [
            f"🔍 Research Report: {topic}",
            "─" * 40,
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        if not self.is_running:
            return ""

        # Step 1: DuckDuckGo
        self._log_step(
            "Step 1: DuckDuckGo search...")
        ddg = self._cached_fetch(
            "ddg", topic, self._duckduckgo)
        if ddg:
            lines += ["📖 Quick Summary:", ddg, ""]

        # Polite delay
        self._wait(1.0)
        if not self.is_running:
            lines.append("[cancelled]")
            return "\n".join(lines)

        # Step 2: Wikipedia
        self._log_step(
            "Step 2: Wikipedia lookup...")
        wiki = self._cached_fetch(
            "wiki", topic, self._wikipedia)
        if wiki:
            lines += ["📚 Wikipedia:", wiki, ""]

        # Step 3: Open browser
        if self.is_running:
            self._log_step(
                "Step 3: Opening browser...")
            self._use_tool(
                "google_search", topic)
            lines += [
                "🌐 Browser search opened.",
                f"🔎 Query: {topic}",
            ]

        if not ddg and not wiki:
            lines.append(
                "\nℹ️ No instant data found."
                "\nCheck browser for results.")

        return "\n".join(lines)

    def _cached_fetch(self,
                      source: str,
                      topic: str,
                      fetcher) -> str:
        key = hashlib.md5(
            f"{source}:{topic}".encode()
        ).hexdigest()

        cached = self._cache.get(key)
        if cached:
            age = time.time() - cached["time"]
            if age < self._CACHE_TTL:
                self._log_step(
                    f"Cache hit: {source}")
                return cached["data"]

        result = fetcher(topic)
        if result:
            self._cache[key] = {
                "data": result,
                "time": time.time(),
            }
        return result

    def _fetch_with_cancel(
            self, url: str,
            timeout: int = 8) -> dict:
        """HTTP GET that respects stop()."""
        if not REQUESTS_OK:
            return {}

        result: dict = {
            "resp": None, "exc": None}
        done = threading.Event()

        def fetch():
            try:
                result["resp"] = (
                    _requests.get(
                        url, timeout=timeout))
            except Exception as exc:
                result["exc"] = exc
            finally:
                done.set()

        t = threading.Thread(
            target=fetch, daemon=True)
        t.start()

        while not done.wait(timeout=0.1):
            if not self.is_running:
                return {}

        resp = result["resp"]
        if resp and resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return {}
        return {}

    def _duckduckgo(self, topic: str) -> str:
        try:
            url = (
                "https://api.duckduckgo.com/?q="
                + urllib.parse.quote(topic)
                + "&format=json&no_html=1"
                "&skip_disambig=1")
            data  = self._fetch_with_cancel(url)
            parts = []

            answer = data.get("Answer", "")
            if answer:
                parts.append(
                    f"Answer: {answer}")

            abstract = data.get(
                "AbstractText", "")
            source   = data.get(
                "AbstractSource", "")
            if abstract:
                parts.append(
                    f"({source}): "
                    f"{abstract[:400]}")

            definition = data.get(
                "Definition", "")
            if definition:
                parts.append(
                    f"Definition: "
                    f"{definition[:300]}")

            return "\n".join(parts)

        except Exception as exc:
            self._log_step(
                f"DuckDuckGo error: {exc}")
            return ""

    def _wikipedia(self, topic: str) -> str:
        try:
            url = (
                "https://en.wikipedia.org"
                "/api/rest_v1/page/summary/"
                + urllib.parse.quote(topic))
            data = self._fetch_with_cancel(url)

            extract  = data.get("extract", "")
            title    = data.get("title", topic)
            page_url = (
                data.get(
                    "content_urls", {})
                .get("desktop", {})
                .get("page", ""))

            if extract:
                return (
                    f"{title}: "
                    f"{extract[:500]}"
                    + (f"\n🔗 {page_url}"
                       if page_url else ""))
            return ""

        except Exception as exc:
            self._log_step(
                f"Wikipedia error: {exc}")
            return ""