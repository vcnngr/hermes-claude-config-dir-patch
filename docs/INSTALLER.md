# Automated installer

`scripts/hermes_patch.py` manages the versioned downstream patch without a
remote bootstrap script. It uses Python's standard library and the local
`patches/manifest.json`.

## Supported scope

The current manifest accepts only Hermes `v0.18.2 (2026.7.7.2)` at upstream
commit `226e8de8`. The Hermes checkout defaults to `~/.hermes/hermes-agent`;
override it with global `--hermes-dir`. The Hermes data root defaults to
`~/.hermes`; override it with global `--hermes-home`.

Global options must precede the subcommand.

## Commands

```bash
# Read-only compatibility, dependency, and optional profile checks
python3 scripts/hermes_patch.py doctor --profile YOUR_PROFILE

# Show patch state without changing anything
python3 scripts/hermes_patch.py status

# Preview or install the patch
python3 scripts/hermes_patch.py install --dry-run
python3 scripts/hermes_patch.py install

# Back up auth.json and configure metadata-only account rows
python3 scripts/hermes_patch.py configure-profile \
  --profile YOUR_PROFILE \
  --claude-dir ~/.claude-team \
  --label claude-team

# Run the official flow for selected configured rows on macOS
python3 scripts/hermes_patch.py setup-tokens \
  --profile YOUR_PROFILE \
  --slot 1

# Preview or remove only the versioned patch
python3 scripts/hermes_patch.py remove --dry-run
python3 scripts/hermes_patch.py remove
```

Use repeated `--slot` values or `--all` for multiple setup-token rows.

## Safety model

- Exact upstream commit selection; unsupported versions fail closed.
- SHA-256 verification before every patch operation.
- Normal and reverse `git apply --check` determine `available`, `installed`,
  or `incompatible` state.
- Installation refuses local changes in patch-touched files and preserves
  unrelated checkout changes.
- Removal reverses only the versioned patch. It never runs `git reset`.
- `configure-profile` is the only command that edits profile data. It creates
  a mode-`0600` backup and writes JSON atomically.
- Profile rows contain paths, labels, sources, and priorities only. Access and
  refresh token fields are removed from matching rows.
- Setup-tokens use a hidden prompt and config-scoped macOS Keychain items.
  Tokens are never command arguments, shell history, profile JSON, or files.
- `doctor` is read-only. It may inspect existing Keychain item health but does
  not print secrets or make an Anthropic request.

Installation does not restart gateways. Restart the intended profile only
after checks pass and during an operator-approved maintenance window.

## Update behavior

Before `hermes update`, run `remove`. After updating, run `install` again. A
new upstream commit is intentionally rejected until the maintainer verifies
that upstream lacks equivalent support, ports the patch, updates the manifest
and checksum, and completes the documented regression suite.

Profile metadata and Keychain setup-tokens survive patch removal. No live
Anthropic inference is part of any installer command.
