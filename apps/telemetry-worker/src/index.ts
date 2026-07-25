import { Hono } from 'hono';
import { cors } from 'hono/cors';

type Bindings = {
  DB: D1Database;
  HEALTH_DB: D1Database;
  HEARTBEAT_RATE_LIMITER: RateLimit;
  HEALTH_RATE_LIMITER: RateLimit;
  ALLOW_UNLIMITED_INGESTION_FOR_TESTS?: string;
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
    inference_health_status?: string | null;
    inference_health_unhealthy_runtimes?: number | null;
    inference_health_degraded_runtimes?: number | null;
    inference_health_total_runtimes?: number | null;
    last_recovery_reason?: string | null;
    last_recovery_status?: string | null;
  };
  hardware?: {
    cuda_available?: boolean | null;
    nvidia_gpu_detected?: boolean | null;
    openvino_available?: boolean | null;
    intel_gpu_available?: boolean | null;
    intel_npu_available?: boolean | null;
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
  event_ids?: string[];
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  sample_context?: Record<string, unknown> | null;
}

interface HealthIssuePayload {
  schema_version?: string;
  report_id?: string;
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
const MAX_HEALTH_EVENTS_PER_REPORT = 250;
const MAX_INGESTION_BODY_BYTES = 128 * 1024;
const MAX_JSON_CHARS = 8192;
// Conservative D1 rows-written estimates include base rows plus primary/secondary
// index maintenance. The 40k operational cap leaves 60k rows/day of Free-plan
// headroom; update these weights whenever an ingestion-table index changes.
const GLOBAL_D1_DAILY_WRITE_BUDGET = 40_000;
const HEARTBEAT_BASE_WRITE_UNITS = 16;
const HEALTH_BASE_WRITE_UNITS = 16;
const HEALTH_ISSUE_WRITE_UNITS = 8;

type BoundedJsonResult =
  | { ok: true; value: unknown }
  | { ok: false; status: 400 | 413; error: string };

async function readBoundedJson(request: Request): Promise<BoundedJsonResult> {
  const contentLength = Number(request.headers.get('content-length') ?? 0);
  if (Number.isFinite(contentLength) && contentLength > MAX_INGESTION_BODY_BYTES) {
    return { ok: false, status: 413, error: 'Payload too large' };
  }
  if (!request.body) return { ok: false, status: 400, error: 'Missing JSON body' };

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_INGESTION_BODY_BYTES) {
      await reader.cancel();
      return { ok: false, status: 413, error: 'Payload too large' };
    }
    chunks.push(value);
  }

  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return { ok: true, value: JSON.parse(new TextDecoder().decode(body)) };
  } catch {
    return { ok: false, status: 400, error: 'Invalid JSON body' };
  }
}

async function withinIngestionRateLimit(
  limiter: RateLimit | undefined,
  request: Request,
  installationId: unknown,
  allowMissingForTests = false,
): Promise<boolean> {
  if (!limiter) {
    if (allowMissingForTests) return true;
    throw new Error('Required ingestion rate limiter is unavailable');
  }
  const ip = request.headers.get('cf-connecting-ip') || 'unknown';
  const installation = safeText(installationId, 'unknown', 160);
  for (const key of [`ip:${ip}`, `installation:${installation}`]) {
    const { success } = await limiter.limit({ key });
    if (!success) return false;
  }
  return true;
}

async function acquireDailyWriteBudget(db: D1Database, writeUnits: number): Promise<boolean> {
  const result = await db.prepare(`
    INSERT INTO ingestion_daily_budget (budget_date, write_units, updated_at)
    VALUES (date('now'), ?, datetime('now'))
    ON CONFLICT(budget_date) DO UPDATE SET
      write_units = ingestion_daily_budget.write_units + excluded.write_units,
      updated_at = datetime('now')
    WHERE ingestion_daily_budget.write_units + excluded.write_units <= ?
    RETURNING write_units
  `).bind(writeUnits, GLOBAL_D1_DAILY_WRITE_BUDGET).first();
  return result !== null;
}

function safeText(value: unknown, fallback = '', limit = 160): string {
  const text = String(value ?? '').trim();
  if (!text) return fallback;
  return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}

function boundedJson(value: unknown, limit = MAX_JSON_CHARS): string {
  const text = JSON.stringify(value ?? {});
  return text.length > limit ? JSON.stringify({ truncated: true }) : text;
}

function normalizeSeverity(value: unknown): string {
  const severity = safeText(value, 'warning', 20).toLowerCase();
  return ['warning', 'error', 'critical'].includes(severity) ? severity : 'warning';
}

function normalizeInferenceHealthStatus(value: unknown): string | null {
  const status = safeText(value, '', 20).toLowerCase();
  return ['ok', 'degraded', 'unhealthy'].includes(status) ? status : null;
}

function normalizeRecoveryStatus(value: unknown): string | null {
  const status = safeText(value, '', 20).toLowerCase();
  return ['recovered', 'failed'].includes(status) ? status : null;
}

function normalizeRecoveryReason(value: unknown): string | null {
  const reason = String(value ?? '').trim().toLowerCase();
  return /^[a-z0-9_]{1,64}$/.test(reason) ? reason : null;
}

function safeRuntimeCount(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const count = Number(value);
  if (!Number.isFinite(count)) return null;
  return Math.min(1_000, Math.max(0, Math.floor(count)));
}

function safeCount(value: unknown): number {
  const count = Number(value ?? 0);
  if (!Number.isFinite(count)) return 0;
  return Math.min(MAX_HEALTH_EVENTS_PER_REPORT, Math.max(0, Math.floor(count)));
}

const ALLOWED_HEALTH_CONTEXT_KEYS = new Set([
  'active_provider', 'attempt', 'backend', 'batch_limit', 'cache_enabled',
  'circuit_failures', 'circuit_open', 'compile_device', 'compile_ok',
  'configured_provider', 'cuda_available', 'device', 'error_type',
  'failure_count', 'fallback_active', 'inference_backend', 'intel_gpu_available',
  'intel_npu_available', 'kind', 'lease_age_seconds', 'max_concurrent',
  'model_id', 'openvino_available', 'pending', 'pressure_level', 'provider',
  'queue_depth', 'reason', 'reason_code', 'runtime', 'runtime_backend', 'source',
  'stage', 'status', 'timeout_seconds', 'worker_pool',
]);

