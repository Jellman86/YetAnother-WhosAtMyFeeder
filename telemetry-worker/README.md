# YA-WAMF Telemetry Worker

This is a Cloudflare Worker designed to collect anonymous usage statistics from YA-WAMF instances.

## Prerequisites

- A Cloudflare account
- `npm` installed locally (or access to a machine with it)
- [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/install-and-update/) installed (`npm install -g wrangler`)

## Setup & Deployment Guide

### 1. Login to Cloudflare
```bash
wrangler login
```

### 2. Create the Database
We use Cloudflare D1 (serverless SQLite) to store the data.

```bash
wrangler d1 create yawamf-telemetry
```

**Important:** The command output will contain a `database_id`. Copy this ID.

### 3. Configure Wrangler
Open `wrangler.toml` and replace the placeholder with your ID:

```toml
[[d1_databases]]
binding = "DB"
database_name = "yawamf-telemetry"
database_id = "PASTE_YOUR_ID_HERE"
```

### 4. Initialize the Schema
Create the tables in your remote database:

```bash
npm install
wrangler d1 execute yawamf-telemetry --file=./schema.sql --remote
```

### 5. Deploy the Worker
Publish the code to the edge:

```bash
npm run deploy
```

You will get a URL like `https://yawamf-telemetry.<your-subdomain>.workers.dev`.

### 6. Update the Main Project
Take your new worker URL and set it as the default telemetry endpoint in `YA-WAMF/backend/app/config.py`:

```python
url: Optional[str] = Field(default="https://your-new-worker.workers.dev/heartbeat", ...)
```

## API Endpoints

- **`POST /heartbeat`**: Receives the telemetry JSON payload.
- **`GET /stats/summary`**: Returns a JSON summary of active installs, versions, and model usage.
