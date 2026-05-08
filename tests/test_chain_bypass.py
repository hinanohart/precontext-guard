"""Tests for the 2026-05-09 R17 audit findings.

Three CRITICAL classes were patched in this branch:

* **CRITICAL #1** — chained-command bypass (a harmless prefix matching
  an allow rule used to short-circuit the whole scan, leaving the
  chained sensitive statement unevaluated).
* **CRITICAL #2** — audit log file mode (was world-readable; now 0o600
  with 0o700 parent dir).
* **CRITICAL #3** — stdin had no size cap and any internal error was
  treated as fail-open, so a 1MB junk payload could neutralise every
  deny rule.

These tests verify the three fixes by exercising representative
attacks and asserting the new (post-fix) behaviour.
"""

from __future__ import annotations

import importlib.util
import importlib.machinery
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "precontext-guard"


def _import_pcg():
    # The file has no .py extension, so we have to construct the loader
    # explicitly rather than relying on spec_from_file_location's
    # extension sniffing.
    loader = importlib.machinery.SourceFileLoader("pcg", str(SCRIPT))
    spec = importlib.util.spec_from_loader("pcg", loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pcg = _import_pcg()


# ---------------------------------------------------------------------------
# CRITICAL #1 — chained-command bypass
# ---------------------------------------------------------------------------

CHAIN_BYPASS_ATTACKS = [
    # (description, command)
    ("semicolon", "rm -rf /tmp/x; cat .env"),
    ("double-amp", "git push && cat .env"),
    ("double-pipe", "git push origin main || gh auth token"),
    ("pipe", "ls -la | gh auth token"),
    ("newline", "git push origin main\ncat /home/me/.aws/credentials"),
    ("background-amp", "ls -la & cat .env"),
    ("triple-chain", "ls; pwd; gh auth token"),
    ("nested-with-allow-prefix", "git status && git push && cat ~/.ssh/id_ed25519"),
    ("pipe-into-secret-cat", "echo hi | cat /home/u/.aws/credentials"),
    ("amp-after-allow", "git push --force origin feature-branch && cat .env"),
]


@pytest.mark.parametrize(
    "description,command",
    CHAIN_BYPASS_ATTACKS,
    ids=[d for d, _ in CHAIN_BYPASS_ATTACKS],
)
def test_chain_bypass_is_blocked(description: str, command: str) -> None:
    """Each chain-bypass attack must be blocked, not allowed.

    These all match an allow rule on the leading segment, but a deny
    rule on a subsequent segment. v1 short-circuited on the first
    allow match and approved the whole call.
    """
    verdict, reason = pcg.decide(command)
    assert verdict == "block", (
        f"chain-bypass attack '{description}' was unexpectedly allowed: "
        f"command={command!r}, reason={reason!r}"
    )


LEGITIMATE_CHAINS = [
    ("two-git-commands", "git push origin main && git tag v1.0"),
    ("status-then-push", "git status; git push"),
    ("pipe-allowed-tools", "git log --oneline | head"),
    ("background-allowed", "ls -la & pwd"),
    ("npm-chain", "npm install && npm test"),
]


@pytest.mark.parametrize(
    "description,command",
    LEGITIMATE_CHAINS,
    ids=[d for d, _ in LEGITIMATE_CHAINS],
)
def test_legitimate_chain_is_allowed(description: str, command: str) -> None:
    """Composing two allow-listed commands must remain allowed."""
    verdict, reason = pcg.decide(command)
    assert verdict == "allow", (
        f"legitimate chain '{description}' was unexpectedly blocked: "
        f"command={command!r}, reason={reason!r}"
    )


def test_separator_inside_double_quotes_is_literal() -> None:
    """A semicolon inside a double-quoted string must not split."""
    assert pcg.split_segments('echo "a; b && c"') == ['echo "a; b && c"']


def test_separator_inside_single_quotes_is_literal() -> None:
    """A separator inside a single-quoted string must not split."""
    assert pcg.split_segments(r"echo 'a;b&&c'") == [r"echo 'a;b&&c'"]


def test_escaped_separator_is_literal() -> None:
    """A backslash-escaped separator must not split."""
    out = pcg.split_segments(r"echo a\;b")
    assert out == [r"echo a\;b"]


def test_split_function_basic() -> None:
    assert pcg.split_segments("a; b") == ["a", "b"]


def test_split_function_empty_yields_no_segments() -> None:
    assert pcg.split_segments("") == []
    assert pcg.split_segments("   \n  \t") == []


def test_split_function_collapses_repeated_separators() -> None:
    """`a;;;b` should not produce empty segments."""
    assert pcg.split_segments("ls;;;pwd") == ["ls", "pwd"]


def test_split_function_handles_mixed_separators() -> None:
    assert pcg.split_segments("a; b && c | d || e\nf & g") == [
        "a", "b", "c", "d", "e", "f", "g",
    ]


def test_split_function_keeps_long_command_whole() -> None:
    cmd = "echo " + "x" * 1000
    out = pcg.split_segments(cmd)
    assert len(out) == 1
    assert out[0] == cmd


# ---------------------------------------------------------------------------
# CRITICAL #2 — audit log permissions
# ---------------------------------------------------------------------------


def test_audit_log_is_mode_0600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A blocked command writes the audit log with 0o600 (owner-only)."""
    monkeypatch.setenv("PCG_LOG_DIR", str(tmp_path / "audit"))
    # Reload the module so it picks up the env var for LOG_DIR / LOG_FILE.
    mod = _import_pcg()
    mod.log_event("block", "echo SECRET-LITERAL", "test reason")

    log_file = tmp_path / "audit" / "audit.jsonl"
    assert log_file.exists()
    mode = stat.S_IMODE(log_file.stat().st_mode)
    assert mode == 0o600, f"audit log mode is {oct(mode)}, expected 0o600"


def test_audit_dir_is_mode_0700(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The audit log directory is 0o700 (no group / world traversal)."""
    monkeypatch.setenv("PCG_LOG_DIR", str(tmp_path / "audit"))
    mod = _import_pcg()
    mod.log_event("block", "echo SECRET-LITERAL", "test reason")

    log_dir = tmp_path / "audit"
    mode = stat.S_IMODE(log_dir.stat().st_mode)
    assert mode == 0o700, f"audit dir mode is {oct(mode)}, expected 0o700"


# ---------------------------------------------------------------------------
# CRITICAL #3 — stdin size cap & fail-secure
# ---------------------------------------------------------------------------


def _run_pcg(stdin_bytes: bytes, env_extra: dict[str, str] | None = None) -> tuple[int, bytes, bytes]:
    """Run precontext-guard as a subprocess with the given stdin."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin_bytes,
        env=env,
        capture_output=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_stdin_within_cap_is_processed(tmp_path: Path) -> None:
    """A normal-sized payload runs to completion."""
    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
    }).encode()
    rc, _stdout, _stderr = _run_pcg(
        payload,
        env_extra={"PCG_LOG_DIR": str(tmp_path / "log")},
    )
    assert rc == 0


def test_stdin_above_cap_is_blocked(tmp_path: Path) -> None:
    """A 2 MiB payload must trigger fail-secure block (rc=2)."""
    payload = b"{" + b"a" * (2 << 20) + b"}"
    rc, _stdout, stderr = _run_pcg(
        payload,
        env_extra={"PCG_LOG_DIR": str(tmp_path / "log")},
    )
    assert rc == 2, f"expected fail-secure block (rc=2), got rc={rc}"
    assert b"fail-secure" in stderr or b"BLOCKED" in stderr
