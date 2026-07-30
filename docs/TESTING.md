# Testing

## Turn-timeout fix

Measured on the production host before changing anything: `134` occurrences of
`Claude Code turn timed out after 900s` across `555` Kanban task logs, with
`108` cards hitting at least one — **19.5%**. Steady at 1–16 per day over
twelve days, so not a datable regression. One card (`t_6c2f6633`) took three
consecutive hits: 45 minutes burned, restarting from scratch each time. The
interactive gateway path is far milder — `14` of `1195` turns, 1.2% — because
Telegram turns are short; the damage concentrates in long agentic Kanban work.

Kanban card budgets in `kanban.db` cluster at 1800–3600s, so the turn wall was
2–4× lower than the runtime allowance the board hands the card.

The delivered symptom is worth recording because it is easy to misread in
logs: the error string is exactly 37 characters, so a timed-out turn appears as
`response ready: time=903.5s api_calls=1 response=37 chars` — a plausible-looking
short answer, not an obvious failure.

Seven regression tests cover the behaviour. An adversarial review of the first
draft (Codex, static analysis) raised nine findings; the four that survived
verification against the code are worth recording, because each was a real
defect the original tests could not have caught:

- Breaking out of the loop at the terminal `result` was unsafe. The Agent SDK
  models `result` as ending a *turn*, not necessarily the run, so frames can
  legitimately follow. Replaced with: stop enforcing deadlines after `result`,
  keep draining for a grace period.
- With that break, a `result` followed by a slow exit hit `proc.wait(timeout=5)`
  → `kill()` → nonzero return code → error, status 500. A delivered answer was
  converted into a failure. Now guarded by `not saw_result`.
- Salvage promoted text attached to `tool_calls`. Since
  `_compose_claude_delivery_text` explicitly treats that as an execution
  preamble, a cut turn could deliver "I'll delete the obsolete files now" as
  its outcome. Salvage now requires standalone prose.
- Appending the reason to `final_text` defeated the caller's transcript
  de-duplication, which compares for equality, writing the same prose twice.
  The marker moved to the caller's response composition.

The test fake was also wrong in a way that hid the second point: its `wait()`
returned 0 while the process was still alive, so the wait/kill path was never
exercised. It now raises `TimeoutExpired`, and models both real behaviours —
exiting after `result`, or lingering.

Two findings were verified as pre-existing rather than introduced here: a
blocking synchronous callback can stall both deadlines (the original single
deadline had the same exposure), and salvage can surface completed text that
newer in-flight deltas were superseding. Both are documented in
`docs/IMPLEMENTATION.md` rather than fixed.

Suite counts with the fix, v0.18.2 / v0.19.0:

| Group | v0.18.2 | v0.19.0 |
|---|---|---|
| adapter/pool/runtime/MCP | `139` + `575` | `147` + `589` |
| credential hydration | `342` | `348` |
| gateway/Kanban/runtime | `174` | `197` |

The seven timing-sensitive tests were run five times consecutively with no
flake. Margins are deliberately wide — a 0.2s stream gap against a 2s idle
budget — rather than tight enough to be scheduler-dependent.

Both patches also pass `git apply --check` forward on pristine checkouts of
their respective bases.

### Known flaky test on v0.19.0

`tests/run_agent/test_run_agent.py::TestRetryAfterCap::test_multi_pool_rotates_before_retry_after_sleep`
fails intermittently on the `v0.19.0` base — roughly one run in three to six.
It is upstream's test and upstream's code path: the same test passes 6/6 on
`v0.18.2` both with and without this patch, and fails on `v0.19.0` with the
previously committed patch too. Re-run before treating a v0.19.0 group-2
failure as a regression.

## v0.19.0 live validation, 2026-07-30

The local install was moved from `v0.18.2` to `v0.19.0` and the base is now
live-validated. Sequence, with the gateway stopped throughout:

1. Confirmed no Kanban card was `running` or `ready` before stopping anything.
2. Timestamped backup of every `auth.json` and `config.yaml` — 27 files.
3. Reversed the previously installed patch. The installer refused the new one
   (`patch cannot be reversed cleanly`), correctly: the checkout carried the
   older patch. The installed version was recovered from git history, verified
   to reverse cleanly, and removed with that file.
