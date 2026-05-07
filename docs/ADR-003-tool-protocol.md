# ADR-003 — Tool protocol

**Status:** Accepted (2026-05-08)
**Context:** Phase 7 — Tool Layer
**Companion:** `docs/AI_INTEGRATION_PLAN.md` §9

## Problem

Phase 7 turns every V2 capability into an agent-callable tool. The plan
lists two reasonable transports:

- **MCP** (Model Context Protocol) — Anthropic's native tool protocol;
  Claude clients (Claude Code, claude.ai, Claude Desktop) speak it
  directly with no shim.
- **HTTP / JSON-RPC** — generic, debuggable from `curl`, but every
  client (Claude included) needs a custom adapter.

This ADR records the decision and the boundary the codebase enforces:
the *transport* is replaceable; the *tool contract* is not.

## Decision

**MCP is the canonical transport.** A Python module
`tools/mcp_server.py` exposes every registered tool over MCP stdio.

The actual tool implementations live in `tools/handlers/*.py` as plain
typed Python functions. They have no MCP imports — they take typed
arguments, return Pydantic models, and raise `ToolError`. The MCP
server (and any future HTTP wrapper) is a thin adapter that converts
between the protocol's JSON envelopes and the handler signatures.

This means:

- Tests call handlers directly. No transport round-trip needed.
- A future HTTP server is ~50 lines, not a rewrite.
- Tool descriptions, schemas, and idempotency markers live with the
  handler, not with the transport.

## Consequences

- **Claude integration is one-step.** Configure the MCP server in
  `~/.claude/mcp.json`; no custom client code.
- **No transport in tests.** `test_tools_smoke.py` drives the entire
  scan→backtest→paper-trade flow by importing handlers, exactly as MCP
  would call them — but without the JSON serialisation overhead.
- **Schema drift is impossible.** The MCP server reads
  `Handler.input_model.model_json_schema()` at registration; there's
  one source of truth.
- **HTTP is on tap.** When/if a non-Claude client needs the tools, a
  FastAPI wrapper that mounts the same handlers is a single PR.

## What this rules out

- Building a hand-written JSON schema document. The Pydantic models
  emit it.
- Hiding tool docs in a separate file. Each handler's docstring is
  the description an agent reads — and `ToolDefinition.description`
  is sourced from that docstring.
- Treating tools as random Python functions. Every tool registers
  with `@tool(name=…, idempotent=True|False, …)` and goes through
  one `ToolResponse`-shaped envelope.

## Alternatives considered

- **HTTP first.** Rejected for now because the primary client is
  Claude; making Claude speak HTTP requires a custom MCP adapter
  inside Claude, which negates the simplicity argument.
- **Both at once.** Considered, but two transports double the surface
  for minor benefit at this phase. The handlers-are-pure design keeps
  HTTP one PR away when a second client appears.