function sanitizeHealthContext(value: unknown, depth = 0): unknown {
  if (depth > 2 || value === null || value === undefined) return null;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') return safeText(value, '', 160);
  if (Array.isArray(value)) {
    return value
      .slice(0, 10)
      .map((item) => sanitizeHealthContext(item, depth + 1))
      .filter((item) => item !== null);
  }
  if (typeof value === 'object') {
    const sanitized: Record<string, unknown> = {};
    for (const [rawKey, rawValue] of Object.entries(value as Record<string, unknown>).slice(0, 20)) {
      const key = safeText(rawKey, '', 80).toLowerCase();
      if (!ALLOWED_HEALTH_CONTEXT_KEYS.has(key)) continue;
      const sanitizedValue = sanitizeHealthContext(rawValue, depth + 1);
      if (sanitizedValue !== null) sanitized[key] = sanitizedValue;
    }
    return sanitized;
  }
  return safeText(value, '', 160);
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

type TrendPoint = { day: string; value: number | null };

function dailyTrend(rows: any[], days: number, valueKey: string): TrendPoint[] {
  const values = new Map(rows.map((row) => [String(row.day), Number(row[valueKey] ?? 0)]));
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  return Array.from({ length: days }, (_, index) => {
    const date = new Date(today);
    date.setUTCDate(today.getUTCDate() - (days - index - 1));
    const day = date.toISOString().slice(0, 10);
    return { day, value: values.has(day) ? values.get(day)! : null };
  });
}

function shortDate(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
}

function renderTrendChart({
  rows,
  days,
  valueKey,
  chartId,
  title,
  ariaLabel,
  caption
}: {
  rows: any[];
  days: number;
  valueKey: string;
  chartId: string;
  title: string;
  ariaLabel: string;
  caption: string;
}): string {
  const points = dailyTrend(rows, days, valueKey);
  const width = 760;
  const height = 190;
  const left = 24;
  const right = 12;
  const top = 18;
  const bottom = 30;
  const plotWidth = width - left - right;
  const baseline = height - bottom;
  const plotHeight = baseline - top;
  const actualPeak = Math.max(0, ...points.map((point) => point.value ?? 0));
  const scalePeak = Math.max(1, actualPeak);
  const coordinates = points.map((point, index) => {
    const x = left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
    const y = point.value === null ? baseline : baseline - (point.value / scalePeak) * plotHeight;
    return { ...point, x, y };
  });
  const observed = coordinates.filter((point) => point.value !== null);
  const line = observed.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  const area = observed.length
    ? `M ${observed[0].x.toFixed(1)} ${baseline} L ${observed.map((point) => `${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' L ')} L ${observed.at(-1)!.x.toFixed(1)} ${baseline} Z`
    : '';
  const middle = points[Math.floor((points.length - 1) / 2)];
  const latest = points.at(-1)?.value;
  const latestObserved = observed.at(-1);
  const accessibleValues = points
    .map((point) => `${point.day}: ${point.value === null ? 'not available' : fmt(point.value)}`)
    .join('; ');

  return `
    <figure class="panel trend-panel">
      <div class="chart-heading">
        <div><span class="eyebrow">Daily rollup</span><h2>${html(title)}</h2></div>
        <div class="chart-latest"><strong>${latest === null || latest === undefined ? '—' : fmt(latest)}</strong><span>latest day</span></div>
      </div>
      <svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${html(ariaLabel)}" aria-describedby="${html(chartId)}-data" preserveAspectRatio="none">
        <line class="chart-grid" x1="${left}" y1="${top}" x2="${width - right}" y2="${top}"></line>
        <line class="chart-grid" x1="${left}" y1="${top + plotHeight / 2}" x2="${width - right}" y2="${top + plotHeight / 2}"></line>
        <line class="chart-axis" x1="${left}" y1="${baseline}" x2="${width - right}" y2="${baseline}"></line>
        <path class="trend-area" d="${area}"></path>
        <polyline class="trend-line" points="${line}"></polyline>
        ${latestObserved ? `<circle class="trend-dot" cx="${latestObserved.x.toFixed(1)}" cy="${latestObserved.y.toFixed(1)}" r="4"></circle>` : ''}
      </svg>
      <div class="chart-labels"><span>${shortDate(points[0].day)}</span><span>${shortDate(middle.day)}</span><span>${shortDate(points.at(-1)!.day)}</span></div>
      <figcaption>${html(caption)} · peak ${fmt(actualPeak)}</figcaption>
      <p class="sr-only" id="${html(chartId)}-data">Daily values for the selected ${days}-day window. ${html(accessibleValues)}. Peak: ${fmt(actualPeak)}.</p>
    </figure>
  `;
}

function severityPill(value: unknown): string {
  const severity = safeText(value, 'unknown', 20).toLowerCase();
  const className = ['critical', 'error', 'warning'].includes(severity) ? severity : 'unknown';
  return `<span class="severity-pill severity-${className}">${html(severity)}</span>`;
}

function humanizeCode(value: unknown): string {
  return safeText(value, 'Unknown', 120).replaceAll('_', ' ');
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
  const modeLabel = view === 'health' ? 'Health Data' : 'User Metrics';
  const modeDescription = view === 'health'
    ? 'Operational issue signals, affected installs, and runtime recovery health'
    : 'Anonymous adoption, platform, model, and runtime trends from active installs';

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${html(title)}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;700;800&family=Instrument+Sans:wght@400;500;600;700&display=swap');
    :root { color-scheme: light dark; --bg:#f8fafc; --panel:#ffffff; --panel-2:#f1f5f9; --text:#334155; --heading:#0f172a; --muted:#64748b; --line:#e2e8f0; --brand:#0f766e; --brand-strong:#115e59; --brand-soft:#ccfbf1; --active:#0f766e; --active-strong:#115e59; --danger:#dc2626; --warn:#d97706; --shadow:0 8px 24px -14px rgba(15,23,42,.22); --font:'Instrument Sans', ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; --font-display:'Bricolage Grotesque', 'Instrument Sans', sans-serif; }
    body.view-health { --brand:#c2410c; --brand-strong:#b91c1c; --brand-soft:#ffedd5; --active:#c2410c; --active-strong:#b91c1c; }
    @media (prefers-color-scheme: dark) { :root { --bg:#030712; --panel:#1e293b; --panel-2:#0f172a; --text:#e2e8f0; --heading:#f1f5f9; --muted:#94a3b8; --line:#334155; --brand:#2dd4bf; --brand-strong:#5eead4; --brand-soft:#134e4a; --danger:#f87171; --warn:#fbbf24; --shadow:0 14px 34px -16px rgba(0,0,0,.7); } body.view-health { --brand:#fb923c; --brand-strong:#f87171; --brand-soft:#7c2d12; } }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font-family:var(--font); font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased; }
    main { width:min(1160px, calc(100vw - 32px)); margin:0 auto; padding:28px 0 56px; }
    a { color:inherit; }
    header.dash { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:22px; }
    .brand { display:flex; align-items:center; gap:12px; }
    .brand .mark { width:40px; height:40px; border-radius:13px; background:linear-gradient(135deg, var(--brand), var(--brand-strong)); color:#fff; display:grid; place-items:center; box-shadow:var(--shadow); }
    .brand .mark svg { width:23px; height:23px; stroke:currentColor; }
    h1 { margin:0; font-family:var(--font-display); font-size:23px; font-weight:800; letter-spacing:-.01em; color:var(--heading); }
    h1 .accent { background:linear-gradient(90deg, var(--brand), var(--brand-strong)); -webkit-background-clip:text; background-clip:text; color:transparent; }
    .subtitle { color:var(--muted); margin:3px 0 0; font-size:12.5px; max-width:58ch; }
    h2 { margin:0 0 14px; font-family:var(--font-display); font-size:13px; font-weight:700; letter-spacing:.01em; color:var(--heading); }
    .tabs, .windows { display:flex; gap:6px; flex-wrap:wrap; }
    .tab, .window-link { color:var(--muted); text-decoration:none; border:1px solid var(--line); border-radius:11px; padding:7px 13px; background:var(--panel); font-weight:600; font-size:13px; transition:border-color .12s, color .12s; }
    .tab:hover, .window-link:hover { border-color:var(--brand); color:var(--brand); }
    .tab.active, .window-link.active { color:#fff; border-color:transparent; background:linear-gradient(135deg, var(--active), var(--active-strong)); box-shadow:var(--shadow); }
    .toolbar { display:flex; flex-direction:column; align-items:flex-end; gap:10px; }
    .grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:14px; margin-bottom:14px; }
    .grid.two { grid-template-columns:repeat(2, minmax(0, 1fr)); }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:18px; min-width:0; box-shadow:var(--shadow); }
    .metric { font-family:var(--font-display); font-size:30px; font-weight:800; letter-spacing:-.02em; line-height:1.05; color:var(--heading); }
    .metric-label { color:var(--muted); font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; margin-top:4px; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { text-align:left; border-bottom:1px solid var(--line); padding:9px 8px; vertical-align:top; }
    th { color:var(--muted); font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; font-weight:700; }
    tbody tr:hover { background:var(--panel-2); }
    tr:last-child td { border-bottom:0; }
    .bar-row { margin:11px 0; }
    .bar-label { display:flex; justify-content:space-between; gap:10px; color:var(--muted); font-size:12px; font-weight:600; }
    .bar-track { height:9px; background:var(--line); border-radius:999px; overflow:hidden; margin-top:5px; }
    .bar-fill { height:100%; background:linear-gradient(90deg, var(--brand), var(--brand-strong)); border-radius:999px; min-width:2px; }
    .map-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(96px, 1fr)); gap:10px; }
    .map-grid > .panel-empty { grid-column:1 / -1; min-height:78px; display:grid; place-items:center; }
    .country { border:1px solid var(--line); border-radius:13px; padding:12px; background:color-mix(in srgb, var(--brand-soft) 40%, var(--panel)); }
    .country strong { display:block; font-family:var(--font-display); font-size:20px; font-weight:800; color:var(--heading); }
    .country span { color:var(--muted); font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.03em; }
    .severity-critical { color:var(--danger); font-weight:800; }
    .severity-error { color:var(--danger); font-weight:700; }
    .severity-warning { color:var(--warn); font-weight:700; }
    .trend-panel { margin:0 0 14px; padding:20px 22px 16px; }
    .chart-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; }
    .chart-heading h2 { margin:2px 0 0; font-size:17px; }
    .eyebrow { color:var(--brand); font-size:10px; font-weight:800; letter-spacing:.09em; text-transform:uppercase; }
    .chart-latest { display:flex; align-items:baseline; gap:7px; color:var(--muted); }
    .chart-latest strong { color:var(--heading); font-family:var(--font-display); font-size:24px; }
    .chart-latest span, figcaption { font-size:11px; }
    .trend-chart { display:block; width:100%; height:190px; margin-top:8px; overflow:visible; }
    .chart-grid, .chart-axis { stroke:var(--line); stroke-width:1; vector-effect:non-scaling-stroke; }
    .trend-area { fill:var(--brand-soft); opacity:.48; }
    .trend-line { fill:none; stroke:var(--brand); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; vector-effect:non-scaling-stroke; }
    .trend-dot { fill:var(--panel); stroke:var(--brand); stroke-width:3; vector-effect:non-scaling-stroke; }
    .chart-labels { display:flex; justify-content:space-between; color:var(--muted); font-size:10.5px; margin-top:-22px; padding:0 4px; }
    figcaption { color:var(--muted); margin-top:8px; }
    .severity-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; }
    .severity-card { border:1px solid var(--line); border-radius:13px; padding:13px; background:var(--panel-2); }
    .severity-card strong { display:block; color:var(--heading); font-family:var(--font-display); font-size:22px; margin-top:8px; }
    .severity-card small { display:block; color:var(--muted); font-size:10.5px; margin-top:2px; }
    .severity-pill { display:inline-flex; align-items:center; width:max-content; border-radius:999px; padding:3px 8px; font-size:10px; font-weight:800; letter-spacing:.05em; text-transform:uppercase; }
    .severity-pill.severity-critical { background:color-mix(in srgb, var(--danger) 18%, transparent); color:var(--danger); }
    .severity-pill.severity-error { background:color-mix(in srgb, var(--danger) 12%, transparent); color:var(--danger); }
    .severity-pill.severity-warning { background:color-mix(in srgb, var(--warn) 16%, transparent); color:var(--warn); }
    .severity-pill.severity-unknown { background:var(--panel-2); color:var(--muted); }
    .table-scroll { overflow-x:auto; margin:0 -4px; padding:0 4px; }
    .table-scroll:focus-visible { outline:3px solid var(--brand); outline-offset:3px; border-radius:8px; }
    .feature-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); column-gap:20px; }
    .scroll-hint { display:none; color:var(--muted); font-size:10.5px; margin:0 0 8px; }
    .issue-reason { color:var(--heading); font-weight:650; text-transform:capitalize; }
    .section-intro { display:flex; justify-content:space-between; gap:20px; align-items:flex-end; margin:24px 2px 10px; }
    .section-intro h2 { font-size:16px; margin:0; }
    .section-intro p { color:var(--muted); font-size:11.5px; margin:0; max-width:58ch; }
    .empty { color:var(--muted); text-align:center; padding:22px; }
    .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0, 0, 0, 0); white-space:nowrap; border:0; }
    .panel-empty { border:1px dashed var(--line); border-radius:16px; box-shadow:none; }
    code { background:var(--panel-2); border:1px solid var(--line); border-radius:6px; padding:2px 6px; font-size:12px; }
    footer.dash { margin-top:28px; color:var(--muted); font-size:12px; text-align:center; border-top:1px solid var(--line); padding-top:16px; }
    footer.dash a { color:var(--brand); text-decoration:none; font-weight:600; }
    @media (max-width: 860px) { header.dash { flex-direction:column; } .toolbar { align-items:flex-start; } .grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } .grid.two { grid-template-columns:1fr; } .section-intro { align-items:flex-start; flex-direction:column; gap:4px; } }
    @media (max-width: 560px) { main { width:min(100% - 20px, 1160px); padding-top:18px; } .tabs { width:100%; } .tab { flex:1; text-align:center; } .panel { padding:15px; border-radius:14px; } .metric { font-size:26px; } .metric-label { font-size:9.5px; } .severity-card { padding:10px 8px; } .severity-card small { line-height:1.35; } .trend-panel { padding:16px 14px 14px; } .trend-chart { height:155px; } .chart-latest span { display:none; } .feature-grid { column-gap:12px; } .scroll-hint { display:block; } }
  </style>
</head>
<body class="view-${view}">
  <main>
    <header class="dash">
      <div class="brand">
        <div class="mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 7h.01"></path><path d="M3.4 18H12a8 8 0 0 0 8-8V7a4 4 0 0 0-7.28-2.3L2 20"></path><path d="m20 7 2 .5-2 .5"></path><path d="M10 18v3"></path><path d="M14 17.75V21"></path><path d="M7 18a6 6 0 0 0 3.84-10.61"></path></svg></div>
        <div>
          <h1>YA-WAMF <span class="accent">${modeLabel}</span></h1>
          <p class="subtitle">${modeDescription} · last ${days} days</p>
        </div>
      </div>
      <div class="toolbar">
        <nav class="tabs" aria-label="Telemetry view">${tab('usage', 'User Metrics')}${tab('health', 'Health Data')}</nav>
        <nav class="windows" aria-label="Reporting window">${windowLink(7)}${windowLink(30)}${windowLink(90)}</nav>
      </div>
    </header>
    ${body}
    <footer class="dash">
      Aggregated, anonymised telemetry — no personal data, hostnames, or media. Enabled per install and cached up to 5&nbsp;minutes.
      · <a href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder">YetAnother-WhosAtMyFeeder</a>
    </footer>
  </main>
</body>
</html>`;
}

