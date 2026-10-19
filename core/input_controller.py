"""Defensive pynput-based operating-system input dispatch."""
from __future__ import annotations
import logging
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Controller as KeyboardController, Key


class InputController:
    """Clamped cursor and button/scroll/zoom operations with safe release."""
    def __init__(self, fail_safe_corner: bool = True) -> None:
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self.fail_safe_corner = fail_safe_corner
        self.left_held = False
        self.logger = logging.getLogger("gestureflow.input")

    def move(self, x: int, y: int) -> None:
        try:
            self.mouse.position = (max(0, x), max(0, y))
        except Exception:
            self.logger.exception("Cursor move failed")

    def press_left(self) -> None:
        if not self.left_held:
            try:
                self.mouse.press(Button.left)
                self.left_held = True
            except Exception: self.logger.exception("Left press failed")

    def release_left(self) -> None:
        if self.left_held:
            try: self.mouse.release(Button.left)
            except Exception: self.logger.exception("Left release failed")
            finally: self.left_held = False

    def click_left(self) -> None:
        """Dispatch one left click without creating a held drag state."""
        try: self.mouse.click(Button.left)
        except Exception: self.logger.exception("Left click failed")

    def click_right(self) -> None:
        try: self.mouse.click(Button.right)
        except Exception: self.logger.exception("Right click failed")

    def double_click_left(self) -> None:
        try: self.mouse.click(Button.left, 2)
        except Exception: self.logger.exception("Double left click failed")

    def scroll(self, amount: int) -> None:
        try: self.mouse.scroll(0, int(amount))
        except Exception: self.logger.exception("Scroll failed")

    def zoom(self, direction: int) -> None:
        try:
            self.keyboard.press(Key.ctrl)
            self.keyboard.press('+' if direction > 0 else '-')
            self.keyboard.release('+' if direction > 0 else '-')
            self.keyboard.release(Key.ctrl)
        except Exception:
            self.logger.exception("Zoom key dispatch failed")
            try: self.keyboard.release(Key.ctrl)
            except Exception: pass

    def close(self) -> None:
        self.release_left()
