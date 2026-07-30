# Claude Code context

Read `AGENTS.md` first.

This repository maintains a downstream Hermes patch for:

- multiple Claude Code accounts, each scoped to one `CLAUDE_CONFIG_DIR`;
- automatic Hermes credential-pool rotation;
- streaming inference and native tool execution through official `claude -p`.

Supported state (the installer matches the checkout's exact `HEAD`):

- Hermes: `v0.19.0 (2026.7.20)`
- upstream: `3ef6bbd201263d354fd83ec55b3c306ded2eb72a`
- patch: `patches/v0.19.0/hermes-claude-config-dir-multipool.patch`
- SHA-256: `3bf6a0ee3df30b95c4c744bd9d831ba4b862fccbeff3d9e68b25666d9572d1dd`
- status: live-validated; this is what the local install currently runs

- Hermes: `v0.18.2 (2026.7.7.2)`
- upstream: `226e8de827a669e8ffa7035b27d70c19e44b1208`
- patch: `patches/v0.18.2/hermes-claude-config-dir-multipool.patch`
- SHA-256: `497d641040a2b72a7cdd93b8108012f2aab4c73fafa1b075c3d9c290baf8da9c`
- status: live-validated; superseded locally by v0.19.0, kept installable

`hermes update` tracks upstream `main`, not the release tag, so after updating
the checkout must be moved to the manifest commit before installing.

The patch also preserves durable gateway session identity across the external
runtime/MCP bridge so Kanban completions wake the exact originating session.

Security invariant: repository contains metadata examples only, never real
credentials or local account identifiers.
