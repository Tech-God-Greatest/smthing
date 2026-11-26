"""
tools/web_tools.py — Real-time web search and web page reading.

TOOL CONTRACT (every tool file must follow this)
================================================
  ALL_TOOLS   list   → OpenAI tool schemas for the tools in this file
  execute     func   → execute(name: str, args: dict) -> str
"""

import datetime
import urllib.parse
import requests
from bs4 import BeautifulSoup
from utils.logger import log_error

# Try the fastest available DuckDuckGo library
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


_http_session = requests.Session()
_http_session.headers.update(HEADERS)

_SEARCH_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 300.0  # 5 minutes

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

# ── Tool implementations ──────────────────────────────────────────────────────

def _run_ddgs(query: str, max_results: int) -> list:
    """Helper to query DDGS with timeout initialization."""
    res = []
    if DDGS is None:
        return res
    try:
        try:
            ddg = DDGS(timeout=2.5)
        except TypeError:
            ddg = DDGS()
        for item in list(ddg.text(query, max_results=max_results)):
            title   = item.get("title", "").strip()
            link    = item.get("href",  "").strip()
            snippet = item.get("body",  "").strip()
            if len(snippet) > 220:
                snippet = snippet[:220] + "..."
            if title or link:
                res.append(f"Title: {title}\nURL: {link}\nSnippet: {snippet}\n")
    except Exception as e:
        log_error("WebSearch", f"DDGS Error: {e}")
    return res


def web_search(query: str, max_results: int = 3) -> str:
    """Search the web using DDGS with an HTML fallback and memory caching."""
    clean_q = (query or "").strip().lower()

    # Fast path: instant answer for pure time/date queries (0ms network latency)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")
    time_triggers = ["what time", "current time", "time now", "what is the date", "what date", "today's date", "day of the week", "what day is today"]
    if any(t in clean_q for t in time_triggers) and len(clean_q.split()) <= 7:
        return f"System Current Time: {now_str}"

    # Fast path: check memory cache
    now = time.time()
    if clean_q in _SEARCH_CACHE:
        cached_time, cached_res = _SEARCH_CACHE[clean_q]
        if (now - cached_time) < _CACHE_TTL:
            return cached_res

    results = []

    # 1. DDGS library (preferred, with strict 2.5s max thread execution timeout)
    if DDGS is not None:
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_ddgs, query, max_results)
                results = future.result(timeout=2.5)
        except FutureTimeoutError:
            log_error("WebSearch", "DDGS search timed out after 2.5s; switching to HTML fallback.")
        except Exception as e:
            log_error("WebSearch", f"DDGS Execution Error: {e}")

    # 2. HTML fallback when DDGS returns nothing
    if not results:
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            resp = _http_session.get(url, timeout=2.5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for result in soup.find_all("div", class_="result"):
                    title_tag   = result.find("a", class_="result__a")
                    snippet_tag = result.find("a", class_="result__snippet")
                    if not title_tag:
                        continue
                    title   = title_tag.get_text(strip=True)
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else "No snippet."
                    link    = title_tag.get("href", "")
                    if "/l/?" in link and "uddg=" in link:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                        link   = parsed.get("uddg", [link])[0]
                    elif link.startswith("//"):
                        link = "https:" + link
                    results.append(f"Title: {title}\nURL: {link}\nSnippet: {snippet}\n")
                    if len(results) >= max_results:
                        break
        except Exception as e:
            log_error("WebSearch", f"HTML Fallback Error: {e}")

    # 3. Always include system time for time/date queries
    if any(k in clean_q for k in ["time", "date", "clock", "today"]):
        time_info = f"System Current Time: {now_str}\n"
        final_str = time_info + ("\n---\n" + "\n---\n".join(results) if results else "")
    elif not results:
        final_str = f"No web search results found. (Current System Time: {now_str})"
    else:
        final_str = "\n---\n".join(results)

    # Store in LRU cache
    if len(_SEARCH_CACHE) > 50:
        _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
    _SEARCH_CACHE[clean_q] = (now, final_str)

    return final_str


def fetch_web_page(url: str, max_chars: int = 4000) -> str:
    """Fetch a URL and return clean body text."""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        resp = requests.get(url, headers=HEADERS, timeout=5)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        if len(text) > max_chars:
            truncated = text[:max_chars]
            last_period = max(truncated.rfind('. '), truncated.rfind('! '), truncated.rfind('? '))
            if last_period > max_chars // 2:
                text = truncated[:last_period + 1] + "... [content truncated]"
            else:
                last_space = truncated.rfind(' ')
                text = (truncated[:last_space] if last_space > 0 else truncated) + "... [content truncated]"
        return text or "Web page fetched but contained no readable text."
    except Exception as e:
        return f"Error fetching web page '{url}': {e}"


# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

ALL_TOOLS = [
    {
        "type": "function",
        "name": "web_search",
        "description": (
            "Search the internet for real-time information, news, current events, "
            "documentation, or facts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query keywords."
                }
            },
            "required": ["query"]
        }
    },
    {
        "type": "function",
        "name": "fetch_web_page",
        "description": "Fetch and extract plain text content from a web page URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The HTTP/HTTPS URL of the page to read."
                }
            },
            "required": ["url"]
        }
    }
]


# ── Dispatcher (called by registry.dispatch) ──────────────────────────────────

def execute(name: str, args: dict) -> str:
    """Route a web tool call by name."""
    if name == "web_search":
        return web_search(args.get("query", ""))
    elif name == "fetch_web_page":
        return fetch_web_page(args.get("url", ""))
    else:
        return f"[web_tools] Unknown tool: '{name}'"


# ── Backwards-compat aliases ──────────────────────────────────────────────────
WEB_TOOLS        = ALL_TOOLS
execute_web_tool = execute
