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
  -> prefer config-scoped Hermes setup-token when present
  -> otherwise read Claude Code login Keychain/file credentials
  -> hydrate borrowed token in memory
  -> select/rotate through normal Anthropic pool
```

Claude-sourced pool rows switch inference to the official runtime
automatically. API-key-only rows stay on the direct Messages API. Explicit
configuration remains available:

```yaml
model:
  anthropic_runtime: claude_code
```

`claude_code_cli` remains a compatibility alias. `native` forces the direct
Messages API.

Runtime flow:

```text
selected pool entry
  -> pass its claude_config_dir to ClaudeCodeSession
  -> strip ambient Anthropic token/provider variables
  -> set child CLAUDE_CONFIG_DIR
  -> set child CLAUDE_CODE_OAUTH_TOKEN only for its selected setup-token
  -> send the compressed Hermes turn over stdin (not process arguments)
  -> run official claude -p with stream-json + partial messages
  -> Claude owns its native Bash/file/MCP agent loop
  -> relay text/reasoning/tool progress to Hermes as it arrives
  -> project completed assistant/tool events into Hermes session history
  -> compose standalone assistant blocks for complete gateway delivery
  -> classify 401/429 and rotate before tool execution only
```

For `~/.claude-work`:

```text
login keychain: Claude Code-credentials-<sha256(path)[:8]>
setup keychain: Hermes Claude Code setup-token-v2-<sha256(path)[:8]>
pool:           claude_code:<sha256(path)[:8]>
```

Default `~/.claude` retains `source: claude_code` for compatibility. Its
Keychain lookup tries the scoped service first, then the old unsuffixed service.
Alternative directories never fall back to the default service, preventing
cross-account borrowing.

Long-lived setup-tokens remain separate from Claude Code's refreshable login
item. Hermes stores their JSON payload over stdin using a fixed-path private
Security.framework helper. The stable executable identity gives macOS
Keychain a durable ACL without exposing the token in process arguments. Only
the selected Claude CLI child receives the token environment variable; the
Hermes MCP bridge remains credential-free. Missing, expired, or unreadable
setup-token items fall back to the matching normal Claude Code login.

## Runtime ownership boundary

Claude Code executes native tools. Projected tool calls are persistence records
only; Hermes never dispatches them again. This restores autonomous multi-step
work while preventing double execution.

Claude Code's terminal `result` event contains only its last assistant block.
When a substantive answer is followed by a control tool and a short epilogue
such as “Waiting”, Hermes composes the distinct standalone assistant blocks for
gateway delivery. Tool-call preambles remain progress-only, while every
substantive answer stays visible instead of existing only in session history.

The child runs in the Hermes session cwd with permission mode `auto` by
default. `HERMES_CLAUDE_PERMISSION_MODE` can override it. Interrupt/close
signals terminate the active CLI process.

Hermes capabilities without a Claude native equivalent are exposed through a
stdio MCP subprocess. The subprocess receives only active profile/toolset
scope, not OAuth tokens in command arguments. It re-exports profile MCP tools,
kanban, browser/web/vision, skills, cron, built-in memory, and session search.
Context-bound duplicates such as terminal/file tools, clarify, Hermes todo, and
Hermes delegation remain excluded; Claude Code supplies native equivalents for
execution, planning, and subagents.

The gateway binds both the routing key and durable `session_id` into the turn's
task-local context. The subprocess environment bridge carries that identity to
Claude Code and the Hermes MCP server. `kanban_create` persists it with the
task. On terminal Kanban events, the notifier resolves the stored session's
exact `SessionSource` and injects the internal wake only when platform, chat,
thread, participant, and profile still match. It never guesses `chat_type`, so
DM creators resume their existing session instead of a fresh group session.

Credential failover replays a turn only when no native tool has started. Once
Bash/Edit/MCP execution may have produced side effects, failure is returned as
partial instead of risking duplicate writes or commands.

## Persistence boundary

Claude Code credentials are borrowed sources. Pool load hydrates access and
refresh tokens in memory. `auth.json` persists:

- id, label, auth type, priority, source;
- normalized `claude_config_dir`;
- expiry/status/request counters;
- non-reversible secret fingerprint.

It does not persist access or refresh tokens. Refresh writes back only to the
entry's selected Claude config directory.

Hermes setup-tokens also never enter `auth.json`. Their config-scoped Keychain
items contain the token plus creation/expiry metadata and do not overwrite or
delete Claude Code's own login credentials.

## Source identity and removal

Scoped sources use `claude_code:<hash8>`. Existing pool deduplication,
suppression, cooldown, and removal can therefore operate independently per
account. A suppression for literal `claude_code` disables only implicit
default-directory discovery; scoped rows remain available.

## Touched upstream modules

- `agent/anthropic_adapter.py`: path normalization, service derivation,
  directory-aware reads/writes/refresh, setup-token Keychain storage.
- `agent/credential_pool.py`: schema alias, scoped hydration, source ranking,
  refresh/resync isolation.
- `agent/credential_sources.py`: removal matching for scoped source ids.
- `agent/transports/claude_code_session.py`: CLI lifecycle, stream parsing,
  event projection, tool progress, interrupt, and environment isolation.
- `agent/claude_runtime.py`: turn ownership, complete multi-block delivery,
  safe pool failover, persistence, memory sync, and usage accounting.
- `agent/transports/hermes_tools_mcp_server.py`: profile-scoped stateless
  Hermes/MCP capability bridge shared with external runtimes.
- `gateway/run.py`, `gateway/kanban_watchers.py`: durable session-id propagation
  and exact-origin Kanban wake routing.
- `hermes_cli/runtime_provider.py`: automatic runtime selection and native
  escape hatch.
- `agent/agent_init.py`, `agent/conversation_loop.py`,
  `agent/agent_runtime_helpers.py`, `run_agent.py`: selected-directory
  propagation, early external-runtime routing, rotation, and interruption.
- Focused runtime, gateway, Kanban, credential tests, and credential-pool docs.
