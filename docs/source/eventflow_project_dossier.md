# EventFlow — Project Dossier for Codex

> **Purpose**: implementation-ready planning dossier for a backend-focused portfolio project.
> **Primary audience**: Codex / coding agent working inside the repository.
> **Status**: v0.1 — initial architecture baseline.
> **Project type**: full-stack SaaS-like platform, backend-heavy.
> **Core problem**: reliable asynchronous delivery of events/webhooks to external HTTP endpoints under failures, retries, duplicates, concurrency and rate limits.

---

## 0. Agent operating contract

The coding agent must treat this file as the project baseline.

### Rules

1. Do not change an architectural decision marked `DECIDED` without creating an ADR proposal first.
2. Prefer simple, observable, testable solutions over clever abstractions.
3. Do not introduce a dependency unless it solves a concrete requirement.
4. Do not add Kubernetes, Kafka, Terraform or cloud-specific infrastructure in the MVP unless a later milestone explicitly activates it.
5. Keep business logic independent from FastAPI transport details where practical.
6. Avoid repository-wide refactors unless required by the current task.
7. Every production-facing feature must include tests.
8. Every schema change must include an Alembic migration.
9. Every external call must have explicit timeout and error handling.
10. Never log secrets, API keys, webhook signing secrets or full authorization headers.
11. Background jobs must be idempotent or otherwise protected from duplicate execution.
12. Prefer explicit code over hidden framework magic.
13. If a requirement is ambiguous, preserve current behavior and document the ambiguity.
14. Keep this project portfolio-friendly: architecture, tradeoffs and reproducibility matter as much as features.

### Definition of done for a task

A task is done only when:

- implementation exists;
- tests exist and pass;
- lint/type checks pass where applicable;
- migration exists if persistence changed;
- API/OpenAPI contract remains coherent;
- error cases are handled;
- relevant documentation is updated;
- no secrets are committed.

---

# 1. Product definition

## 1.1 One-sentence description

EventFlow is a multi-tenant platform that accepts application events and reliably delivers them as signed HTTP webhooks to registered subscriber endpoints using asynchronous workers, retries, dead-letter handling and delivery observability.

## 1.2 Portfolio objective

This project is not primarily intended to showcase CRUD development. It must demonstrate:

- backend architecture;
- asynchronous processing;
- distributed-systems failure handling;
- idempotency;
- retry semantics;
- concurrency control;
- data modeling;
- API design;
- security;
- observability;
- performance measurement;
- testing strategy;
- deployment readiness;
- engineering tradeoff documentation.

## 1.3 Target user

A developer or small team that wants to:

1. create a project/workspace;
2. register one or more webhook endpoints;
3. publish application events to EventFlow;
4. let EventFlow deliver matching events to subscribers;
5. inspect delivery attempts;
6. replay failed events.

## 1.4 Core user story

Given a registered endpoint subscribed to `order.created`, when a producer sends an `order.created` event, EventFlow persists the event and asynchronously attempts delivery until it either succeeds or reaches terminal failure.

---

# 2. Scope

## 2.1 MVP scope — DECIDED

MVP includes:

- user authentication;
- organization/workspace ownership;
- API keys for producers;
- endpoint registration;
- event-type subscriptions;
- event ingestion API;
- durable event persistence;
- asynchronous webhook delivery;
- HMAC request signing;
- delivery attempt history;
- retry with exponential backoff + jitter;
- dead-letter state;
- manual replay;
- basic rate limiting;
- React admin dashboard;
- structured logging;
- metrics;
- Docker Compose local environment;
- CI pipeline;
- automated tests;
- architecture documentation;
- reproducible load test.

## 2.2 Explicit non-goals for MVP — DECIDED

Do not implement initially:

- arbitrary visual workflows;
- user-defined code execution;
- workflow DAGs;
- Kafka;
- Kubernetes;
- multi-region deployment;
- billing/payment integration;
- OAuth provider marketplace;
- GraphQL;
- WebSockets for all dashboard updates;
- exactly-once delivery guarantees;
- dynamic plugins;
- end-user scripting;
- AI features.

## 2.3 Later extensions — DEFERRED

Possible later work:

- transactional outbox for internal domain-event publication;
- partitioned delivery queues;
- endpoint-level concurrency limits;
- circuit breaker;
- adaptive backoff;
- schema registry;
- event payload validation;
- tenant plans/quotas;
- OpenTelemetry tracing;
- Prometheus + Grafana dashboards;
- Terraform;
- AWS ECS/RDS/ElastiCache deployment;
- S3 archival;
- Kafka comparison branch;
- multi-region architecture design document.

---

# 3. Architectural style

## 3.1 Baseline architecture — DECIDED

Use a modular monolith for the API plus separate background workers.

```text
React SPA
   |
   v
FastAPI API
   |
   +--> PostgreSQL
   |
   +--> Redis
           |
           v
       Celery workers
           |
           v
    External webhook endpoints
```

Rationale:

- simpler than microservices;
- still demonstrates async/distributed behavior;
- easier to run locally;
- easier to test;
- suitable for portfolio review;
- can later be decomposed if justified.

## 3.2 Service boundaries — DECIDED

Logical components:

- `api`: HTTP API for users, configuration and event ingestion;
- `worker`: asynchronous webhook delivery;
- `scheduler`: delayed retries / periodic maintenance if required;
- `frontend`: React dashboard;
- `postgres`: source of truth;
- `redis`: broker + rate limiting + ephemeral coordination.

Do not split into separately deployed domain microservices in MVP.

---

# 4. Technology baseline

## 4.1 Backend — DECIDED

- Python: 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x async style
- Alembic
- PostgreSQL 17
- Redis 8
- Celery
- HTTP client: `httpx`
- Authentication: JWT access tokens for dashboard users
- Password hashing: Argon2 via a maintained library
- Testing: pytest
- Async test support: pytest-asyncio or AnyIO-compatible approach
- Quality: Ruff
- Type checking: mypy
- Packaging/dependency management: Poetry