app.get('/', (c) => c.text('YA-WAMF Telemetry Receiver is operational.'));

// Channel-aware latest-version lookup for the in-app update prompt. D1 is the source of truth:
// CI writes one row per published branch (`dev`, `main`) plus the latest release row (`stable`),
// and installs compare only against the row for their installed branch/channel. No telemetry
// payload — a plain GET, so installs with telemetry disabled can still learn about updates.
type VersionChannels = {
  stable: { version: string | null; url: string | null };
  dev: { version: string | null; commit: string | null; url: string | null };
  branches: Record<string, { version: string | null; commit: string | null; url: string | null }>;
};
const VERSION_CACHE: { data: VersionChannels | null; expires: number } = { data: null, expires: 0 };
const VERSION_CACHE_TTL_MS = 30 * 60 * 1000;

// Versions published by CI. D1 is authoritative for update checks; if the table or a branch row
// is missing, the corresponding channel stays null instead of being guessed from GitHub.
async function readVersionsFromD1(db: D1Database): Promise<Partial<VersionChannels>> {
  try {
    const { results } = await db
      .prepare('SELECT channel, version, commit_sha, url FROM app_versions')
      .all<{ channel: string; version: string | null; commit_sha: string | null; url: string | null }>();
    const branches: VersionChannels['branches'] = {};
    const out: Partial<VersionChannels> = { branches };
    for (const row of results ?? []) {
      if (row.channel === 'stable') out.stable = { version: row.version, url: row.url };
      else {
        const branchVersion = { version: row.version, commit: row.commit_sha, url: row.url };
        branches[row.channel] = branchVersion;
        if (row.channel === 'dev') out.dev = branchVersion;
      }
    }
    return out;
  } catch {
    return {};
  }
}

