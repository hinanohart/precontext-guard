# Installing the hook into Claude Code

`precontext-guard` is registered as a `PreToolUse` hook for the `Bash`
tool.  Claude Code reads `~/.claude/settings.json` (user-wide) and
`<project>/.claude/settings.json` (project-local); pick the scope you
want and merge the snippet from `examples/hooks.json` into it.

> ⚠️  **Read this section before merging.**
>
> The example file in this directory is **strict JSON** — no comments,
> no trailing commas — because `settings.json` itself must be strict
> JSON.  Any earlier version of this file that contained `//` comments
> would corrupt `settings.json` if you copy-pasted it verbatim;
> use the file shipped here as of v0.1.0 or later.

---

## Option A — manual merge (safe, no extra tools)

1. Open `~/.claude/settings.json` (create it if it does not exist;
    starting content is `{}`).
2. If the file already has a top-level `"hooks"` key, add a new entry
   to its `"PreToolUse"` array.  Otherwise, copy the whole `"hooks"`
   block from `examples/hooks.json`.
3. Replace `/path/to/precontext-guard` with the **absolute path** to
   the executable script.

A minimal merged file looks like:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/home/you/precontext-guard/precontext-guard"
          }
        ]
      }
    ]
  }
}
```

After saving, run:

```bash
python3 -c 'import json,sys; json.load(open("~/.claude/settings.json".replace("~", __import__("os").path.expanduser("~"))))' \
  && echo "settings.json parses OK"
```

If that prints `settings.json parses OK`, you are done.

---

## Option B — automatic merge with `jq` (recommended)

This appends a `Bash` `PreToolUse` hook to your existing
`settings.json`, after taking a timestamped backup.  It does not
duplicate the entry if you run it twice.

```bash
SETTINGS="$HOME/.claude/settings.json"
PCG="$(realpath ./precontext-guard)"   # absolute path to the script

# 1) Backup.
cp -n "$SETTINGS" "${SETTINGS}.bak.$(date +%s)" 2>/dev/null \
  || echo "{}" > "$SETTINGS"

# 2) Show what we would do (dry run).
jq --arg cmd "$PCG" '
  .hooks.PreToolUse = (
    (.hooks.PreToolUse // [])
    | (map(select(.matcher == "Bash" and (
        any(.hooks[]?; .command == $cmd)
      )))) as $existing
    | if ($existing | length) > 0 then .
      else
        . + [{
          "matcher": "Bash",
          "hooks": [{"type": "command", "command": $cmd}]
        }]
      end
  )
' "$SETTINGS"

# 3) If the dry-run output above looks right, apply it in place.
TMP="$(mktemp)"
jq --arg cmd "$PCG" '
  .hooks.PreToolUse = (
    (.hooks.PreToolUse // [])
    | (map(select(.matcher == "Bash" and (
        any(.hooks[]?; .command == $cmd)
      )))) as $existing
    | if ($existing | length) > 0 then .
      else
        . + [{
          "matcher": "Bash",
          "hooks": [{"type": "command", "command": $cmd}]
        }]
      end
  )
' "$SETTINGS" > "$TMP" \
  && python3 -c 'import json,sys; json.load(open("'"$TMP"'"))' \
  && mv "$TMP" "$SETTINGS" \
  && echo "merged into $SETTINGS"
```

The `python3 -c json.load` step is intentional: it refuses to overwrite
`settings.json` if `jq` ever produced something the Python JSON
decoder can't read, which is the same parser Claude Code uses.

---

## Verifying

Send a test command through the assistant — for example, ask it to run
`gh auth token`.  Claude Code should refuse the call, and the BLOCKED
message from `precontext-guard` should appear in the transcript.

You can also test the hook directly without going through the
assistant:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"gh auth token"}}' \
  | /path/to/precontext-guard ; echo "exit=$?"
```

`exit=2` and a `BLOCKED` stderr message means the hook is working.

---

## Uninstalling

Remove the entry you added (manual edit), then verify
`~/.claude/settings.json` still parses as strict JSON.  The audit log
under `~/.local/state/precontext-guard/` is yours to keep or delete.