### SQLModel decision

Status: `OPEN`.

Preferred recommendation: use SQLAlchemy 2.x directly for EventFlow to demonstrate explicit persistence modeling and avoid coupling API schemas to ORM entities.

If SQLModel is chosen instead, document the reason in ADR-001 before implementation.

## 4.2 Frontend — DECIDED

- React
- TypeScript
- Vite
- React Router
- API client: generated or thin typed wrapper around `fetch`
- Query/cache layer: TanStack Query
- Styling: minimal; choose one lightweight approach and avoid UI-framework sprawl

## 4.3 Infrastructure — DECIDED for local MVP

Docker Compose services:

- `api`
- `worker`
- `postgres`
- `redis`
- `frontend` optional in compose depending on DX

Deferred:

- reverse proxy;
- TLS termination;
- cloud IaC.

## 4.4 CI — DECIDED

GitHub Actions pipeline should run:

1. install dependencies;
2. Ruff check;
3. mypy;
4. backend tests;
5. frontend lint/tests;
6. production build;
7. optional integration tests with service containers.

---

# 5. Repository structure

## 5.1 Monorepo — DECIDED

```text
eventflow/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps/
│   │   │   └── v1/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── tasks/
│   │   ├── security/
│   │   ├── observability/
│   │   └── main.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   ├── tests/
│   ├── package.json
│   └── Dockerfile
│
├── docs/
│   ├── architecture.md
│   ├── security.md
│   ├── testing.md
│   ├── performance.md
│   ├── api-conventions.md
│   └── adr/
│
├── infra/
│   ├── compose.yaml
│   └── env/
│
├── scripts/
├── .github/workflows/
├── .env.example
├── README.md
├── AGENTS.md
└── eventflow_project_dossier.md
```

## 5.2 Layering — DECIDED

Use pragmatic layering:

```text
API route
  -> service/use-case
      -> repository / infrastructure
          -> DB / Redis / external HTTP
```

Rules:

- routes should stay thin;
- business rules belong in services/use-cases;
- repositories own persistence queries;
- Celery tasks call application services where practical;
- Pydantic API schemas are not ORM models;
- avoid generic base-repository abstractions unless repetition clearly justifies them.

---

# 6. Core domain model

## 6.1 Entities — DECIDED baseline

### User

Fields:

- id: UUID
- email
- password_hash
- full_name optional
- is_active
- created_at
- updated_at

### Organization

Fields:

- id: UUID
- name
- slug
- created_at
- updated_at

### OrganizationMember

Fields:

- organization_id
- user_id
- role (`owner`, `admin`, `developer`, `viewer`)
- created_at

Composite uniqueness:

- `(organization_id, user_id)`

### ApiKey

Fields:

- id: UUID
- organization_id
- name
- key_prefix
- secret_hash
- last_used_at nullable
- revoked_at nullable
- created_at

Rules:

- raw secret shown only once at creation;
- only hash stored;
- prefix stored for identification.

### WebhookEndpoint

Fields:

- id: UUID
- organization_id
- name
- url
- signing_secret_encrypted or signing_secret protected by application secret strategy
- is_active
- timeout_seconds
- max_retries
- created_at
- updated_at

### Subscription

Fields:

- id: UUID
- endpoint_id
- event_type
- created_at

Uniqueness:

- `(endpoint_id, event_type)`

Initial wildcard support: `DEFERRED`.

### Event

Fields:

- id: UUID/ULID
- organization_id
- event_type
- payload JSONB
- idempotency_key nullable
- occurred_at optional
- created_at

Uniqueness option:

- `(organization_id, idempotency_key)` where idempotency_key is not null.

### Delivery

Represents one Event -> WebhookEndpoint delivery lifecycle.

Fields:

- id: UUID
- event_id
- endpoint_id
- status
- attempt_count
- next_attempt_at nullable
- delivered_at nullable
- failed_at nullable
- last_error_type nullable
- last_error_message nullable, sanitized
- created_at
- updated_at

Possible statuses:

- `pending`
- `processing`
- `retry_scheduled`
- `succeeded`
- `dead_lettered`
- `cancelled`

Unique constraint:

- `(event_id, endpoint_id)`

### DeliveryAttempt

Fields:

- id: UUID
- delivery_id
- attempt_number
- request_timestamp
- response_timestamp nullable
- response_status_code nullable
- duration_ms nullable
- error_type nullable
- error_message nullable, sanitized/truncated
- response_body_preview nullable, size limited and sanitized
- created_at

Rule:

- do not persist authorization headers or secrets;
- cap stored body preview.

---

# 7. Identifier strategy

Status: `DECIDED`.

Use UUID v4 initially for simplicity.

Potential later experiment:

- UUIDv7 or ULID for temporal locality and sortable event IDs.

Do not block MVP on identifier micro-optimization.

---

# 8. Multi-tenancy

## 8.1 Strategy — DECIDED

Shared database, shared schema, every tenant-scoped row includes `organization_id` directly or is reachable through a tenant-owned FK.

All tenant queries must be scoped explicitly.

No schema-per-tenant in MVP.

## 8.2 Security invariant

A user authenticated in organization A must never read or mutate resources belonging to organization B.

This must have integration tests.

---

# 9. Authentication and authorization

## 9.1 Dashboard authentication — DECIDED

Use email/password + JWT access token.

Refresh-token strategy: `OPEN`.

Recommendation for MVP:

- short-lived access token;
- refresh token stored securely in HttpOnly cookie;
- server-side token revocation strategy only if needed.

Alternative simpler MVP:

- access token only, short expiry, user signs in again.

Choose once before auth implementation and record in ADR.

## 9.2 Producer authentication — DECIDED

Event ingestion uses API keys.

Header example:

```http
Authorization: Bearer ef_live_xxxxx
```

API key rules:

