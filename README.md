# Hermes multi-Claude Code auth patch

Small downstream patch adding multiple `CLAUDE_CONFIG_DIR` accounts to one
Hermes Anthropic credential pool.

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
f24e9bb3b0d7e8266b25ad1c92924adff82e182c058dfb7783ace7f8935b9070
```

## Configure one Hermes profile

Add metadata-only rows to that profile's `auth.json`:

```json
{
  "credential_pool": {
    "anthropic": [
      {
        "id": "cc-work",
        "label": "claude-work",
        "auth_type": "oauth",
        "priority": 0,
        "source": "claude_code",
        "claude_config_dir": "~/.claude-work"
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
scripts/run_tests.sh \
  tests/agent/test_anthropic_keychain.py \
  tests/agent/test_anthropic_adapter.py \
  tests/agent/test_credential_pool.py \
  tests/hermes_cli/test_auth_commands.py -q

HERMES_HOME=~/.hermes/profiles/YOUR_PROFILE hermes auth list anthropic
```

Expected shape:

```text
anthropic (2 credentials):
  #1  claude-work      oauth  claude_code:xxxxxxxx
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

`337` focused Hermes tests passed on the supported base. A real four-account
profile check hydrated four distinct Claude Code credentials: three completed
live `claude-opus-4-8` requests, while one correctly returned HTTP 429 and the
pool selected the next healthy account.

## License

MIT. Hermes Agent is copyright Nous Research; see [LICENSE](LICENSE).

## Maintainer documentation

- [Implementation](docs/IMPLEMENTATION.md)
- [Maintenance runbook](docs/MAINTENANCE.md)
- [Testing](docs/TESTING.md)
