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
Open `wrangler.toml` and replace the placeholder with your ID:

```toml
[[d1_databases]]
binding = "DB"
database_name = "yawamf-telemetry"
database_id = "PASTE_YOUR_ID_HERE"

[[d1_databases]]
binding = "HEALTH_DB"
database_name = "yawamf-health-issues"
database_id = "PASTE_YOUR_HEALTH_ID_HERE"
```

### 5. Initialize the Schema
Create the tables in your remote database:

```bash
npm ci
npx wrangler d1 execute yawamf-telemetry --file=./schema.sql --remote
npx wrangler d1 execute yawamf-telemetry --file=./migrations/telemetry/0001_daily_heartbeats.sql --remote
npx wrangler d1 execute yawamf-health-issues --file=./health_schema.sql --remote
npx wrangler d1 execute yawamf-health-issues --file=./migrations/health/0001_report_batches.sql --remote
```

The rollup migrations are idempotent. They add one usage snapshot per installation/day (keyed by an opaque installation hash), one compact health batch marker per unique report, and a shared daily write-budget row. Rollups, detailed health aggregates, and batch markers retain 400 days; normal ingestion removes expired rows in bounded chunks. Health ingestion uses at most 30 D1 statements per request, below Cloudflare Free's 50-query invocation limit.

### 6. Deploy the Worker
Publish the code to the edge:

```bash
npm run deploy
```

You will get a URL like `https://yawamf-telemetry.<your-subdomain>.workers.dev`.

## Deploying Updates

Pushes to `dev` that touch `apps/telemetry-worker/**` run `.github/workflows/deploy-telemetry-worker.yml`. The workflow installs locked dependencies, runs the Worker+D1 integration suite, applies both idempotent migrations, and deploys only after all prior steps pass.

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

The current dashboard is a public, aggregate-only view. It does not expose installation IDs, hostnames, media, raw diagnostic messages, or configuration secrets. Maintainer-only protection for detailed Health Data is implemented separately from the ingestion changes.

The dashboard has two views:

- **Usage:** installs, active installs, versions, models, feature adoption, runtime/provider adoption, GPU capability flags, deployment image split, platform split, and country distribution.
- **Health:** affected installs, severity/component breakdowns, country distribution, top recurring issue fingerprints, and the health ingestion endpoint status.

Use `?days=7`, `?days=30`, or `?days=90` to change the reporting window.

## API Endpoints

- **`POST /heartbeat`**: Receives the telemetry JSON payload.
- **`POST /health-issues`**: Receives deduped, sanitized anonymous health issue reports.
- **`GET /dashboard`**: Returns the current public aggregate HTML dashboard.
- **`GET /stats/summary`**: Returns a JSON summary of active installs, versions, and model usage.
- **`GET /stats/health-issues`**: Returns aggregate health issue summaries from the separate health D1 database.

Both POST endpoints reject bodies larger than 128 KiB before JSON parsing. Cloudflare's native rate-limit bindings provide per-location, eventually consistent best-effort limits keyed by source IP and installation (heartbeat: 6/minute; health issues: 1/minute) before D1 writes. They are not global ceilings. An atomic account-wide budget in the usage D1 is the hard write guard and limits estimated indexed writes to 40,000 units/day across both endpoints; exhausted requests receive `503` before telemetry rows are written. The estimate deliberately leaves substantial headroom below Cloudflare Free's 100,000 rows-written/day allowance.

Health schema v3 sends only installation-scoped SHA-256 event identities. Batch-marker SQL compares those opaque identities with prior 400-day markers, so an exact retry or a service restart with overlapping diagnostic history does not increment aggregate counts twice. Existing v1/v2 clients remain accepted with their prior report-level idempotency behavior.

Ingestion is intentionally anonymous and unauthenticated so open-source installations require no shared secret. Rate limits and the global budget bound abuse, but caller-supplied data can still be forged; aggregates are directional product telemetry, not an authoritative audit or billing record.
