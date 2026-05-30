#!/usr/bin/env bash
# statusline-metrics — a Claude Code status line that surfaces live session
# metrics, with the context-window fill front and center.
#
# Claude Code feeds this script a JSON blob on stdin (see `claude docs statusline`).
# We pull the fields we care about, then print ONE line of emoji-tagged,
# ANSI-colored metrics. stdout's first line becomes the status line.
#
# Requires: jq. If jq is missing we degrade to a minimal line.
#
# NB: no `set -e`/`set -u` — a status line must never crash mid-render. Bash
# `(( ))` arithmetic returns exit 1 on a zero/false result (fatal under `-e`),
# and absent JSON fields are normal (fatal under `-u`). We default everything.
set -o pipefail

input="$(cat)"

# --- jq missing? degrade gracefully -----------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  printf '🧠 ?%% · ⚠️  install jq for statusline-metrics\n'
  exit 0
fi

# --- one jq pass → one field per line ----------------------------------------
# Fields that can legitimately be absent/null (early session, after /compact,
# non-subscriber, etc.) come back as the empty string. We emit one field per
# line and read into an array: this preserves empty fields (a tab-separated
# `read` would collapse them, since tab is an IFS-whitespace char and shifts
# every later column).
mapfile -t F < <(printf '%s' "$input" | jq -r '
  [ (.context_window.used_percentage // ""),
    (.context_window.context_window_size // ""),
    (.model.display_name // "?"),
    (.effort.level // ""),
    (.thinking.enabled // false),
    (.cost.total_lines_added // 0),
    (.cost.total_lines_removed // 0),
    (.cost.total_cost_usd // 0),
    (.rate_limits.five_hour.used_percentage // ""),
    (.output_style.name // ""),
    (.workspace.current_dir // .cwd // "")
  ] | .[] | tostring')

pct=${F[0]:-};   ctxsize=${F[1]:-};  model=${F[2]:-?}; effort=${F[3]:-}
thinking=${F[4]:-false}; added=${F[5]:-0}; removed=${F[6]:-0}; cost=${F[7]:-0}
rl5=${F[8]:-};   ostyle=${F[9]:-};   curdir=${F[10]:-}

# --- colors ------------------------------------------------------------------
RST=$'\033[0m'; DIM=$'\033[2m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RED=$'\033[31m'; CYN=$'\033[36m'

segments=()

# --- 🧠 context window -------------------------------------------------------
# used_percentage is input-only (excludes output tokens), pre-computed by Claude
# Code. It is "" before the first API call and right after /compact.
if [[ -n "$pct" ]]; then
  p=${pct%.*}; [[ -z "$p" ]] && p=0
  if   (( p < 50 )); then cc=$GRN
  elif (( p < 80 )); then cc=$YEL
  else                    cc=$RED
  fi
  # 8-cell fill bar
  filled=$(( (p + 6) / 13 )); (( filled > 8 )) && filled=8; (( filled < 0 )) && filled=0
  bar=""; for ((i=0;i<8;i++)); do (( i < filled )) && bar+="█" || bar+="·"; done
  # context window size label (1000000 → 1M, 200000 → 200k)
  szlabel=""
  if [[ -n "$ctxsize" ]]; then
    if   (( ctxsize >= 1000000 )); then szlabel=" ${DIM}$(( ctxsize / 1000000 ))M${RST}"
    elif (( ctxsize >= 1000 ));    then szlabel=" ${DIM}$(( ctxsize / 1000 ))k${RST}"
    fi
  fi
  segments+=("🧠 ${cc}${p}% ${bar}${RST}${szlabel}")
else
  segments+=("🧠 ${DIM}—${RST}")
fi

# --- 🤖 model (+ ⚡ effort, 💭 thinking) --------------------------------------
modelseg="🤖 ${CYN}${model}${RST}"
[[ -n "$effort" ]] && modelseg+=" ⚡${effort}"
[[ "$thinking" == "true" ]] && modelseg+=" 💭"
segments+=("$modelseg")

# --- 🌿 git branch (JSON has no branch field; derive from current_dir) -------
if [[ -n "$curdir" ]] && command -v git >/dev/null 2>&1; then
  branch="$(git -C "$curdir" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [[ -n "$branch" ]] && segments+=("🌿 ${branch}")
fi

# --- ➕➖ lines changed this session -----------------------------------------
if (( added > 0 || removed > 0 )); then
  segments+=("${GRN}➕${added}${RST} ${RED}➖${removed}${RST}")
fi

# --- 💰 cost -----------------------------------------------------------------
segments+=("💰 $(printf '$%.2f' "$cost")")

# --- 📊 5-hour rate-limit usage (subscribers only) ---------------------------
if [[ -n "$rl5" ]]; then
  r=${rl5%.*}
  segments+=("📊 ${r}% ${DIM}5h${RST}")
fi

# --- 🎨 non-default output style ---------------------------------------------
[[ -n "$ostyle" && "$ostyle" != "default" && "$ostyle" != "null" ]] && segments+=("🎨 ${ostyle}")

# --- join with " · " ---------------------------------------------------------
out=""
for s in "${segments[@]}"; do
  [[ -n "$out" ]] && out+=" ${DIM}·${RST} "
  out+="$s"
done
printf '%s\n' "$out"
