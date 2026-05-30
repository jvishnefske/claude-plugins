---
description: Wire the statusline-metrics status line into settings.json (user or project scope)
arguments:
  - name: scope
    description: "Where to install: 'user' (~/.claude/settings.json, default) or 'project' (./.claude/settings.json)"
    required: false
---

You are wiring the **statusline-metrics** status line into Claude Code settings.
Claude Code plugins cannot register a `statusLine` directly, so this command
merges the setting into the appropriate `settings.json`.

The status line script ships with this plugin at:

```
${CLAUDE_PLUGIN_ROOT}/scripts/statusline.sh
```

## Steps

1. **Resolve the absolute script path.** The literal value above already has
   `${CLAUDE_PLUGIN_ROOT}` expanded to a real directory — use that exact path.
   Verify the file exists with `ls -l` and make it executable:
   `chmod +x "<resolved>/scripts/statusline.sh"`.
   If it does not exist, stop and report the path you tried.

2. **Pick the target settings file** from the `scope` argument
   (`{{scope}}` — default to `user` if empty):
   - `user` → `~/.claude/settings.json`
   - `project` → `./.claude/settings.json` (relative to the current project)

3. **Merge, don't clobber.** Read the target file if it exists (it is JSON).
   Add or replace ONLY the top-level `statusLine` key, preserving everything
   else verbatim:

   ```json
   "statusLine": {
     "type": "command",
     "command": "<absolute path to statusline.sh>"
   }
   ```

   If the file doesn't exist, create it as `{ "statusLine": { ... } }`.
   Prefer `jq` for the merge if available, e.g.:

   ```sh
   jq --arg cmd "<abs path>" '.statusLine = {type:"command", command:$cmd}' \
      ~/.claude/settings.json > /tmp/sl.json && mv /tmp/sl.json ~/.claude/settings.json
   ```

   Otherwise edit the JSON directly, keeping it valid.

4. **Smoke-test** the script so the user sees the result immediately:

   ```sh
   echo '{"cwd":".","workspace":{"current_dir":"."},"model":{"display_name":"Opus"},"effort":{"level":"high"},"thinking":{"enabled":true},"cost":{"total_cost_usd":0.04,"total_lines_added":12,"total_lines_removed":3},"context_window":{"used_percentage":42,"context_window_size":1000000}}' \
     | bash "<abs path to statusline.sh>"
   ```

5. **Report** the file you changed and the rendered sample line, and tell the
   user the status line refreshes after the next assistant message (a new
   session or `/statusline` reload picks it up immediately).

Do not modify any settings key other than `statusLine`.
