"""
tools/__init__.py — Public surface of the tools package.

Import from here in llm.py and anywhere else:

    from tools import ALL_SCHEMAS, dispatch
    from tools import search_memory            # direct helper, if needed
"""

# ── Registry (the only file you normally need to edit to add a tool) ──────────
from tools.registry import ALL_SCHEMAS, dispatch, EXECUTOR_MAP   # noqa: F401

# ── Individual tool helpers re-exported for convenience ───────────────────────
from tools.memory_tools import (    # noqa: F401
    search_memory,
    MEMORY_TOOLS,
    execute_memory_tool,
)
from tools.web_tools import (       # noqa: F401
    web_search,
    fetch_web_page,
    WEB_TOOLS,
    execute_web_tool,
)
from tools.keyboard_tools import (    # noqa: F401
    keyboard_action,
    KEYBOARD_TOOLS,
    execute_keyboard_tool,
)
from tools.mouse_tools import (       # noqa: F401
    mouse_action,
    mouse_click,
    move_mouse,
    mouse_scroll,
    get_mouse_position,
    MOUSE_TOOLS,
    execute_mouse_tool,
)
from tools.system_tools import (      # noqa: F401
    get_system_overview,
    get_cpu_status,
    get_cpu_specs,
    get_gpu_status,
    get_display_info,
    get_ram_status,
    get_ram_hardware_specs,
    get_disk_status,
    get_storage_hardware_info,
    get_motherboard_info,
    get_network_info,
    get_battery_status,
    get_temperatures,
    get_fan_speeds,
    get_power_draw,
    get_top_resource_apps,
    get_process_list,
    ALL_TOOLS as SYSTEM_TOOLS,
    execute as execute_system_tool,
)
from tools.os_control_tools import (   # noqa: F401
    list_open_windows,
    focus_window,
    minimize_window,
    maximize_window,
    restore_window,
    resize_window,
    lock_pc,
    sleep_pc,
    restart_pc,
    shutdown_pc,
    logoff_user,
    open_task_manager,
    kill_process,
    set_volume,
    mute_audio,
    change_brightness,
    empty_recycle_bin,
    ALL_TOOLS as OS_CONTROL_TOOLS,
    execute as execute_os_control_tool,
)
from tools.app_tools import (       # noqa: F401
    open_app,
    close_app,
    open_website,
    ALL_TOOLS as APP_TOOLS,
    execute as execute_app_tool,
)

__all__ = [
    # Registry
    "ALL_SCHEMAS",
    "dispatch",
    "EXECUTOR_MAP",
    # Memory helpers
    "search_memory",
    "MEMORY_TOOLS",
    "execute_memory_tool",
    # Web helpers
    "web_search",
    "fetch_web_page",
    "WEB_TOOLS",
    "execute_web_tool",
    # Keyboard helpers
    "keyboard_action",
    "KEYBOARD_TOOLS",
    "execute_keyboard_tool",
    # Mouse helpers
    "mouse_action",
    "mouse_click",
    "move_mouse",
    "mouse_scroll",
    "get_mouse_position",
    "MOUSE_TOOLS",
    "execute_mouse_tool",
    # System helpers
    "get_system_overview",
    "get_cpu_status",
    "get_cpu_specs",
    "get_gpu_status",
    "get_display_info",
    "get_ram_status",
    "get_ram_hardware_specs",
    "get_disk_status",
    "get_storage_hardware_info",
    "get_motherboard_info",
    "get_network_info",
    "get_battery_status",
    "get_temperatures",
    "get_fan_speeds",
    "get_power_draw",
    "get_top_resource_apps",
    "get_process_list",
    "SYSTEM_TOOLS",
    "execute_system_tool",
    # OS Control helpers
    "list_open_windows",
    "focus_window",
    "minimize_window",
    "maximize_window",
    "restore_window",
    "resize_window",
    "lock_pc",
    "sleep_pc",
    "restart_pc",
    "shutdown_pc",
    "logoff_user",
    "open_task_manager",
    "kill_process",
    "set_volume",
    "mute_audio",
    "change_brightness",
    "empty_recycle_bin",
    "OS_CONTROL_TOOLS",
    "execute_os_control_tool",
    # App helpers
    "open_app",
    "close_app",
    "open_website",
    "APP_TOOLS",
    "execute_app_tool",
]
