"""macOS Accessibility API integration.

Uses pyobjc to read the UI element tree from the frontmost application.
This gives pixel-perfect element positions, labels, roles, and states —
eliminating the need for the VLM to guess click coordinates.
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from typing import Any

from desktop_agent.log import get_logger

log = get_logger(__name__)


@dataclass
class UIElement:
    """A single UI element from the accessibility tree."""

    role: str  # e.g. "AXButton", "AXTextField", "AXStaticText"
    title: str = ""
    value: str = ""
    description: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    enabled: bool = True
    focused: bool = False
    children: list[UIElement] = field(default_factory=list)

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    @property
    def label(self) -> str:
        """Best human-readable label for this element."""
        return self.title or self.description or self.value or self.role

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "w": self.width,
            "h": self.height,
            "enabled": self.enabled,
            "focused": self.focused,
            "value": self.value[:100] if self.value else "",
        }


class AccessibilityTree:
    """Reads the macOS accessibility tree for the frontmost application."""

    def __init__(self) -> None:
        self._available: bool | None = None

    async def is_available(self) -> bool:
        """Check if accessibility permissions are granted."""
        if self._available is not None:
            return self._available
        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,
            )
            from CoreFoundation import (
                CFStringRef,
                kCFBooleanTrue,
            )

            options = {
                "AXTrustedCheckOptionPrompt": kCFBooleanTrue,
            }
            self._available = AXIsProcessTrustedWithOptions(options)
        except ImportError:
            log.warning("pyobjc_not_available", msg="Accessibility API unavailable")
            self._available = False
        except Exception as e:
            log.warning("accessibility_check_failed", error=str(e))
            self._available = False
        return self._available

    async def get_frontmost_app(self) -> str:
        """Return the name of the frontmost application."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    async def get_ui_tree(self, *, max_depth: int = 5) -> list[UIElement]:
        """Extract the UI element tree from the frontmost application.

        Returns a flat list of interactive elements (buttons, fields, links, etc.).
        """
        if not await self.is_available():
            return []

        try:
            return await asyncio.to_thread(self._extract_tree, max_depth)
        except Exception as e:
            log.warning("ui_tree_extraction_failed", error=str(e))
            return []

    def _extract_tree(self, max_depth: int) -> list[UIElement]:
        """Synchronous extraction using pyobjc AXUIElement API."""
        try:
            from ApplicationServices import (
                AXUIElementCreateApplication,
                AXUIElementCreateSystemWide,
            )
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowListOptionOnScreenOnly,
            )
            import Cocoa
        except ImportError:
            return []

        # Get frontmost app PID
        workspace = Cocoa.NSWorkspace.sharedWorkspace()
        frontmost = workspace.frontmostApplication()
        if not frontmost:
            return []

        pid = frontmost.processIdentifier()
        app_ref = AXUIElementCreateApplication(pid)

        elements: list[UIElement] = []
        self._walk_element(app_ref, elements, depth=0, max_depth=max_depth)
        return elements

    def _walk_element(
        self,
        element: Any,
        out: list[UIElement],
        depth: int,
        max_depth: int,
    ) -> None:
        """Recursively walk an AXUIElement tree."""
        if depth > max_depth:
            return

        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
            )
            from CoreFoundation import CFGetTypeID, CFArrayGetCount

            # Get role
            err, role = AXUIElementCopyAttributeValue(element, "AXRole", None)
            role = str(role) if not err and role else "unknown"

            # Get properties
            err, title = AXUIElementCopyAttributeValue(element, "AXTitle", None)
            title = str(title) if not err and title else ""

            err, desc = AXUIElementCopyAttributeValue(element, "AXDescription", None)
            desc = str(desc) if not err and desc else ""

            err, value = AXUIElementCopyAttributeValue(element, "AXValue", None)
            value = str(value) if not err and value else ""

            err, enabled = AXUIElementCopyAttributeValue(element, "AXEnabled", None)
            is_enabled = bool(enabled) if not err else True

            err, focused = AXUIElementCopyAttributeValue(element, "AXFocused", None)
            is_focused = bool(focused) if not err else False

            # Get position and size
            x, y, w, h = 0, 0, 0, 0
            err, pos = AXUIElementCopyAttributeValue(element, "AXPosition", None)
            if not err and pos:
                try:
                    from Quartz import AXValueGetValue, kAXValueTypeCGPoint
                    import ctypes

                    class CGPoint(ctypes.Structure):
                        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

                    point = CGPoint()
                    AXValueGetValue(pos, kAXValueTypeCGPoint, ctypes.byref(point))
                    x, y = int(point.x), int(point.y)
                except Exception:
                    pass

            err, size = AXUIElementCopyAttributeValue(element, "AXSize", None)
            if not err and size:
                try:
                    from Quartz import AXValueGetValue, kAXValueTypeCGSize

                    class CGSize(ctypes.Structure):
                        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

                    sz = CGSize()
                    AXValueGetValue(size, kAXValueTypeCGSize, ctypes.byref(sz))
                    w, h = int(sz.width), int(sz.height)
                except Exception:
                    pass

            # Only collect interactive or informative elements
            interactive_roles = {
                "AXButton",
                "AXTextField",
                "AXTextArea",
                "AXCheckBox",
                "AXRadioButton",
                "AXPopUpButton",
                "AXComboBox",
                "AXSlider",
                "AXLink",
                "AXMenuItem",
                "AXMenuBarItem",
                "AXTab",
                "AXStaticText",
                "AXImage",
                "AXToolbar",
                "AXList",
                "AXTable",
                "AXCell",
                "AXRow",
                "AXColumn",
                "AXScrollBar",
                "AXMenu",
                "AXSearchField",
                "AXIncrementor",
            }

            if role in interactive_roles and w > 0 and h > 0:
                ui_elem = UIElement(
                    role=role,
                    title=title,
                    value=value,
                    description=desc,
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    enabled=is_enabled,
                    focused=is_focused,
                )
                out.append(ui_elem)

            # Recurse into children
            err, children = AXUIElementCopyAttributeValue(element, "AXChildren", None)
            if not err and children:
                try:
                    count = len(children)
                    for i in range(min(count, 100)):  # Cap children to prevent infinite recursion
                        child = children[i]
                        self._walk_element(child, out, depth + 1, max_depth)
                except Exception:
                    pass

        except Exception as e:
            log.debug("ax_element_walk_error", error=str(e), depth=depth)

    def format_for_prompt(self, elements: list[UIElement], screen_w: int, screen_h: int) -> str:
        """Format UI elements as a compact text description for the LLM.

        Converts pixel positions to the 0-1000 coordinate system.
        """
        if not elements:
            return ""

        lines = ["## Accessible UI Elements (from accessibility tree)"]
        for elem in elements[:80]:  # Cap at 80 elements to stay within token budget
            nx = int(elem.center[0] * 1000 / screen_w) if screen_w else 0
            ny = int(elem.center[1] * 1000 / screen_h) if screen_h else 0
            state = ""
            if not elem.enabled:
                state = " [DISABLED]"
            if elem.focused:
                state += " [FOCUSED]"
            lines.append(
                f"  - {elem.role}: \"{elem.label}\"{state} @ ({nx},{ny})"
            )
        return "\n".join(lines)
