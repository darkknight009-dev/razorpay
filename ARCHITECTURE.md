# ARCHITECTURE.md — Freshdesk Agent Connector architecture

This document describes the code-level architecture, module responsibilities, and data
flow of the Freshdesk Agent Connector. Read PRD.md for the product-level requirements;
this file describes how the implementation matches them.

## High-level shape

```text
A[Agent / MCP Host]
  → B[MCP Server]
    → C[Typed Tool Schemas and Guardrails]
      → D[Connector Service]
        → E{Mode}
          → F[Deterministic Mock Repository]
          → G[Freshdesk API Client]
            → H[Config + Basic Auth]
            → I[Rate limiter + retry policy]
            → J[Timeout + error normalizer]
            → K[HTTPS Freshdesk API v2]
```

The connector is deliberately a short path: MCP tool call → typed input → service → a
single source → normalized model → MCP result.

## Module responsibilities

### `src/connector/__init__.py`

Package marker; exposes `__version__ = "0.1.0"`.

### `src/connector/config.py`

Environment-backed application configuration.

- Reads `MOCK_MODE`, `FRESHDESK_DOMAIN`, `FRESHDESK_API_KEY`, and operational bounds
  from environment variables.
- Loads `.env` only for developer convenience.
- Produces an immutable `Settings` dataclass.
- Validates live credentials and domain format; raises `ConfigurationError` with
  secret-free messages.
- Computes `base_url = https://{domain}/api/v2`.

### `src/connector/errors.py`

Safe, agent-facing errors.

- `ConnectorError` is the base with a `public_message()` suitable for an MCP tool
  result; it never includes secrets.
- Subclasses: `ConfigurationError`, `ValidationError`, `AuthenticationError`,
  `PermissionDeniedError`, `NotFoundError`, `BadRequestError`, `RateLimitError`,
  `NetworkError`, `UpstreamError`.
- `safe_upstream_message()` sanitizes Freshdesk error bodies into short descriptions.

### `src/connector/models.py`

Typed input, output, and domain models.

- Pydantic input schemas: `ListTicketsRequest`, `GetTicketRequest`,
  `SearchTicketsRequest`.
- Value objects: `Requester`, `Company`, `Ticket`, `PageInfo`, `TicketPage`,
  `SearchPage`.
- Enums and labels: `TicketInclude`, `STATUS_LABELS`, `PRIORITY_LABELS`.
- `normalize_ticket()` converts a Freshdesk-like dict into a stable model and never
  crashes on missing optional fields.

### `src/connector/source.py`

Shared ticket-source protocol.

- `TicketSource` is a Protocol with `list_tickets`, `get_ticket`, and `search_tickets`.
- `close_source()` dispatches `aclose()` when present.

### `src/connector/client.py`

The only class allowed to make live Freshdesk HTTP requests.

- Uses `httpx.AsyncClient` with an explicit timeout.
- Sends only `GET` requests to `/tickets`, `/tickets/{id}`, and `/search/tickets`.
- Uses Basic Auth (`API_KEY:X`) with `Accept: application/json`.
- Enforces timeouts, bounded retry/backoff, `Retry-After` honoring on 429, and
  rate-limit serialization through `RateLimiter`.
- Normalizes upstream errors into the `ConnectorError` hierarchy.
- Parses the `Link` header for `next_page` pagination.
- Never accepts caller-supplied URLs or arbitrary paths.

### `src/connector/rate_limit.py`

Small async client-side rate limiter.

- Serializes request starts and enforces `request_spacing_seconds`.
- `acquire()` is called before each live request.
- `wait(seconds)` is used for explicit retry delays.

### `src/connector/mock.py`

Deterministic fictional ticket source for demos and offline tests.

- `MOCK_TICKETS` holds synthetic records with IDs such as 10001 and fictional names.
- `MockTicketSource` implements `TicketSource` with list/get/search and pagination.
- Supports `email`, `requester_id`, `filter=new_and_my_open`, and documented query
  grammar for mock mode.
- Returns predictable not-found and invalid-input behavior.

### `src/connector/service.py`

Use-case boundary shared by MCP tools, mock mode, and live mode.

- `ConnectorService` enforces semantic validation and bounded limits on top of the
  source, then delegates to the source.
- `build_service()` selects `MockTicketSource` in mock mode or `FreshdeskClient` in
  live mode.

### `src/connector/mcp_server.py`

Protocol boundary.

- `create_server()` builds an `MCPServer` with the three tools.
- Each tool validates typed inputs, calls the service, and maps errors to
  `ToolError` with `isError=true`.
- `main()` and `__main__` run the stdio server.

## Data flow

1. MCP host discovers the three tools.
2. Agent sends a typed tool call.
3. MCP schema validation rejects malformed arguments before the service runs.
4. Connector service applies semantic validation and bounded limits.
5. The selected source executes a read-only list/get/search operation.
6. Live client sends an HTTPS GET with Basic Auth; mock mode reads in-memory fixtures.
7. Response is validated/normalized, pagination metadata is calculated, and sensitive
   fields are excluded.
8. The MCP layer returns structured JSON plus a concise text or safe tool error.
9. The agent summarizes only the returned information and must state when a result is
   partial, empty, stale, or unavailable.

## Mode selection

`build_service()` chooses the source:

- `MOCK_MODE=true` → `MockTicketSource()`.
- `MOCK_MODE=false` → `FreshdeskClient(settings)`, which requires live credentials and
  rejects use in mock mode.

## Security controls in code

- No global mutable credential state; credentials live in `Settings`.
- Live client only exports GET endpoints for tickets and search; no write verbs.
- Input schemas forbid extra fields (`extra="forbid"`).
- Tool annotations are hints; the service enforces read-only behavior in code.
- Error messages are sanitized; secrets and full query contents are never logged.
