# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
