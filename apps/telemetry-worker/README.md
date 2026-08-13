# YA-WAMF Telemetry Worker

This is a Cloudflare Worker designed to collect anonymous usage statistics from YA-WAMF instances. It also owns a separate D1 database for opt-in anonymous health issue diagnostics.

## Prerequisites

- A Cloudflare account
- `npm` installed locally
- [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/install-and-update/) installed (`npm install -g wrangler`)

## Setup & Deployment Guide (Headless / CI)

Since I am running in a headless environment (like code-server) where browser login is not possible, use a Cloudflare API Token.

### 1. Create a Cloudflare API Token
1. Go to [Cloudflare Dashboard > My Profile > API Tokens](https://dash.cloudflare.com/profile/api-tokens).
2. Click **Create Token**.
3. Use the **"Edit Cloudflare Workers"** template.
4. **Important:** Add D1 Database permissions:
   - Under **Permissions**, click **Add more**.
   - Select **Account** -> **D1** -> **Edit**.
5. Set **Account Resources** to "Include" -> "All accounts" (or your specific account).
6. Click **Continue to summary** -> **Create Token**.
7. Copy the token string.

### 2. Authenticate in Terminal
In your terminal, export the token as an environment variable:

```bash
export CLOUDFLARE_API_TOKEN=your_token_here
```

Verify access:
```bash
npx wrangler whoami
```

### 3. Create the Database
I use Cloudflare D1 (serverless SQLite) to store the data.

```bash
npx wrangler d1 create yawamf-telemetry
npx wrangler d1 create yawamf-health-issues
```

**Important:** Each command output will contain a `database_id`. Copy both IDs.

### 4. Configure Wrangler
Open `wrangler.jsonc` and replace the two database IDs:

```jsonc
"d1_databases": [
  { "binding": "DB", "database_name": "yawamf-telemetry", "database_id": "PASTE_USAGE_ID_HERE" },
  { "binding": "HEALTH_DB", "database_name": "yawamf-health-issues", "database_id": "PASTE_HEALTH_ID_HERE" }
]
```

### 5. Initialize the Schema
Apply the ordered migrations to your remote databases:

```bash
npm ci
npm run db:migrate:telemetry
npm run db:migrate:health
```

Never run a destructive schema bootstrap against an existing database. `schema.sql` and
`health_schema.sql` are safe, idempotent local references; production schema ownership lives in
the ordered migration directories.

The migrations add one usage snapshot per installation/day (keyed by an opaque installation
hash), one compact health batch marker per unique report, and a shared daily write-budget row.
Daily rollups and health history retain 400 days, while latest-state heartbeat rows retain 90 days.
A bounded 03:17 UTC scheduled pass enforces retention and removes legacy unhashed installation
identifiers. Ingestion retains small opportunistic cleanup chunks, so a missed scheduled event does
not allow unbounded growth.

### 6. Deploy the Worker
Publish the code to the edge:

```bash
npm run deploy
```

You will get a URL like `https://yawamf-telemetry.<your-subdomain>.workers.dev`.

## Deploying Updates

Pushes to `dev` that touch `apps/telemetry-worker/**` run `.github/workflows/deploy-telemetry-worker.yml`. The workflow installs locked dependencies, runs the Worker+D1 integration suite, applies both ordered migration streams, and deploys only after all prior steps pass.

For an authorised manual deployment:

1. **Set the Cloudflare API token**:
   ```bash
   export CLOUDFLARE_API_TOKEN=your_token_here
   ```

2. **Apply migrations, then deploy**:
   ```bash
   npm run db:migrate:telemetry
   npm run db:migrate:health
   npm run deploy
   ```
   Migrations are idempotent and must succeed before publishing the Worker. These commands are non-interactive when the API token is set.

## Dashboard

The worker includes a small server-rendered dashboard at:

```text
https://yawamf-telemetry.<your-subdomain>.workers.dev/dashboard
```

The current dashboard is a public, aggregate-only view. It does not expose installation IDs,
hostnames, media, raw diagnostic messages, or configuration secrets. Categories and health detail
are published only when at least three distinct installations contribute; smaller groups read as a
low cohort or are omitted. Recent health totals come from accepted batch rows, so a lifetime issue
counter cannot inflate a 7-, 30-, or 90-day window. Public timestamps are day-granularity.

The dashboard has two views:

- **Usage:** installs, active installs, versions, models, feature adoption, runtime/provider adoption, GPU capability flags, deployment image split, platform split, and country distribution.
- **Health:** affected installs, severity/component breakdowns, country distribution, top recurring issue fingerprints, and the health ingestion endpoint status.

Use `?days=7`, `?days=30`, or `?days=90` to change the reporting window.

## API Endpoints

- **`POST /heartbeat`**: Receives the telemetry JSON payload.
- **`POST /health-issues`**: Receives deduped, sanitized anonymous health issue reports.
- **`POST /forget`**: Deletes the caller's hashed usage and health history after telemetry is disabled.
- **`GET /dashboard`**: Returns the current public aggregate HTML dashboard.
- **`GET /stats/summary`**: Returns a JSON summary of active installs, versions, and model usage.
- **`GET /stats/health-issues`**: Returns aggregate health issue summaries from the separate health D1 database.

Both POST endpoints reject bodies larger than 128 KiB before JSON parsing. Cloudflare's native rate-limit bindings provide per-location, eventually consistent best-effort limits keyed by source IP and installation (heartbeat: 6/minute; health issues: 1/minute) before D1 writes. They are not global ceilings. An atomic account-wide budget in the usage D1 is the hard write guard and limits estimated indexed writes to 40,000 units/day across both endpoints; exhausted requests receive `503` before telemetry rows are written. The estimate deliberately leaves substantial headroom below Cloudflare Free's 100,000 rows-written/day allowance.

New heartbeat rows use only a SHA-256 installation identity; the receiver does not retain the raw
UUID. Health schema v3 sends only installation-scoped SHA-256 event identities. Exact report replays
are rejected before they consume the shared daily write budget. Batch-marker SQL compares opaque
event identities with prior 400-day markers, so a service restart with overlapping diagnostic
history does not increment aggregate counts twice. Existing v1/v2 clients remain accepted with
their prior report-level idempotency behaviour.

This deployment is intentionally held within Cloudflare's Free plan. The application-level cap is
40,000 estimated indexed D1 writes/day, leaving substantial room below the current 100,000-row Free
allowance. Dashboard results are cached for five minutes, retention work is bounded, Workers Logs
sample 10% of invocations, and distributed tracing is disabled. Revisit these controls before adding
new indexes, ingestion rows, dashboard queries, or observability exporters.

Ingestion is intentionally anonymous and unauthenticated so open-source installations require no shared secret. Rate limits and the global budget bound abuse, but caller-supplied data can still be forged; aggregates are directional product telemetry, not an authoritative audit or billing record.
