# Freshdesk Agent Connector

A small, read-only MCP integration that lets an Agent Studio-style AI agent retrieve
Freshdesk support-ticket information through three typed tools: `list_tickets`,
`get_ticket`, and `search_tickets`.

It uses Freshdesk API v2 with API-key authentication, bounded pagination, centralized
retries/rate-limit handling, normalized Pydantic models, and deterministic mock fixtures
so the whole thing is runnable and testable **without a Freshdesk account**.

## Requirements

- Python 3.12+ (the local dev environment provides Python 3.13).

## Install

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Keep `MOCK_MODE=true` in `.env` (the default) for the no-credentials demo. Never commit
`.env`.

## Run the mock demo

```bash
python examples/demo.py
```

This is the one-command offline demo described in the PRD:

1. Runs `search_tickets` with `tag:'payment-failure'`.
2. Runs `list_tickets` with `filter="new_and_my_open"` and a small page size to show
   pagination.
3. Runs `get_ticket` for `10001`.
4. Runs `get_ticket` for a missing ID to show a safe error.

Expected shape of each tool result is normalized JSON with ticket summaries and page
metadata. Live mode is opt-in and should only be run with a reviewer-owned test account
and non-production data.

## Live mode

Set a Freshdesk subdomain and API key in the environment and make sure the Freshdesk
identity can view tickets:

```bash
export FRESHDESK_DOMAIN=your-subdomain.freshdesk.com
export FRESHDESK_API_KEY=replace-with-a-test-only-api-key
python examples/demo.py
```

The live client targets only `https://{FRESHDESK_DOMAIN}/api/v2` and only these GET
endpoints:

| Operation | Freshdesk endpoint |
|---|---|
| List | `/tickets` |
| Get | `/tickets/{id}` |
| Search | `/search/tickets` |

## Run the tests

```bash
pytest
```

All tests are offline and use either the deterministic mock repository or mocked HTTP
responses.

## MCP usage

The server is a stdio MCP server. Once installed, the console script is:

```bash
freshdesk-mcp
```

With the MCP Python SDK, you can also point an MCP client at the package entry point.
The MCP layer:

- Registers exactly three read-only tools: `list_tickets`, `get_ticket`, `search_tickets`.
- Validates inputs with typed Pydantic schemas.
- Maps service errors to MCP tool errors with `isError=true` semantics.
- Emits no credentials.

See `TOOLS.md` for the canonical tool specs, and `CAPABILITIES.md`, `SECURITY.md`,
`ARCHITECTURE.md`, and `REQUIREMENTS.md` for the rest of the documented contract.

## Documentation

- `TOOLS.md` — canonical tool names, descriptions, input constraints, output shape,
  errors, examples, and limitations.
- `CAPABILITIES.md` — can/cannot boundary.
- `SECURITY.md` — operational security checklist.
- `ARCHITECTURE.md` — code-level architecture, module responsibilities, and data flow.
- `REQUIREMENTS.md` — requirement traceability from PRD to implementation/tests.

## Test coverage

- Configuration success and missing credentials, secret-safe errors.
- List success, empty, pagination, filters, and maximum bounds.
- Get success, missing ticket, invalid ID, and optional includes.
- Search matches, empty results, invalid/overlong query, and page cap.
- 429 with `Retry-After`, retry success, backoff fallback, and retry exhaustion.
- Timeout, connection error, malformed JSON, and upstream 500.
- No credentials in logs/errors/results.
- MCP tool discovery, valid schemas, invalid inputs, read-only annotations, and
  formatted results.
- End-to-end mock demo path from tool invocation to normalized response.
