# statusline-metrics

An emoji-rich Claude Code **status line** that puts your **context-window fill**
front and center, alongside the session metrics you actually watch.

```
🧠 42% ███····· 1M · 🤖 Opus ⚡high 💭 · 🌿 main · ➕156 ➖23 · 💰 $0.04 · 📊 23% 5h
```

## Segments

| Emoji | Metric | Source (statusline stdin JSON) |
|-------|--------|--------------------------------|
| 🧠 | Context-window used %, an 8-cell fill bar, and window size (`1M`/`200k`). Green < 50%, yellow < 80%, red ≥ 80%. Shows `—` before the first API call / right after `/compact`. | `context_window.used_percentage`, `context_window.context_window_size` |
| 🤖 | Model display name | `model.display_name` |
| ⚡ | Reasoning effort level (if the model supports it) | `effort.level` |
| 💭 | Extended thinking is on | `thinking.enabled` |
| 🌿 | Current git branch (derived via `git` in `workspace.current_dir`) | — |
| ➕ ➖ | Lines added / removed this session (hidden when both 0) | `cost.total_lines_added`, `cost.total_lines_removed` |
| 💰 | Session cost (USD) | `cost.total_cost_usd` |
| 📊 | 5-hour rate-limit usage (Pro/Max subscribers only) | `rate_limits.five_hour.used_percentage` |
| 🎨 | Active output style (hidden when `default`) | `output_style.name` |

Context percent comes straight from Claude Code's pre-computed
`context_window.used_percentage` (input tokens ÷ window size, output excluded) —
no transcript parsing.

## Install

Claude Code plugins **cannot** register a `statusLine` directly (only the main
`settings.json` can). After enabling this plugin, run:

```
/statusline-metrics:install            # user scope — ~/.claude/settings.json
/statusline-metrics:install project    # project scope — ./.claude/settings.json
```

That merges a `statusLine` entry pointing at this plugin's `scripts/statusline.sh`,
preserving the rest of your settings.

### Manual install

```jsonc
// ~/.claude/settings.json
{
  "statusLine": {
    "type": "command",
    "command": "/abs/path/to/statusline-metrics/scripts/statusline.sh"
  }
}
```

## Requirements

- `jq` (the script degrades to a minimal line with a warning if it's missing)
- `git` is optional (only used for the 🌿 branch segment)

## Notes

- The script never uses `set -e`/`set -u`, so a missing field can't crash your
  status line.
- ANSI colors and emoji are supported by Claude Code status lines; terminals
  without color support will show the raw text.
