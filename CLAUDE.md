# Claude Code context

Read `AGENTS.md` first.

This repository maintains a downstream Hermes patch for:

- multiple Claude Code accounts, each scoped to one `CLAUDE_CONFIG_DIR`;
- automatic Hermes credential-pool rotation;
- streaming inference and native tool execution through official `claude -p`.

Supported state:

- Hermes: `v0.18.2 (2026.7.7.2)`
- upstream: `226e8de827a669e8ffa7035b27d70c19e44b1208`
- patch: `patches/v0.18.2/hermes-claude-config-dir-multipool.patch`
- SHA-256: `aa521aadc059b9b023c71539ca9cd3d8289e1d1314eb47298a173bea1a77b90f`

The patch also preserves durable gateway session identity across the external
runtime/MCP bridge so Kanban completions wake the exact originating session.

Security invariant: repository contains metadata examples only, never real
credentials or local account identifiers.