- secret generated with CSPRNG;
- secret never stored in plaintext;
- prefix identifies the key;
- compare using constant-time operation where applicable;
- revocable;
- optional scopes later.

## 9.3 RBAC — DECIDED baseline

Roles:

- owner: full access, organization settings;
- admin: operational access, member/config management;
- developer: event/endpoints access;
- viewer: read-only.

Do not build a generic permission engine initially.

---

# 10. Event ingestion API

## 10.1 Endpoint — DECIDED

```http
POST /api/v1/events
```

Request:

```json
{
  "type": "order.created",
  "payload": {
    "order_id": "ord_123",
    "amount": 92.50
  },
  "occurred_at": "2026-09-30T15:10:00Z"
}
```

Optional header:

```http
Idempotency-Key: client-generated-key
```

Response baseline:

```http
202 Accepted
```

```json
{
  "id": "...",
  "status": "accepted"
}
```

## 10.2 Ingestion semantics — DECIDED

1. authenticate API key;
2. validate payload size and event type;
3. enforce rate limit;
4. persist Event;
5. discover active matching subscriptions;
6. create Delivery rows;
7. enqueue delivery jobs;
8. return 202.

Atomicity concern between DB commit and queue publish must be explicitly addressed.

### MVP approach — OPEN

Option A — direct publish after commit:

- simpler;
- leaves a failure window.

Option B — transactional outbox from the beginning:

- more robust;
- more complex;
- stronger portfolio value.

**Recommendation**: implement Option A for milestone 1, then intentionally migrate to transactional outbox in a dedicated milestone and document the failure mode + improvement.

This creates a clear engineering story.

---

# 11. Delivery semantics

## 11.1 Guarantee — DECIDED

EventFlow provides **at-least-once delivery attempts**, not exactly-once delivery.

Consequences:

- duplicates are possible;
- each delivery has stable identifiers;
- consumers should use event IDs for idempotency;
- documentation must state this clearly.

## 11.2 Webhook request — DECIDED

Example headers:

```http
Content-Type: application/json
User-Agent: EventFlow/1.0
X-EventFlow-Event-Id: <event_id>
X-EventFlow-Delivery-Id: <delivery_id>
X-EventFlow-Timestamp: <unix_timestamp>
X-EventFlow-Signature: v1=<hex_or_base64_signature>
```

Body:

```json
{
  "id": "event-id",
  "type": "order.created",
  "created_at": "...",
  "data": { ... }
}
```

---

# 12. Webhook signing

## 12.1 Algorithm — DECIDED

Use HMAC-SHA256.

Signing input:

```text
<timestamp>.<raw_request_body>
```

Signature format:

```text
v1=<signature>
```

Requirements:

- raw body bytes must be deterministic;
- document verification procedure;
- include timestamp to help consumers mitigate replay attacks;
- provide recommended tolerance window, e.g. 5 minutes;
- signing secret must not appear in logs.

Secret rotation: `DEFERRED`.

---

# 13. Retry policy

## 13.1 Retryable failures — DECIDED baseline

Retry:

- connection failure;
- DNS/network transient failure;
- timeout;
- HTTP 408;
- HTTP 425 optionally;
- HTTP 429;
- HTTP 500–599.

Do not retry by default:

- HTTP 2xx: success;
- HTTP 3xx: `OPEN` — recommendation: do not automatically follow redirects, treat as failure unless explicitly enabled;
- HTTP 400/401/403/404/410/422: terminal by default.

## 13.2 Redirect policy — DECIDED

Do not follow redirects automatically in MVP.

Reason:

- reduces SSRF/redirection abuse surface;
- preserves endpoint correctness;
- makes behavior explicit.

## 13.3 Backoff — DECIDED

Use exponential backoff with jitter.

Concept:

```text
base_delay * 2^(attempt-1) + jitter
```

Initial defaults:

- base delay: 2 seconds;
- max delay: 15 minutes;
- max attempts: 7;
- jitter: random bounded component.

These are configuration defaults, not hard-coded business constants.

## 13.4 `Retry-After` — DEFERRED/OPTIONAL

For HTTP 429/503, later support valid `Retry-After` values with an upper cap.

---

# 14. Dead-letter handling

## 14.1 Terminal state — DECIDED

After `max_attempts`, Delivery becomes `dead_lettered`.

Dashboard must allow:

- inspect failure reason;
- inspect attempts;
- manually replay.

## 14.2 Replay semantics — DECIDED

Replay does not mutate historical attempts.

Preferred model:

- same Delivery returns to pending and new DeliveryAttempt rows are appended;
- increment replay metadata or audit record.

Alternative of creating a new Delivery is possible, but baseline is same Delivery lifecycle for simpler UI.

Record manual replay in audit log later if implemented.

---

# 15. Concurrency and worker safety

## 15.1 Core risk

Celery is not an exactly-once execution system. A task may execute more than once.

## 15.2 Required invariant — DECIDED

Duplicate task execution must not create duplicate logical Delivery rows or corrupt attempt numbering/status.

## 15.3 Worker locking strategy — OPEN

Candidate approaches:

A. database row locking with `SELECT ... FOR UPDATE`;
B. optimistic locking/version column;
C. Redis distributed lock;
D. Celery-level controls only.

Recommendation:

- prefer PostgreSQL row-level locking for delivery state transitions;
- avoid Redis lock as primary correctness mechanism.

Document final choice in ADR.

## 15.4 Attempt numbering — DECIDED

Attempt number is derived transactionally from delivery state / existing attempts, not from Celery retry count alone.

---

# 16. Transactional outbox milestone

## 16.1 Problem to demonstrate

Naive sequence:

```text
COMMIT event + deliveries
CRASH
publish task never happens
```

## 16.2 Target solution

Add `outbox_messages` table written in the same PostgreSQL transaction.

Example fields:

- id
- topic/type
- aggregate_id
- payload JSONB
- created_at
- published_at nullable
- attempts
- last_error nullable

Publisher process:

