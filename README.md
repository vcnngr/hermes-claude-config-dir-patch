# Hermes multi-Claude Code auth patch

Small downstream patch adding multiple `CLAUDE_CONFIG_DIR` accounts to one
Hermes Anthropic credential pool and an opt-in official Claude Code CLI runtime.

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
- Inference through official `claude -p`, using the selected entry's directory.
- Automatic rotation to another configured directory on auth/rate-limit errors.

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
3f9c16faa06235afd8a87e62d01e0a1fd08912e4ed70b37321c62d15749009d8
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

Enable the official CLI adapter only in the selected profile's `config.yaml`:

```yaml
model:
  provider: anthropic
  anthropic_runtime: claude_code_cli
```

Without `anthropic_runtime`, Hermes keeps its normal direct Anthropic runtime.
With it, each turn runs through the official Claude Code CLI and the active
pool entry's `CLAUDE_CONFIG_DIR`.

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
  tests/agent/test_claude_code_cli_client.py \
  tests/agent/test_credential_pool_routing.py \
  tests/agent/test_credential_pool.py

venv/bin/pytest -q \
  tests/hermes_cli/test_runtime_provider_resolution.py \
  tests/run_agent/test_run_agent.py

venv/bin/pytest -q \
  tests/agent/test_anthropic_keychain.py \
  tests/agent/test_anthropic_adapter.py \
  tests/hermes_cli/test_auth_commands.py

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

`675` adapter/routing/runtime tests passed on the supported base. A live test
proved the new path end-to-end: the default Claude directory returned HTTP 401,
Hermes rotated automatically, and the next configured directory returned the
expected `OK` response through official `claude -p`.

Current adapter is deliberately small: response streaming is buffered until
the CLI turn completes, and Claude Code supplies its own tools rather than
Hermes forwarding tool schemas into the subprocess.

## License

MIT. Hermes Agent is copyright Nous Research; see [LICENSE](LICENSE).

## Maintainer documentation

- [Implementation](docs/IMPLEMENTATION.md)
- [Maintenance runbook](docs/MAINTENANCE.md)
- [Testing](docs/TESTING.md)
