# Production operations

Phase 25 keeps StudentSuccessful as one modular application with four independent processes: the Next.js frontend, FastAPI backend, collector, and alert worker. PostgreSQL and resume storage are external durable services. No hosting provider is configured in this repository, so this guide defines the production contract without claiming a live deployment.

## Deployment shape

Use `docker-compose.production.yml` with managed PostgreSQL and private S3-compatible storage. The frontend is bound to loopback; a managed HTTPS ingress or reverse proxy publishes the configured frontend origin. The backend is never published directly.

Release in this order:

1. Build the backend and frontend from their locked dependency inputs.
2. Run the one-off `migrate` service until `alembic upgrade head` succeeds.
3. Start backend, collector, alert worker, and frontend.
4. Monitor `/health/ready` for the API and `/health/workers` for the independent workers.

The API never runs Alembic during startup, so web instances cannot race migrations. Collector and alert-worker deployment overlap is protected by a database lease; existing source-level leases still protect individual polls.

## Configuration and secrets

Use [production.env.example](../deploy/production.env.example) only as a placeholder reference. Put populated values in the platform secret store; do not create or commit a populated file.

| Category | Values |
| --- | --- |
| Public | `FRONTEND_ORIGIN`, one exact HTTPS browser origin. |
| Private | `DATABASE_URL`, optional `DATABASE_MIGRATION_URL`, S3 credentials, and any platform workload identity. |
| Source configuration | `LIVE_JOB_SOURCES_JSON` and bounded polling settings. Public board identifiers need no credentials but require review before activation. |

Production validation rejects HTTP origins, insecure session cookies, SQLite, debug mode, a non-`__Host-ss_session` cookie name, local resume storage, and invalid managed-storage settings. `ALLOW_EPHEMERAL_LOCAL_STORAGE=true` is the sole storage exception: it permits `STORAGE_BACKEND=local` for a demo or staging deployment while leaving all other production checks in force. `DATABASE_URL` is the pooled application connection; the one-off migration job uses `DATABASE_MIGRATION_URL` when supplied and otherwise falls back to `DATABASE_URL`. Each process defaults to a conservative database pool of five connections plus at most five overflow connections.

The browser-facing frontend and API are same-origin through Next.js rewrites. Browser sessions retain host-only `Secure`, `HttpOnly`, and `SameSite=Lax` cookie behavior. Credentialed CORS and registration/login Origin checks allow only the configured frontend origin.

## Resume storage

Production requires the `s3` adapter by default. It stores opaque server-generated keys below the configured prefix, requests AES-256 server-side encryption on writes, and never returns direct public object URLs. The bucket must block public access. Grant the deployed identity only bucket-head/list and prefix-scoped object get/put/delete permission. Enable bucket versioning and provider-managed encryption where available.

For a Render demo or staging deployment only, set `STORAGE_BACKEND=local` and `ALLOW_EPHEMERAL_LOCAL_STORAGE=true`. Render's local filesystem is ephemeral, so uploaded resumes can disappear after a restart or redeploy. Do not use this exception for durable production resume uploads.

## Backups and restore

Before production traffic, enable the PostgreSQL provider's automated backup and point-in-time recovery with at least seven days of retention, or the provider's stronger default. Record the retention and restore window in the platform change record.

Restore first into an isolated database. Run `alembic current --check-heads`, verify a test account's application history and resume metadata, then schedule any production recovery. Do not restore over a live database as a smoke test. Resume objects are durable private data too; configure bucket versioning and object recovery alongside the database backup plan.

## Workers, health, and recovery

Both workers renew a durable lease and heartbeat before and after each cycle. `/health/live` covers only the API process. `/health/ready` checks PostgreSQL and storage. `/health/workers` exposes only aggregate `healthy`, `stale`, `stopped`, or `not_started` state without source URLs, tokens, or database details.

On graceful termination a worker releases its lease. After a crash, the lease expires and a replacement or standby process can take ownership. The collector retains its existing idempotent ingestion, per-source leases, retry, and backoff. Alert reconciliation and delivery state remain durable, so restart resumes pending work without fabricating duplicate alerts.

For a staging restart check, restart only the collector or alert worker, wait for `/health/workers` to become healthy, then verify that source or alert state advances without duplicate canonical jobs or events.

## Logging and metrics

