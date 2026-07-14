# Hermes multi-Claude Code patch context

Read `AGENTS.md` first. This repository maintains a downstream patch, not a
fork of Hermes Agent.

Current supported base:

- Hermes `v0.18.2 (2026.7.7.2)`
- upstream `226e8de827a669e8ffa7035b27d70c19e44b1208`
- patch `patches/v0.18.2/hermes-claude-config-dir-multipool.patch`

Core invariant: every scoped pool entry maps to exactly one normalized config
directory, one Claude Code Keychain/file credential, and one stable source id.
Refresh and resync must use that same directory. Hermes `auth.json` stores only
metadata/fingerprint for these borrowed credentials.

macOS Keychain service algorithm:

```text
Claude Code-credentials-<sha256(absolute_config_dir)[:8]>
```

Compatibility:

- default `~/.claude` keeps pool source `claude_code`;
- non-default directories use `claude_code:<hash8>`;
- legacy unsuffixed Keychain fallback applies only to default `~/.claude`;
- input accepts `claude_config_dir` and `CLAUDE_CONFIG_DIR`;
- persisted field is always `claude_config_dir`.

Test profile: `codexauthtest` only. Use:

```bash
HERMES_HOME=~/.hermes/profiles/codexauthtest hermes auth list anthropic
```

Before changing behavior, read `docs/IMPLEMENTATION.md`,
`docs/MAINTENANCE.md`, and `docs/TESTING.md`.
