# Testing

## Automated regression suite

Always use Hermes' test runner:

```bash
cd ~/.hermes/hermes-agent
scripts/run_tests.sh \
  tests/agent/test_anthropic_keychain.py \
  tests/agent/test_anthropic_adapter.py \
  tests/agent/test_credential_pool.py \
  tests/hermes_cli/test_auth_commands.py -q
```

Current base result: `337 passed, 0 failed` across the focused files.

Coverage includes:

- config-scoped Keychain service selection;
- legacy fallback only for default directory;
- explicit credential-file read/write directory;
- uppercase input alias normalization;
- two scoped accounts hydrated in one pool;
- no access/refresh token persistence in `auth.json`;
- scoped refresh/resync and removal matching;
- existing Anthropic/Nous credential-pool regressions.

## Real local hydration test

Use only `codexauthtest`:

```bash
HERMES_HOME=~/.hermes/profiles/codexauthtest hermes auth list anthropic
```

Expected: the default `claude_code` row plus one distinct
`claude_code:<hash8>` row for every configured alternative directory. Current
validation covered default plus three alternatives in one profile.

Safe assertions:

- distinct runtime credential values in memory;
- each persisted fingerprint matches the corresponding scoped Keychain item;
- no `access_token` or `refresh_token` keys in profile `auth.json`;
- only the `codexauthtest` profile changed.

For the 2026-07-14 live validation, the user explicitly authorized testing on
`cz-claude`. Four credentials hydrated; three completed minimal live
`claude-opus-4-8` requests. The default credential returned HTTP 429 and pool
rotation selected the next healthy scoped entry. Future tests return to
`codexauthtest` unless the user explicitly authorizes another profile.

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
