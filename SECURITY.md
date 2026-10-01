# SECURITY.md — Freshdesk Agent Connector operational checklist

## Authentication and secrets

- Secrets come from environment variables only: `FRESHDESK_DOMAIN` and
  `FRESHDESK_API_KEY`.
- `.env` is gitignored and used only for developer convenience.
- `.env.example` contains placeholders only.
- The API key is never a tool argument, model output, exception string, or log field.
- Live requests use Freshdesk API v2 personal API-key Basic Auth:
  `Authorization: Basic base64(API_KEY:X)` over HTTPS.
- The domain is constrained to a Freshdesk hostname/subdomain format before any URL is
  built.
- The client never accepts an arbitrary URL or credential from a tool call.

## Input validation

- Every tool input is validated with Pydantic and `extra="forbid"`.
- Ticket IDs must be positive integers.
- Search queries are 1-512 chars and URL-encoded through the HTTP client.
- List filters, page, per_page, requester/company IDs, emails, and dates are bounded
  and allow-listed.
- `include` values for get tickets are restricted to `requester`, `company`, `stats`,
  and `conversations`.

## Read-only enforcement

- The server exposes only the three read-only tools with annotations
  `readOnlyHint=True, openWorldHint=False`.
- The connector never routes writes: there is no create/update/delete/reply endpoint.
- Ticket content is treated as untrusted data, not instructions.
- The connector cannot bypass Freshdesk visibility rules.

## Secrets handling

- API keys are never logged, returned, or interpolated into error text.
- Error messages use safe upstream descriptions or fixed safe strings.
- Logs never include API keys, Authorization headers, full query contents that may
  contain customer data, ticket descriptions, email addresses, or raw response bodies.

## Network and resource limits

- Timeouts are explicit per request.
- Retries are bounded for 429 and 5xx only; 400/401/403/404 are never retried.
- Local concurrency/spacing rate limiting avoids burst requests.
- Result caps: list per_page is at most 100 and connector `max_list_results` caps
  total; search page is at most 10.
- The live client uses the upstream `Link` header for pagination, never a
  caller-supplied URL.

## Error handling

- Errors are normalized into safe categories with agent-facing messages.
- Upstream payloads are sanitized via `safe_upstream_message` before exposure.
- Malformed JSON and malformed responses become safe upstream errors, not stack
  traces.

## Testing security properties

- Tests verify that no credentials or secrets appear in logs, errors, results, or MCP
  arguments.
- Tests verify bounded retries, rate limits, timeouts, and upstream error mapping.
- Tests verify MCP tool discovery, schemas, valid inputs, and read-only annotations.
- Tests run 100% offline using mocked HTTP or the deterministic mock repository.

## Operational checklist

- [ ] `.env` is ignored and not committed.
- [ ] `.env.example` contains only placeholders.
- [ ] `pyproject.toml` has no credentials or real customer data.
- [ ] Live mode requires `FRESHDESK_DOMAIN` and `FRESHDESK_API_KEY`.
- [ ] No tool accepts credentials, arbitrary URLs, or write methods.
- [ ] All ticket content is returned as normalized data only.
- [ ] Logs contain no auth headers, API keys, query bodies, descriptions, or email
      addresses.
- [ ] Error text never exposes auth failures, stack traces, or request/response bodies.
