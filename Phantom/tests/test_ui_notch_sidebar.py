import unittest
import sys
from PyQt6.QtWidgets import QApplication
from storage import storage
from ui.sidebar import PhantomSidebar, ChatItemWidget
from ui.notch import PhantomNotch, ChatGroupWidget

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

class TestUINotchSidebar(unittest.TestCase):
    def setUp(self):
        storage.init_db()
        self.notches = []
        self.sidebars = []

    def tearDown(self):
        for notch in self.notches:
            try:
                if hasattr(notch, 'voice_worker') and notch.voice_worker:
                    notch.voice_worker.running = False
                    notch.voice_worker.quit()
                    notch.voice_worker.wait(100)
                if hasattr(notch, 'hotkey_worker') and notch.hotkey_worker:
                    notch.hotkey_worker.running = False
                    notch.hotkey_worker.quit()
                    notch.hotkey_worker.wait(100)
                if hasattr(notch, 'preloader_worker') and notch.preloader_worker:
                    notch.preloader_worker.quit()
                    notch.preloader_worker.wait(100)
                if hasattr(notch, 'hud_timer'):
                    notch.hud_timer.stop()
                if hasattr(notch, 'collapse_timer'):
                    notch.collapse_timer.stop()
            except Exception:
                pass
        for sidebar in self.sidebars:
            try:
                if hasattr(sidebar, 'collapse_timer'):
                    sidebar.collapse_timer.stop()
            except Exception:
                pass

    def _create_sidebar(self):
        sidebar = PhantomSidebar()
        self.sidebars.append(sidebar)
        return sidebar

    def _create_notch(self, sidebar):
        notch = PhantomNotch(sidebar)
        self.notches.append(notch)
        return notch

    def test_chat_group_widget_creation(self):
        card = ChatGroupWidget(user_text="Hello Phantom", ai_text="Greetings human!")
        self.assertIsNotNone(card)
        self.assertEqual(card.user_text, "Hello Phantom")
        self.assertEqual(card.ai_text, "Greetings human!")

    def test_chat_group_widget_thinking(self):
        card = ChatGroupWidget(user_text="What is quantum gravity?", is_thinking=True)
        self.assertTrue(card.is_thinking)
        card.set_ai_reply("Quantum gravity seeks to unify general relativity with quantum mechanics.")
        self.assertFalse(card.is_thinking)
        self.assertIn("Quantum gravity", card.ai_text)

    def test_phantom_sidebar_instantiation(self):
        sidebar = self._create_sidebar()
        self.assertIsNotNone(sidebar)
        self.assertEqual(sidebar.collapsed_width, 22)
        self.assertEqual(sidebar.expanded_width, 340)

    def test_phantom_notch_instantiation(self):
        sidebar = self._create_sidebar()
        notch = self._create_notch(sidebar)
        self.assertIsNotNone(notch)
        self.assertEqual(notch.notch_width, 440)
        self.assertGreaterEqual(notch.min_expanded_height, 150)

    def test_notch_auto_collapse_timer_after_reply(self):
        sidebar = self._create_sidebar()
        notch = self._create_notch(sidebar)
        notch.expand_notch()
        self.assertTrue(notch.is_expanded)

        # Give text_input focus to simulate user having typed input
        notch.text_input.setFocus()

        # Simulate completion of AI reply
        notch._on_done(notch.current_request_id)

        # Timer should be active (5s timer started)
        self.assertTrue(notch.collapse_timer.isActive())

        # Focus alone should NOT count as user interacting when mouse is not over UI
        self.assertFalse(notch._is_user_interacting())

        # Trigger auto collapse (simulating timer expiry)
        notch._auto_collapse()
        self.assertFalse(notch.is_expanded)

    def test_notch_auto_collapse_after_hover_leave(self):
        sidebar = self._create_sidebar()
        notch = self._create_notch(sidebar)
        notch.is_busy = False
        notch.expand_notch()
        self.assertTrue(notch.is_expanded)

        # Mock _is_user_interacting to return False in headless test environment
        notch._is_user_interacting = lambda: False

        # Start collapse timer (as mouse leave does)
        notch._start_collapse_timer()
        self.assertTrue(notch.collapse_timer.isActive())

        # Trigger auto collapse
        notch._auto_collapse()
        self.assertFalse(notch.is_expanded)


if __name__ == "__main__":
    unittest.main()
