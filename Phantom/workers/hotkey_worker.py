import sys
from PyQt6.QtCore import QThread, pyqtSignal
from utils.logger import log_info, log_error


class HotkeyWorker(QThread):
    """Background thread that continuously monitors global key states.
    Emits hotkey_pressed when Alt+Ctrl is held down, and hotkey_released when released."""
    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()

    def __init__(self, poll_interval_ms: int = 30):
        super().__init__()
        self.running = True
        self.is_held = False
        self.poll_interval_ms = poll_interval_ms

    def run(self):
        if sys.platform == "win32":
            import ctypes
            user32 = ctypes.windll.user32
            VK_MENU = 0x12     # Alt key
            VK_CONTROL = 0x11  # Ctrl key

            while self.running:
                try:
                    alt_pressed = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                    ctrl_pressed = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                    both_held = alt_pressed and ctrl_pressed

                    if both_held and not self.is_held:
                        self.is_held = True
                        log_info("Hotkey", "Alt+Ctrl HELD DOWN -> emitting hotkey_pressed")
                        self.hotkey_pressed.emit()
                    elif not both_held and self.is_held:
                        self.is_held = False
                        log_info("Hotkey", "Alt+Ctrl RELEASED -> emitting hotkey_released")
                        self.hotkey_released.emit()
                except Exception as e:
                    log_error("Hotkey", f"{e}")

                self.msleep(self.poll_interval_ms)
        else:
            try:
                from pynput import keyboard
                current_keys = set()

                def on_press(key):
                    if not self.running:
                        return False
                    current_keys.add(key)
                    is_alt = any(k in current_keys for k in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr))
                    is_ctrl = any(k in current_keys for k in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r))
                    if is_alt and is_ctrl and not self.is_held:
                        self.is_held = True
                        log_info("Hotkey", "Alt+Ctrl HELD DOWN -> emitting hotkey_pressed")
                        self.hotkey_pressed.emit()

                def on_release(key):
                    if not self.running:
                        return False
                    if key in current_keys:
                        current_keys.remove(key)
                    is_alt = any(k in current_keys for k in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr))
                    is_ctrl = any(k in current_keys for k in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r))
                    if not (is_alt and is_ctrl) and self.is_held:
                        self.is_held = False
                        log_info("Hotkey", "Alt+Ctrl RELEASED -> emitting hotkey_released")
                        self.hotkey_released.emit()

                with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                    while self.running:
                        self.msleep(100)
                    listener.stop()
            except Exception as e:
                log_error("Hotkey", f"{e}")

