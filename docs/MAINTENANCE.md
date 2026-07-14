# Maintenance runbook

## 1. Inspect new Hermes base

```bash
cd ~/.hermes/hermes-agent
git status --short
git branch --show-current
git rev-parse HEAD
venv/bin/hermes --version
```

Do not proceed over unrelated dirty files. Record the new base in `README.md`
and `CLAUDE.md`.

Search upstream for native support before carrying the patch forward:

```bash
rg -n "claude_config_dir|CLAUDE_CONFIG_DIR|Claude Code-credentials" agent tests website/docs
```

## 2. Remove old patch if required by updater

```bash
cd ~/.hermes/hermes-agent
OLD=~/Documents/claude/hermes-claude-config-dir-patch/patches/v0.18.2/hermes-claude-config-dir-multipool.patch
git apply --check --reverse "$OLD"
git apply --reverse "$OLD"
hermes update
```

This reverses only tracked hunks from this patch. Never use a hard reset.

## 3. Reapply or port

First attempt:

```bash
git apply --check "$OLD"
git apply --3way "$OLD"
```

If it conflicts, inspect new upstream behavior and reproduce only the required
hunks. Keep the invariants in `docs/IMPLEMENTATION.md`. Do not blindly accept
old code around changed authentication/security logic.

## 4. Test

Follow `docs/TESTING.md`. Test real local hydration only on `codexauthtest`.

## 5. Generate versioned patch

```bash
cd ~/.hermes/hermes-agent
VERSION=vX.Y.Z
OUT=~/Documents/claude/hermes-claude-config-dir-patch/patches/$VERSION
mkdir -p "$OUT"

git add -N agent/claude_code_cli_client.py tests/agent/test_claude_code_cli_client.py
git diff --binary --output="$OUT/hermes-claude-config-dir-multipool.patch" -- \
  agent/agent_init.py \
  agent/agent_runtime_helpers.py \
  agent/anthropic_adapter.py \
  agent/claude_code_cli_client.py \
  agent/credential_pool.py \
  agent/credential_sources.py \
  hermes_cli/runtime_provider.py \
  run_agent.py \
  tests/agent/test_anthropic_adapter.py \
  tests/agent/test_anthropic_keychain.py \
  tests/agent/test_claude_code_cli_client.py \
  tests/agent/test_credential_pool.py \
  tests/agent/test_credential_pool_routing.py \
  tests/hermes_cli/test_auth_commands.py \
  tests/run_agent/test_run_agent.py \
  website/docs/user-guide/features/credential-pools.md
git restore --staged agent/claude_code_cli_client.py tests/agent/test_claude_code_cli_client.py

git apply --check --reverse "$OUT/hermes-claude-config-dir-multipool.patch"
shasum -a 256 "$OUT/hermes-claude-config-dir-multipool.patch"
```

Update README version table, SHA, `CLAUDE.md`, and test result. Keep older
version directories so installed older Hermes copies remain recoverable.

## 6. Publish

```bash
cd ~/Documents/claude/hermes-claude-config-dir-patch
git status --short
git add AGENTS.md CLAUDE.md LICENSE README.md docs patches
git commit -m "Add Hermes <version> multi-Claude Code patch"
git push origin main
```

Verify the public raw patch URL and repository tree after push.
