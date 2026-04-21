"""macOS knowledge base — app database, shortcuts, recovery strategies.

Provides structured knowledge about macOS system behavior to improve
agent decision-making and error recovery.
"""

from __future__ import annotations

# ── Application Database ──────────────────────────────────────────

MACOS_APPS: dict[str, dict] = {
    "Finder": {
        "bundle_id": "com.apple.finder",
        "launch": "open -a Finder",
        "verify": "pgrep -x Finder",
        "titles": ["Finder"],
    },
    "Terminal": {
        "bundle_id": "com.apple.Terminal",
        "launch": "open -a Terminal",
        "verify": "pgrep -x Terminal",
        "titles": ["Terminal", "bash", "zsh"],
    },
    "Notes": {
        "bundle_id": "com.apple.Notes",
        "launch": "open -a Notes",
        "verify": "pgrep -x Notes",
        "titles": ["Notes"],
    },
    "Safari": {
        "bundle_id": "com.apple.Safari",
        "launch": "open -a Safari",
        "verify": "pgrep -x Safari",
        "titles": ["Safari"],
        "tips": "Address/search bar is at TOP CENTER. Use Cmd+L to focus it before typing a URL.",
    },
    "TextEdit": {
        "bundle_id": "com.apple.TextEdit",
        "launch": "open -a TextEdit",
        "verify": "pgrep -x TextEdit",
        "titles": ["TextEdit"],
    },
    "System Settings": {
        "bundle_id": "com.apple.systempreferences",
        "launch": "open -a 'System Settings'",
        "verify": "pgrep -x 'System Settings'",
        "titles": ["System Settings", "System Preferences"],
    },
    "Preview": {
        "bundle_id": "com.apple.Preview",
        "launch": "open -a Preview",
        "verify": "pgrep -x Preview",
        "titles": ["Preview"],
    },
    "Mail": {
        "bundle_id": "com.apple.mail",
        "launch": "open -a Mail",
        "verify": "pgrep -x Mail",
        "titles": ["Mail"],
    },
    "Messages": {
        "bundle_id": "com.apple.MobileSMS",
        "launch": "open -a Messages",
        "verify": "pgrep -x Messages",
        "titles": ["Messages"],
    },
    "Calendar": {
        "bundle_id": "com.apple.iCal",
        "launch": "open -a Calendar",
        "verify": "pgrep -x Calendar",
        "titles": ["Calendar"],
    },
    "Reminders": {
        "bundle_id": "com.apple.reminders",
        "launch": "open -a Reminders",
        "verify": "pgrep -x Reminders",
        "titles": ["Reminders"],
    },
    "Activity Monitor": {
        "bundle_id": "com.apple.ActivityMonitor",
        "launch": "open -a 'Activity Monitor'",
        "verify": "pgrep -x 'Activity Monitor'",
        "titles": ["Activity Monitor"],
    },
    "Photos": {
        "bundle_id": "com.apple.Photos",
        "launch": "open -a Photos",
        "verify": "pgrep -x Photos",
        "titles": ["Photos"],
    },
    "Music": {
        "bundle_id": "com.apple.Music",
        "launch": "open -a Music",
        "verify": "pgrep -x Music",
        "titles": ["Music"],
    },
    "Pages": {
        "bundle_id": "com.apple.iWork.Pages",
        "launch": "open -a Pages",
        "verify": "pgrep -x Pages",
        "titles": ["Pages"],
    },
    "Numbers": {
        "bundle_id": "com.apple.iWork.Numbers",
        "launch": "open -a Numbers",
        "verify": "pgrep -x Numbers",
        "titles": ["Numbers"],
    },
    "Keynote": {
        "bundle_id": "com.apple.iWork.Keynote",
        "launch": "open -a Keynote",
        "verify": "pgrep -x Keynote",
        "titles": ["Keynote"],
    },
    "Visual Studio Code": {
        "bundle_id": "com.microsoft.VSCode",
        "launch": "open -a 'Visual Studio Code'",
        "verify": "pgrep -f 'Visual Studio Code'",
        "titles": ["Visual Studio Code"],
    },
    "Google Chrome": {
        "bundle_id": "com.google.Chrome",
        "launch": "open -a 'Google Chrome'",
        "verify": "pgrep -x 'Google Chrome'",
        "titles": ["Google Chrome", "Chrome"],
    },
}

# ── Keyboard Shortcuts ────────────────────────────────────────────