app.get('/version', async (c) => {
  const now = Date.now();
  if (VERSION_CACHE.data && VERSION_CACHE.expires > now) {
    return c.json(VERSION_CACHE.data, 200, { 'Cache-Control': 'public, max-age=1800' });
  }
  try {
    const stored = await readVersionsFromD1(c.env.DB);
    const payload: VersionChannels = {
      stable: stored.stable ?? { version: null, url: null },
      dev: stored.dev ?? { version: null, commit: null, url: null },
      branches: stored.branches ?? {},
    };
    VERSION_CACHE.data = payload;
    VERSION_CACHE.expires = now + VERSION_CACHE_TTL_MS;
    return c.json(payload, 200, { 'Cache-Control': 'public, max-age=1800' });
  } catch (e: any) {
    if (VERSION_CACHE.data) return c.json(VERSION_CACHE.data, 200);
    return c.json({ error: e?.message ?? 'fetch_failed' }, 502);
  }
});

// Public, read-only aggregate dashboard. A short per-isolate in-memory cache keeps
// traffic bursts off D1 so the worker stays comfortably within Cloudflare's free
// tier (the edge Cache API is a no-op on *.workers.dev, so we cache in-process).
const DASHBOARD_CACHE = new Map<string, { html: string; expires: number }>();
const DASHBOARD_CACHE_TTL_MS = 5 * 60 * 1000;

