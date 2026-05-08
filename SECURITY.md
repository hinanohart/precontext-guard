# Security policy

## Scope

`precontext-guard` is a small guard-rail for an everyday workflow.  It is
not a security-critical control plane.  See [docs/threat-model.md](docs/threat-model.md)
for what it does and does not protect against.

## Reporting a vulnerability

If you believe you have found a security-relevant bug — for example, a
default deny pattern that fails to match an obviously dangerous CLI
shape, or a path where the hook itself can be made to leak — please open
a private security advisory via GitHub:

  Security ▸ Advisories ▸ Report a vulnerability

If for any reason you cannot use that channel, file a regular issue
**without** including any actual secret material; we will respond and
move the conversation to a private channel.

## What we will and will not patch

- ✅ A new dangerous CLI subcommand we missed.
- ✅ An over-broad allow pattern that lets a known-bad shape through.
- ✅ A crash that lets a Bash command run when it should have been
  blocked.
- ❌ Bypasses through obfuscation (`bash -c "..."`, `eval`, base64
  pipes).  These are out of scope; see threat-model.md.

## Disclosure

We will publish a fix and a brief note in the changelog.  We will not
publicly disclose the reporter's identity without their consent.
