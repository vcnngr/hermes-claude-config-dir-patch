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
cd /path/to/hermes-claude-config-dir-patch
python3 scripts/hermes_patch.py remove --dry-run
python3 scripts/hermes_patch.py remove
hermes update
```

This reverses only tracked hunks from this patch. Never use a hard reset.

## 3. Reapply or port

After checking for equivalent upstream support, add the new base and patch to
`patches/manifest.json`. Then use the manager for the first attempt:

```bash
python3 scripts/hermes_patch.py install --dry-run
python3 scripts/hermes_patch.py install
```

If it conflicts, inspect new upstream behavior and reproduce only the required
hunks. Keep the invariants in `docs/IMPLEMENTATION.md`. Do not blindly accept
old code around changed authentication/security logic.

## 4. Test

Follow `docs/TESTING.md`. Test real credentials on one explicitly authorized
profile only.

## 5. Generate versioned patch

```bash
cd ~/.hermes/hermes-agent
VERSION=vX.Y.Z
OUT=~/Documents/claude/hermes-claude-config-dir-patch/patches/$VERSION
mkdir -p "$OUT"

git add -N \
  agent/claude_runtime.py \
  agent/transports/claude_code_session.py \
  tests/agent/transports/test_claude_code_session.py \
  tests/run_agent/test_claude_code_runtime.py
git diff --binary --output="$OUT/hermes-claude-config-dir-multipool.patch" -- \
  agent/agent_init.py \
  agent/agent_runtime_helpers.py \
  agent/anthropic_adapter.py \
  agent/claude_runtime.py \
  agent/conversation_loop.py \
  agent/credential_pool.py \
  agent/credential_sources.py \
  agent/transports/claude_code_session.py \
  agent/transports/hermes_tools_mcp_server.py \
  gateway/kanban_watchers.py \
  gateway/run.py \
  hermes_cli/runtime_provider.py \
  run_agent.py \
  tests/agent/test_anthropic_adapter.py \
  tests/agent/test_anthropic_keychain.py \
  tests/agent/test_credential_pool.py \
  tests/agent/test_credential_pool_routing.py \
  tests/agent/transports/test_claude_code_session.py \
  tests/agent/transports/test_hermes_tools_mcp_server.py \
  tests/gateway/test_kanban_notifier.py \
  tests/gateway/test_session_env.py \
  tests/hermes_cli/test_auth_commands.py \
  tests/run_agent/test_claude_code_runtime.py \
  tests/run_agent/test_run_agent.py \
  website/docs/user-guide/features/credential-pools.md
git restore --staged \
  agent/claude_runtime.py \
  agent/transports/claude_code_session.py \
  tests/agent/transports/test_claude_code_session.py \
  tests/run_agent/test_claude_code_runtime.py

git apply --check --reverse "$OUT/hermes-claude-config-dir-multipool.patch"
shasum -a 256 "$OUT/hermes-claude-config-dir-multipool.patch"
```

Update `patches/manifest.json`, README version table and SHA, `CLAUDE.md`, and
test result. Keep older version directories so installed older Hermes copies
remain recoverable. Verify every manifest SHA against its versioned patch.

## 6. Publish

```bash
cd ~/Documents/claude/hermes-claude-config-dir-patch
git status --short
git add AGENTS.md CLAUDE.md LICENSE README.md docs patches scripts tests
git commit -m "Add Hermes <version> multi-Claude Code patch"
git push -u origin HEAD
```

Open a pull request, verify checks and diff, then merge. Verify the public raw
patch URL and repository tree after merge.
