# MCP Test Harness — Design

**Status:** Approved (2026-04-23)  
**Context:** Greenfield repo; goal is a dedicated harness to validate **one** known MCP server (fixed command/paths in config), with optional **GPT-4.1** reporting. Primary focus is **option C**: test the MCP layer (tools, schemas, server behavior), not product QA or running arbitrary app test suites.

---

## 1. Goals and non-goals

**Goals**

- Start a **single** MCP server process from **local config** (command, args, cwd, optional env).
- Use an MCP **client** over **stdio** to exercise the protocol: `initialize` / `initialized`, `tools/list`, and optionally `resources/list`, `prompts/list` if enabled in config.
- Apply **deterministic** checks: required capabilities, non-empty tool list when expected, presence/shape of tool metadata (e.g. name, description, `inputSchema` when applicable).
- Optionally run **whitelisted** `tools/call` smoke tests using **fixtures** from config (avoid destructive or unknown calls).
- Optionally call **OpenAI** with model **`gpt-4.1`** (or a pinned API identifier such as `gpt-4.1-2025-04-14`) to produce a **human-readable summary** of results; pass/fail remains driven by harness logic, not the LLM.

**Non-goals (v1)**

- Multiple servers, SSE/HTTP remote transports, or dynamic discovery of servers.
- Property-based or fuzz testing of tools (possible future work).
- Replacing deterministic assertions with LLM judgment for pass/fail.

---

## 2. Architecture

| Piece | Responsibility |
|--------|----------------|
| **Config** | Declares how to spawn the server child process and optional fixture lists for smoke `tools/call`. |
| **Harness runtime** | Spawns child, connects MCP client over stdio, runs protocol steps and assertions. |
| **Reporter (optional)** | Sends a compact, structured summary to OpenAI for narrative output; failures if API missing should not flip MCP pass/fail semantics (exit code reflects MCP checks). |

**Stack:** TypeScript, Node.js LTS, `@modelcontextprotocol/sdk`, `openai` (official Node SDK). **Config format for v1:** **JSON** only (e.g. default `mcp-test.config.json` or path passed via CLI).

---

## 3. Configuration (contract)

Minimum fields (exact names can be finalized in implementation):

- `command`: executable (e.g. `node`, `npx`).
- `args`: array of strings.
- `cwd`: absolute or repo-relative path to the server project.
- `env`: optional map of extra env vars for the child only.
- `features`: flags such as `listResources`, `listPrompts` (default false if omitted).
- `smokeCalls`: optional list of `{ tool: string, arguments: object }` restricted to known-safe tools.
- `expect`: optional expectations (e.g. minimum tool count, required tool names).

Secrets: **`OPENAI_API_KEY`** read from the environment for the optional reporter; document in `.env.example`, never commit real keys.

---

## 4. Data flow

1. Load and validate config (fail fast on missing required fields).
2. Spawn server subprocess with given `command`, `args`, `cwd`, `env`.
3. Connect MCP client (stdio) → `initialize` → wait for `initialized`.
4. `tools/list` → run schema/metadata assertions.
5. If enabled: `resources/list`, `prompts/list` with appropriate assertions.
6. If `smokeCalls` present: for each entry, `tools/call` with fixture arguments; capture errors/timeouts.
7. Aggregate deterministic result (pass/fail + structured detail).
8. If OpenAI configured: send compact summary → optional narrative to stdout or file; if OpenAI fails, log warning and still exit with MCP-driven code.

---

## 5. Error handling and exit codes

- **Timeouts:** Server startup, each MCP request, and overall session bounded by configurable timeouts.
- **Child exit:** If the server process exits before completion, surface stderr tail and fail the run.
- **Protocol errors:** Map to failed assertions with clear messages.
- **Exit code:** Non-zero if any deterministic MCP check fails; zero only when all required checks pass. LLM step must not change this rule.

---

## 6. Testing the harness itself

- Unit tests for config parsing and assertion helpers (with mocked transport where practical).
- Integration test optional in CI: minimal fake MCP server or recorded fixtures if full subprocess is too heavy for default CI.

---

## 7. Open questions resolved in this spec

| Topic | Decision |
|--------|----------|
| “Testing” meaning | MCP protocol and tool surface for one fixed server (option **C**). |
| Targeting | Single known project via fixed config paths/commands (option **A**). |
| Language | TypeScript + official MCP SDK + OpenAI Node SDK. |
| LLM role | Reporting/summary only; deterministic checks define success. |

---

## 8. Next step

Implementation follows **`writing-plans`**: produce `docs/superpowers/plans/2026-04-23-mcp-test-harness.md` with bite-sized tasks after this spec is reviewed.
