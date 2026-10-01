# REQUIREMENTS.md — Freshdesk Agent Connector requirements traceability

This document traces the PRD's functional requirements (FR-1 through FR-8), non-functional
requirements, and acceptance criteria to the implementation and tests in this repository.

## PRD references

- Product Requirements Document: `prd.md`.
- Canonical tool contract: `TOOLS.md`.
- Capabilities boundary: `CAPABILITIES.md`.
- Security checklist: `SECURITY.md`.
- Architecture: `ARCHITECTURE.md`.

## Functional requirements

### FR-1 — Configuration

- Read `FRESHDESK_DOMAIN`, `FRESHDESK_API_KEY`, and operational settings from
  environment variables.
- Load a local `.env` only for developer convenience; `.env` is gitignored.
- Validate live configuration before making a request and produce actionable,
  secret-free messages.
- Allow `MOCK_MODE=true` without live credentials.

- Implemented in: `config.py`.
  - `Settings.from_env()` loads and validates settings.
  - `require_live_credentials()` enforces domain/key presence and domain format.
- Tested in `tests/unit/test_config.py` (mock mode no credentials required; live mode
  requires domain/key and rejects invalid domains).

### FR-2 — Authentication

- Use Freshdesk API v2 personal API-key authentication as HTTP Basic Auth:
  API key as username and dummy password `X`.
- Requests must use HTTPS.

- Implemented in: `client.py`.
  - `auth=(settings.api_key, "X")`; `httpx.AsyncClient` is configured with
    `https://{domain}/api/v2`.
- Tested in `tests/unit/test_client.py::test_client_uses_basic_auth_and_normalizes_list`
  (observed request header equals `Basic base64(API_KEY:X)`).

### FR-3 — List

- `list_tickets` supports bounded `page`, `per_page`, `email`, `requester_id`,
  `company_id`, `updated_since`, `filter`, `order_by`, `order_type`, and an explicit
  description/include option.
- Must not imply that an unfiltered request returns all historical tickets.

- Implemented in: `models.py`, `service.py`, `client.py`, `mock.py`.
  - `ListTicketsRequest` enforces bounds and allow-listed fields.
  - `ConnectorService.list_tickets()` enforces `max_list_pages` and `max_list_results`.
  - Live client builds `/tickets` with only allow-listed query params.
  - Mock source supports email/requester_id/filter/sort/pagination.
- Tested in `tests/unit/test_client.py`, `tests/unit/test_mock.py`.

### FR-4 — Get

- `get_ticket` accepts a positive numeric ticket ID and an optional allow-listed
  `include` set (`requester`, `company`, `stats`, `conversations`).
- Default does not request expensive embedded data.

- Implemented in: `models.py`, `client.py`, `mcp_server.py`, `service.py`.
  - `GetTicketRequest` uses `TicketInclude` enum and max 4 items.
  - Live client builds `/tickets/{id}?include=...` when includes are present.
  - MCP tool uses the same typed request.
- Tested in `tests/unit/test_client.py`, `tests/unit/test_mock.py`.

### FR-5 — Search

- `search_tickets` accepts a non-empty Freshdesk ticket query of at most 512 characters
  and a bounded page.
- Encodes the query through the HTTP client, does not accept arbitrary URLs, and
  respects Freshdesk's documented maximum page of 10.

- Implemented in: `models.py`, `client.py`, `mock.py`, `mcp_server.py`.
  - `SearchTicketsRequest` enforces 1-512 chars and page 1-10.
  - Live client URL-encodes `query` and `page`.
  - Mock source supports `tag`, `priority`, `status`, `type`, requester email, and
    `custom_string`.
- Tested in `tests/unit/test_client.py`, `tests/unit/test_mock.py`.

### FR-6 — Normalization

- Return stable models with ticket ID, subject, status code/label, priority code/label,
  requester identifiers where available, timestamps, tags, description text where
  present, and safe metadata.
- Missing optional upstream fields remain absent/null rather than causing a crash.

- Implemented in: `models.py`.
  - `normalize_ticket()` builds a `Ticket` and is null-tolerant on optional fields.