4. `hermes update`, then the base was moved to the manifest commit — see the
   trap below.
5. Installed the `v0.19.0` patch. `Overlapping: 0 file(s)`.
6. Verified the installed tree byte-for-byte against the clone that had passed
   the suites. The regenerated venv no longer carries `pytest`, and it was not
   added to a production install; file identity is the stronger check anyway.
7. Live turn on a throwaway profile seeded with two credential rows:

   ```
   $ hermes -p v19probe -z "Run the shell command: printf V19_OK…"
   I don't see the shell command output yet — let me run it.
   V19_OK                                                    (14s)
   ```

   Real turn through `acp://claude-code`, native Bash executed once, and the
   multi-block delivery path exercised. Profile deleted; the other fourteen
   were untouched.
8. Restarted the `cz-claude` gateway: Telegram connected, no traceback.

### Trap: `hermes update` does not stop on the release tag

It tracks upstream `main`. Here it landed on `8defb9fd`, which the installer
refused as an unsupported base — the fail-closed guard working. The gap is not
small: `3ef6bbd2..8defb9fd` is 4745 files and ~439k lines, and the patch does
not apply there. `git rev-list --count` reported `1`, which is wrong; the
Hermes checkout is a shallow clone, so its ancestry counts are meaningless.
Verify with `git diff --stat` between the two commits instead.

The fix is to check out the commit named in `patches/manifest.json` after
updating, before installing.

## v0.19.0 port result

Ported onto a throwaway clone of upstream `v2026.7.20` (`3ef6bbd2`); the local
install stayed on `v0.18.2` throughout. Same four groups, run with the
`v0.18.2` venv over `PYTHONPATH`:

| Group | v0.18.2 | v0.19.0 |
|---|---|---|
| adapter/pool/runtime/MCP | `132` + `575` | `140` + `589` |
| credential hydration | `342` | `348` |
| gateway/Kanban/runtime | `167` | `190` |

The higher counts are upstream's own added tests in the same files, not new
downstream ones. `git apply --check` also passes forward on a pristine
`v2026.7.20` checkout, which is the path the installer takes.

Of 25 patched files, 24 applied unchanged. Only
`agent/transports/hermes_tools_mcp_server.py` conflicted, 3 hunks of 11.

One reconciliation is worth recording because a test caught it. Upstream
independently solved the problem our `_apply_json_schema_signature()` existed
for, via `_signature_from_schema()` — better, since it maps JSON types to
Python types and sets annotations. Dropping our helper for theirs looks
correct and is half right: their signature governs how FastMCP *invokes* the
tool, while the schema FastMCP then derives from it is lossy — `minimum`,
enum members, and descriptions do not survive the round-trip through Python
annotations. `test_real_fastmcp_uses_authoritative_schema_and_normal_kwargs`
fails on exactly that. The port therefore keeps upstream's signature synthesis
*and* re-applies the post-registration `registered.parameters` override, which
governs what the client sees. Both, not either.

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

Current result: `132 passed, 0 failed` and `575 passed, 0 failed` (`707`
total) across these two groups.

Unset `CLAUDE_CONFIG_DIR` when running the credential-pool tests. Five tests in
`tests/agent/test_credential_pool.py` assert that the default row is selected
first and fail when the ambient shell exports a scoped directory, because the
pool then discovers `claude_code:<hash8>` instead. This is host leakage, not a
regression:

```bash
env -u CLAUDE_CONFIG_DIR venv/bin/pytest -q tests/agent/test_credential_pool.py
```

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

Current result: `167 passed, 0 failed`.

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
- rotation when a subscription cap arrives as a successful `exit 0` turn, and
  no rotation when an agent merely writes about its own quota;
- reset-time parsing for dated, time-only, and year-crossing cap notices, with
  a fallback to the pool cooldown on an unparsable or out-of-horizon reset;
- a capped turn reported as failed, not completed, when no spare credential
  remains;
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
