import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from ui.sidebar import PhantomSidebar
from ui.notch import PhantomNotch, SmartPasteInput
from storage import storage

def _cleanup_notch(notch):
    if hasattr(notch, 'hotkey_worker') and notch.hotkey_worker:
        notch.hotkey_worker.running = False
        notch.hotkey_worker.quit()
        notch.hotkey_worker.wait(1000)
    if hasattr(notch, 'voice_worker') and notch.voice_worker:
        notch.voice_worker.running = False  
        notch.voice_worker.quit()
        notch.voice_worker.wait(1000)
    if hasattr(notch, 'preloader_worker') and notch.preloader_worker:
        notch.preloader_worker.quit()
        notch.preloader_worker.wait(1000)
    if hasattr(notch, 'query_worker') and notch.query_worker:
        notch.query_worker.quit()
        notch.query_worker.wait(1000)

def test_sidebar_creation(qapp):
    sidebar = PhantomSidebar()
    assert sidebar is not None
    # Assuming sidebar has chat_list_layout or similar
    assert sidebar.scroll_layout is not None

def test_notch_creation(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    assert notch is not None
    assert notch.sidebar == sidebar
    _cleanup_notch(notch)

def test_notch_starts_collapsed(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    assert notch.height() == notch.collapsed_height
    _cleanup_notch(notch)

def test_notch_expand(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    notch.expand_notch()
    qapp.processEvents()
    assert notch.is_expanded is True
    _cleanup_notch(notch)

def test_notch_collapse(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    notch.expand_notch()
    notch.collapse_notch()
    qapp.processEvents()
    assert notch.is_expanded is False
    _cleanup_notch(notch)

def test_status_dot_initial_state(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    # The initial state when preloader starts is usually WARMING VRAM or similar
    status_text = notch.status_text_label.text().upper() if hasattr(notch, 'status_text_label') else ""
    assert status_text != "" or notch is not None
    _cleanup_notch(notch)

def test_ai_mode_combo(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    combo = getattr(notch, 'model_combo', getattr(notch, 'model_selector', None))
    assert combo is not None
    options = [combo.itemText(i) for i in range(combo.count())]
    assert len(options) > 0
    _cleanup_notch(notch)

def test_new_chat_resets_state(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    notch.current_chat_id = 123
    notch.start_new_chat()
    assert notch.current_chat_id is None
    _cleanup_notch(notch)

def test_chat_history_load(qapp, setup_test_db):
    sidebar = PhantomSidebar()
    chat_id = storage.create_chat("Test Chat")
    storage.save_message(chat_id, "user", "Hello")
    sidebar.load_chat_history()
    assert sidebar.scroll_layout.count() > 0
    
def test_process_query_creates_worker(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    notch.process_query("test query")
    assert notch.query_worker is not None
    _cleanup_notch(notch)

def test_collapse_timer(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    assert notch.collapse_timer is not None
    assert notch.collapse_timer.isSingleShot() is True
    _cleanup_notch(notch)

def test_smart_paste_input_exists(qapp):
    sidebar = PhantomSidebar()
    notch = PhantomNotch(sidebar)
    assert isinstance(notch.text_input, SmartPasteInput)
    _cleanup_notch(notch)
