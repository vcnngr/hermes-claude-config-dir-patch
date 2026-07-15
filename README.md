# Hermes multi-Claude Code auth patch

Small downstream patch adding multiple `CLAUDE_CONFIG_DIR` accounts to one
Hermes Anthropic credential pool and a streaming official Claude Code runtime.

Supported base:

| Hermes | Upstream commit | Patch status |
|---|---|---|
| `v0.18.2 (2026.7.7.2)` | `226e8de8` | Tested |

## What it adds

- Multiple `claude_code` rows in one profile and one rotation pool.
- Per-row `claude_config_dir`; uppercase `CLAUDE_CONFIG_DIR` accepted as alias.
- macOS Keychain lookup using Claude Code's config-directory hash.
- Refresh/sync written back only to the matching Claude config directory.
- Metadata and fingerprints in Hermes `auth.json`; no copied OAuth tokens.
- Backward-compatible default `~/.claude` behavior.
- Inference through official `claude -p --output-format stream-json`, using the
  selected entry's directory.
- Real response deltas, native Bash/Read/Edit/Write agent loop, interrupts, and
  tool progress instead of a buffered chatbot-style completion.
- Complete multi-block response delivery when Claude answers, invokes a
  control tool such as `ScheduleWakeup`, then emits a short final epilogue.
- Enabled Hermes tools, profile MCP servers, memory, session search, and kanban
  bridged into Claude Code over a credential-free stdio MCP process.
- Durable gateway session identity bridged into the Claude/MCP subprocess, so
  Kanban completion events wake the exact originating DM/group/thread session.
- Automatic rotation to another configured directory on auth/rate-limit errors,
  including an expired Claude Code OAuth session. A turn is never replayed
  after a native tool starts, preventing duplicate side effects.

Non-default source ids become `claude_code:<8-char-directory-hash>`. The
default directory keeps `source: "claude_code"`.

## Apply

```bash
mkdir -p ~/Documents/claude/hermes-claude-config-dir-patch/patches/v0.18.2
curl -L \
  https://raw.githubusercontent.com/vcnngr/hermes-claude-config-dir-patch/main/patches/v0.18.2/hermes-claude-config-dir-multipool.patch \
  -o ~/Documents/claude/hermes-claude-config-dir-patch/patches/v0.18.2/hermes-claude-config-dir-multipool.patch

cd ~/.hermes/hermes-agent
PATCH=~/Documents/claude/hermes-claude-config-dir-patch/patches/v0.18.2/hermes-claude-config-dir-multipool.patch
git apply --check "$PATCH"
git apply --3way "$PATCH"
```

Patch SHA-256:

```text
aa521aadc059b9b023c71539ca9cd3d8289e1d1314eb47298a173bea1a77b90f
```

## Configure one Hermes profile

Add metadata-only rows to that profile's `auth.json`:

```json
{
  "credential_pool": {
    "anthropic": [
      {
        "id": "cc-work",
        "label": "claude-team",
        "auth_type": "oauth",
        "priority": 0,
        "source": "claude_code",
        "claude_config_dir": "~/.claude-team"
      },
      {
        "id": "cc-personal",
        "label": "claude-personal",
        "auth_type": "oauth",
        "priority": 1,
        "source": "claude_code",
        "CLAUDE_CONFIG_DIR": "~/.claude-personal"
      }
    ]
  }
}
```

Each directory must already be authenticated with Claude Code. Hermes reads
its matching Keychain/file credentials on pool load.

Claude-sourced Anthropic pool rows select the official runtime automatically.
No per-profile config edit is required, so the behavior applies consistently
to every Hermes profile using `claude_config_dir` rows.

An explicit equivalent setting is:

```yaml
model:
  provider: anthropic
  anthropic_runtime: claude_code
```

Legacy `claude_code_cli` is accepted and upgraded to the full agent runtime.
API-key-only Anthropic rows keep the normal Messages API. To force the direct
Messages runtime for a Claude-sourced row, set `anthropic_runtime: native`.

To exclude implicit `~/.claude` discovery while retaining scoped rows:

```json
{
  "suppressed_sources": {
    "anthropic": ["claude_code"]
  }
}
```

## Verify

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

venv/bin/pytest -q \
  tests/agent/test_anthropic_keychain.py \
  tests/agent/test_anthropic_adapter.py \
  tests/agent/test_credential_pool.py \
  tests/hermes_cli/test_auth_commands.py

venv/bin/pytest -q \
  tests/gateway/test_session_env.py \
  tests/gateway/test_kanban_notifier.py \
  tests/gateway/test_internal_event_bypass_pairing.py \
  tests/tools/test_kanban_tools.py \
  tests/agent/transports/test_hermes_tools_mcp_server.py \
  tests/agent/transports/test_claude_code_session.py \
  tests/run_agent/test_claude_code_runtime.py

HERMES_HOME=~/.hermes/profiles/YOUR_PROFILE hermes auth list anthropic
```

Expected shape:

```text
anthropic (2 credentials):
  #1  claude-team      oauth  claude_code:xxxxxxxx
  #2  claude-personal  oauth  claude_code:yyyyyyyy
```

## Update Hermes, then reapply

If the updater refuses a dirty checkout, remove only this patch first:

```bash
cd ~/.hermes/hermes-agent
PATCH=~/Documents/claude/hermes-claude-config-dir-patch/patches/v0.18.2/hermes-claude-config-dir-multipool.patch

git apply --check --reverse "$PATCH"
git apply --reverse "$PATCH"
hermes update
git apply --3way "$PATCH"
```

Never use `git reset --hard` for this workflow: the Hermes checkout may contain
unrelated local work. If upstream adds equivalent support, test upstream and
retire the downstream patch.

## Test result

The two primary adapter/pool/runtime/MCP groups passed `697` tests on the
supported base. The credential-hydration group passed `337`; the focused
gateway/Kanban/runtime group passed `157`. Groups overlap. Coverage includes
real FastMCP schema dispatch, streaming, safe failover, interrupt, persistence,
complete multi-block delivery, exact originating-session wake, and the
no-double-execution boundary.

On 2026-07-15, an explicitly authorized profile passed a live end-to-end
canary. One expired OAuth directory returned 401, Hermes rotated to the next
directory, Claude Code executed Bash exactly once (`STREAM_CODE_OK`), streamed
tool progress, and returned `CANARY_OK`. No other profile made a live Anthropic
request.

The Kanban session-wake fix was validated without a live Anthropic request and
without modifying profile or board data.

## License

MIT. Hermes Agent is copyright Nous Research; see [LICENSE](LICENSE).

## Maintainer documentation

- [Implementation](docs/IMPLEMENTATION.md)
- [Maintenance runbook](docs/MAINTENANCE.md)
- [Testing](docs/TESTING.md)