1. select unpublished rows;
2. claim rows safely;
3. publish to Celery/Redis;
4. mark published;
5. retry publication failures.

Use `FOR UPDATE SKIP LOCKED` if multiple outbox publishers exist.

## 16.3 Portfolio requirement

Document:

- failure scenario before outbox;
- architecture after outbox;
- consistency tradeoff;
- remaining duplicate-delivery possibility.

---

# 17. HTTP client policy

## 17.1 Library — DECIDED

Use `httpx`.

## 17.2 Required configuration

Every outbound webhook request must have:

- connect timeout;
- read timeout;
- write timeout;
- pool timeout where applicable;
- maximum response size strategy;
- redirects disabled;
- explicit User-Agent.

## 17.3 Connection pooling — DECIDED

Reuse HTTP clients within worker process where safe rather than constructing a brand-new pool per request.

## 17.4 SSRF protection — REQUIRED DESIGN DECISION

Webhook systems create SSRF risk.

MVP must at minimum decide policy for blocking:

- localhost;
- loopback IP ranges;
- private RFC1918 networks;
- link-local addresses;
- cloud metadata endpoints;
- IPv6 local/private equivalents.

### Baseline recommendation

Before request:

1. only allow `https` in production; local dev may permit `http`;
2. resolve hostname;
3. reject private/local/link-local addresses;
4. protect against DNS rebinding as far as practical;
5. do not follow redirects.

This is security-critical and must have tests.

---

# 18. Rate limiting

## 18.1 Scope — DECIDED

Initial rate limit applies to event ingestion per organization/API key.

Redis-backed implementation.

## 18.2 Algorithm — OPEN

Options:

- fixed window;
- sliding window log;
- sliding window counter;
- token bucket.

Recommendation:

- start with fixed window for MVP simplicity;
- later implement token bucket as an engineering improvement if useful.

Return:

```http
429 Too Many Requests
```

Include rate-limit headers if implemented consistently.

---

# 19. Payload constraints

## 19.1 Event payload — DECIDED baseline

- JSON only;
- maximum body size configurable;
- initial max recommendation: 256 KB;
- max event type length defined;
- event type format restricted, e.g. lowercase dot notation.

Example regex concept:

```text
^[a-z0-9]+(?:[._-][a-z0-9]+)*$
```

Avoid storing arbitrarily large payloads in PostgreSQL for MVP.

---

# 20. Database decisions

## 20.1 PostgreSQL — DECIDED

PostgreSQL is the durable source of truth.

Redis must not be required to reconstruct core event/delivery state.

## 20.2 JSONB — DECIDED

Event payload stored as JSONB.

Do not create indexes inside arbitrary payload fields initially.

## 20.3 Time columns — DECIDED

Use timezone-aware UTC timestamps.

Naming convention:

- `created_at`
- `updated_at`
- `delivered_at`
- `failed_at`

## 20.4 Soft delete — DECIDED

Do not introduce generic soft-delete infrastructure.

Use explicit states (`revoked_at`, `is_active`) only where domain requires them.

## 20.5 Initial indexes — REQUIRED

At minimum consider:

- Event `(organization_id, created_at DESC)`;
- Delivery `(endpoint_id, created_at DESC)`;
- Delivery `(status, next_attempt_at)`;
- Delivery `(event_id)`;
- DeliveryAttempt `(delivery_id, attempt_number)`;
- Subscription `(event_type)` plus endpoint relation;
- ApiKey prefix lookup;
- tenant-scoped resource indexes.

Validate with `EXPLAIN ANALYZE` later.

---

# 21. API conventions

## 21.1 Versioning — DECIDED

Prefix public API with:

```text
/api/v1
```

## 21.2 Error format — DECIDED

Use one consistent application error envelope.

Example:

```json
{
  "error": {
    "code": "endpoint_not_found",
    "message": "Webhook endpoint was not found",
    "details": null,
    "request_id": "..."
  }
}
```

Do not expose stack traces.

## 21.3 Pagination — DECIDED

Use cursor pagination for event/delivery lists if practical.

If implementation complexity is excessive for MVP, offset pagination is acceptable initially, but document upgrade path.

Recommendation: cursor pagination for events/deliveries because they are naturally time-ordered.

## 21.4 Request IDs — DECIDED

Generate or accept a trusted request ID and include it in structured logs and responses.

---

# 22. Observability

## 22.1 Logging — DECIDED

Structured JSON logs in production.

Every log should include relevant context when available:

- timestamp;
- level;
- service;
- request_id;
- organization_id;
- event_id;
- delivery_id;
- task_id.

Never log:

- API-key secret;
- password;
- JWT;
- signing secret;
- full Authorization header.

## 22.2 Metrics — DECIDED baseline

Track at least:

- events accepted total;
- events rejected total;
- deliveries attempted total;
- delivery success total;
- delivery failure total by type/status;
- retries scheduled total;
- dead-letter total;
- request latency;
- webhook delivery latency;
- queue depth if accessible;
- worker task duration.

Prometheus instrumentation is recommended.

## 22.3 Tracing — DEFERRED milestone

Add OpenTelemetry after core async pipeline works.

Goal:

trace one event from ingestion -> DB -> queue -> worker -> outbound HTTP.

---

# 23. Health checks

## 23.1 API health endpoints — DECIDED

Expose:

- `/health/live`: process alive, no external dependencies;
- `/health/ready`: verifies required dependencies such as PostgreSQL and optionally Redis.

Keep checks lightweight.

---

# 24. Testing strategy

## 24.1 Test pyramid — DECIDED

### Unit tests

For:

- retry-policy calculations;
- signature generation/verification;
- permissions;
- payload validation;
- state-transition functions;
- rate-limiting policy wrappers.

### Integration tests

For:

- PostgreSQL repositories;
- tenant isolation;
- API-key auth;
- Alembic migration correctness;
- event ingestion transaction;
- worker state transitions;
- Redis-backed rate limiting.