SHORTCUTS: dict[str, dict[str, str]] = {
    "system": {
        "Cmd+Space": "Spotlight search",
        "Cmd+Tab": "Switch apps",
        "Cmd+Q": "Quit app",
        "Cmd+W": "Close window/tab",
        "Cmd+N": "New window/document",
        "Cmd+S": "Save",
        "Cmd+Shift+S": "Save As",
        "Cmd+Z": "Undo",
        "Cmd+Shift+Z": "Redo",
        "Cmd+C": "Copy",
        "Cmd+V": "Paste",
        "Cmd+X": "Cut",
        "Cmd+A": "Select all",
        "Cmd+F": "Find",
        "Cmd+,": "Preferences",
        "Cmd+Shift+3": "Screenshot full",
        "Cmd+Shift+4": "Screenshot region",
        "Cmd+Option+Esc": "Force Quit",
    },
    "finder": {
        "Cmd+Shift+N": "New folder",
        "Cmd+Shift+G": "Go to folder",
        "Cmd+Shift+.": "Toggle hidden files",
        "Cmd+O": "Open selected file",
        "Cmd+Down": "Open selected file (alt)",
        "Space": "Quick Look",
        "Enter": "Rename (NEVER use to open files!)",
    },
    "terminal": {
        "Ctrl+C": "Cancel command",
        "Ctrl+D": "Exit session",
        "Ctrl+A": "Line start",
        "Ctrl+E": "Line end",
        "Ctrl+R": "Reverse search",
        "Tab": "Autocomplete",
    },
    "text_editing": {
        "Cmd+Left": "Line start",
        "Cmd+Right": "Line end",
        "Cmd+Up": "Doc start",
        "Cmd+Down": "Doc end",
        "Option+Left": "Word left",
        "Option+Right": "Word right",
        "Option+Delete": "Delete word back",
    },
}

# ── Verification Commands ─────────────────────────────────────────

VERIFY_COMMANDS: dict[str, str] = {
    "frontmost_app": (
        "osascript -e 'tell application \"System Events\" to get name "
        "of first application process whose frontmost is true'"
    ),
    "app_running": "pgrep -x '{name}'",
    "window_title": (
        "osascript -e 'tell application \"System Events\" to get title "
        "of front window of first application process whose frontmost is true'"
    ),
    "file_exists": "test -f '{path}' && echo exists || echo missing",
    "dir_exists": "test -d '{path}' && echo exists || echo missing",
    "clipboard": "pbpaste",
    "running_apps": (
        "osascript -e 'tell application \"System Events\" to get name "
        "of every application process whose visible is true'"
    ),
}

# ── Recovery Strategies ───────────────────────────────────────────

RECOVERY: dict[str, list[str]] = {
    "app_not_opening": [
        "Use open_app action to launch apps",
        "Try spotlight_search as alternative",
        "Kill hung instance first via Activity Monitor then reopen",
        "Use osascript: tell application 'AppName' to activate",
    ],
    "click_missed": [
        "Re-examine screenshot for actual element position",
        "Elements often lower than expected due to menu bar (add ~25px)",
        "Use keyboard navigation: Tab, arrows, Enter",
        "Use menu bar items instead of GUI clicks",
    ],
    "typing_wrong_field": [
        "Press Escape to dismiss popups",
        "Click directly on target field first",
        "Cmd+Z to undo accidental input",
        "Verify frontmost app matches expected app",
    ],
    "command_failed": [
        "Check error message for clues",
        "Try alternative approach using GUI",
        "Try alternative approach using the GUI",
    ],
    "spotlight_stuck": [
        "Click empty desktop area first",
        "Wait 1s, try Cmd+Space again",
        "Use 'open -a' as alternative",
    ],
    "no_window": [
        "Press Cmd+N for new window",
        "Use osascript to activate app",
        "Click app icon in Dock",
        "Cmd+Tab to switch to app",
    ],
}


# ── Public API ────────────────────────────────────────────────────

def get_app_info(name: str) -> dict | None:
    """Look up app info by name (case-insensitive, fuzzy)."""
    name_lower = name.lower()
    # Exact
    for app_name, info in MACOS_APPS.items():
        if app_name.lower() == name_lower:
            return {**info, "name": app_name}
    # Fuzzy
    for app_name, info in MACOS_APPS.items():
        if name_lower in app_name.lower() or app_name.lower() in name_lower:
            return {**info, "name": app_name}
    return None


def get_recovery(problem: str) -> list[str]:
    """Get recovery strategies for a problem type."""
    return RECOVERY.get(problem, [])


def format_for_prompt() -> str:
    """Compact knowledge for system prompt injection."""
    lines = [
        "## macOS Quick Reference",
        "",
        "### Opening Apps",
        "- BEST: open_app action",
        "- ALT: spotlight_search (type name, wait, Enter)",
        "- VERIFY: check frontmost app via screenshot",
        "",
        "### Text Editing (CRITICAL)",
        "- New line = press Enter (NEVER click below text)",
        "- Multi-line: use paste_text with \\n",
        "- Cursor movement: arrow keys, NOT clicks",
        "- End of doc: Cmd+Down. Start: Cmd+Up",
        "",
        "### Key Shortcuts",
    ]
    for key, desc in list(SHORTCUTS["system"].items())[:12]:
        lines.append(f"- {key}: {desc}")

    lines.extend([
        "",
        "### Common Pitfalls",
        "- Finder: NEVER press Enter to open files — Enter RENAMES. Double-click or Cmd+O to open",
        "- Calculator: NEVER use — open Safari for calculations",
        "- Screenshots: wait 0.5-1s after action before capturing",
        "- Menu bar: ~25px offset from top affects click Y coords",
    ])
    return "\n".join(lines)
