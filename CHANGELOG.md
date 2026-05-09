# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security (2026-05-09 follow-up audit — fail-secure on rules-file errors)

- **`PCG_RULES_FILE` failure now blocks (BREAKING).** When the env var
  is configured but the file cannot be opened (`OSError`: removed,
  permissions flipped, race) or contains invalid JSON, the decider
  used to silently fall back to an empty extra-rule set. That is
  fail-open: an attacker who can briefly perturb the rules file
  strips the user's custom deny entries and leaves only
  `DENY_DEFAULT` to catch them. The decider now returns
  `("block", "PCG_RULES_FILE configured but unreadable/invalid …")`
  and emits a `rules-error` log event. Users who relied on the old
  silent-skip behaviour must either unset `PCG_RULES_FILE` or
  guarantee the file is always readable. The TOCTOU-prone
  `os.path.isfile` pre-check has been removed in favour of trusting
  the `open()` path.

### Security (2026-05-09 R17 audit — three CRITICAL classes patched)

- **Chained-command bypass closed (CRITICAL #1).** Previously a command
  like `git push && cat .env` short-circuited on the leading allow-rule
  match and approved the whole call, leaving the chained `cat .env`
  unevaluated. The decider now splits at top-level shell separators
  (`;`, `&&`, `||`, `|`, `\n`, `&`) — quote- and escape-aware — and
  evaluates each statement independently. A whole-string deny pass is
  also retained so structural patterns like `curl ... | sh` are still
  caught.
- **Audit log permissions hardened (CRITICAL #2).** Blocked-command
  rows can legitimately contain hard-coded credential literals; writing
  them to a 0o644 file leaked them to every other local user. The audit
  file is now opened with explicit mode 0o600 (and `O_NOFOLLOW`), and
  the parent directory is forced to 0o700 on creation.
- **Stdin cap + fail-secure (CRITICAL #3).** Stdin had no size limit and
  any internal error escalated to "fail-open: tool call proceeds", so a
  ~1 MiB junk payload could exhaust the regex engine and bypass every
  deny rule. Reads are now capped at 1 MiB and overflow returns a
  hook-Block (rc=2) with a stable `fail-secure` reason; this is well
  above any real Claude Code PreToolUse payload.

### Added
- **Inline-shell bypass deny** (`bash -c`, `sh -c`, `zsh -c`, `fish -c`,
  `dash -c`, `eval`).  Without these, every other deny pattern could be
  trivially escaped by wrapping the command in `bash -c '...'`.
- **Path-redacted audit log**.  A blocked `cat /home/alice/.aws/credentials`
  now records as `cat <redacted:/.aws/credentials>` — the kind of file is
  preserved, the absolute filesystem path is not. This prevents the
  audit trail itself from leaking your home directory layout if it ever
  gets accidentally shared.
- README section explicitly comparing `precontext-guard` to
  Anthropic's built-in `permissions.deny` and to `claude-safety-guard`,
  so users can pick the right layer (or all three) instead of guessing.

### Changed
- Replaced the previous JSONC `examples/settings.json.fragment` (which
  contained `//` comments) with a strict-JSON `examples/hooks.json`.
  Pasting the old fragment verbatim into `~/.claude/settings.json`
  would have corrupted that file; the new example round-trips through
  `json.load` cleanly.

### Added
- `examples/INSTALL.md` walks the reader through both a manual merge
  and an idempotent `jq` one-liner with a timestamped backup and a
  dry-run step.
- Six new tests in `tests/test_examples.py` enforce strict JSON in
  `examples/`, exercise the documented `jq` merge for idempotency, and
  guard against future JSONC regressions.

### Removed
- `examples/settings.json.fragment` (replaced by `examples/hooks.json`).

## [0.1.0] - 2026-05-08

### Added
- Initial release.
- Single-file Python 3 implementation of a Claude Code `PreToolUse` hook.
- Default deny patterns for: GitHub CLI tokens, `git credential.helper=store`,
  AWS / GCP / Azure auth dumps, `kubectl config view --raw`, `docker login -p`,
  reads of `.env` / `.netrc` / `id_*` / `~/.kube/config` / `~/.aws/credentials`
  / `.npmrc` / `.pypirc` / `.docker/config.json` and similar credential files,
  `printenv`, `env`, `echo $*TOKEN/KEY/SECRET/PASSWORD`, `printf` of the same,
  `curl|sh` / `wget|bash`, `vault read`, `op read --reveal`,
  `doppler secrets get`/`download`, `bw get password`, `bw export`,
  `sops --decrypt`, `pass show`, `secret-tool lookup`, `keyring get`,
  `gpg --decrypt`, `openssl rsa/ec/pkey/enc -passin pass:`,
  `history` and `fc -l`.
- Default allow patterns covering common safe shapes of `gh`, `git`, `npm`,
  `yarn`, `pnpm`, `npx`, `pip`, `pipx`, `cargo`, `go`, `docker`, `kubectl`,
  `ls`, `pwd`.
- `PCG_RULES_FILE` for project- or user-specific extensions; bad patterns
  are logged and skipped, never crash the hook.
- `PCG_OVERRIDE=1` for one-shot bypass.
- JSONL audit log under `$XDG_STATE_HOME/precontext-guard`.
- 108 unit tests; CI matrix on Ubuntu and macOS for Python 3.10–3.13.
- Lint job (ruff + lenient mypy).
- Leak-audit job that fails CI if any user-specific identifier slips into
  the repo.