### E2E tests

Spin up stack and test:

1. create user/org;
2. create API key;
3. register endpoint;
4. publish event;
5. fake webhook receiver responds;
6. assert delivery succeeds.

Second scenario:

- receiver fails N times then succeeds;
- verify retries and attempt history.

Third scenario:

- receiver always fails;
- verify dead-letter state;
- replay after receiver recovers.

## 24.2 External webhook test server — DECIDED

Create a small test-only receiver service or pytest fixture capable of:

- returning configurable status codes;
- delaying response;
- recording requests;
- failing first N requests;
- validating signatures.

This is essential for meaningful integration tests.

## 24.3 Test database strategy — OPEN

Preferred:

- Testcontainers for integration tests.

Alternative:

- Docker Compose test services.

Do not use SQLite to simulate PostgreSQL behavior for integration tests.

---

# 25. State machine

## 25.1 Delivery state transitions — DECIDED

Allowed conceptual transitions:

```text
pending -> processing
processing -> succeeded
processing -> retry_scheduled
processing -> dead_lettered
retry_scheduled -> processing
retry_scheduled -> cancelled
 dead_lettered -> pending   # manual replay
```

Transitions must be implemented centrally rather than scattered across route/task code.

Illegal transitions should fail loudly in tests.

---

# 26. Background task design

## 26.1 Celery broker — DECIDED

Redis initially.

## 26.2 Result backend — DECIDED

Do not use Celery result backend as the source of application state.

Application state lives in PostgreSQL.

Celery result storage can be disabled unless needed operationally.

## 26.3 Task arguments — DECIDED

Pass identifiers, not large payloads.

Good:

```text
deliver_webhook(delivery_id)
```

Avoid embedding entire event payload in broker messages where unnecessary.

## 26.4 Acknowledgement strategy — OPEN

Evaluate `acks_late` and worker-crash semantics before enabling.

Whichever configuration is chosen must align with idempotent/locked task execution.

---

# 27. Security baseline

Required controls:

- secure password hashing;
- API-key hashing;
- authorization per tenant;
- HMAC signing;
- SSRF mitigation;
- input/body-size limits;
- outbound request timeouts;
- secrets via environment/config provider;
- CORS explicitly configured;
- no debug mode in production;
- sanitized logs;
- dependency vulnerability scanning later;
- no credentials in repository.

Optional later controls:

- secret rotation;
- audit logs;
- endpoint allowlists;
- 2FA;
- API-key scopes;
- webhook mTLS.

---

# 28. Configuration strategy

## 28.1 DECIDED

Use `pydantic-settings`.

Environment variables are the deployment interface.

Group settings conceptually:

- app;
- database;
- redis;
- auth;
- celery;
- webhook delivery;
- rate limiting;
- observability.

Provide `.env.example` with safe placeholders.

Never commit real `.env` files.

---

# 29. Local developer experience

Required commands should be simple and documented.

Target examples:

```bash
make dev
make test
make lint
make typecheck
make migrate
make migration name="..."
make worker
make load-test
```

Status: Makefile/task runner choice `OPEN`.

Recommendation: use a small Makefile for memorable commands.

Codex should prefer repository commands over inventing new ad hoc command sequences.

---

# 30. Migration policy

- every DB model change requires migration;
- migrations must be reversible when practical;
- never edit an already-applied shared migration casually;
- CI should verify `alembic upgrade head` on a clean database;
- later add migration smoke test from previous release if project evolves.

---

# 31. Performance plan

## 31.1 Goals

Do not claim performance without measurements.

Create a reproducible benchmark.

## 31.2 Tool — DECIDED

Use k6 or Locust.

Recommendation: k6 for API load generation, Locust acceptable if Python-only tooling is preferred.

## 31.3 Benchmark scenarios

At minimum:

### Scenario A — ingestion throughput

- N concurrent producers;
- publish events to `/api/v1/events`;
- measure requests/sec and p50/p95/p99.

### Scenario B — delivery throughput

- receiver responds quickly 2xx;
- measure deliveries/sec and queue depth.

### Scenario C — failing receiver

- receiver returns 503;
- observe retry storm protection and queue behavior.

## 31.4 Performance document

`docs/performance.md` must include:

- hardware/environment;
- dataset;
- command used;
- concurrency;
- before/after changes;
- latency percentiles;
- throughput;
- bottleneck found;
- optimization applied;
- tradeoff.

---

# 32. Data retention

Status: `OPEN`.

MVP recommendation:

- keep events and attempts indefinitely in local/demo deployments;
- design tables so retention jobs can later delete/archive old attempts;
- do not implement archival until data volume warrants it.

Potential later policy:

- events: 30–90 days;
- attempts: 30 days;
- aggregate statistics longer.

---

# 33. Frontend scope

The frontend exists to expose backend engineering clearly.

Required screens:

1. sign in;
2. organization dashboard;
3. API keys;
4. webhook endpoints;
5. endpoint subscriptions;
6. events list;
7. event detail;
8. delivery detail;
9. failed/dead-letter deliveries;
10. replay action;
11. basic operational metrics.

Do not spend disproportionate effort on animations/design system.

Prefer clear tables, filters, badges and timeline views.

---

# 34. API resources

Initial endpoint groups:

```text
/auth
/users
/organizations
/members
/api-keys
/webhook-endpoints
/subscriptions
/events
/deliveries
```

Internal/admin endpoints should be clearly separated if added.

---

# 35. Event subscription matching

## 35.1 MVP — DECIDED

Exact event-type matching only.

Example:

```text
order.created == order.created
```

No wildcard initially.

## 35.2 Later

Potential:

```text
order.*
*
```

If added, define matching semantics precisely and benchmark query approach.

---

# 36. Auditability

MVP requires operational history through DeliveryAttempt.

General-purpose audit log: `DEFERRED`.

If later added, capture:

- API key created/revoked;
- endpoint created/changed/deleted;
- secret rotated;
- replay triggered;
- organization membership changes.

