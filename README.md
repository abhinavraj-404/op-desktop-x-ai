<div align="center">

# OP DesktopX

**Autonomous AI agent that controls a macOS desktop.**  
Perceives the screen, plans multi-step tasks, executes actions, and learns from experience.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%2012%2B-lightgrey?style=flat-square)](https://apple.com/macos)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

[**GitHub →**](https://github.com/abhinavraj-404/op-desktop-x-ai)

</div>

---

## How it works

A dual-model pipeline runs every step:

1. **Planner** (large reasoning model) — receives a natural language task + screenshot, breaks it into a concrete step-by-step plan. Handles escalation and replanning when the executor gets stuck.
2. **Executor** (fast vision model) — sees the current screenshot + plan step, outputs exactly one typed action as JSON. Pydantic validates it before anything touches the desktop.

Perception fuses four signals in parallel before each LLM call: a screenshot, the macOS Accessibility Tree (AXUIElement), optional OCR, and a pixel-level screen diff that drives stuck detection.

---

## Architecture

```
src/desktop_agent/
├── core/          # Agent orchestrator, Planner, Executor, action schema (19 typed actions)
├── perception/    # ScreenCapture (pyautogui), AccessibilityTree (pyobjc), OCREngine (EasyOCR), ScreenDiff (numpy)
├── control/       # Mouse, Keyboard, AppManager, DesktopController
├── memory/        # ShortTermMemory (per-task), LongTermMemory (ChromaDB), SkillLibrary
├── knowledge/     # macOS app database — bundle IDs, launch commands, UI tips
└── ui/            # CLI (Click + Rich)
```

---

## Requirements

- **macOS 12+**
- **Python 3.11+**
- **Accessibility permission** — System Settings → Privacy & Security → Accessibility → enable your terminal
- **Screen Recording permission** — System Settings → Privacy & Security → Screen Recording → enable your terminal
- A [Novita AI](https://novita.ai) API key (or any OpenAI-compatible endpoint)

---

## Installation

```bash
git clone https://github.com/abhinavraj-404/op-desktop-x-ai.git
cd op-desktop-x-ai

# Install (use a virtualenv)
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Configure
cp .env.example .env
# Set PLANNER_API_KEY and EXECUTOR_API_KEY — models/endpoints are in config/default.toml
```

---

## Usage

```bash
# Run a single task
op-desktopx run "Research cheap laptops on Amazon and save a summary to Notes"

# Override max steps for long tasks
op-desktopx run "Compile and run my Python project" --max-steps 80

# Interactive mode — enter tasks one after another
op-desktopx interactive

# Debug mode — prints full LLM reasoning per step
op-desktopx --debug run "Open Finder and screenshot the Desktop folder"

# List recorded skills with reliability scores
op-desktopx skills

# Print current configuration
op-desktopx config
```

---

## Configuration

`.env` holds only API keys. Everything else (models, endpoints, timeouts) lives in `config/default.toml` — edit that file directly.

```bash
# .env — the only two lines you need
PLANNER_API_KEY=your_planner_key
EXECUTOR_API_KEY=your_executor_key

# Use the same key if both models share a provider account
```

To switch providers or models, edit `config/default.toml`:

```toml
[llm]
planner_model    = "gpt-4o"
planner_base_url = "https://api.openai.com/v1"

executor_model    = "gpt-4o-mini"
executor_base_url = "https://api.openai.com/v1"
```

Any OpenAI-compatible endpoint works.

---

## Key capabilities

| Capability | Implementation |
|---|---|
| Multi-signal perception | Screenshot + AX tree + OCR + pixel diff fused per step |
| Typed action schema | 19 Pydantic-validated actions — click, type, scroll, drag, hotkey, open\_app, and more |
| Stuck detection | Consecutive screen-unchanged steps trigger Planner escalation |
| Skill library | Record → replay → rate sequences; keyword-searched by reliability score |
| Vector memory | ChromaDB — three collections: strategies, task outcomes, knowledge |
| macOS-native | PyObjC (ApplicationServices, Quartz, Cocoa) for AX tree and screen capture |
| JSONL task logs | Every step logged: action, params, timing breakdown, verification result, LLM thought |

---

## Task log format

Every task writes a JSONL file to `data/logs/tasks/`. Each step event looks like:

```json
{
  "event": "step_executed",
  "timestamp": "2026-04-20T13:23:30Z",
  "elapsed_s": 41.079,
  "step": 1,
  "action": "open_app",
  "params": { "app_name": "Safari" },
  "thought": "I need to open Safari as specified in step 1 of the plan.",
  "timing": {
    "llm_decision_ms": 5085,
    "perception_ms": 653,
    "execution_ms": 2717,
    "total_step_ms": 8455
  },
  "verification": { "verified": true, "screen_changed": true },
  "stuck_warning": null
}
```

---

## Models

Default configuration uses [Novita AI](https://novita.ai) hosted models:

| Role | Default model |
|---|---|
| Planner | `deepseek/deepseek-v3.2` |
| Executor | `qwen/qwen3-vl-235b-a22b-instruct` |

Any OpenAI-compatible endpoint works — set `PLANNER_BASE_URL` / `EXECUTOR_BASE_URL` in `.env`.

---

## License

MIT
