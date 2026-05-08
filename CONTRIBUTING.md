# Contributing

Thanks for considering a contribution.

## How to add a new deny pattern

1. Find an authoritative source that says **this CLI shape prints a
   secret to stdout**.  Cite the docs or a `--help` excerpt in the PR
   description.
2. Add the pattern to `DENY_DEFAULT` in `precontext-guard` along with a
   short, action-oriented `reason` (≤120 chars, second person, says
   what to do instead).
3. Add at least one BLOCK test and one ALLOW test in
   `tests/test_decide.py`.  The ALLOW test should be a similar-but-safe
   subcommand of the same CLI, to make sure your regex isn't too
   broad.  (Example: blocking `aws configure` should not block
   `aws s3 ls`.)
4. Run the suite locally:

   ```bash
   python -m pytest tests/ -q
   ```

5. Update `CHANGELOG.md` under `[Unreleased]`.

## Code style

- Single file, no runtime dependencies.  If you find yourself reaching
  for a third-party library, please open an issue first to discuss
  whether the feature belongs here.
- Type hints encouraged but not required for the matcher itself; CI
  runs `mypy --ignore-missing-imports --allow-untyped-defs` so the bar
  is "no obviously wrong types."
- `ruff check` should be clean.

## What not to add

- **Anything tied to a specific person, host, or local path.**  See the
  `leak-audit` CI job in `.github/workflows/ci.yml`.
- **Network calls.**  The hook must remain offline.
- **Default rules with a high false-positive rate.**  When in doubt,
  document the pattern in `examples/rules.example.json` instead of
  shipping it in `DENY_DEFAULT`.

## Reporting bugs / requesting CLIs

For new CLI coverage, open an issue with:

- The CLI name and version.
- The exact command shape that prints a secret.
- A safe sibling command to use as the ALLOW test.

Minimal repros beat long descriptions.
