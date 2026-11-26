"""
tests/test_mouse_tools.py — Unit tests for Phantom AI mouse tools module.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add root project path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import registry, mouse_tools


class TestMouseTools(unittest.TestCase):

    @patch("tools.mouse_tools.pyautogui.size", return_value=(1920, 1080))
    @patch("tools.mouse_tools.pyautogui.position", return_value=(960, 540))
    def test_get_mouse_position(self, mock_pos, mock_size):
        result = mouse_tools.get_mouse_position()
        self.assertIn("(960, 540)", result)
        self.assertIn("(1920x1080)", result)

    @patch("tools.mouse_tools.pyautogui.size", return_value=(1920, 1080))
    @patch("tools.mouse_tools.pyautogui.moveTo")
    def test_move_mouse_absolute_xy(self, mock_move_to, mock_size):
        result = mouse_tools.move_mouse(x=500, y=300)
        mock_move_to.assert_called_once_with(500, 300, duration=0.1)
        self.assertIn("(500, 300)", result)

    @patch("tools.mouse_tools.pyautogui.size", return_value=(1920, 1080))
    @patch("tools.mouse_tools.pyautogui.moveTo")
    def test_move_mouse_preset_center(self, mock_move_to, mock_size):
        result = mouse_tools.move_mouse(preset="center")
        # Center of 1920x1080 is (960, 540)
        mock_move_to.assert_called_once_with(960, 540, duration=0.1)
        self.assertIn("Center", result)
        self.assertIn("(960, 540)", result)

    @patch("tools.mouse_tools.pyautogui.size", return_value=(1920, 1080))
    @patch("tools.mouse_tools.pyautogui.position", return_value=(960, 490))
    @patch("tools.mouse_tools.pyautogui.moveRel")
    def test_move_mouse_relative_up(self, mock_move_rel, mock_pos, mock_size):
        result = mouse_tools.move_mouse(direction="up", distance=50)
        # Up mult is (0, -1) -> (0, -50)
        mock_move_rel.assert_called_once_with(0, -50, duration=0.1)
        self.assertIn("up by 50 pixels", result)

    @patch("tools.mouse_tools.pyautogui.size", return_value=(1920, 1080))
    @patch("tools.mouse_tools.pyautogui.position", return_value=(960, 540))
    @patch("tools.mouse_tools.pyautogui.click")
    def test_mouse_click_lmb(self, mock_click, mock_pos, mock_size):
        result = mouse_tools.mouse_click(button="left", clicks=1)
        mock_click.assert_called_once_with(button="left", clicks=1, interval=0.05)
        self.assertIn("Left (LMB)", result)

    @patch("tools.mouse_tools.pyautogui.size", return_value=(1920, 1080))
    @patch("tools.mouse_tools.pyautogui.position", return_value=(960, 540))
    @patch("tools.mouse_tools.pyautogui.click")
    def test_mouse_click_rmb(self, mock_click, mock_pos, mock_size):
        result = mouse_tools.mouse_click(button="right", clicks=1)
        mock_click.assert_called_once_with(button="right", clicks=1, interval=0.05)
        self.assertIn("Right (RMB)", result)

    @patch("tools.mouse_tools.pyautogui.size", return_value=(1920, 1080))
    @patch("tools.mouse_tools.pyautogui.position", return_value=(960, 540))
    @patch("tools.mouse_tools.pyautogui.doubleClick")
    def test_mouse_double_click(self, mock_dbl_click, mock_pos, mock_size):
        result = mouse_tools.mouse_click(button="left", clicks=2)
        mock_dbl_click.assert_called_once_with(button="left")
        self.assertIn("Double-clicked", result)

    @patch("tools.mouse_tools.pyautogui.scroll")
    def test_mouse_scroll_down(self, mock_scroll):
        result = mouse_tools.mouse_scroll(direction="down", scroll_amount=5)
        # 5 notches * -100 units = -500
        mock_scroll.assert_called_once_with(-500)
        self.assertIn("down by 5 notches", result)

    @patch("tools.mouse_tools.pyautogui.scroll")
    def test_mouse_scroll_up(self, mock_scroll):
        result = mouse_tools.mouse_scroll(direction="up", scroll_amount=5)
        # 5 notches * 100 units = 500
        mock_scroll.assert_called_once_with(500)
        self.assertIn("up by 5 notches", result)

    def test_registry_has_mouse_action(self):
        schema_names = [s["function"]["name"] for s in registry.ALL_SCHEMAS]
        self.assertIn("mouse_action", schema_names)
        self.assertIn("mouse_action", registry.EXECUTOR_MAP)

    @patch("tools.mouse_tools.pyautogui.size", return_value=(1920, 1080))
    @patch("tools.mouse_tools.pyautogui.moveTo")
    def test_registry_dispatch_mouse_action_move(self, mock_move_to, mock_size):
        res = registry.dispatch("mouse_action", {"action_type": "move", "preset": "center"})
        mock_move_to.assert_called_once_with(960, 540, duration=0.1)
        self.assertIn("Center", res)


if __name__ == "__main__":
    unittest.main()
