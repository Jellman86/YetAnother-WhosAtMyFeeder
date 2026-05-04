import { Hono } from 'hono';
import { cors } from 'hono/cors';

type Bindings = {
  DB: D1Database;
  HEALTH_DB: D1Database;
  DASHBOARD_USERNAME?: string;
  DASHBOARD_PASSWORD?: string;
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
  runtime?: {
    model_runtime?: string | null;
    inference_provider_configured?: string | null;
    inference_provider_active?: string | null;
    inference_backend_active?: string | null;
    image_execution_mode?: string | null;
    bird_crop_detector_tier?: string | null;
  };
  hardware?: {
    cuda_available?: boolean | null;
    nvidia_gpu_detected?: boolean | null;
    openvino_available?: boolean | null;
    intel_gpu_available?: boolean | null;
    openvino_gpu_compile_ok?: boolean | null;
    openvino_gpu_compile_device?: string | null;
    openvino_gpu_fallback_active?: boolean | null;
  };
  deployment?: {
    mode?: string | null;
    image_flavor?: string | null;
    image_arch?: string | null;
    app_branch?: string | null;
    git_hash?: string | null;
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

function clampDashboardDays(value: unknown): number {
  const days = Number(value ?? 30);
  if (!Number.isFinite(days)) return 30;
  if (days <= 7) return 7;
  if (days <= 30) return 30;
  return 90;
}

function html(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmt(value: unknown): string {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? Math.floor(number).toLocaleString('en-GB') : '0';
}

function pct(value: unknown, total: unknown): string {
  const numerator = Number(value ?? 0);
  const denominator = Number(total ?? 0);
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) return '0%';
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function renderRows(rows: any[], columns: Array<[string, string | ((row: any) => unknown)]>): string {
  if (!rows.length) {
    return `<tr><td colspan="${columns.length}" class="empty">No data in this window</td></tr>`;
  }
  return rows.map((row) => `
    <tr>
      ${columns.map(([, accessor]) => {
        const value = typeof accessor === 'function' ? accessor(row) : row[accessor];
        return `<td>${html(value)}</td>`;
      }).join('')}
    </tr>
  `).join('');
}

function renderBars(rows: any[], labelKey: string, valueKey: string, total: unknown): string {
  if (!rows.length) return '<div class="empty panel-empty">No data in this window</div>';
  return rows.map((row) => {
    const value = Number(row[valueKey] ?? 0);
    const width = pct(value, total);
    return `
      <div class="bar-row">
        <div class="bar-label"><span>${html(row[labelKey] || 'Unknown')}</span><strong>${fmt(value)}</strong></div>
        <div class="bar-track"><div class="bar-fill" style="width:${width}"></div></div>
      </div>
    `;
  }).join('');
}

function isDashboardAuthorized(request: Request, env: Bindings): boolean {
  if (!env.DASHBOARD_USERNAME || !env.DASHBOARD_PASSWORD) return false;
  const header = request.headers.get('authorization') || '';
  const [scheme, encoded] = header.split(' ');
  if (scheme !== 'Basic' || !encoded) return false;
  try {
    const decoded = atob(encoded);
    const separator = decoded.indexOf(':');
    if (separator < 0) return false;
    const username = decoded.slice(0, separator);
    const password = decoded.slice(separator + 1);
    return username === env.DASHBOARD_USERNAME && password === env.DASHBOARD_PASSWORD;
  } catch {
    return false;
  }
}

function unauthorizedDashboard(): Response {
  return new Response('Authentication required', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="YA-WAMF Telemetry Dashboard", charset="UTF-8"',
      'Cache-Control': 'no-store'
    }
  });
}

function dashboardShell({
  title,
  view,
  days,
  body
}: {
  title: string;
  view: 'usage' | 'health';
  days: number;
  body: string;
}): string {
  const tab = (key: 'usage' | 'health', label: string) =>
    `<a class="tab ${view === key ? 'active' : ''}" href="/dashboard?view=${key}&days=${days}">${label}</a>`;
  const windowLink = (value: number) =>
    `<a class="window-link ${days === value ? 'active' : ''}" href="/dashboard?view=${view}&days=${value}">${value}d</a>`;

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${html(title)}</title>
  <style>
    :root { color-scheme: light dark; --bg:#f8fafc; --panel:#ffffff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0; --accent:#0f766e; --accent-soft:#ccfbf1; --danger:#dc2626; --warn:#d97706; }
    @media (prefers-color-scheme: dark) { :root { --bg:#020617; --panel:#0f172a; --text:#e2e8f0; --muted:#94a3b8; --line:#1e293b; --accent:#2dd4bf; --accent-soft:#134e4a; --danger:#f87171; --warn:#fbbf24; } }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font:14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width:min(1180px, calc(100vw - 32px)); margin:0 auto; padding:24px 0 48px; }
    header { display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:20px; }
    h1 { margin:0; font-size:24px; letter-spacing:0; }
    h2 { margin:0 0 12px; font-size:15px; }
    p { color:var(--muted); margin:4px 0 0; }
    .tabs, .windows { display:flex; gap:8px; flex-wrap:wrap; }
    .tab, .window-link { color:var(--muted); text-decoration:none; border:1px solid var(--line); border-radius:8px; padding:8px 10px; background:var(--panel); font-weight:700; }
    .tab.active, .window-link.active { color:var(--accent); border-color:var(--accent); background:var(--accent-soft); }
    .toolbar { display:flex; flex-direction:column; align-items:flex-end; gap:10px; }
    .grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:14px; margin-bottom:14px; }
    .grid.two { grid-template-columns:repeat(2, minmax(0, 1fr)); }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; }
    .metric { font-size:28px; font-weight:900; letter-spacing:0; }
    .metric-label { color:var(--muted); font-size:11px; font-weight:800; text-transform:uppercase; }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; border-bottom:1px solid var(--line); padding:8px 6px; vertical-align:top; }
    th { color:var(--muted); font-size:11px; text-transform:uppercase; }
    tr:last-child td { border-bottom:0; }
    .bar-row { margin:10px 0; }
    .bar-label { display:flex; justify-content:space-between; gap:10px; color:var(--muted); font-size:12px; font-weight:700; }
    .bar-track { height:8px; background:var(--line); border-radius:999px; overflow:hidden; margin-top:4px; }
    .bar-fill { height:100%; background:var(--accent); border-radius:999px; min-width:2px; }
    .map-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(96px, 1fr)); gap:8px; }
    .country { border:1px solid var(--line); border-radius:8px; padding:10px; background:color-mix(in srgb, var(--accent-soft) 45%, transparent); }
    .country strong { display:block; font-size:18px; }
    .country span { color:var(--muted); font-size:11px; font-weight:800; text-transform:uppercase; }
    .severity-critical { color:var(--danger); font-weight:900; }
    .severity-error { color:var(--danger); font-weight:800; }
    .severity-warning { color:var(--warn); font-weight:800; }
    .empty { color:var(--muted); text-align:center; padding:18px; }
    .panel-empty { border:1px dashed var(--line); border-radius:8px; }
    code { background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:2px 5px; }
    @media (max-width: 860px) { header { flex-direction:column; } .toolbar { align-items:flex-start; } .grid, .grid.two { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>YA-WAMF Telemetry Dashboard</h1>
        <p>Aggregate usage and health diagnostics from Cloudflare D1. Window: ${days} days.</p>
      </div>
      <div class="toolbar">
        <nav class="tabs">${tab('usage', 'Usage')}${tab('health', 'Health')}</nav>
        <nav class="windows">${windowLink(7)}${windowLink(30)}${windowLink(90)}</nav>
      </div>
    </header>
    ${body}
  </main>
</body>
</html>`;
}

app.get('/', (c) => c.text('YA-WAMF Telemetry Receiver is operational.'));

app.get('/dashboard', async (c) => {
  if (!c.env.DASHBOARD_USERNAME || !c.env.DASHBOARD_PASSWORD) {
    return c.text('Dashboard disabled', 404);
  }
  if (!isDashboardAuthorized(c.req.raw, c.env)) {
    return unauthorizedDashboard();
  }

  const days = clampDashboardDays(c.req.query('days'));
  const view = c.req.query('view') === 'health' ? 'health' : 'usage';
  const activeThreshold = `datetime('now', '-${days} days')`;

  if (view === 'health') {
    const totals = await c.env.HEALTH_DB.prepare(`
      SELECT
        count(*) as total_issues,
        count(DISTINCT installation_id_hash) as affected_installs,
        coalesce(sum(report_count), 0) as reports,
        coalesce(sum(occurrence_count), 0) as occurrences
      FROM health_issue_reports
      WHERE updated_at > ${activeThreshold}
    `).first();

    const severity = await c.env.HEALTH_DB.prepare(`
      SELECT severity, count(*) as issue_count, sum(report_count) as report_count, sum(occurrence_count) as occurrence_count
      FROM health_issue_reports
      WHERE updated_at > ${activeThreshold}
      GROUP BY severity
      ORDER BY issue_count DESC
    `).all();

    const components = await c.env.HEALTH_DB.prepare(`
      SELECT issue_component, count(*) as issue_count, sum(report_count) as report_count, sum(occurrence_count) as occurrence_count
      FROM health_issue_reports
      WHERE updated_at > ${activeThreshold}
      GROUP BY issue_component
      ORDER BY issue_count DESC
      LIMIT 12
    `).all();

    const topIssues = await c.env.HEALTH_DB.prepare(`
      SELECT issue_component, issue_reason_code, severity, app_version, count(DISTINCT installation_id_hash) as install_count, sum(report_count) as report_count, sum(occurrence_count) as occurrence_count, max(updated_at) as last_seen
      FROM health_issue_reports
      WHERE updated_at > ${activeThreshold}
      GROUP BY issue_component, issue_reason_code, severity, app_version
      ORDER BY install_count DESC, occurrence_count DESC
      LIMIT 30
    `).all();

    const countries = await c.env.HEALTH_DB.prepare(`
      SELECT ip_country, count(DISTINCT installation_id_hash) as installs, count(*) as issue_count
      FROM health_issue_reports
      WHERE updated_at > ${activeThreshold}
      GROUP BY ip_country
      ORDER BY installs DESC, issue_count DESC
      LIMIT 24
    `).all();

    const totalIssues = Number(totals?.total_issues ?? 0);
    const body = `
      <section class="grid">
        <div class="panel"><div class="metric">${fmt(totals?.total_issues)}</div><div class="metric-label">Issue groups</div></div>
        <div class="panel"><div class="metric">${fmt(totals?.affected_installs)}</div><div class="metric-label">Affected installs</div></div>
        <div class="panel"><div class="metric">${fmt(totals?.reports)}</div><div class="metric-label">Reports</div></div>
        <div class="panel"><div class="metric">${fmt(totals?.occurrences)}</div><div class="metric-label">Occurrences</div></div>
      </section>
      <section class="grid two">
        <div class="panel">
          <h2>Severity</h2>
          <table>
            <thead><tr><th>Severity</th><th>Issues</th><th>Reports</th><th>Occurrences</th></tr></thead>
            <tbody>${renderRows(severity.results, [
              ['Severity', 'severity'],
              ['Issues', (row) => fmt(row.issue_count)],
              ['Reports', (row) => fmt(row.report_count)],
              ['Occurrences', (row) => fmt(row.occurrence_count)]
            ])}</tbody>
          </table>
        </div>
        <div class="panel">
          <h2>Components</h2>
          ${renderBars(components.results, 'issue_component', 'issue_count', totalIssues)}
        </div>
      </section>
      <section class="panel" style="margin-bottom:14px">
        <h2>Health Geography</h2>
        <div class="map-grid">
          ${countries.results.length ? countries.results.map((row: any) => `
            <div class="country"><strong>${fmt(row.installs)}</strong><span>${html(row.ip_country || 'XX')} installs / ${fmt(row.issue_count)} issues</span></div>
          `).join('') : '<div class="empty panel-empty">No health reports in this window</div>'}
        </div>
      </section>
      <section class="panel">
        <h2>Top Recurring Health Issues</h2>
        <table>
          <thead><tr><th>Component</th><th>Reason</th><th>Severity</th><th>Version</th><th>Installs</th><th>Occurrences</th><th>Last seen</th></tr></thead>
          <tbody>${renderRows(topIssues.results, [
            ['Component', 'issue_component'],
            ['Reason', 'issue_reason_code'],
            ['Severity', 'severity'],
            ['Version', 'app_version'],
            ['Installs', (row) => fmt(row.install_count)],
            ['Occurrences', (row) => fmt(row.occurrence_count)],
            ['Last seen', 'last_seen']
          ])}</tbody>
        </table>
        <p>Ingestion endpoint: <code>POST /health-issues</code>. Reports are deduped per install and issue fingerprint.</p>
      </section>
    `;
    return c.html(dashboardShell({ title: 'YA-WAMF Health Diagnostics', view, days, body }));
  }

  const totals = await c.env.DB.prepare(`
    SELECT
      count(*) as total_installs,
      count(CASE WHEN last_seen > ${activeThreshold} THEN 1 END) as active_installs
    FROM heartbeats
  `).first();

  const versions = await c.env.DB.prepare(`
    SELECT app_version, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY app_version
    ORDER BY count DESC
    LIMIT 12
  `).all();

  const models = await c.env.DB.prepare(`
    SELECT model_type, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY model_type
    ORDER BY count DESC
    LIMIT 12
  `).all();

  const platforms = await c.env.DB.prepare(`
    SELECT platform_machine, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY platform_machine
    ORDER BY count DESC
    LIMIT 12
  `).all();

  const countries = await c.env.DB.prepare(`
    SELECT ip_country, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY ip_country
    ORDER BY count DESC
    LIMIT 32
  `).all();

  const features = await c.env.DB.prepare(`
    SELECT
      sum(birdnet_enabled) as birdnet,
      sum(birdweather_enabled) as birdweather,
      sum(ebird_enabled) as ebird,
      sum(inaturalist_enabled) as inaturalist,
      sum(llm_enabled) as llm,
      sum(media_cache_enabled) as media_cache,
      sum(media_cache_clips) as clips_cache,
      sum(auto_video_classification) as auto_video,
      sum(notifications_discord) as discord,
      sum(notifications_pushover) as pushover,
      sum(notifications_telegram) as telegram,
      sum(notifications_email) as email,
      sum(access_auth_enabled) as auth_enabled,
      sum(access_public_enabled) as public_access
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
  `).first();

  const runtimeSummary = await c.env.DB.prepare(`
    SELECT
      sum(cuda_available) as cuda,
      sum(nvidia_gpu_detected) as nvidia_gpu,
      sum(openvino_available) as openvino,
      sum(intel_gpu_available) as intel_gpu,
      sum(openvino_gpu_compile_ok) as openvino_compile_ok,
      sum(openvino_gpu_fallback_active) as gpu_fallback
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
  `).first();

  const configuredProviders = await c.env.DB.prepare(`
    SELECT inference_provider_configured as provider, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY inference_provider_configured
    ORDER BY count DESC
    LIMIT 12
  `).all();

  const activeProviders = await c.env.DB.prepare(`
    SELECT inference_provider_active as provider, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY inference_provider_active
    ORDER BY count DESC
    LIMIT 12
  `).all();

  const backends = await c.env.DB.prepare(`
    SELECT inference_backend_active as backend, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY inference_backend_active
    ORDER BY count DESC
    LIMIT 12
  `).all();

  const runtimes = await c.env.DB.prepare(`
    SELECT model_runtime, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY model_runtime
    ORDER BY count DESC
    LIMIT 12
  `).all();

  const deployment = await c.env.DB.prepare(`
    SELECT image_flavor, image_arch, deployment_mode, count(*) as count
    FROM heartbeats
    WHERE last_seen > ${activeThreshold}
    GROUP BY image_flavor, image_arch, deployment_mode
    ORDER BY count DESC
    LIMIT 16
  `).all();

  const activeInstalls = Number(totals?.active_installs ?? 0);
  const featureRows = [
    ['BirdNET-Go', features?.birdnet],
    ['BirdWeather', features?.birdweather],
    ['eBird', features?.ebird],
    ['iNaturalist', features?.inaturalist],
    ['LLM', features?.llm],
    ['Media cache', features?.media_cache],
    ['Clip cache', features?.clips_cache],
    ['Auto video', features?.auto_video],
    ['Discord', features?.discord],
    ['Pushover', features?.pushover],
    ['Telegram', features?.telegram],
    ['Email', features?.email],
    ['Auth enabled', features?.auth_enabled],
    ['Public access', features?.public_access]
  ].map(([name, count]) => ({ name, count }));

  const hardwareRows = [
    ['CUDA available', runtimeSummary?.cuda],
    ['NVIDIA GPU detected', runtimeSummary?.nvidia_gpu],
    ['OpenVINO available', runtimeSummary?.openvino],
    ['Intel GPU available', runtimeSummary?.intel_gpu],
    ['OpenVINO GPU compile OK', runtimeSummary?.openvino_compile_ok],
    ['GPU fallback active', runtimeSummary?.gpu_fallback]
  ].map(([name, count]) => ({ name, count }));

  const body = `
    <section class="grid">
      <div class="panel"><div class="metric">${fmt(totals?.total_installs)}</div><div class="metric-label">Total installs</div></div>
      <div class="panel"><div class="metric">${fmt(totals?.active_installs)}</div><div class="metric-label">Active installs</div></div>
      <div class="panel"><div class="metric">${fmt(countries.results.length)}</div><div class="metric-label">Countries</div></div>
      <div class="panel"><div class="metric">${fmt(versions.results.length)}</div><div class="metric-label">Active versions</div></div>
    </section>
    <section class="grid two">
      <div class="panel">
        <h2>Usage Geography</h2>
        <div class="map-grid">
          ${countries.results.length ? countries.results.map((row: any) => `
            <div class="country"><strong>${fmt(row.count)}</strong><span>${html(row.ip_country || 'XX')}</span></div>
          `).join('') : '<div class="empty panel-empty">No active installs in this window</div>'}
        </div>
      </div>
      <div class="panel">
        <h2>Feature Adoption</h2>
        ${renderBars(featureRows, 'name', 'count', activeInstalls)}
      </div>
    </section>
    <section class="grid two">
      <div class="panel">
        <h2>Versions</h2>
        <table><thead><tr><th>Version</th><th>Installs</th></tr></thead><tbody>${renderRows(versions.results, [['Version', 'app_version'], ['Installs', (row) => fmt(row.count)]])}</tbody></table>
      </div>
      <div class="panel">
        <h2>Models</h2>
        <table><thead><tr><th>Model</th><th>Installs</th></tr></thead><tbody>${renderRows(models.results, [['Model', 'model_type'], ['Installs', (row) => fmt(row.count)]])}</tbody></table>
      </div>
    </section>
    <section class="grid two">
      <div class="panel">
        <h2>Runtime Providers</h2>
        <table><thead><tr><th>Configured</th><th>Installs</th></tr></thead><tbody>${renderRows(configuredProviders.results, [['Configured', (row) => row.provider || 'Unknown'], ['Installs', (row) => fmt(row.count)]])}</tbody></table>
        <table style="margin-top:12px"><thead><tr><th>Active</th><th>Installs</th></tr></thead><tbody>${renderRows(activeProviders.results, [['Active', (row) => row.provider || 'Unknown'], ['Installs', (row) => fmt(row.count)]])}</tbody></table>
      </div>
      <div class="panel">
        <h2>Hardware Capabilities</h2>
        ${renderBars(hardwareRows, 'name', 'count', activeInstalls)}
      </div>
    </section>
    <section class="grid two">
      <div class="panel">
        <h2>Inference Backends</h2>
        <table><thead><tr><th>Backend</th><th>Installs</th></tr></thead><tbody>${renderRows(backends.results, [['Backend', (row) => row.backend || 'Unknown'], ['Installs', (row) => fmt(row.count)]])}</tbody></table>
      </div>
      <div class="panel">
        <h2>Model Runtimes</h2>
        <table><thead><tr><th>Runtime</th><th>Installs</th></tr></thead><tbody>${renderRows(runtimes.results, [['Runtime', (row) => row.model_runtime || 'Unknown'], ['Installs', (row) => fmt(row.count)]])}</tbody></table>
      </div>
    </section>
    <section class="panel">
      <h2>Platforms</h2>
      <table><thead><tr><th>Machine</th><th>Installs</th></tr></thead><tbody>${renderRows(platforms.results, [['Machine', 'platform_machine'], ['Installs', (row) => fmt(row.count)]])}</tbody></table>
    </section>
    <section class="panel">
      <h2>Deployment Images</h2>
      <table><thead><tr><th>Flavor</th><th>Architecture</th><th>Mode</th><th>Installs</th></tr></thead><tbody>${renderRows(deployment.results, [
        ['Flavor', (row) => row.image_flavor || 'Unknown'],
        ['Architecture', (row) => row.image_arch || 'Unknown'],
        ['Mode', (row) => row.deployment_mode || 'Unknown'],
        ['Installs', (row) => fmt(row.count)]
      ])}</tbody></table>
    </section>
  `;

  return c.html(dashboardShell({ title: 'YA-WAMF Usage Telemetry', view, days, body }));
});

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
        model_runtime,
        inference_provider_configured,
        inference_provider_active,
        inference_backend_active,
        image_execution_mode,
        bird_crop_detector_tier,
        cuda_available,
        nvidia_gpu_detected,
        openvino_available,
        intel_gpu_available,
        openvino_gpu_compile_ok,
        openvino_gpu_compile_device,
        openvino_gpu_fallback_active,
        deployment_mode,
        image_flavor,
        image_arch,
        app_branch,
        git_hash,
        ip_country, 
        last_seen
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
        model_runtime = excluded.model_runtime,
        inference_provider_configured = excluded.inference_provider_configured,
        inference_provider_active = excluded.inference_provider_active,
        inference_backend_active = excluded.inference_backend_active,
        image_execution_mode = excluded.image_execution_mode,
        bird_crop_detector_tier = excluded.bird_crop_detector_tier,
        cuda_available = excluded.cuda_available,
        nvidia_gpu_detected = excluded.nvidia_gpu_detected,
        openvino_available = excluded.openvino_available,
        intel_gpu_available = excluded.intel_gpu_available,
        openvino_gpu_compile_ok = excluded.openvino_gpu_compile_ok,
        openvino_gpu_compile_device = excluded.openvino_gpu_compile_device,
        openvino_gpu_fallback_active = excluded.openvino_gpu_fallback_active,
        deployment_mode = excluded.deployment_mode,
        image_flavor = excluded.image_flavor,
        image_arch = excluded.image_arch,
        app_branch = excluded.app_branch,
        git_hash = excluded.git_hash,
        ip_country = excluded.ip_country,
        last_seen = datetime('now')
    `);

    // Helper for boolean to int
    const b2i = (val?: boolean) => val ? 1 : 0;
    const b2iNullable = (val?: boolean | null) => typeof val === 'boolean' ? (val ? 1 : 0) : null;

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
      payload.runtime?.model_runtime || null,
      payload.runtime?.inference_provider_configured || null,
      payload.runtime?.inference_provider_active || null,
      payload.runtime?.inference_backend_active || null,
      payload.runtime?.image_execution_mode || null,
      payload.runtime?.bird_crop_detector_tier || null,
      b2i(payload.hardware?.cuda_available ?? undefined),
      b2i(payload.hardware?.nvidia_gpu_detected ?? undefined),
      b2i(payload.hardware?.openvino_available ?? undefined),
      b2i(payload.hardware?.intel_gpu_available ?? undefined),
      b2iNullable(payload.hardware?.openvino_gpu_compile_ok),
      payload.hardware?.openvino_gpu_compile_device || null,
      b2i(payload.hardware?.openvino_gpu_fallback_active ?? undefined),
      payload.deployment?.mode || null,
      payload.deployment?.image_flavor || null,
      payload.deployment?.image_arch || null,
      payload.deployment?.app_branch || null,
      payload.deployment?.git_hash || null,
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
