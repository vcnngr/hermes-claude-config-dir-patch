# Repository instructions

## Purpose

Maintain the smallest downstream Hermes Agent patch that enables multiple
Claude Code accounts, each selected through its own `CLAUDE_CONFIG_DIR`, in a
single Anthropic credential pool.

The upstream checkout is normally `~/.hermes/hermes-agent`. This repository
stores patches and maintenance knowledge; it is not a Hermes fork.

## Safety and scope

- Test real profile behavior only with `codexauthtest`.
- Never modify another Hermes profile for this work.
- Never print, copy, commit, or persist OAuth access/refresh tokens.
- Keychain validation may compare SHA-256 fingerprints in memory; output only
  booleans, source ids, and non-secret fingerprints.
- Do not send live Anthropic inference requests unless explicitly requested.
- Preserve unrelated upstream changes. Never use `git reset --hard`.
- Keep patch minimal. Do not add a custom credential store or duplicate Claude
  Code secrets into Hermes.

## Required workflow for each Hermes release

1. Read `CLAUDE.md` and all files under `docs/`.
2. Record Hermes version, upstream commit, branch, and dirty state.
3. Check whether upstream now supports per-entry `claude_config_dir`. Retire
   this patch if upstream behavior is equivalent and tests pass.
4. Rebase/recreate the patch against the new clean upstream base. Resolve only
   conflicts related to this feature.
5. Run tests through `scripts/run_tests.sh`; never invoke pytest directly.
6. Validate only `codexauthtest` with an explicit `HERMES_HOME`.
7. Store the new patch under `patches/<hermes-version>/` and update checksums,
   version table, architecture notes, and test results.
8. Commit and push this repository only after `git apply --check` succeeds on
   the intended clean base and `git apply --check --reverse` succeeds on the
   patched checkout.

If `~/.hermes/hermes-agent/graphify-out/graph.json` exists, query Graphify
before broad source browsing. After upstream code modifications, run
`graphify update .` from the Hermes checkout.

## Patch contents

The patch may modify only the smallest relevant set:

- `agent/anthropic_adapter.py`
- `agent/credential_pool.py`
- `agent/credential_sources.py`
- focused tests for those modules/removal registry
- credential-pool documentation

Any expansion beyond that list requires a documented reason in
`docs/MAINTENANCE.md`.
