# Claude Code context

Read `AGENTS.md` first.

This repository maintains a downstream Hermes patch for:

- multiple Claude Code accounts, each scoped to one `CLAUDE_CONFIG_DIR`;
- automatic Hermes credential-pool rotation;
- opt-in inference through the official `claude -p` CLI.

Supported state:

- Hermes: `v0.18.2 (2026.7.7.2)`
- upstream: `226e8de827a669e8ffa7035b27d70c19e44b1208`
- patch: `patches/v0.18.2/hermes-claude-config-dir-multipool.patch`
- SHA-256: `3f9c16faa06235afd8a87e62d01e0a1fd08912e4ed70b37321c62d15749009d8`

Security invariant: repository contains metadata examples only, never real
credentials or local account identifiers.
