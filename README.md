# precontext-guard

> **Disclaimer:** This is an **independent third-party tool**. It is **not affiliated with, endorsed by, or sponsored by Anthropic**. "Claude" and "Claude Code" are trademarks of Anthropic and are used here nominatively to identify the official CLI/product this tool integrates with.

> Block CLI commands that would leak secrets into your AI assistant's
> context window — *before* they run.

[![ci](https://github.com/hinanohart/precontext-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/hinanohart/precontext-guard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

`precontext-guard` is a single-file [Claude Code](https://docs.anthropic.com/claude-code)
`PreToolUse` hook.  When the assistant is about to run a shell command, the
hook inspects it and refuses anything whose **literal output would carry a
secret into the chat transcript** — `gh auth token`, `cat .env`,
`echo $OPENAI_API_KEY`, `aws sts get-session-token`, `op read --reveal`,
`vault read secret/...`, `gpg --decrypt`, and friends.

The point is the *layer*: this is **pre-context**.  Other tools scan your
git tree (`gitleaks`, `trufflehog`) or your commits (`git-secrets`,
`pre-commit` hooks) — by then the secret has already passed through your
prompt.  `precontext-guard` stops it earlier, at the moment the assistant
asks the runtime to execute the command.

Read more about why this layer matters in
[docs/threat-model.md](docs/threat-model.md).

---

## What it does

```
┌─ Claude Code ────────────────────────────────────────────────────┐
│                                                                  │
│   user prompt → planner → tool_call(Bash, command="...")         │
│                                │                                 │
│                                ▼ PreToolUse                      │
│                  ┌──────────────────────────┐                    │
│                  │  precontext-guard        │                    │
│                  │   1. allow list          │                    │
│                  │   2. deny patterns       │                    │
│                  │   3. audit log           │                    │
│                  └─────┬──────────┬─────────┘                    │
│                  ALLOW │          │ BLOCK (exit 2)               │
│                        ▼          ▼                              │
│                   real Bash    stderr: reason + how to redo it   │
│                                 → assistant sees BLOCK & retries │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

A blocked command produces output like:

```
[precontext-guard] BLOCKED — gh auth token prints the literal access token;
capture it via '!' prefix in your own shell instead.

How to run it safely:
  - From your own shell directly: prefix the command with '!' so it runs
    locally and its output never reaches the assistant.
        e.g.  ! gh ...
  - Or capture into an environment variable first, then have the
    assistant use that variable by name (without ever reading its
    value):
        ! read -rs MY_TOKEN; export MY_TOKEN
        # in chat afterwards:  invoke as $MY_TOKEN
```

---

## 30-second install

```bash
git clone https://github.com/hinanohart/precontext-guard.git
chmod +x precontext-guard/precontext-guard
```

Then merge the strict-JSON snippet from `examples/hooks.json` into
your `~/.claude/settings.json`.  Step-by-step instructions, including
a safe `jq` one-liner with backup and a dry-run, are in
[examples/INSTALL.md](examples/INSTALL.md).

Requirements: Python ≥ 3.10 (the standard library is enough — no `pip
install` needed at runtime).

---

## Configuration

| Variable           | Purpose                                                                |
| ------------------ | ---------------------------------------------------------------------- |
| `PCG_OVERRIDE=1`   | One-shot bypass for the next invocation (the next exec, then expires). |
| `PCG_RULES_FILE`   | JSON file with extra `allow` and `deny` patterns. See `examples/rules.example.json`. |
| `PCG_LOG_DIR`      | Audit log directory. Default: `$XDG_STATE_HOME/precontext-guard` (or `~/.local/state/precontext-guard`). |

The audit log (`audit.jsonl`) records every decision (`block`, `allow`,
`override`).  It stays on your machine; the guard never makes a network
call.

### Adding your own rules

```json
{
  "allow": ["^\\s*my-internal-tool\\s+(list|status)(\\s|$)"],
  "deny":  [{
    "pattern": "\\bmy-vault\\s+get\\b",
    "reason":  "in-house vault prints plaintext on get"
  }]
}
```

Save it somewhere private, point `PCG_RULES_FILE` at it.  Allow rules run
before deny rules; the first match in each stage wins.

---

## How it differs from related tools

| Tool                                    | When                  | What it inspects             | This stops a secret from… |
| --------------------------------------- | --------------------- | ---------------------------- | -------------------------- |
| `precontext-guard` (this)               | **Before** Bash exec  | The command string (regex)   | … *entering* the assistant's context window. |
| Anthropic `permissions.deny` (built-in) | Before tool exec      | Glob-prefix match            | … running specific *prefixes*. Glob-only — no regex, no reason text, no audit log. |
| `gitleaks`, `trufflehog`                | After commit / push   | Git tree, commits, history   | … leaving your repo. |
| `pre-commit` secret hooks               | At `git commit`       | Staged diff                  | … getting committed. |

These are **complementary** layers — run them together.

### Specifically vs. Anthropic's built-in `permissions.deny`

The built-in `permissions.deny` lets you write rules like
`Bash(gh auth token*)` and is enforced natively by Claude Code with no
extra process.  Use it first.  `precontext-guard` adds the things the
built-in can't do today:

- **Regex anywhere in the command**, not just a prefix glob — so
  `echo $GITHUB_TOKEN` and `echo "$GH_PAT"` are both caught.
- **A `reason` string** explaining *why* the command was blocked and
  *what to type instead* (the built-in just silently denies).
- **A path-redacted JSONL audit log** (`~/.local/state/precontext-guard/audit.jsonl`)
  that records every decision without leaking the *paths* of the
  credential files it blocked.
- **One-shot bypass** via `PCG_OVERRIDE=1` so the assistant can recover
  from a false positive without you editing settings.json.

If your threat model is fully covered by `Bash(<prefix>*)` rules, you
may not need this OSS at all — that's a healthy outcome and the README
above includes a worked example of how to express the most common
deny rules in `permissions.deny`.

### Specifically vs. `claude-safety-guard`

`claude-safety-guard` (a sibling project) is also a `PreToolUse` hook,
but its focus is **filesystem destruction** (`rm -rf /`,
`git push --force`, `mkfs.*`, fork bombs, `git reset --hard origin/*`).
`precontext-guard`'s focus is **secret literals reaching the model's
context** (`gh auth token`, `cat .env`, `printenv`, `vault read`,
`op --reveal`, `gpg --decrypt`, `gcloud auth print-*-token`).

The two overlap on a handful of stdlib commands (`cat .env`,
`curl|sh`, `printenv`) but otherwise look at the *category* of
"what could go wrong" through different lenses.  Run both.

---

## Default rules

The shipped rule set covers the common offenders:

- **GitHub CLI**: `gh auth token`, `gh auth login --with-token`
- **Cloud tokens**: `aws configure`, `aws sts get-session-token`,
  `gcloud auth print-*-token`
- **Kubernetes**: `kubectl config view --raw`, `docker login -p`
- **Credential files**: `cat .env`, `.netrc`, `credentials.json`,
  `id_ed25519`, `~/.kube/config`, `~/.aws/credentials`, `.npmrc`,
  `.pypirc`, `.docker/config.json`
- **Environment dumps**: `printenv`, bare `env`, `echo $*TOKEN/KEY/SECRET`
- **Pipe-to-shell**: `curl … | sh`, `wget … | bash`
- **Secret managers**: `vault read`, `op --reveal`, `doppler secrets get`,
  `bw get password`, `bw export`, `sops --decrypt`, `pass show`,
  `secret-tool lookup`, `keyring get`
- **Crypto leakage**: `gpg --decrypt`, `openssl … -passin pass:`
- **Shell history**: `history`, `fc -l`
- **Inline-shell bypasses**: `bash -c '...'`, `sh -c '...'`, `eval '...'`
  (these would otherwise be a single-line escape from every other rule)

The full list lives in `precontext-guard` itself (one Python file — read it
top-to-bottom in five minutes).

---

## Testing

```bash
python -m pytest tests/ -q
```

25 test functions, expanded by `pytest.mark.parametrize` to ~120
parameterised cases, cover the matcher and the audit log.  CI also runs
the hook end-to-end with synthetic JSON payloads, validates the bundled
JSON examples, and exercises the documented `jq` merge for idempotency.

---

## Limitations (read these)

- **Regex is heuristic.**  An adversary determined to exfiltrate via the
  assistant can paraphrase (`bash -c 'cat .e'\\''nv'`).  This is a guard
  against accidents, not against active attackers.
- **Composite commands** — `bash -c "..."`, `eval`, here-docs — are
  inspected as a single string; obfuscation defeats the regex.
- **Allow list is intentionally narrow.**  When a safe-looking command
  isn't recognised it falls through to "gray-allow" with an audit-log
  entry (no block).  Tighten with `PCG_RULES_FILE` if you want
  default-deny.
- **Not a replacement** for proper secret hygiene (use a secret manager,
  short-lived tokens, scoped credentials, etc.).

---

## Contributing

Pull requests welcome.  Keep the code in one file; new rules belong in
`DENY_DEFAULT` with a `(pattern, reason)` pair and a corresponding test in
`tests/test_decide.py`.

When proposing a new pattern, please:

1. Document the exact CLI version where the dangerous output is emitted.
2. Add at least one BLOCK test and one ALLOW test (a similar-but-safe
   subcommand, to make sure the regex isn't over-broad).
3. Phrase the reason in the second person, action-oriented, ≤120
   characters.

---

## License

[MIT](LICENSE).