---

# 37. Failure taxonomy

Define canonical error types so UI/metrics do not depend on arbitrary exception strings.

Initial categories:

- `dns_error`
- `connection_error`
- `connect_timeout`
- `read_timeout`
- `tls_error`
- `http_4xx`
- `http_429`
- `http_5xx`
- `invalid_url`
- `blocked_destination`
- `response_too_large`
- `internal_error`

Store sanitized human-readable details separately.

---

# 38. Deletion behavior

## 38.1 Webhook endpoint deletion — DECIDED recommendation

Prefer deactivate/archive semantics if historical deliveries reference the endpoint.

Do not cascade-delete historical delivery evidence.

Possible approach:

- `is_active = false`;
- optional `deleted_at` later;
- retain historical endpoint display data.

## 38.2 Organization deletion — DEFERRED

Do not implement hard account deletion until retention semantics are explicitly defined.

---

# 39. HTTP response classification

Baseline:

| Result | Classification | Retry |
|---|---|---|
| 200–299 | success | no |
| 300–399 | failure | no |
| 400 | permanent client failure | no |
| 401/403 | auth/config failure | no |
| 404 | endpoint/config failure | no |
| 408 | transient | yes |
| 409 | default permanent | no |
| 410 | endpoint gone | no |
| 422 | permanent payload failure | no |
| 429 | throttled | yes |
| 500–599 | transient server failure | yes |
| network/timeout | transient | yes |

This table may evolve, but changes must be explicit and tested.

---

# 40. API idempotency

## 40.1 Ingestion idempotency — DECIDED

Support optional `Idempotency-Key`.

Behavior:

- key scoped to organization;
- repeated same key returns original accepted event;
- do not create duplicate Event or Delivery rows.

Payload mismatch for same key:

Status: `OPEN`.

Recommendation:

- store request fingerprint;
- if same key used with different payload/type, return `409 Conflict`.

---

# 41. Time and clock strategy

- use UTC everywhere in backend/database;
- serialize ISO 8601 with timezone;
- do not depend on local server timezone;
- retry calculations must use timezone-aware timestamps;
- tests involving time should use injectable clock/freezing library where helpful.

---

# 42. Secret storage

## 42.1 Local MVP

- app master secret via environment variable;
- webhook signing secrets may be encrypted at rest using application-level symmetric encryption.

Status: `OPEN` whether encryption-at-rest is implemented in MVP.

Recommendation:

- API keys: hash because they never need retrieval;
- webhook signing secrets: encrypt because platform needs plaintext to sign requests;
- document difference between hashing and encryption.

Future cloud:

- KMS/secrets manager envelope encryption.

---

# 43. Dependency policy

Before adding a library, ask:

1. Is this part of product requirements?
2. Does standard library/current stack already solve it sufficiently?
3. Is the library maintained?
4. Does it complicate async/thread/process behavior?
5. Can it be tested locally?

Keep dependency graph intentionally small.

---

# 44. Coding conventions

- type hints on application code;
- explicit return types for public functions;
- small functions around one responsibility;
- domain-specific names;
- no `utils.py` dumping ground;
- avoid hidden global state;
- inject infrastructure at boundaries;
- use enums for controlled status values;
- use constants/config for retry/timeout defaults;
- keep ORM sessions short-lived;
- never share SQLAlchemy sessions across tasks/threads.

---

# 45. Suggested backend package responsibilities

```text
app/core/
  config, application setup, shared exceptions

app/db/
  session, base, migration helpers

app/models/
  SQLAlchemy persistence models

app/schemas/
  API request/response schemas

app/repositories/
  persistence queries

app/services/
  application use-cases and domain rules

app/tasks/
  Celery tasks and task orchestration

app/security/
  passwords, JWT, API keys, webhook signing, SSRF checks

app/observability/
  logging, metrics, tracing

app/api/
  FastAPI routing/dependencies
```

---

# 46. Initial ADR backlog

Create short ADRs as decisions are finalized.

Suggested:

- ADR-001: SQLAlchemy vs SQLModel
- ADR-002: modular monolith architecture
- ADR-003: Redis + Celery for background processing
- ADR-004: at-least-once webhook delivery semantics
- ADR-005: PostgreSQL as durable source of truth
- ADR-006: ingestion idempotency strategy
- ADR-007: delivery concurrency control
- ADR-008: transactional outbox introduction
- ADR-009: SSRF protection strategy
- ADR-010: refresh-token/auth strategy
- ADR-011: rate-limiting algorithm
- ADR-012: webhook secret encryption approach

ADR template:

```md
# ADR-XXX: Title

## Status
Accepted / Proposed / Superseded

## Context

## Decision

## Alternatives considered

## Consequences

## Verification
```

---

# 47. Milestone plan

## Milestone 0 — Repository bootstrap

Goal: deterministic development environment.

Tasks:

- create monorepo structure;
- initialize Poetry backend;
- initialize Vite React TS frontend;
- configure Ruff;
- configure mypy;
- configure pytest;
- configure Alembic;
- Docker Compose PostgreSQL + Redis;
- settings management;
- health endpoints;
- CI skeleton;
- README bootstrap instructions.

Acceptance:

- fresh clone can start dependencies;
- API boots;
- frontend boots;
- DB migration runs;
- test/lint/type commands work.

## Milestone 1 — Identity and tenancy

Implement:

- User;
- Organization;
- membership;
- authentication;
- tenant authorization;
- API keys.

Acceptance:

- user cannot cross tenant boundary;
- API-key secret only visible at creation;
- revoked key cannot ingest events.

## Milestone 2 — Endpoint configuration

Implement:

- WebhookEndpoint CRUD;
- Subscription CRUD;
- webhook signing secret generation;
- URL validation;
- SSRF policy validation baseline.

Acceptance:

- endpoint can subscribe to exact event types;
- invalid/blocked URL rejected;
- secret handled safely.

