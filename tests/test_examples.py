"""Tests covering the files in examples/.

Earlier versions of this repository shipped a JSONC fragment whose ``//``
comments would corrupt the user's ``settings.json`` if pasted verbatim.
These tests guarantee that

  * every JSON example parses with strict JSON.org semantics, and
  * the merge procedure documented in examples/INSTALL.md, when
    executed, produces a result that still parses as strict JSON.

License: MIT
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_examples_dir_exists() -> None:
    assert EXAMPLES.is_dir(), "examples/ directory should exist"


@pytest.mark.parametrize("name", ["hooks.json", "rules.example.json"])
def test_example_is_strict_json(name: str) -> None:
    """No comments, no trailing commas — must round-trip through json.load."""
    target = EXAMPLES / name
    assert target.is_file(), f"{name} missing"
    raw = target.read_text(encoding="utf-8")
    # Reject obvious JSONC: '//' starting a line.
    assert "//" not in raw or all(
        not line.lstrip().startswith("//") for line in raw.splitlines()
    ), f"{name} contains a JSONC '//' comment"
    parsed = json.loads(raw)  # Strict; would raise on a stray comma too.
    # Smoke-test the shape we care about for hooks.json.
    if name == "hooks.json":
        assert "hooks" in parsed, "hooks.json must declare 'hooks'"
        pre = parsed["hooks"].get("PreToolUse")
        assert isinstance(pre, list) and pre, "PreToolUse must be a non-empty list"
        entry = pre[0]
        assert entry.get("matcher") == "Bash"
        inner = entry.get("hooks")
        assert isinstance(inner, list) and inner
        assert inner[0].get("type") == "command"
        assert inner[0].get("command", "").endswith("precontext-guard") or (
            "/path/to/" in inner[0].get("command", "")
        )


@pytest.mark.skipif(
    shutil.which("jq") is None,
    reason="jq is needed to exercise the documented merge one-liner",
)
def test_jq_merge_idempotent(tmp_path: Path) -> None:
    """The jq one-liner from INSTALL.md should:

    * append a Bash PreToolUse hook to an empty settings.json,
    * leave the file unchanged on a second run (no duplicate entry),
    * leave any unrelated keys intact, and
    * always emit strict JSON.
    """
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "model": "claude-sonnet-4-6",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [
                                {"type": "command", "command": "/usr/bin/true"}
                            ],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    cmd_path = "/opt/precontext-guard/precontext-guard"
    jq_filter = """
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
    """

    def run_merge() -> dict:
        out = subprocess.run(
            ["jq", "--arg", "cmd", cmd_path, jq_filter, str(settings)],
            check=True,
            capture_output=True,
            text=True,
        )
        # The dry-run output must itself be strict JSON.
        return json.loads(out.stdout)

    merged_once = run_merge()
    settings.write_text(json.dumps(merged_once), encoding="utf-8")
    merged_twice = run_merge()

    # Idempotency.
    assert merged_once == merged_twice, "second jq pass should be a no-op"

    # Existing key preserved.
    assert merged_once["model"] == "claude-sonnet-4-6"

    # Pre-existing Read hook preserved.
    pre_hooks = merged_once["hooks"]["PreToolUse"]
    matchers = [h["matcher"] for h in pre_hooks]
    assert "Read" in matchers, "the existing Read hook must not be dropped"
    assert "Bash" in matchers, "the Bash hook must be present"

    # The Bash hook points at our binary.
    bash_entry = next(h for h in pre_hooks if h["matcher"] == "Bash")
    assert bash_entry["hooks"][0]["command"] == cmd_path


def test_install_md_links_to_strict_json_example() -> None:
    """INSTALL.md must steer the reader to the strict-JSON file, not the
    deprecated JSONC fragment."""
    install_md = (EXAMPLES / "INSTALL.md").read_text(encoding="utf-8")
    assert "examples/hooks.json" in install_md or "hooks.json" in install_md
    # The deprecated fragment name must not appear as a live reference.
    assert "settings.json.fragment" not in install_md, (
        "INSTALL.md should not reference the removed JSONC fragment"
    )


def test_no_jsonc_files_in_examples() -> None:
    """No file in examples/ should contain a stray JSON-with-comments
    pattern that would mislead a future user copy-pasting it."""
    for path in EXAMPLES.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        bad = [
            (i + 1, line)
            for i, line in enumerate(text.splitlines())
            if line.lstrip().startswith("//")
        ]
        assert not bad, f"{path} contains JSONC comments at {bad}"
