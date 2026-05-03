import { Hono } from 'hono';
import { cors } from 'hono/cors';

type Bindings = {
  DB: D1Database;
  HEALTH_DB: D1Database;
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

interface HealthIssue {
  fingerprint: string;
  source?: string | null;
  component?: string | null;
  reason_code?: string | null;
  stage?: string | null;
  severity?: string | null;
  count?: number;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  sample_context?: Record<string, unknown> | null;
}

interface HealthIssuePayload {
  schema_version?: string;
  installation_id: string;
  timestamp: string;
  version: string;
  platform?: {
    system?: string;
    release?: string;
    machine?: string;
  };
  runtime?: Record<string, unknown>;
  integrations?: Record<string, unknown>;
  diagnostics_window?: Record<string, unknown>;
  issues: HealthIssue[];
}

const MAX_HEALTH_ISSUES_PER_REPORT = 25;
const MAX_JSON_CHARS = 8192;

function safeText(value: unknown, fallback = '', limit = 160): string {
  const text = String(value ?? '').trim();
  if (!text) return fallback;
  return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}

function boundedJson(value: unknown, limit = MAX_JSON_CHARS): string {
  const text = JSON.stringify(value ?? {});
  return text.length > limit ? text.slice(0, limit - 3) + '...' : text;
}

function normalizeSeverity(value: unknown): string {
  const severity = safeText(value, 'warning', 20).toLowerCase();
  return ['warning', 'error', 'critical'].includes(severity) ? severity : 'warning';
}

function safeCount(value: unknown): number {
  const count = Number(value ?? 0);
  if (!Number.isFinite(count)) return 0;
  return Math.max(0, Math.floor(count));
}

async function sha256Hex(value: string): Promise<string> {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
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

app.post('/health-issues', async (c) => {
  try {
    const payload = await c.req.json<HealthIssuePayload>();
    const country = c.req.raw.cf?.country || 'XX';

    if (!payload.installation_id) {
      return c.json({ error: 'Missing installation_id' }, 400);
    }
    if (!Array.isArray(payload.issues)) {
      return c.json({ error: 'Missing issues' }, 400);
    }

    const installationHash = await sha256Hex(payload.installation_id);
    const issues = payload.issues.slice(0, MAX_HEALTH_ISSUES_PER_REPORT);
    const payloadBase = {
      schema_version: safeText(payload.schema_version, 'unknown', 80),
      timestamp: safeText(payload.timestamp, '', 80),
      runtime: payload.runtime ?? {},
      integrations: payload.integrations ?? {},
      diagnostics_window: payload.diagnostics_window ?? {}
    };

    const stmt = c.env.HEALTH_DB.prepare(`
      INSERT INTO health_issue_reports (
        report_key,
        installation_id_hash,
        issue_fingerprint,
        app_version,
        platform_system,
        platform_release,
        platform_machine,
        issue_source,
        issue_component,
        issue_reason_code,
        issue_stage,
        severity,
        first_seen_at,
        last_seen_at,
        report_count,
        occurrence_count,
        sample_context_json,
        last_payload_json,
        ip_country,
        created_at,
        updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, datetime('now'), datetime('now'))
      ON CONFLICT(report_key) DO UPDATE SET
        app_version = excluded.app_version,
        platform_system = excluded.platform_system,
        platform_release = excluded.platform_release,
        platform_machine = excluded.platform_machine,
        issue_source = excluded.issue_source,
        issue_component = excluded.issue_component,
        issue_reason_code = excluded.issue_reason_code,
        issue_stage = excluded.issue_stage,
        severity = excluded.severity,
        first_seen_at = COALESCE(MIN(health_issue_reports.first_seen_at, excluded.first_seen_at), excluded.first_seen_at, health_issue_reports.first_seen_at),
        last_seen_at = COALESCE(MAX(health_issue_reports.last_seen_at, excluded.last_seen_at), excluded.last_seen_at, health_issue_reports.last_seen_at),
        report_count = health_issue_reports.report_count + 1,
        occurrence_count = health_issue_reports.occurrence_count + excluded.occurrence_count,
        sample_context_json = excluded.sample_context_json,
        last_payload_json = excluded.last_payload_json,
        ip_country = excluded.ip_country,
        updated_at = datetime('now')
    `);

    let accepted = 0;
    for (const issue of issues) {
      const fingerprint = safeText(issue.fingerprint, '', 80);
      if (!fingerprint) continue;
      const reportKey = await sha256Hex(`${installationHash}:${fingerprint}`);
      const count = safeCount(issue.count);
      await stmt.bind(
        reportKey,
        installationHash,
        fingerprint,
        safeText(payload.version, 'unknown', 80),
        safeText(payload.platform?.system, '', 80) || null,
        safeText(payload.platform?.release, '', 120) || null,
        safeText(payload.platform?.machine, '', 80) || null,
        safeText(issue.source, 'unknown', 80),
        safeText(issue.component, 'unknown', 80),
        safeText(issue.reason_code, 'unknown_reason', 120),
        safeText(issue.stage, '', 80) || null,
        normalizeSeverity(issue.severity),
        safeText(issue.first_seen_at, '', 80) || null,
        safeText(issue.last_seen_at, '', 80) || null,
        count,
        boundedJson(issue.sample_context ?? {}, 2048),
        boundedJson({ ...payloadBase, issue }, MAX_JSON_CHARS),
        country
      ).run();
      accepted++;
    }

    return c.json({ status: 'ok', accepted });
  } catch (e: any) {
    console.error('Health issue telemetry error:', e);
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

app.get('/stats/health-issues', async (c) => {
  const activeThreshold = "datetime('now', '-30 days')";

  const total = await c.env.HEALTH_DB.prepare("SELECT count(*) as count FROM health_issue_reports").first('count');
  const active30d = await c.env.HEALTH_DB.prepare(`SELECT count(*) as count FROM health_issue_reports WHERE updated_at > ${activeThreshold}`).first('count');

  const bySeverity = await c.env.HEALTH_DB.prepare(`
    SELECT severity, count(*) as issue_count, sum(report_count) as report_count, sum(occurrence_count) as occurrence_count
    FROM health_issue_reports
    WHERE updated_at > ${activeThreshold}
    GROUP BY severity
    ORDER BY issue_count DESC
  `).all();

  const byComponent = await c.env.HEALTH_DB.prepare(`
    SELECT issue_component, count(*) as issue_count, sum(report_count) as report_count, sum(occurrence_count) as occurrence_count
    FROM health_issue_reports
    WHERE updated_at > ${activeThreshold}
    GROUP BY issue_component
    ORDER BY issue_count DESC
    LIMIT 20
  `).all();

  const topIssues = await c.env.HEALTH_DB.prepare(`
    SELECT issue_component, issue_reason_code, severity, app_version, count(*) as install_count, sum(report_count) as report_count, sum(occurrence_count) as occurrence_count, max(updated_at) as last_seen
    FROM health_issue_reports
    WHERE updated_at > ${activeThreshold}
    GROUP BY issue_component, issue_reason_code, severity, app_version
    ORDER BY install_count DESC, occurrence_count DESC
    LIMIT 30
  `).all();

  return c.json({
    total_issues: total,
    active_last_30_days: active30d,
    by_severity: bySeverity.results,
    by_component: byComponent.results,
    top_issues: topIssues.results
  });
});

export default app;