## Milestone 3 — Event ingestion

Implement:

- `POST /events`;
- idempotency key;
- Event persistence;
- Delivery generation;
- enqueue tasks.

Acceptance:

- event creates expected deliveries;
- duplicate idempotency key does not duplicate deliveries;
- request returns 202.

## Milestone 4 — Delivery worker

Implement:

- HTTP delivery;
- HMAC signature;
- DeliveryAttempt persistence;
- success/failure classification;
- timeouts;
- state machine.

Acceptance:

- local test receiver confirms signed request;
- successful webhook creates successful delivery;
- failures are recorded without leaking secrets.

## Milestone 5 — Retries and dead letter

Implement:

- exponential backoff;
- jitter;
- retryable classification;
- dead-letter transition;
- manual replay.

Acceptance:

- flaky endpoint eventually succeeds;
- permanently failing endpoint dead-letters;
- replay works after recovery.

## Milestone 6 — Operational dashboard

Implement frontend screens for:

- endpoints;
- subscriptions;
- events;
- deliveries;
- attempts;
- failures;
- replay.

Acceptance:

- reviewer can understand event lifecycle without reading DB directly.

## Milestone 7 — Rate limiting and security hardening

Implement:

- Redis rate limit;
- body-size limits;
- stricter SSRF protection;
- CORS/security configuration;
- negative security tests.

## Milestone 8 — Transactional outbox

Refactor ingestion/task publication to use outbox.

Acceptance:

- DB event creation and outbox creation are atomic;
- publisher recovers unpublished messages;
- documentation compares before/after failure modes.

## Milestone 9 — Observability

Implement:

- structured logs;
- Prometheus metrics;
- correlation IDs;
- optional OpenTelemetry tracing.

Acceptance:

- one event can be followed operationally from API to webhook attempt.

## Milestone 10 — Performance engineering

Implement:

- load scripts;
- baseline benchmark;
- identify bottleneck;
- optimize one or more measurable issues;
- publish before/after metrics.

## Milestone 11 — Deployment

Deploy a public demo.

Recommended later stack:

- API/worker: AWS ECS/Fargate or equivalent;
- PostgreSQL: managed DB;
- Redis: managed Redis;
- frontend: static hosting/CDN;
- secrets: managed secret store;
- CI/CD: GitHub Actions.

Do not choose cloud provider before MVP unless deployment is imminent.

---

# 48. Suggested first backlog for Codex

The agent should implement one task at a time.

1. Initialize repository folders.
2. Create backend Poetry project.
3. Configure FastAPI application factory/startup.
4. Add pydantic-settings configuration.
5. Add PostgreSQL async connection/session.
6. Configure Alembic.
7. Add Redis connection settings.
8. Add Celery application bootstrap.
9. Add `/health/live`.
10. Add `/health/ready`.
11. Add Ruff configuration.
12. Add mypy configuration.
13. Add pytest configuration.
14. Add base integration-test database fixture.
15. Add Docker Compose PostgreSQL + Redis.
16. Add `.env.example`.
17. Add GitHub Actions backend pipeline.
18. Initialize React + TypeScript + Vite.
19. Add frontend lint/test/build CI.
20. Create initial ADR files marked Proposed.

Do not start domain features until milestone 0 is reproducible.

---

# 49. Acceptance scenarios for the final portfolio demo

## Scenario A — happy path

1. Create endpoint.
2. Subscribe to `order.created`.
3. Publish event.
4. Dashboard shows pending delivery.
5. Worker sends signed request.
6. Receiver responds 200.
7. Dashboard shows success + latency.

## Scenario B — transient failure

1. Receiver returns 503 twice.
2. EventFlow schedules retries.
3. Third attempt returns 200.
4. Dashboard shows complete attempt timeline.

## Scenario C — dead letter

1. Receiver always returns 503.
2. Delivery reaches max attempts.
3. Status becomes dead-lettered.
4. Receiver is fixed.
5. User clicks replay.
6. Delivery succeeds.

## Scenario D — duplicate ingestion

1. Publish event with idempotency key.
2. Repeat exact request.
3. Only one Event exists.
4. Only one logical Delivery per endpoint exists.

## Scenario E — security

1. Register blocked/private destination.
2. System rejects it.
3. Cross-tenant resource access returns forbidden/not found according to policy.
4. Logs contain no secrets.

## Scenario F — outbox recovery

1. Persist event/outbox message.
2. Simulate publisher interruption before queue publication confirmation.
3. Restart publisher.
4. Unpublished message is eventually published.

---

# 50. README requirements

Final README should lead with engineering value, not framework names.

Recommended sections:

1. What EventFlow solves
2. Architecture diagram
3. Reliability guarantees
4. Failure handling
5. Security model
6. Tech stack
7. Local quickstart
8. Demo walkthrough
9. Observability screenshots
10. Performance benchmark
11. Key ADRs
12. Testing strategy
13. Known limitations
14. Future improvements

Avoid generic claims such as “high performance” without evidence.

---

# 51. Key engineering questions to preserve during implementation

The project should explicitly answer these questions in code/docs:

1. What happens if PostgreSQL commits but queue publication fails?
2. What happens if Celery executes a task twice?
3. What happens if the consumer processed the webhook but EventFlow timed out?
4. How are retries classified?
5. How are retries delayed?
6. How is webhook authenticity verified?
7. How are replay attacks mitigated?
8. How is SSRF mitigated?
9. How is tenant isolation enforced?
10. How are API keys stored?
11. How are webhook secrets stored?
12. What state is durable vs ephemeral?
13. How is a failed delivery debugged?
14. How is queue growth observed?
15. What happens when ingress rate exceeds worker throughput?
16. What database queries become bottlenecks first?
17. How are schema migrations deployed safely?
18. How is performance measured reproducibly?
19. Which guarantees does the system explicitly not provide?
20. Which components could be scaled independently later?

---

# 52. Backpressure plan

