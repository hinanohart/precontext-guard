# precontext-guard

> Block CLI commands that would leak secrets into your AI assistant's
> context window — *before* they run.

[![ci](https://github.com/hinanohart/precontext-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/hinanohart/precontext-guard/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

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
[docs/threat-model.md](docs/threat-model.md) (TODO).

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

# Add to ~/.claude/settings.json (merge the snippet from
# examples/settings.json.fragment into the existing file).
```

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

| Tool                       | When it runs           | What it inspects                | This stops a secret from… |
| -------------------------- | ---------------------- | ------------------------------- | -------------------------- |
| `precontext-guard` (this)  | **Before** Bash exec   | The command string itself       | … entering the assistant's context window in the first place. |
| `gitleaks`, `trufflehog`   | After commit / on push | Git tree, commits, history      | … leaving your repo. |
| `pre-commit` secret hooks  | At `git commit`        | Staged diff                     | … getting committed. |
| Anthropic `permissions.deny` (built-in) | Before tool exec | Exact command match | (similar layer, but exact-match — `precontext-guard` is regex with reasons.) |

These are complementary.  Run them together.

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

The full list lives in `precontext-guard` itself (one Python file — read it
top-to-bottom in five minutes).

---

## Testing

```bash
python -m pytest tests/ -q
```

108 unit tests cover the matcher.  CI also runs the hook end-to-end with
synthetic JSON payloads.

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

[Apache-2.0](LICENSE).