app.get('/dashboard', async (c) => {
  const days = clampDashboardDays(c.req.query('days'));
  const view = c.req.query('view') === 'health' ? 'health' : 'usage';

  const cacheKey = `${view}:${days}`;
  const cachedDashboard = DASHBOARD_CACHE.get(cacheKey);
  if (cachedDashboard && cachedDashboard.expires > Date.now()) {
    return c.html(cachedDashboard.html, 200, { 'Cache-Control': 'public, max-age=300' });
  }
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
      LIMIT 10
    `).all();

    const topIssues = await c.env.HEALTH_DB.prepare(`
      SELECT issue_component, issue_reason_code, severity, app_version, count(DISTINCT installation_id_hash) as install_count, sum(report_count) as report_count, sum(occurrence_count) as occurrence_count, max(updated_at) as last_seen
      FROM health_issue_reports
      WHERE updated_at > ${activeThreshold}
      GROUP BY issue_component, issue_reason_code, severity, app_version
      ORDER BY install_count DESC, occurrence_count DESC
      LIMIT 12
    `).all();

    const countries = await c.env.HEALTH_DB.prepare(`
      SELECT ip_country, count(DISTINCT installation_id_hash) as installs, count(*) as issue_count
      FROM health_issue_reports
      WHERE updated_at > ${activeThreshold}
      GROUP BY ip_country
      ORDER BY installs DESC, issue_count DESC
      LIMIT 18
    `).all();

    const dailyReports = await c.env.HEALTH_DB.prepare(`
      SELECT report_date as day, count(*) as reports
      FROM health_report_batches
      WHERE report_date >= date('now', '-${days - 1} days')
      GROUP BY report_date
      ORDER BY report_date
    `).all();

    const inferenceHealthStatuses = await c.env.DB.prepare(`
      SELECT inference_health_status as status, count(*) as count
      FROM heartbeats
      WHERE last_seen > ${activeThreshold}
        AND inference_health_status IN ('ok', 'degraded', 'unhealthy')
      GROUP BY inference_health_status
      ORDER BY count DESC
      LIMIT 3
    `).all();

    const inferenceHealthAggregate = await c.env.DB.prepare(`
      SELECT
        sum(inference_health_unhealthy_runtimes) as unhealthy_runtimes,
        sum(inference_health_degraded_runtimes) as degraded_runtimes,
        sum(inference_health_total_runtimes) as total_runtimes,
        sum(CASE WHEN inference_health_unhealthy_runtimes > 0 THEN 1 ELSE 0 END) as installs_with_unhealthy,
        sum(CASE WHEN inference_health_degraded_runtimes > 0 THEN 1 ELSE 0 END) as installs_with_degraded
      FROM heartbeats
      WHERE last_seen > ${activeThreshold}
    `).first();

    const recoveryReasons = await c.env.DB.prepare(`
      SELECT last_recovery_reason as reason, last_recovery_status as status, count(*) as count
      FROM heartbeats
      WHERE last_seen > ${activeThreshold}
        AND last_recovery_status IN ('recovered', 'failed')
        AND length(last_recovery_reason) BETWEEN 1 AND 64
        AND last_recovery_reason NOT GLOB '*[^a-z0-9_]*'
      GROUP BY last_recovery_reason, last_recovery_status
      ORDER BY count DESC
      LIMIT 10
    `).all();

    const severityByName = new Map(severity.results.map((row: any) => [String(row.severity || 'unknown').toLowerCase(), row]));
    const severityCards = ['critical', 'error', 'warning'].map((name) => {
      const row: any = severityByName.get(name) ?? {};
      return `<div class="severity-card">${severityPill(name)}<strong>${fmt(row.issue_count ?? 0)}</strong><small>${fmt(row.report_count ?? 0)} reports · ${fmt(row.occurrence_count ?? 0)} occurrences</small></div>`;
    }).join('');
    const totalIssues = Number(totals?.total_issues ?? 0);
    const issueRows = topIssues.results.length
      ? topIssues.results.map((row: any) => `<tr>
          <td>${html(row.issue_component || 'Unknown')}</td>
          <td class="issue-reason">${html(humanizeCode(row.issue_reason_code))}</td>
          <td>${severityPill(row.severity)}</td>
          <td>${html(row.app_version || 'Unknown')}</td>
          <td>${fmt(row.install_count)}</td>
          <td>${fmt(row.occurrence_count)}</td>
          <td>${html(row.last_seen || 'Unknown')}</td>
        </tr>`).join('')
      : '<tr><td colspan="7" class="empty">No health issues in this window</td></tr>';

    const body = `
      <section class="grid">
        <div class="panel"><div class="metric">${fmt(totals?.affected_installs)}</div><div class="metric-label">Affected installs</div></div>
        <div class="panel"><div class="metric">${fmt(totals?.total_issues)}</div><div class="metric-label">Issue groups</div></div>
        <div class="panel"><div class="metric">${fmt(inferenceHealthAggregate?.installs_with_unhealthy ?? 0)}</div><div class="metric-label">Unhealthy runtimes</div></div>
        <div class="panel"><div class="metric">${fmt(inferenceHealthAggregate?.installs_with_degraded ?? 0)}</div><div class="metric-label">Degraded runtimes</div></div>
      </section>
      ${renderTrendChart({
        rows: dailyReports.results,
        days,
        valueKey: 'reports',
        chartId: 'health-report-trend',
        title: 'Reports by day',
        ariaLabel: 'Daily health reports trend',
        caption: 'One accepted health snapshot per report ID; repeated deliveries are ignored'
      })}
      <section class="grid two">
        <div class="panel">
          <h2>Severity at a glance</h2>
          <div class="severity-grid">${severityCards}</div>
        </div>
        <div class="panel">
          <h2>Affected components</h2>
          ${renderBars(components.results, 'issue_component', 'issue_count', totalIssues)}
        </div>
      </section>
      <div class="section-intro"><h2>Runtime recovery</h2><p>Latest aggregate state reported by active installations, separate from deduplicated issue details.</p></div>
      <section class="grid two">
        <div class="panel">
          <h2>Inference health status</h2>
          <div class="table-scroll"><table><thead><tr><th>Status</th><th>Installs</th></tr></thead><tbody>${
            inferenceHealthStatuses.results.length
              ? renderRows(inferenceHealthStatuses.results, [
                  ['Status', (row) => row.status || 'Unknown'],
                  ['Installs', (row) => fmt(row.count)]
                ])
              : '<tr><td colspan="2" class="empty">No runtime reports yet</td></tr>'
          }</tbody></table></div>
          <div class="table-scroll"><table style="margin-top:12px"><thead><tr><th>Aggregate</th><th>Value</th></tr></thead><tbody>
            <tr><td>Unhealthy runtime sum</td><td>${fmt(inferenceHealthAggregate?.unhealthy_runtimes ?? 0)}</td></tr>
            <tr><td>Degraded runtime sum</td><td>${fmt(inferenceHealthAggregate?.degraded_runtimes ?? 0)}</td></tr>
            <tr><td>Tracked runtime sum</td><td>${fmt(inferenceHealthAggregate?.total_runtimes ?? 0)}</td></tr>
          </tbody></table></div>
        </div>
        <div class="panel">
          <h2>Most-recent recovery reasons</h2>
          <div class="table-scroll"><table><thead><tr><th>Reason</th><th>Status</th><th>Installs</th></tr></thead><tbody>${
            recoveryReasons.results.length
              ? renderRows(recoveryReasons.results, [
                  ['Reason', (row) => humanizeCode(row.reason)],
                  ['Status', (row) => row.status || 'Unknown'],
                  ['Installs', (row) => fmt(row.count)]
                ])
              : '<tr><td colspan="3" class="empty">No recovery reports yet</td></tr>'
          }</tbody></table></div>
        </div>
      </section>
      <section class="panel" style="margin-bottom:14px">
        <h2>Affected-install geography</h2>
        <div class="map-grid">
          ${countries.results.length ? countries.results.map((row: any) => `
            <div class="country"><strong>${fmt(row.installs)}</strong><span>${html(row.ip_country || 'XX')} · ${fmt(row.issue_count)} issues</span></div>
          `).join('') : '<div class="empty panel-empty">No health reports in this window</div>'}
        </div>
      </section>
      <section class="panel">
        <div class="section-intro" style="margin-top:0"><div><span class="eyebrow">Deduplicated detail</span><h2>Top recurring issues</h2></div><p>Highest-impact issue groups, capped at 12. Full aggregate data remains available from the JSON stats endpoint.</p></div>
        <p class="scroll-hint">Scroll horizontally for full details →</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="Top recurring issues; scroll horizontally for all columns"><table>
          <thead><tr><th>Component</th><th>Reason</th><th>Severity</th><th>Version</th><th>Installs</th><th>Occurrences</th><th>Last seen</th></tr></thead>
          <tbody>${issueRows}</tbody>
        </table></div>
      </section>
    `;
    const healthHtml = dashboardShell({ title: 'YA-WAMF Health Data', view, days, body });
    DASHBOARD_CACHE.set(cacheKey, { html: healthHtml, expires: Date.now() + DASHBOARD_CACHE_TTL_MS });
    return c.html(healthHtml, 200, { 'Cache-Control': 'public, max-age=300' });
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
      sum(intel_npu_available) as intel_npu,
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

  const dailyInstalls = await c.env.DB.prepare(`
    SELECT report_date as day, count(*) as installs
    FROM heartbeat_daily
    WHERE report_date >= date('now', '-${days - 1} days')
    GROUP BY report_date
    ORDER BY report_date
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
    ['Intel NPU available', runtimeSummary?.intel_npu],
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
    ${renderTrendChart({
      rows: dailyInstalls.results,
      days,
      valueKey: 'installs',
      chartId: 'active-install-trend',
      title: 'Active installs by day',
      ariaLabel: 'Daily active installs trend',
      caption: 'One privacy-preserving daily snapshot per active installation'
    })}
    <div class="section-intro"><h2>Adoption</h2><p>Where active installations run and which optional capabilities they choose to enable.</p></div>
    <section class="grid two">
      <div class="panel">
        <h2>Active-install geography</h2>
        <div class="map-grid">
          ${countries.results.length ? countries.results.map((row: any) => `
            <div class="country"><strong>${fmt(row.count)}</strong><span>${html(row.ip_country || 'XX')}</span></div>
          `).join('') : '<div class="empty panel-empty">No active installs in this window</div>'}
        </div>
      </div>
      <div class="panel">
        <h2>Feature Adoption</h2>
        <div class="feature-grid">${renderBars(featureRows, 'name', 'count', activeInstalls)}</div>
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
      <h2>Deployment images</h2>
      <div class="table-scroll"><table><thead><tr><th>Flavor</th><th>Architecture</th><th>Mode</th><th>Installs</th></tr></thead><tbody>${renderRows(deployment.results, [
        ['Flavor', (row) => row.image_flavor || 'Unknown'],
        ['Architecture', (row) => row.image_arch || 'Unknown'],
        ['Mode', (row) => row.deployment_mode || 'Unknown'],
        ['Installs', (row) => fmt(row.count)]
      ])}</tbody></table></div>
    </section>
  `;

  const usageHtml = dashboardShell({ title: 'YA-WAMF User Metrics', view, days, body });
  DASHBOARD_CACHE.set(cacheKey, { html: usageHtml, expires: Date.now() + DASHBOARD_CACHE_TTL_MS });
  return c.html(usageHtml, 200, { 'Cache-Control': 'public, max-age=300' });
});

app.post('/heartbeat', async (c) => {
  try {
    const parsed = await readBoundedJson(c.req.raw);
    if (!parsed.ok) return c.json({ error: parsed.error }, parsed.status);
    if (!parsed.value || typeof parsed.value !== 'object' || Array.isArray(parsed.value)) {
      return c.json({ error: 'JSON body must be an object' }, 400);
    }
    const payload = parsed.value as TelemetryPayload;
    const country = c.req.raw.cf?.country || 'XX';

    if (!payload.installation_id) {
      return c.json({ error: 'Missing installation_id' }, 400);
    }
    if (!await withinIngestionRateLimit(
      c.env.HEARTBEAT_RATE_LIMITER,
      c.req.raw,
      payload.installation_id,
      c.env.ALLOW_UNLIMITED_INGESTION_FOR_TESTS === 'true',
    )) {
      return c.json({ error: 'Rate limit exceeded' }, 429, { 'Retry-After': '60' });
    }
    const expiredDaily = await c.env.DB.prepare(`
      SELECT COUNT(*) AS count FROM (
        SELECT 1 FROM heartbeat_daily
        WHERE report_date < date('now', '-400 days')
        LIMIT 1
      )
    `).first<number>('count') ?? 0;
    const heartbeatWriteUnits = HEARTBEAT_BASE_WRITE_UNITS + (expiredDaily > 0 ? 4 : 0);
    if (!await acquireDailyWriteBudget(c.env.DB, heartbeatWriteUnits)) {
      return c.json({ error: 'Daily ingestion budget exhausted' }, 503, { 'Retry-After': '86400' });
    }
    const installationHash = await sha256Hex(payload.installation_id);

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
        intel_npu_available,
        openvino_gpu_compile_ok,
        openvino_gpu_compile_device,
        openvino_gpu_fallback_active,
        deployment_mode,
        image_flavor,
        image_arch,
        app_branch,
        git_hash,
        inference_health_status,
        inference_health_unhealthy_runtimes,
        inference_health_degraded_runtimes,
        inference_health_total_runtimes,
        last_recovery_reason,
        last_recovery_status,
        ip_country,
        last_seen
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
        intel_npu_available = excluded.intel_npu_available,
        openvino_gpu_compile_ok = excluded.openvino_gpu_compile_ok,
        openvino_gpu_compile_device = excluded.openvino_gpu_compile_device,
        openvino_gpu_fallback_active = excluded.openvino_gpu_fallback_active,
        deployment_mode = excluded.deployment_mode,
        image_flavor = excluded.image_flavor,
        image_arch = excluded.image_arch,
        app_branch = excluded.app_branch,
        git_hash = excluded.git_hash,
        inference_health_status = excluded.inference_health_status,
        inference_health_unhealthy_runtimes = excluded.inference_health_unhealthy_runtimes,
        inference_health_degraded_runtimes = excluded.inference_health_degraded_runtimes,
        inference_health_total_runtimes = excluded.inference_health_total_runtimes,
        last_recovery_reason = excluded.last_recovery_reason,
        last_recovery_status = excluded.last_recovery_status,
        ip_country = excluded.ip_country,
        last_seen = datetime('now')
    `);

    // Helper for boolean to int
    const b2i = (val?: boolean) => val ? 1 : 0;
    const b2iNullable = (val?: boolean | null) => typeof val === 'boolean' ? (val ? 1 : 0) : null;

    const heartbeatStmt = stmt.bind(
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
      b2i(payload.hardware?.intel_npu_available ?? undefined),
      b2iNullable(payload.hardware?.openvino_gpu_compile_ok),
      payload.hardware?.openvino_gpu_compile_device || null,
      b2i(payload.hardware?.openvino_gpu_fallback_active ?? undefined),
      payload.deployment?.mode || null,
      payload.deployment?.image_flavor || null,
      payload.deployment?.image_arch || null,
      payload.deployment?.app_branch || null,
      payload.deployment?.git_hash || null,
      normalizeInferenceHealthStatus(payload.runtime?.inference_health_status),
      safeRuntimeCount(payload.runtime?.inference_health_unhealthy_runtimes),
      safeRuntimeCount(payload.runtime?.inference_health_degraded_runtimes),
      safeRuntimeCount(payload.runtime?.inference_health_total_runtimes),
      normalizeRecoveryReason(payload.runtime?.last_recovery_reason),
      normalizeRecoveryStatus(payload.runtime?.last_recovery_status),
      country
    );

    const dailyStmt = c.env.DB.prepare(`
      INSERT INTO heartbeat_daily (
        report_date,
        installation_id_hash,
        last_reported_at,
        version,
        channel,
        platform,
        machine,
        inference_provider,
        configured_inference_provider,
        model,
        country,
        deployment_image,
        runtime_flavor,
        environment,
        feature_flags
      ) VALUES (date('now'), ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(report_date, installation_id_hash) DO UPDATE SET
        last_reported_at = excluded.last_reported_at,
        version = excluded.version,
        channel = excluded.channel,
        platform = excluded.platform,
        machine = excluded.machine,
        inference_provider = excluded.inference_provider,
        configured_inference_provider = excluded.configured_inference_provider,
        model = excluded.model,
        country = excluded.country,
        deployment_image = excluded.deployment_image,
        runtime_flavor = excluded.runtime_flavor,
        environment = excluded.environment,
        feature_flags = excluded.feature_flags
    `).bind(
      installationHash,
      payload.version,
      payload.deployment?.app_branch || null,
      payload.platform?.system || null,
      payload.platform?.machine || null,
      payload.runtime?.inference_provider_active || null,
      payload.runtime?.inference_provider_configured || null,
      payload.configuration?.model_type || null,
      country,
      payload.deployment?.image_flavor || null,
      payload.runtime?.model_runtime || null,
      payload.deployment?.mode || null,
      boundedJson({
        birdnet: payload.integrations?.birdnet_enabled ?? payload.configuration?.birdnet_enabled ?? false,
        birdweather: payload.integrations?.birdweather_enabled ?? payload.configuration?.birdweather_enabled ?? false,
        llm: payload.configuration?.llm_enabled ?? false,
        auto_video: payload.configuration?.auto_video_classification ?? false,
        ebird: payload.integrations?.ebird_enabled ?? false,
        inaturalist: payload.integrations?.inaturalist_enabled ?? false,
      }, 1024),
    );

    const retentionCleanup = c.env.DB.prepare(`
      DELETE FROM heartbeat_daily
      WHERE (report_date, installation_id_hash) IN (
        SELECT report_date, installation_id_hash FROM heartbeat_daily
        WHERE report_date < date('now', '-400 days')
        ORDER BY report_date
        LIMIT 1
      )
    `);
    await c.env.DB.batch([heartbeatStmt, dailyStmt, retentionCleanup]);

    return c.json({ status: 'ok' });
  } catch (e: any) {
    console.error('Telemetry error:', e);
    return c.json({ error: e.message }, 500);
  }
});

