# Ralph Loop for Antigravity

[![CI](https://github.com/GindaChen/ralph-loop-antigravity/actions/workflows/ci.yml/badge.svg)](https://github.com/GindaChen/ralph-loop-antigravity/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/GindaChen/ralph-loop-antigravity)

> An autonomous AI agent extension for Antigravity — automates multi-step coding tasks with iterative loop execution, file-based memory, and backpressure validation.

---

## Overview

AI coding assistants are powerful, but they come with two fundamental limitations:

1. **Context decay** — LLMs lose track of important details as conversations grow longer.
2. **Manual babysitting** — Developers must constantly guide the AI, re-prompting after every step.

**Ralph Loop** eliminates both problems by:
- **Externalizing memory** to persistent files on disk (`PRD.md` + `progress.txt`)
- **Running iterative loops** where each cycle gets a fresh context window
- **Reading from disk** so the agent picks up exactly where the last cycle left off

No manual intervention required. Just hit play and let the agent work through your entire task list.

## Quick Start

1. **Install** — Build from source or install from VSIX (see [Installation](#installation))
2. **Create a task file** — Write a `PRD.md` with discrete, actionable tasks
3. **Open the sidebar** — Click the Ralph Loop icon in the Activity Bar
4. **Configure** — Set your task file, mode, model, and max iterations
5. **Hit play** — The loop starts and the agent works autonomously

> 💡 **Recommended**: Start with **Planning mode** to draft your task file, then switch to **Fast mode** for execution.

## File Structure

| File | Role | Details |
|------|------|---------|
| `PRD.md` | Task Specification | Your requirements and task list. **Read-only** — the agent never modifies this. |
| `progress.txt` | Progress Journal | The agent appends entries here after each step. Single source of truth. |
| `prompt.md` | Custom Instructions | Optional file for additional guidance or constraints. |

### Task File Format

Your task file should contain **self-contained, actionable tasks**:

```markdown
# PRD: My Feature

## Task 1: Authentication
Implement JWT-based auth with login/logout endpoints.
- POST /api/auth/login
- POST /api/auth/logout
- Token refresh

## Task 2: User Profiles
Create user profile CRUD operations.
- GET/PUT /api/users/:id
- Profile picture upload
```

**Golden rule:** Each `## Task N:` section should be small enough for one iteration.

## Features

### 🎛️ Dedicated Sidebar
Full visibility and control from the Activity Bar:
- **Live session info** — Status, iteration count, elapsed time, mode, model
- **Quick configuration** — Click to change any setting

### 📊 Status Bar Integration
Persistent indicator showing:
- Loop state: `Running` · `Paused` · `Stopped`
- Current iteration: `15/50`
- Elapsed time: `2m 34s`

### 🔄 Smart Auto-Completion
Each session generates a unique completion marker. When the agent finishes all tasks, it appends the marker to `progress.txt`. Ralph detects this and stops the loop automatically.

### 🔧 Backpressure Validation
Run test/lint/build/package commands after each iteration. Failures are injected into the next prompt so the agent can self-correct.

### 🌿 Git Integration
- Auto-commit after each iteration (configurable)
- Create a new branch per session (configurable)

### 📝 Dynamic Model Registry
Ships with bundled models (Gemini 3 Flash, Claude Sonnet 4.5, etc.) and supports remote model lists via URL.

## Commands

| Command | Description |
|---------|-------------|
| `Ralph: Start Ralph Loop` | Launch a new autonomous loop session |
| `Ralph: Stop Ralph Loop` | Graceful stop after current iteration |
| `Ralph: Pause/Resume Ralph Loop` | Toggle pause/resume |
| `Ralph: Emergency Stop Ralph Loop` | Immediately terminate |
| `Ralph: Select Task File` | Choose your task specification |
| `Ralph: Configure Iterations` | Set max iterations |
| `Ralph: Set Mode` | Switch between Fast and Planning |
| `Ralph: Set Model` | Choose AI model |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `ralphLoop.maxIterations` | `50` | Max iterations per loop |
| `ralphLoop.defaultMode` | `Fast` | Default operating mode |
| `ralphLoop.defaultModel` | `Gemini 3 Flash` | Default AI model |
| `ralphLoop.taskFile` | `PRD.md` | Task specification path |
| `ralphLoop.progressFile` | `progress.txt` | Progress journal path |
| `ralphLoop.promptFile` | `(empty)` | Optional custom prompt file |
| `ralphLoop.enabledBackpressure` | `[]` | Checks to run: test, lint, build, package |
| `ralphLoop.useGit` | `true` | Auto-commit after iterations |
| `ralphLoop.antigravity.port` | `0` | Port (0 = auto-discover) |

## Installation

### From Source

```bash
git clone https://github.com/GindaChen/ralph-loop-antigravity.git
cd ralph-loop-antigravity
npm install
npm run compile
npx @vscode/vsce package
```

Then install the generated `.vsix` file in Antigravity: `Extensions → ⋯ → Install from VSIX`

## How It Works

1. **Fresh context every cycle** — each iteration starts a new Cascade session with a clean context window
2. **Structured agent instructions** — the agent reads tasks from disk, completes one, appends progress
3. **Disk-based memory** — all state lives in `progress.txt`, not in the AI's volatile memory
4. **Completion detection** — unique markers prevent false positives from previous runs
5. **Backpressure** — failed tests/lints are fed back into the next prompt for self-correction

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No task file selected" | Choose a task file from the sidebar |
| "No workspace folder open" | Open a project folder first |
| Loop not responding | Use `Ralph: Emergency Stop` from Command Palette |
| Can't connect to Antigravity | Set `ralphLoop.antigravity.port` manually |
| CSRF token expired | Update `ralphLoop.antigravity.csrfToken` from DevTools |

## Credits

Inspired by the [Ralph Loop methodology](https://ghuntley.com/ralph/) by Geoffrey Huntley and the community extensions by [abhishekbhakat](https://github.com/abhishekbhakat) and [afganrasulov](https://github.com/afganrasulov).

## License

MIT — see [LICENSE](LICENSE)