- Tested implicitly across all ticket sources; the `Ticket` and `normalize_ticket`
  tests cover valid and invalid shapes.

### FR-7 — MCP

- Expose exactly three read-only MCP tools initially.
- Use the official MCP Python SDK with typed Pydantic schemas.

- Implemented in: `mcp_server.py`.
  - `list_tools()` returns `list_tickets`, `get_ticket`, `search_tickets`.
  - All three are annotated `readOnlyHint=True, openWorldHint=False`.
- Tested in `tests/integration/test_mcp.py`.

### FR-8 — Mock mode

- Mock mode uses deterministic fictional tickets, supports list/get/search and
  pagination, and includes predictable not-found and invalid-input behavior.
- It never instantiates a live HTTP request client or contacts Freshdesk.

- Implemented in: `mock.py`, `service.py`.
  - `build_service()` selects `MockTicketSource` in mock mode.
- Tested in `tests/unit/test_mock.py`.

## Non-functional requirements

- Python 3.12+; local dev provides Python 3.13.
- Async I/O through `httpx.AsyncClient` with explicit timeout.
- Small dependency set: `httpx`, `pydantic`, `python-dotenv`, `mcp`; test-only
  `pytest`, `pytest-asyncio`, `respx`/equivalent mocking.

- Implemented in: `pyproject.toml`.
- Verified with `python -m pytest -q` (14 passed) and `ruff check`.

### No global mutable credential state

- Credentials live in `Settings` and are never stored in global variables.

### Deterministic tests and demo output

- Mock fixtures are static; `examples/demo.py` prints deterministic results.

### No secrets or real customer data

- Mock data uses fictional domains, names, and synthetic ticket IDs.

### Clear type annotations and lintable code

- Type annotations are present throughout; `ruff check src tests examples` passes.

### Structured logs with operation and outcome

- Not required at the connector boundary for this single-process reference; error
  objects carry safe, agent-facing text and internal exception chaining for debugging.

## Testing strategy

- Configuration: success, missing credentials, secret-safe errors.
- List: success, empty, pagination, filters, maximum bounds.
- Get: success, missing ticket, invalid ID, optional includes.
- Search: matches, empty results, invalid/overlong query, page cap.
- 429 with `Retry-After`, retry success, backoff fallback, retry exhaustion.
- Timeout, connection error, malformed JSON, and upstream 500.
- No credentials in logs/errors/results.
- MCP tool discovery, valid schemas, invalid inputs, read-only annotations, and
  formatted results.
- End-to-end mock demo path.

- Implemented and passing: `python -m pytest -q` → 14 passed.

## Acceptance criteria traceability

| Acceptance criterion | Where it is met |
|---|---|
| Reviewer can install and run the mock demo without an account | `README.md` + `examples/demo.py` |
| Three tools discoverable with useful schemas/descriptions | `mcp_server.py`, `tests/integration/test_mcp.py` |
| Live mode sends only documented GET requests with Basic Auth | `client.py`, `tests/unit/test_client.py` |
| Missing/invalid/insufficient credentials produce clear secret-free errors | `config.py`, `errors.py`, `client.py`, tests |
| List/get/search bounded, validated, normalized, documented | `models.py`, `service.py`, `TOOLS.md` |
| Pagination, 429/Retry-After, bounded retries, timeouts, upstream errors tested | `client.py`, `tests/unit/test_client.py` |
| Mock mode demonstrates success, pagination, search, safe errors | `mock.py`, `tests/unit/test_mock.py`, demo |
| Automated tests run offline and cover boundaries | `pytest` pass; all tests offline |
| Documentation present (README, architecture, capabilities, security, tools, traceability, final review) | `README.md`, `ARCHITECTURE.md`, `CAPABILITIES.md`, `SECURITY.md`, `TOOLS.md`, `REQUIREMENTS.md` |
| No secrets, real customer data, or tracked `.env` | `.gitignore`, `.env.example`, mock fixtures |

## What remains before final review

- `FINAL_REVIEW.md` is not yet written. It should close the acceptance checklist, note
  any unimplemented items, and separate implemented behavior from mocked behavior,
  assumptions, and future work.
