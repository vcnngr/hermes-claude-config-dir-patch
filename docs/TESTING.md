# Testing

## Automated regression suite

Installer regression suite:

```bash
cd /path/to/hermes-claude-config-dir-patch
python3 -m pytest -q tests/test_hermes_patch_installer.py
```

Current result: `11 passed, 0 failed`. Coverage includes exact-commit and
SHA-256 gating, idempotent install/remove, dirty-file protection, preservation
of unrelated changes, metadata-only profile writes, backups, path-traversal
rejection, malformed-profile handling, dry runs, and explicit setup-token slot
selection.

An end-to-end installer run used a temporary clean worktree at upstream commit
`226e8de8`. Install, status, Python compilation, `14` focused Hermes tests,
remove, and final clean-tree checks passed. It did not modify a real profile,
read or write real credentials, or make a live Anthropic request.

Current adapter/runtime regression commands:

```bash
cd ~/.hermes/hermes-agent
venv/bin/pytest -q \
  tests/agent/transports/test_claude_code_session.py \
  tests/run_agent/test_claude_code_runtime.py \
  tests/agent/transports/test_hermes_tools_mcp_server.py \
  tests/agent/test_credential_pool_routing.py \
  tests/agent/test_credential_pool.py

venv/bin/pytest -q \
  tests/hermes_cli/test_runtime_provider_resolution.py \
  tests/run_agent/test_run_agent.py
```

Current result: `123 passed, 0 failed` and `575 passed, 0 failed` (`698`
total) across these two groups.

The older credential hydration regression set remains useful:

```bash
venv/bin/pytest -q \
  tests/agent/test_anthropic_keychain.py \
  tests/agent/test_anthropic_adapter.py \
  tests/agent/test_credential_pool.py \
  tests/hermes_cli/test_auth_commands.py
```

Current result: `342 passed, 0 failed`.

The session-identity/Kanban wake regression set is:

```bash
venv/bin/pytest -q \
  tests/gateway/test_session_env.py \
  tests/gateway/test_kanban_notifier.py \
  tests/gateway/test_internal_event_bypass_pairing.py \
  tests/tools/test_kanban_tools.py \
  tests/agent/transports/test_hermes_tools_mcp_server.py \
  tests/agent/transports/test_claude_code_session.py \
  tests/run_agent/test_claude_code_runtime.py
```

Current result: `158 passed, 0 failed`.

Coverage includes:

- config-scoped Keychain service selection;
- one-year setup-token storage over stdin, never process arguments;
- setup-token priority with directory-matched login fallback;
- selected-token injection into only the matching Claude CLI child;
- legacy fallback only for default directory;
- explicit credential-file read/write directory;
- uppercase input alias normalization;
- two scoped accounts hydrated in one pool;
- no access/refresh token persistence in `auth.json`;
- scoped refresh/resync and removal matching;
- existing Anthropic/Nous credential-pool regressions.

Runtime coverage includes:

- real incremental text/reasoning callbacks from `stream-json`;
- native tool start/completion projection without Hermes re-execution;
- stdin prompt delivery and exact `CLAUDE_CONFIG_DIR` environment isolation;
- active profile toolset propagation into the Hermes MCP bridge;
- profile MCP, memory, session-search, kanban, and stateless tool exposure;
- clean 401/429 credential rotation;
- no turn replay after native tool execution may have side effects;
- subprocess interrupt/close handling and session persistence.
- complete delivery when an answer precedes a control-tool/wakeup epilogue;
- durable gateway `session_id` propagation into child/MCP environments;
- exact DM/group/thread origin recovery for internal Kanban completion wakes;
- fail-closed refusal when a task session and notification destination differ;
- credential tests isolated from the operator's host Keychain.

## Real local hydration test

Use only one explicitly authorized test profile:

```bash
HERMES_HOME=~/.hermes/profiles/YOUR_AUTHORIZED_PROFILE hermes auth list anthropic
```

Expected: the default `claude_code` row plus one distinct
`claude_code:<hash8>` row for every configured alternative directory. Current
validation covered default plus three alternatives in one profile.

Safe assertions:

- distinct runtime credential values in memory;
- each persisted fingerprint matches the corresponding scoped Keychain item;
- no `access_token` or `refresh_token` keys in profile `auth.json`;
- only the explicitly authorized profile changed.

For the 2026-07-15 runtime validation, the user explicitly authorized one
profile. The first selected directory returned HTTP 401; Hermes rotated to the
next directory. Official Claude Code then executed one Bash canary, persisted
`STREAM_CODE_OK`, and returned `CANARY_OK`. No other profile made a live
Anthropic request. Future tests still require explicit authorization.

The 2026-07-15 Kanban session-wake change used temporary test databases only;
it made no live Anthropic request and changed no profile or real board data.

The 2026-07-15 multi-block delivery fix used synthetic Claude stream events
only; it made no live Anthropic request and changed no profile or board data.

On 2026-07-16, the user explicitly completed official `claude setup-token`
authorization for four configured directories in one authorized profile.
Safe local checks confirmed four readable, distinct Keychain items, future
expiry, and exact per-directory runtime selection. The user then confirmed a
live end-to-end response. The maintenance process made no live Anthropic
inference request, and the same shared credentials were not tested against any
other profile.

Do not print token values. Do not make a live Anthropic inference request
unless the user explicitly authorizes usage consumption.

## Patch integrity

On the patched checkout:

```bash
cd ~/.hermes/hermes-agent
PATCH=~/Documents/claude/hermes-claude-config-dir-patch/patches/v0.18.2/hermes-claude-config-dir-multipool.patch
git apply --check --reverse "$PATCH"
shasum -a 256 "$PATCH"
```

On a clean matching checkout, replace `--reverse` with a normal
`git apply --check`.
