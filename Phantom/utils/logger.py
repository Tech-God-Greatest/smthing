import sys
import datetime

# Reconfigure standard output streams to UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Enable VT100 / ANSI color sequences on Windows console if colorama is available
try:
    import colorama
    colorama.just_fix_windows_console()
except Exception:
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

# ANSI Formatting & Colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

CYAN = "\033[36m"
MAGENTA = "\033[35m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
RED = "\033[31m"
BRIGHT_BLACK = "\033[90m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_CYAN = "\033[96m"

TAG_COLORS = {
    "STT": BRIGHT_CYAN,
    "TTS": MAGENTA,
    "Groq": GREEN,
    "Ollama": BLUE,
    "Local AI": BLUE,
    "Vision": YELLOW,
    "Preloader": BRIGHT_BLUE,
    "Hotkey": BRIGHT_BLACK,
    "Voice": CYAN,
    "WebSearch": YELLOW,
    "Notch": CYAN,
    "Query": BRIGHT_BLUE,
    "TitleWorker": BRIGHT_BLACK,
}


def _get_timestamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def log_info(tag: str, message: str):
    """Log formatted informational message."""
    color = TAG_COLORS.get(tag, BOLD)
    ts = f"{DIM}[{_get_timestamp()}]{RESET}"
    tag_str = f"{BOLD}{color}[{tag}]{RESET}"
    print(f"{ts} {tag_str} {message}")


def log_success(tag: str, message: str):
    """Log formatted success message."""
    color = TAG_COLORS.get(tag, GREEN)
    ts = f"{DIM}[{_get_timestamp()}]{RESET}"
    tag_str = f"{BOLD}{color}[{tag}]{RESET}"
    print(f"{ts} {tag_str} {GREEN}✔ {message}{RESET}")


def log_warning(tag: str, message: str):
    """Log formatted warning message."""
    ts = f"{DIM}[{_get_timestamp()}]{RESET}"
    tag_str = f"{BOLD}{YELLOW}[{tag}]{RESET}"
    print(f"{ts} {tag_str} {YELLOW}⚠ {message}{RESET}")


def log_error(tag: str, message: str):
    """Log formatted error message."""
    ts = f"{DIM}[{_get_timestamp()}]{RESET}"
    tag_str = f"{BOLD}{RED}[{tag}]{RESET}"
    print(f"{ts} {tag_str} {RED}✖ {message}{RESET}")


def log_user(message: str):
    """Log user speech / input message."""
    ts = f"{DIM}[{_get_timestamp()}]{RESET}"
    user_tag = f"{BOLD}{BRIGHT_GREEN}You:{RESET}"
    print(f"{ts} {user_tag} {message}")


def log_assistant(message: str):
    """Log assistant speech / response message."""
    ts = f"{DIM}[{_get_timestamp()}]{RESET}"
    assistant_tag = f"{BOLD}{BRIGHT_BLUE}Assistant:{RESET}"
    print(f"{ts} {assistant_tag} {message}")
