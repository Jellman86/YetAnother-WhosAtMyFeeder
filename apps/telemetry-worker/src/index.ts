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
    // Legacy location
    birdnet_enabled?: boolean;
    birdweather_enabled?: boolean;
    llm_enabled: boolean;
    llm_provider: string;
    media_cache_enabled: boolean;
    media_cache_clips?: boolean;
    auto_video_classification?: boolean;
  };
  integrations?: {
    birdnet_enabled: boolean;
    birdweather_enabled: boolean;
    ebird_enabled: boolean;
    inaturalist_enabled: boolean;
  };
  notifications?: {
    discord_enabled: boolean;
    pushover_enabled: boolean;
    telegram_enabled: boolean;
    email_enabled: boolean;
    mode: string;
  };
  enrichment?: {
    mode: string;
    summary_source: string;
    sightings_source: string;
    taxonomy_source: string;
  };
  access?: {
    auth_enabled: boolean;
    public_access_enabled: boolean;
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
        media_cache_clips,
        auto_video_classification,
        ebird_enabled,
        inaturalist_enabled,
        notifications_discord,
        notifications_pushover,
        notifications_telegram,
        notifications_email,
        enrichment_mode,
        access_auth_enabled,
        access_public_enabled,
        ip_country, 
        last_seen
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
        media_cache_clips = excluded.media_cache_clips,
        auto_video_classification = excluded.auto_video_classification,
        ebird_enabled = excluded.ebird_enabled,
        inaturalist_enabled = excluded.inaturalist_enabled,
        notifications_discord = excluded.notifications_discord,
        notifications_pushover = excluded.notifications_pushover,
        notifications_telegram = excluded.notifications_telegram,
        notifications_email = excluded.notifications_email,
        enrichment_mode = excluded.enrichment_mode,
        access_auth_enabled = excluded.access_auth_enabled,
        access_public_enabled = excluded.access_public_enabled,
        ip_country = excluded.ip_country,
        last_seen = datetime('now')
    `);

    // Helper for boolean to int
    const b2i = (val?: boolean) => val ? 1 : 0;

    await stmt.bind(
      payload.installation_id,
      payload.version,
      payload.platform?.system || null,
      payload.platform?.release || null,
      payload.platform?.machine || null,
      payload.configuration?.model_type || null,
      // Handle legacy vs new location for birdnet/birdweather
      b2i(payload.integrations?.birdnet_enabled ?? payload.configuration?.birdnet_enabled),
      b2i(payload.integrations?.birdweather_enabled ?? payload.configuration?.birdweather_enabled),
      b2i(payload.configuration?.llm_enabled),
      payload.configuration?.llm_provider || null,
      b2i(payload.configuration?.media_cache_enabled),
      b2i(payload.configuration?.media_cache_clips),
      b2i(payload.configuration?.auto_video_classification),
      b2i(payload.integrations?.ebird_enabled),
      b2i(payload.integrations?.inaturalist_enabled),
      b2i(payload.notifications?.discord_enabled),
      b2i(payload.notifications?.pushover_enabled),
      b2i(payload.notifications?.telegram_enabled),
      b2i(payload.notifications?.email_enabled),
      payload.enrichment?.mode || null,
      b2i(payload.access?.auth_enabled),
      b2i(payload.access?.public_access_enabled),
      country
    ).run();

    return c.json({ status: 'ok' });
  } catch (e: any) {
    console.error('Telemetry error:', e);
    return c.json({ error: e.message }, 500);
  }
});

// Simple stats endpoint
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

  // Add feature stats
  const features = await c.env.DB.prepare(`
    SELECT 
      sum(birdnet_enabled) as birdnet,
      sum(ebird_enabled) as ebird,
      sum(inaturalist_enabled) as inaturalist,
      sum(llm_enabled) as llm,
      sum(media_cache_clips) as clips_cache,
      sum(notifications_email) as email_notifs,
      sum(access_public_enabled) as public_access
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
  `).first();

  return c.json({
    total_installs: total,
    active_last_7_days: active7d,
    versions: versions.results,
    models: models.results,
    features: features
  });
});

export default app;