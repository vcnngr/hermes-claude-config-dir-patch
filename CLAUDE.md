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
- SHA-256: `dbfaa70206b762e37b5f1f23d1ae68947064d636abaea43f2a44bf24abee947f`
- status: full automated suite green; no live turn served yet

- Hermes: `v0.18.2 (2026.7.7.2)`
- upstream: `226e8de827a669e8ffa7035b27d70c19e44b1208`
- patch: `patches/v0.18.2/hermes-claude-config-dir-multipool.patch`
- SHA-256: `ef6cf75c9b214cd461f3cbac6e8230ed05651a3e237bd34bc689285d011fac1d`
- status: live-validated; this is what the local install currently runs

The patch also preserves durable gateway session identity across the external
runtime/MCP bridge so Kanban completions wake the exact originating session.

Security invariant: repository contains metadata examples only, never real
credentials or local account identifiers.
