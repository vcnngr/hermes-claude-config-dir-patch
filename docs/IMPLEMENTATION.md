# Implementation

## Problem

Unpatched Hermes reads one ambient Claude Code identity:

- process `CLAUDE_CONFIG_DIR`, otherwise `~/.claude`;
- historically, one unsuffixed macOS Keychain service;
- one pool row with `source: claude_code`.

That cannot represent several Claude Code logins inside one Hermes profile.
Changing a profile `.env` selects only one directory for the whole process.
Directly replaying borrowed OAuth tokens also does not reproduce Claude Code's
supported inference path.

## Design

Each `auth.json` row may include `claude_config_dir`. Hermes normalizes the
path and reads exactly that Claude Code credential source.

```text
auth.json row
  -> normalize config directory
  -> derive pool source id
  -> derive macOS Keychain service
  -> hydrate borrowed token in memory
  -> select/rotate through normal Anthropic pool
```

The optional profile setting below switches inference to the official CLI:

```yaml
model:
  anthropic_runtime: claude_code_cli
```

Runtime flow:

```text
selected pool entry
  -> pass its claude_config_dir to ClaudeCodeCLIClient
  -> strip ambient Anthropic token variables
  -> set child CLAUDE_CONFIG_DIR
  -> run official claude -p with JSON output
  -> map result/usage into Hermes' chat-completion interface
  -> rotate pool entry on 401/429
```

For `/Users/example/.claude-work`:

```text
keychain: Claude Code-credentials-<sha256(path)[:8]>
pool:     claude_code:<sha256(path)[:8]>
```

Default `~/.claude` retains `source: claude_code` for compatibility. Its
Keychain lookup tries the scoped service first, then the old unsuffixed service.
Alternative directories never fall back to the default service, preventing
cross-account borrowing.

## Persistence boundary

Claude Code credentials are borrowed sources. Pool load hydrates access and
refresh tokens in memory. `auth.json` persists:

- id, label, auth type, priority, source;
- normalized `claude_config_dir`;
- expiry/status/request counters;
- non-reversible secret fingerprint.

It does not persist access or refresh tokens. Refresh writes back only to the
entry's selected Claude config directory.

## Source identity and removal

Scoped sources use `claude_code:<hash8>`. Existing pool deduplication,
suppression, cooldown, and removal can therefore operate independently per
account. A suppression for literal `claude_code` disables only implicit
default-directory discovery; scoped rows remain available.

## Touched upstream modules

- `agent/anthropic_adapter.py`: path normalization, service derivation,
  directory-aware reads/writes/refresh.
- `agent/credential_pool.py`: schema alias, scoped hydration, source ranking,
  refresh/resync isolation.
- `agent/credential_sources.py`: removal matching for scoped source ids.
- `agent/claude_code_cli_client.py`: small OpenAI-compatible facade over
  official `claude -p`.
- `hermes_cli/runtime_provider.py`: profile opt-in runtime selection.
- `agent/agent_init.py`, `agent/agent_runtime_helpers.py`, `run_agent.py`:
  selected-directory propagation and credential rotation.
- Focused tests and credential-pool docs.
