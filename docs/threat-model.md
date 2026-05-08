# Threat model

This document is short on purpose: `precontext-guard` is a small tool with
a small purpose, and that smallness is part of the design.

## What this guards against

You're using an AI coding assistant that runs shell commands on your
behalf.  Some of those commands, *if executed*, would print a literal
secret to standard output — and that output then becomes part of the
conversation transcript that the assistant reads, the request payload
that's sent to the model provider, and the logs/replay tooling that
follow.

Examples:

- `gh auth token` — prints your GitHub PAT.
- `cat .env` — prints every key=value in it.
- `echo $OPENAI_API_KEY` — prints the value.
- `aws sts get-session-token` — prints fresh STS credentials.
- `op read 'op://Personal/x' --reveal` — prints the stored secret.

`precontext-guard` runs *before* the assistant's runtime executes the
command (Claude Code's `PreToolUse` hook).  When it sees one of these
shapes, it returns exit code 2 with a stderr explanation, the runtime
declines to execute, and the secret never enters the model's context.

## What this does **not** guard against

This tool is a guard rail, not an adversarial defence.  It assumes the
assistant is well-meaning but careless, and that you (the human) want a
backstop for accidents.

It will *not* save you from:

1. **A determined exfiltration attempt.**  An attacker with prompt
   injection on the assistant can paraphrase: `bash -c 'ca''t .e''nv'`,
   `eval "c"a"t" .env`, base64-decode-and-pipe, or simply read the file
   via the runtime's `Read` tool instead of `Bash`.  Regex on the command
   string cannot follow obfuscation.

2. **The runtime itself going rogue.**  If the runtime ignores the hook's
   exit code, the guard does nothing.  Trust in the hook depends on
   trust in the runtime.

3. **Secrets that leak via filesystem reads.**  `precontext-guard`
   only inspects `Bash` tool calls.  A `Read` call against `.env` flows
   through a separate path — see [related tools](../README.md#how-it-differs-from-related-tools)
   for layers that cover that.

4. **Side channels.**  Network calls the assistant makes from inside an
   allowed `Bash` invocation, environment-variable exfiltration via
   subprocess args, tool-output truncation working in the attacker's
   favour.

5. **Secrets that are already in the chat history.**  If you typed a
   token into the conversation last week, this guard cannot retract it.

## Why "default-allow with deny patterns"

A default-deny shell would be unusable; the assistant would be blocked
several times a turn.  We default to **allow + audit** for unknown
commands and reserve refusal for shapes that have no plausible
non-leaky reason to exist.

If you want a tighter posture, supply your own `PCG_RULES_FILE` with
allow patterns covering exactly the commands your workflow needs, then
add a deny pattern of `.*` at the end.  (We do not ship this as the
default because it would surprise first-time users.)

## What "verbatim" means in practice

A pattern like `\bgh\s+auth\s+(token|login\s+--with-token)\b` matches the
literal command string the runtime is about to run.  It does not run the
command, it does not look up history, it does not consult a database.
The match is purely syntactic.

This means:

- Patterns must enumerate every spelling that matters.  We try to be
  comprehensive in the default list, but contributions are welcome when
  a CLI version adds new dangerous subcommands.
- A safe-looking command that happens to *contain* a dangerous substring
  may be over-matched.  Where we noticed this risk, the pattern is
  anchored (`\b`, `^\s*`).  When you find an over-broad pattern,
  please open an issue.

## Auditing

Every decision (`block`, `allow`, `override`, error) is appended to
`audit.jsonl` in `$XDG_STATE_HOME/precontext-guard/` (or
`~/.local/state/precontext-guard/`).  The file is local-only; the guard
makes no network calls.

Inspect with:

```bash
tail -n 50 ~/.local/state/precontext-guard/audit.jsonl | jq .
```

`PCG_OVERRIDE=1` uses for one invocation are also logged with their
command, so you can see what you bypassed.