app.post('/health-issues', async (c) => {
  try {
    const parsed = await readBoundedJson(c.req.raw);
    if (!parsed.ok) return c.json({ error: parsed.error }, parsed.status);
    if (!parsed.value || typeof parsed.value !== 'object' || Array.isArray(parsed.value)) {
      return c.json({ error: 'JSON body must be an object' }, 400);
    }
    const payload = parsed.value as HealthIssuePayload;
    const country = c.req.raw.cf?.country || 'XX';

    if (!payload.installation_id) {
      return c.json({ error: 'Missing installation_id' }, 400);
    }
    if (!Array.isArray(payload.issues)) {
      return c.json({ error: 'Missing issues' }, 400);
    }
    if (!await withinIngestionRateLimit(
      c.env.HEALTH_RATE_LIMITER,
      c.req.raw,
      payload.installation_id,
      c.env.ALLOW_UNLIMITED_INGESTION_FOR_TESTS === 'true',
    )) {
      return c.json({ error: 'Rate limit exceeded' }, 429, { 'Retry-After': '60' });
    }

    const installationHash = await sha256Hex(payload.installation_id);
    const issues = payload.issues.slice(0, MAX_HEALTH_ISSUES_PER_REPORT);
    const suppliedReportId = safeText(payload.report_id, '', 64).toLowerCase();
    const isDeltaReport = /^[a-f0-9]{64}$/.test(suppliedReportId);
    const legacyIdentity = issues
      .map((issue) => [
        safeText(issue.fingerprint, '', 80),
        safeCount(issue.count),
        safeText(issue.first_seen_at, '', 80),
        safeText(issue.last_seen_at, '', 80),
        normalizeSeverity(issue.severity),
      ])
      .sort((a, b) => String(a[0]).localeCompare(String(b[0])));
    const clientReportId = isDeltaReport
      ? suppliedReportId
      : await sha256Hex(JSON.stringify(legacyIdentity));
    const reportId = await sha256Hex(`${installationHash}:${clientReportId}`);
    const runtime = payload.runtime ?? {};
    const integrations = payload.integrations ?? {};
    const diagnosticsWindow = payload.diagnostics_window ?? {};
    const windowSeverityCounts = typeof diagnosticsWindow.severity_counts === 'object' && diagnosticsWindow.severity_counts
      ? diagnosticsWindow.severity_counts as Record<string, unknown>
      : {};
    const payloadBase = {
      schema_version: safeText(payload.schema_version, 'unknown', 80),
      timestamp: safeText(payload.timestamp, '', 80),
      runtime: {
        model_type: safeText(runtime.model_type, '', 120) || null,
        inference_provider: safeText(runtime.inference_provider, '', 80) || null,
        image_execution_mode: safeText(runtime.image_execution_mode, '', 80) || null,
        bird_crop_detector_tier: safeText(runtime.bird_crop_detector_tier, '', 80) || null,
        auto_video_classification: runtime.auto_video_classification === true,
      },
      integrations: {
        birdnet_enabled: integrations.birdnet_enabled === true,
        birdweather_enabled: integrations.birdweather_enabled === true,
        ebird_enabled: integrations.ebird_enabled === true,
        inaturalist_enabled: integrations.inaturalist_enabled === true,
        llm_enabled: integrations.llm_enabled === true,
      },
      diagnostics_window: {
        captured_at: safeText(diagnosticsWindow.captured_at, '', 80) || null,
        total_events: safeCount(diagnosticsWindow.total_events),
        returned_events: safeCount(diagnosticsWindow.returned_events),
        severity_counts: {
          critical: safeCount(windowSeverityCounts.critical),
          error: safeCount(windowSeverityCounts.error),
          warning: safeCount(windowSeverityCounts.warning),
        },
      },
    };

    const schemaVersion = safeText(payload.schema_version, 'unknown', 80);
    const isEventReport = isDeltaReport && schemaVersion === '2026-07-25.health-issues.v3';
    const occurrenceUpdate = isDeltaReport
      ? 'health_issue_reports.occurrence_count + excluded.occurrence_count'
      : 'MAX(health_issue_reports.occurrence_count, excluded.occurrence_count)';
    const legacyIssueStmt = c.env.HEALTH_DB.prepare(`
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
      )
      SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, datetime('now'), datetime('now')
      WHERE NOT EXISTS (
        SELECT 1 FROM health_report_batches WHERE report_id = ?
      )
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
        occurrence_count = ${occurrenceUpdate},
        sample_context_json = excluded.sample_context_json,
        last_payload_json = excluded.last_payload_json,
        ip_country = excluded.ip_country,
        updated_at = datetime('now')
    `);
    const eventIssueStmt = c.env.HEALTH_DB.prepare(`
      WITH new_events(event_id) AS (
        SELECT DISTINCT CAST(value AS TEXT) FROM json_each(?)
        EXCEPT
        SELECT DISTINCT CAST(seen.value AS TEXT)
        FROM health_report_batches AS prior,
             json_each(COALESCE(prior.event_groups_json, '[]')) AS prior_group,
             json_each(COALESCE(json_extract(prior_group.value, '$.event_ids'), '[]')) AS seen
        WHERE prior.installation_id_hash = ?
          AND prior.report_date >= date('now', '-400 days')
          AND json_extract(prior_group.value, '$.fingerprint') = ?
      )
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
      )
      SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
             (SELECT COUNT(*) FROM new_events), ?, ?, ?, datetime('now'), datetime('now')
      WHERE NOT EXISTS (
        SELECT 1 FROM health_report_batches WHERE report_id = ?
      )
        AND EXISTS (SELECT 1 FROM new_events)
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

    const statements: D1PreparedStatement[] = [];
    const eventGroups: Array<{ fingerprint: string; severity: string; event_ids: string[] }> = [];
    let remainingEventIds = MAX_HEALTH_EVENTS_PER_REPORT;
    let accepted = 0;
    let eventCount = 0;
    const severityCounts = { critical: 0, error: 0, warning: 0 };
    for (const issue of issues) {
      const fingerprint = safeText(issue.fingerprint, '', 80);
      if (!fingerprint) continue;
      const eventIds = isEventReport
        ? Array.from(new Set(
            (Array.isArray(issue.event_ids) ? issue.event_ids : [])
              .map((value) => safeText(value, '', 64).toLowerCase())
              .filter((value) => /^[a-f0-9]{64}$/.test(value)),
          )).slice(0, remainingEventIds)
        : [];
      if (isEventReport && eventIds.length === 0) continue;
      remainingEventIds -= eventIds.length;

      const reportKey = await sha256Hex(`${installationHash}:${fingerprint}`);
      const count = isEventReport ? eventIds.length : safeCount(issue.count);
      const severity = normalizeSeverity(issue.severity) as keyof typeof severityCounts;
      const source = safeText(issue.source, 'unknown', 80);
      const component = safeText(issue.component, 'unknown', 80);
      const reasonCode = safeText(issue.reason_code, 'unknown_reason', 120);
      const stage = safeText(issue.stage, '', 80) || null;
      const firstSeenAt = safeText(issue.first_seen_at, '', 80) || null;
      const lastSeenAt = safeText(issue.last_seen_at, '', 80) || null;
      const sampleContext = sanitizeHealthContext(issue.sample_context ?? {}) ?? {};
      const sanitizedIssue = {
        fingerprint,
        source,
        component,
        reason_code: reasonCode,
        stage,
        severity,
        count,
        first_seen_at: firstSeenAt,
        last_seen_at: lastSeenAt,
        sample_context: sampleContext,
      };
      const commonBindings = [
        reportKey,
        installationHash,
        fingerprint,
        safeText(payload.version, 'unknown', 80),
        safeText(payload.platform?.system, '', 80) || null,
        safeText(payload.platform?.release, '', 120) || null,
        safeText(payload.platform?.machine, '', 80) || null,
        source,
        component,
        reasonCode,
        stage,
        severity,
        firstSeenAt,
        lastSeenAt,
      ];
      const trailingBindings = [
        boundedJson(sampleContext, 2048),
        boundedJson({ ...payloadBase, issue: sanitizedIssue }, MAX_JSON_CHARS),
        country,
        reportId,
      ];
      if (isEventReport) {
        eventGroups.push({ fingerprint, severity, event_ids: eventIds });
        statements.push(eventIssueStmt.bind(
          JSON.stringify(eventIds),
          installationHash,
          fingerprint,
          ...commonBindings,
          ...trailingBindings,
        ));
      } else {
        statements.push(legacyIssueStmt.bind(
          ...commonBindings,
          count,
          ...trailingBindings,
        ));
      }
      accepted++;
      eventCount += count;
      severityCounts[severity]++;
    }

    if (accepted === 0) {
      return c.json({ status: 'ok', accepted: 0, duplicate: false });
    }

    const expiredRows = await c.env.HEALTH_DB.prepare(`
      SELECT
        (SELECT COUNT(*) FROM (
          SELECT report_key FROM health_issue_reports
          WHERE updated_at < datetime('now', '-400 days')
          LIMIT 25
        )) AS issue_count,
        (SELECT COUNT(*) FROM (
          SELECT report_id FROM health_report_batches
          WHERE report_date < date('now', '-400 days')
          LIMIT 1
        )) AS batch_count
    `).first<{ issue_count: number; batch_count: number }>();
    const expiredIssueCount = Number(expiredRows?.issue_count ?? 0);
    const expiredBatchCount = Number(expiredRows?.batch_count ?? 0);
    const healthWriteUnits = HEALTH_BASE_WRITE_UNITS
      + accepted * HEALTH_ISSUE_WRITE_UNITS
      + expiredIssueCount * HEALTH_ISSUE_WRITE_UNITS
      + expiredBatchCount * 4;
    if (!await acquireDailyWriteBudget(c.env.DB, healthWriteUnits)) {
      return c.json({ error: 'Daily ingestion budget exhausted' }, 503, { 'Retry-After': '86400' });
    }

    const eventGroupsJson = JSON.stringify(eventGroups);
    const legacyBatchMarker = c.env.HEALTH_DB.prepare(`
      INSERT INTO health_report_batches (
        report_id,
        installation_id_hash,
        report_date,
        reported_at,
        app_version,
        schema_version,
        country,
        issue_group_count,
        event_count,
        critical_count,
        error_count,
        warning_count,
        event_groups_json
      ) VALUES (?, ?, date('now'), datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, NULL)
      ON CONFLICT(report_id) DO NOTHING
    `).bind(
      reportId,
      installationHash,
      safeText(payload.version, 'unknown', 80),
      schemaVersion,
      country,
      accepted,
      eventCount,
      severityCounts.critical,
      severityCounts.error,
      severityCounts.warning,
    );
    const eventBatchMarker = c.env.HEALTH_DB.prepare(`
      WITH incoming AS (
        SELECT DISTINCT
          CAST(json_extract(issue_group.value, '$.fingerprint') AS TEXT) AS fingerprint,
          CAST(json_extract(issue_group.value, '$.severity') AS TEXT) AS severity,
          CAST(event_id.value AS TEXT) AS event_id
        FROM json_each(?) AS issue_group,
             json_each(COALESCE(json_extract(issue_group.value, '$.event_ids'), '[]')) AS event_id
      ),
      previous AS (
        SELECT DISTINCT
          CAST(json_extract(issue_group.value, '$.fingerprint') AS TEXT) AS fingerprint,
          CAST(event_id.value AS TEXT) AS event_id
        FROM health_report_batches AS prior,
             json_each(COALESCE(prior.event_groups_json, '[]')) AS issue_group,
             json_each(COALESCE(json_extract(issue_group.value, '$.event_ids'), '[]')) AS event_id
        WHERE prior.installation_id_hash = ?
          AND prior.report_date >= date('now', '-400 days')
      ),
      new_keys AS (
        SELECT fingerprint, event_id FROM incoming
        EXCEPT
        SELECT fingerprint, event_id FROM previous
      ),
      new_events AS (
        SELECT incoming.fingerprint, incoming.severity, incoming.event_id
        FROM incoming
        INNER JOIN new_keys USING (fingerprint, event_id)
      )
      INSERT INTO health_report_batches (
        report_id,
        installation_id_hash,
        report_date,
        reported_at,
        app_version,
        schema_version,
        country,
        issue_group_count,
        event_count,
        critical_count,
        error_count,
        warning_count,
        event_groups_json
      )
      SELECT ?, ?, date('now'), datetime('now'), ?, ?, ?,
             COUNT(DISTINCT fingerprint),
             COUNT(*),
             COUNT(DISTINCT CASE WHEN severity = 'critical' THEN fingerprint END),
             COUNT(DISTINCT CASE WHEN severity = 'error' THEN fingerprint END),
             COUNT(DISTINCT CASE WHEN severity = 'warning' THEN fingerprint END),
             ?
      FROM new_events
      HAVING COUNT(*) > 0
      ON CONFLICT(report_id) DO NOTHING
    `).bind(
      eventGroupsJson,
      installationHash,
      reportId,
      installationHash,
      safeText(payload.version, 'unknown', 80),
      schemaVersion,
      country,
      eventGroupsJson,
    );
    const issueRetentionCleanup = c.env.HEALTH_DB.prepare(`
      DELETE FROM health_issue_reports
      WHERE report_key IN (
        SELECT report_key FROM health_issue_reports
        WHERE updated_at < datetime('now', '-400 days')
        ORDER BY updated_at
        LIMIT 25
      )
    `);
    const batchRetentionCleanup = c.env.HEALTH_DB.prepare(`
      DELETE FROM health_report_batches
      WHERE report_id IN (
        SELECT report_id FROM health_report_batches
        WHERE report_date < date('now', '-400 days')
        ORDER BY report_date
        LIMIT 1
      )
    `);
    statements.unshift(issueRetentionCleanup, batchRetentionCleanup);
    statements.push(isEventReport ? eventBatchMarker : legacyBatchMarker);

    const results = await c.env.HEALTH_DB.batch(statements);
    const markerResult = results[results.length - 1];
    const duplicate = Number(markerResult?.meta?.changes ?? 0) === 0;
    return c.json({ status: 'ok', accepted: duplicate ? 0 : accepted, duplicate });
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
