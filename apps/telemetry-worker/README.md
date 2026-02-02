# YA-WAMF Telemetry Worker

This is a Cloudflare Worker designed to collect anonymous usage statistics from YA-WAMF instances.

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
```

**Important:** The command output will contain a `database_id`. Copy this ID.

### 4. Configure Wrangler
Open `wrangler.toml` and replace the placeholder with your ID:

```toml
[[d1_databases]]
binding = "DB"
database_name = "yawamf-telemetry"
database_id = "PASTE_YOUR_ID_HERE"
```

### 5. Initialize the Schema
Create the tables in your remote database:

```bash
npm install
npx wrangler d1 execute yawamf-telemetry --file=./schema.sql --remote
```

### 6. Deploy the Worker
Publish the code to the edge:

```bash
npm run deploy
```

You will get a URL like `https://yawamf-telemetry.<your-subdomain>.workers.dev`.

## Deploying Updates

When you make changes to the worker code (e.g., updating `src/index.ts`), you can push the new version using the same non-interactive method:

1. **Set the API Token**:
   ```bash
   export CLOUDFLARE_API_TOKEN=your_token_here
   ```

2. **Deploy**:
   ```bash
   npm run deploy
   ```
   *Note: This command is non-interactive and does not require a browser login when the API token is set.*

## API Endpoints

- **`POST /heartbeat`**: Receives the telemetry JSON payload.
- **`GET /stats/summary`**: Returns a JSON summary of active installs, versions, and model usage.