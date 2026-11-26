"""
tools/app_tools.py -- Simple, clean app launcher and process manager.

The AI determines the app name (e.g., 'Visual Studio Code').
This module simply opens/closes the requested app or website without complex letter-matching engines.

  - open_app(name)      -> opens installed app from Start Menu
  - close_app(name)     -> kills running process by name
  - open_website(url)   -> opens URL in default web browser

TOOL CONTRACT
=============
  ALL_TOOLS   list   -> OpenAI tool schemas
  execute     func   -> execute(name: str, args: dict) -> str
"""

import os
import glob
import webbrowser
import subprocess

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ── App Indexing ──────────────────────────────────────────────────────────────

_START_MENU_ROOTS = [
    os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                 "Microsoft", "Windows", "Start Menu", "Programs"),
    os.path.join(os.environ.get("APPDATA", ""),
                 "Microsoft", "Windows", "Start Menu", "Programs"),
]

def _build_index() -> dict:
    """Map normalized app names to shortcut paths."""
    index = {}
    for root in _START_MENU_ROOTS:
        if not os.path.isdir(root):
            continue
        for lnk in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
            raw_name = os.path.splitext(os.path.basename(lnk))[0]
            norm_name = raw_name.lower().strip()
            if norm_name and norm_name not in index:
                index[norm_name] = lnk
    return index

_APP_INDEX: dict = _build_index()

def refresh_app_index():
    global _APP_INDEX
    _APP_INDEX = _build_index()

def _find_app(name: str) -> tuple:
    """
    Look up app shortcut by name.
    Normalizes underscores to spaces (e.g. 'Visual_Studio_Code' -> 'visual studio code').
    """
    if not name:
        return "", ""

    q = name.replace("_", " ").lower().strip()
    if not q:
        return "", ""

    # 1. Exact match
    if q in _APP_INDEX:
        return q, _APP_INDEX[q]

    # 2. Prefix / Substring match
    candidates = []
    for app_name, lnk_path in _APP_INDEX.items():
        if app_name.startswith(q) or q in app_name:
            candidates.append((app_name, lnk_path))

    if candidates:
        # Pick the shortest matching name
        best = min(candidates, key=lambda x: len(x[0]))
        return best

    return "", ""

# ── Tool Implementations ──────────────────────────────────────────────────────

COMMON_WEB_SERVICES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "netflix": "https://www.netflix.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "twitch": "https://www.twitch.tv",
    "whatsapp": "https://web.whatsapp.com",
    "linkedin": "https://www.linkedin.com",
    "amazon": "https://www.amazon.com",
}

def open_app(name: str) -> str:
    """Open an installed desktop application by name."""
    app_name, lnk_path = _find_app(name)
    if not app_name or not lnk_path:
        q = (name or "").replace("_", " ").lower().strip()
        if q in COMMON_WEB_SERVICES:
            return open_website(COMMON_WEB_SERVICES[q])
        return f"App '{name}' not found in Start Menu shortcuts. If it's a website, use open_website."

    try:
        os.startfile(lnk_path)
        return f"Opened {app_name.title()}."
    except Exception as e:
        return f"Found '{app_name.title()}' but failed to open it: {e}"

def close_app(name: str) -> str:
    """Close a running application process by name."""
    if not name or not name.strip():
        return "No app name provided to close."

    q = name.replace("_", " ").lower().strip()

    if HAS_PSUTIL:
        matched_proc = None
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = os.path.splitext(proc.info["name"] or "")[0].lower()
                if pname == q or q in pname:
                    matched_proc = proc
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if matched_proc:
            try:
                proc_name = matched_proc.info.get("name") or name
                for child in matched_proc.children(recursive=True):
                    try:
                        child.kill()
                    except Exception:
                        pass
                matched_proc.kill()
                return f"Closed {proc_name}."
            except Exception as e:
                return f"Could not close '{name}': {e}"

        return f"App '{name}' is not currently running."

    # Fallback to taskkill
    target = q.replace(" ", "") + ".exe"
    res = subprocess.run(["taskkill", "/IM", target, "/F"], capture_output=True, text=True)
    if res.returncode == 0:
        return f"Closed {name}."
    return f"Could not close '{name}'."

def open_website(url: str) -> str:
    """Open a website URL in default browser."""
    if not url:
        return "No URL provided."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url} in browser."

# ── Schemas & Dispatcher ──────────────────────────────────────────────────────

ALL_TOOLS = [
    {
        "type": "function",
        "name": "open_app",
        "description": "Open an installed desktop application by name (e.g. 'Visual Studio Code', 'Spotify', 'Chrome', 'Steam').",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the application to open, e.g. 'Visual Studio Code', 'Visual_Studio_Code', or 'Spotify'."
                }
            },
            "required": ["name"]
        }
    },
    {
        "type": "function",
        "name": "close_app",
        "description": "Close a running application process by name (e.g. 'Visual Studio Code', 'Chrome', 'Spotify').",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name or process name of the app to close."
                }
            },
            "required": ["name"]
        }
    },
    {
        "type": "function",
        "name": "open_website",
        "description": "Open any website URL in the browser (e.g. 'youtube.com', 'github.com').",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Website URL or domain to open."
                }
            },
            "required": ["url"]
        }
    }
]

def execute(name: str, args: dict) -> str:
    if name == "open_app":
        return open_app(args.get("name", ""))
    elif name == "close_app":
        return close_app(args.get("name", ""))
    elif name == "open_website":
        return open_website(args.get("url", ""))
    return f"[app_tools] Unknown tool: '{name}'"