MVP should observe, not over-engineer, backpressure.

Initial controls:

- ingestion rate limiting;
- bounded worker concurrency;
- metrics for queue depth;
- endpoint timeouts;
- retry delay to avoid hot loops.

Later experiments:

- priority queues;
- tenant fairness;
- endpoint concurrency caps;
- queue partitioning;
- load shedding;
- autoscaling policy.

Do not implement autoscaling before metrics exist.

---

# 53. Scaling assumptions

Initial deployment assumptions:

- single PostgreSQL primary;
- single Redis instance;
- multiple stateless API processes possible;
- multiple worker processes possible;
- one frontend deployment;
- all correctness anchored in PostgreSQL where feasible.

Horizontal worker scaling must not break delivery state correctness.

---

# 54. Possible later cloud architecture

Not part of MVP, but reserve this direction:

```text
Internet
  |
Load Balancer
  |
ECS/Fargate API
  |
  +----> RDS PostgreSQL
  |
  +----> ElastiCache Redis
             |
             v
        ECS/Fargate workers
             |
             v
       External endpoints
```

Static frontend may use object storage + CDN.

Terraform should be added only once deployment architecture is stable.

---

# 55. Known intentional limitations

Initial system may intentionally have:

- exact event-type matching only;
- one region;
- one PostgreSQL primary;
- Redis broker dependency;
- no guaranteed delivery ordering across endpoints;
- no exactly-once guarantee;
- limited payload size;
- no binary payloads;
- no arbitrary custom headers except controlled metadata;
- no per-event schema registry;
- no billing.

Document limitations openly.

---

# 56. Ordering semantics

Status: `DECIDED` for MVP.

No global ordering guarantee.

Potential endpoint ordering:

- not guaranteed in MVP when multiple workers process deliveries concurrently.

Document this clearly.

If strict ordering is explored later, it requires partitioning/serialization decisions and can reduce throughput.

---

# 57. Webhook endpoint configuration defaults

Suggested defaults:

- timeout: 10 seconds;
- max retries/attempts: 7 total attempts;
- active: true;
- redirects: disabled;
- signing enabled: yes.

All defaults must live in configuration/domain defaults, not scattered literals.

---

# 58. Error-handling principles

- expected domain errors map to stable API error codes;
- infrastructure exceptions are translated at boundaries;
- task exceptions update delivery state before retry where feasible;
- unexpected exceptions are logged with correlation IDs;
- user-facing errors never expose stack traces/internal DSNs;
- task retry logic must not hide terminal failure.

---

# 59. Documentation files to maintain

Required:

```text
README.md
AGENTS.md
docs/architecture.md
docs/api-conventions.md
docs/security.md
docs/testing.md
docs/performance.md
docs/adr/*.md
```

Optional later:

```text
docs/runbook.md
docs/threat-model.md
docs/deployment.md
docs/data-retention.md
```

---

# 60. AGENTS.md recommendation

Keep `AGENTS.md` short and operational.

It should point Codex to this dossier rather than duplicating it.

Suggested contents:

```md
# AGENTS.md

Read `eventflow_project_dossier.md` before changing architecture.

Before coding:
1. identify current milestone/task;
2. inspect relevant existing code/tests;
3. do not introduce new dependencies without justification;
4. preserve tenant isolation, idempotency and delivery-state invariants.

Before finishing:
1. run relevant tests;
2. run Ruff;
3. run mypy;
4. add migration if persistence changed;
5. update docs/ADR when architecture changed.

Prefer small, reviewable patches.
```

---

# 61. Open decisions that must be closed before or during early milestones

Codex must not silently choose these. Record decision in ADR or implementation note.

1. SQLAlchemy vs SQLModel.
2. JWT refresh-token strategy.
3. webhook signing-secret encryption implementation.
4. database test strategy: Testcontainers vs Compose.
5. rate-limiting algorithm.
6. worker concurrency-lock strategy.
7. Celery acknowledgement/retry configuration.
8. cursor vs offset pagination for initial lists.
9. exact SSRF hostname/IP verification strategy.
10. handling of reused idempotency key with different payload.
11. whether Prometheus ships in first public demo or observability milestone.
12. production hosting provider when deployment begins.

---

# 62. Recommended early technical decisions

To reduce startup ambiguity, the default recommendation is:

- SQLAlchemy 2.x, not SQLModel;
- async SQLAlchemy for API DB access;
- PostgreSQL 17;
- Redis 8;
- Celery workers;
- `httpx` outbound requests;
- UUID v4 initially;
- JWT access + refresh token in HttpOnly cookie;
- API-key secrets hashed;
- webhook signing secrets encrypted;
- exact event subscription matching;
- no redirect following;
- HTTPS-only production endpoints;
- PostgreSQL row locks for critical delivery transitions;
- fixed-window Redis rate limit first;
- Testcontainers for integration tests;
- Prometheus metrics before OpenTelemetry traces;
- transactional outbox introduced as a later deliberate refactor.

If no stronger reason exists, use these defaults.

---

# 63. Portfolio success criteria

The project is portfolio-ready when a reviewer can verify all of the following without trusting marketing language:

- the system runs from documented instructions;
- architecture diagram matches code;
- failed deliveries visibly retry;
- dead-letter and replay work;
- duplicate ingestion is controlled;
- outbound webhooks are signed;
- tenant isolation is tested;
- SSRF risk is addressed;
- queue/database failure modes are documented;
- transactional outbox has a rationale and tests;
- metrics/logs make failures diagnosable;
- benchmark is reproducible;
- CI is green;
- public demo or recorded demo exists;
- key tradeoffs are captured in ADRs.

---

# 64. Final implementation principle

The value of EventFlow is not the number of technologies used.

The value is the demonstrated reasoning around:

```text
correctness
reliability
failure recovery
security
observability
performance
maintainability
```

When choosing between adding a new technology and deepening one of these properties, prefer the second unless the technology is necessary to demonstrate the property.