Application logs are compact JSON. API completion records include request ID, method, path, status, and duration. Worker records include event, worker name, duration, and aggregate result counts. Request bodies, cookies, passwords, CSRF values, resume contents, notes, and source payloads are not structured log fields.

`X-Request-ID` allows platform logs to correlate browser/API requests. Durable live-source rows retain success, failure, timing, freshness, observed-job, duplicate, and official-Apply totals. Alert delivery state plus log-derived latency and error metrics provide the Phase 26 inputs. Use deployment-platform health alerts and log-derived metrics rather than adding a second metrics stack.

Monitor `/health/ready`, `/health/workers`, repeated collector cycle failures, and the managed PostgreSQL service. A healthy API with stale workers is an operational alert, not an API readiness failure.

## Source configuration

Start with a small reviewed registry of supported public Greenhouse, Lever, Ashby, SmartRecruiters, or RSS/Atom boards relevant to internships, co-ops, new-grad, and entry-level software roles. Keep every source bounded. Validate a candidate configuration before activation with:

```sh
python -m backend.app.commands.collect_live health
```

The existing validator rejects malformed, unsupported, unsafe, and duplicate source identities. Disabled sources never poll and malformed source configuration never changes existing canonical job data.

## Production validation

With placeholder values, validate the deployment definition without reaching a provider:

```sh
docker compose --env-file deploy/production.env.example -f docker-compose.production.yml config --quiet
```

Substitute real secret-store values only in the deployment environment, run the release migration once, then perform API, worker, storage, and restart smoke checks with a dedicated staging account. The ingress must terminate HTTPS for `FRONTEND_ORIGIN`; enable its HSTS policy once the domain is HTTPS-only.


## Continuous collector process

Run the collector as a separate background service with the same backend image,
server-only configuration and database as the API:

```sh
python -m backend.app.commands.collect_live run
```

The API never starts a collector. HTTP traffic is not required. The existing
production Compose collector role already uses this command. On Render, configure
an independently running background-worker service with this start command and
the existing backend configuration; do not use an HTTP request or web startup hook
to launch it. No hosting plan or deployment availability is verified by this code.
Choose hosting that keeps background processes running and restarts failures.

The collector claims the existing singleton worker lease using a unique runtime
UUID. It heartbeats before/after cycles, at most every ten seconds while waiting
on collection or discovery, and after idle waits of at most twenty seconds
(shorter for smaller worker leases). The coordinator renews in-flight source
leases while HTTP runs in executor threads; there is no heartbeat thread or new
scheduler. Each continuous/once cycle claims at most `LIVE_COLLECTOR_CONCURRENCY`
sources, oldest due first, without queuing work behind soon-to-expire leases.
Existing per-source budgets, adaptive scheduling and source backoff still apply.

Temporary database/cycle failures produce safe structured error logs and
interruptible retries at 5, 10, 20, 40, then at most 60 seconds. Successful cycles
reset this delay. Existing SQLAlchemy pre-ping, recycle, connection timeout and
pool limits handle reconnection; no separate connection pool is introduced.
A failed source is recorded independently and does not prevent other sources
from completing. Unexpected source exceptions remain visible in structured logs.

SIGINT/SIGTERM stop further claims and signal in-flight collection between safe
batches. Committed cursor progress survives interruption; hard termination is
recovered through existing lease expiry and idempotent ingestion. Active HTTP
units remain bounded by existing provider budgets and may take longer than a
platform's termination grace period. Set the platform grace period appropriately;
hard-kill correctness does not rely on a successful final lease release. Database
resources are disposed on command exit. A failed cleanup is logged, not hidden.

Bounded verification uses the same runtime and a real **due-source** scheduler
cycle, including worker claim/heartbeat/release. It does not force future polls:

```sh
python -m backend.app.commands.collect_live once --all
python -m backend.app.commands.worker_health collector
python -m backend.app.commands.job_intelligence report
python -m backend.app.commands.collect_live health
```

A successful `once` exits zero (including no due work); source/cycle failure or an
already-held worker lease exits nonzero. After `once`, worker health correctly
reports stopped. The intelligence report's `operations` section includes runtime
identity, start time, heartbeat age/status, source leases/expiry, due work, recent
errors and last collection success. These details stay in the operator command;
the public worker health endpoint continues to expose only aggregate freshness.
