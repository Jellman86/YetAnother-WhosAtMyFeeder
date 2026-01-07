import { Hono } from 'hono';
import { cors } from 'hono/cors';

type Bindings = {
  DB: D1Database;
};

const app = new Hono<{ Bindings: Bindings }>();

// Enable CORS
app.use('/*', cors());

interface TelemetryPayload {
  installation_id: string;
  timestamp: string;
  version: string;
  platform: {
    system: string;
    release: string;
    machine: string;
  };
  configuration: {
    model_type: string;
    birdnet_enabled: boolean;
    birdweather_enabled: boolean;
    llm_enabled: boolean;
    llm_provider: string;
    media_cache_enabled: boolean;
  };
}

app.get('/', (c) => c.text('YA-WAMF Telemetry Receiver is operational.'));

app.post('/heartbeat', async (c) => {
  try {
    const payload = await c.req.json<TelemetryPayload>();
    const country = c.req.raw.cf?.country || 'XX';

    if (!payload.installation_id) {
      return c.json({ error: 'Missing installation_id' }, 400);
    }

    const stmt = c.env.DB.prepare(`
      INSERT INTO heartbeats (
        installation_id, 
        app_version, 
        platform_system, 
        platform_release, 
        platform_machine, 
        model_type, 
        birdnet_enabled, 
        birdweather_enabled, 
        llm_enabled, 
        llm_provider, 
        media_cache_enabled, 
        ip_country, 
        last_seen
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
      ON CONFLICT(installation_id) DO UPDATE SET
        app_version = excluded.app_version,
        platform_system = excluded.platform_system,
        platform_release = excluded.platform_release,
        platform_machine = excluded.platform_machine,
        model_type = excluded.model_type,
        birdnet_enabled = excluded.birdnet_enabled,
        birdweather_enabled = excluded.birdweather_enabled,
        llm_enabled = excluded.llm_enabled,
        llm_provider = excluded.llm_provider,
        media_cache_enabled = excluded.media_cache_enabled,
        ip_country = excluded.ip_country,
        last_seen = datetime('now')
    `);

    await stmt.bind(
      payload.installation_id,
      payload.version,
      payload.platform?.system || null,
      payload.platform?.release || null,
      payload.platform?.machine || null,
      payload.configuration?.model_type || null,
      payload.configuration?.birdnet_enabled ? 1 : 0,
      payload.configuration?.birdweather_enabled ? 1 : 0,
      payload.configuration?.llm_enabled ? 1 : 0,
      payload.configuration?.llm_provider || null,
      payload.configuration?.media_cache_enabled ? 1 : 0,
      country
    ).run();

    return c.json({ status: 'ok' });
  } catch (e: any) {
    console.error('Telemetry error:', e);
    return c.json({ error: e.message }, 500);
  }
});

// Simple stats endpoint (Optional - consider securing this)
app.get('/stats/summary', async (c) => {
  const activeThreshold = "datetime('now', '-7 days')";
  
  const total = await c.env.DB.prepare("SELECT count(*) as count FROM heartbeats").first('count');
  const active7d = await c.env.DB.prepare(`SELECT count(*) as count FROM heartbeats WHERE last_seen > ${activeThreshold}`).first('count');
  
  const versions = await c.env.DB.prepare(`
    SELECT app_version, count(*) as count 
    FROM heartbeats 
    WHERE last_seen > ${activeThreshold} 
    GROUP BY app_version 
    ORDER BY count DESC
  `).all();

  const models = await c.env.DB.prepare(`
    SELECT model_type, count(*) as count 
    FROM heartbeats 
    WHERE last_seen > ${activeThreshold} 
    GROUP BY model_type 
    ORDER BY count DESC
  `).all();

  return c.json({
    total_installs: total,
    active_last_7_days: active7d,
    versions: versions.results,
    models: models.results
  });
});

export default app;
