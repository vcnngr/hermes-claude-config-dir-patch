# Maintainer instructions

- Supported bases: Hermes `v0.20.1 (2026.8.13)` commit `3d34b191`, `v0.19.0
  (2026.7.20)` commit `3ef6bbd2`, and `v0.18.2 (2026.7.7.2)` commit `226e8de8`.
- Keep the patch minimal and versioned under `patches/<version>/`.
- Never commit OAuth tokens, credential files, Keychain exports, fingerprints,
  real account labels, or absolute user paths.
- Test real credentials on one explicitly authorized Hermes profile only.
- Do not make live Anthropic requests without explicit authorization.
- Preserve unrelated checkout changes; never use `git reset --hard`.
- Before porting, check whether upstream already supports multiple
  `CLAUDE_CONFIG_DIR` values and the official Claude Code CLI runtime.
- After changes, update patch SHA-256, docs, automated results, and live-test
  status.

Read `docs/IMPLEMENTATION.md`, `docs/MAINTENANCE.md`, and `docs/TESTING.md`
before modifying the patch.
