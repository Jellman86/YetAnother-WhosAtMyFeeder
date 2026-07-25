import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { after, before, test } from "node:test";
import { Miniflare } from "miniflare";

let mf;
let usageDb;
let healthDb;

async function applySql(db, path) {
  const sql = await readFile(new URL(path, import.meta.url), "utf8");
  const statements = sql
    .split(";")
    .map((statement) => statement.trim())
    .filter(Boolean)
    .map((statement) => db.prepare(statement));
  await db.batch(statements);
}

before(async () => {
  const script = await readFile(new URL("../.wrangler/dry-run/index.js", import.meta.url), "utf8");
  mf = new Miniflare({
    modules: true,
    script,
    compatibilityDate: "2024-01-01",
    bindings: { ALLOWED_ORIGIN: "*", ALLOW_UNLIMITED_INGESTION_FOR_TESTS: "true" },
    d1Databases: { DB: "test-usage", HEALTH_DB: "test-health" },
  });
  usageDb = await mf.getD1Database("DB");
  healthDb = await mf.getD1Database("HEALTH_DB");
  await applySql(usageDb, "../schema.sql");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await applySql(usageDb, "../migrations/telemetry/0001_daily_heartbeats.sql");
  }
  await applySql(healthDb, "../health_schema.sql");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await applySql(healthDb, "../migrations/health/0001_report_batches.sql");
  }
});

after(async () => {
  await mf?.dispose();
});

test("user metrics dashboard renders a bounded daily trend and distinct mode", async (t) => {
  await usageDb.prepare(`
    INSERT INTO heartbeat_daily (
      report_date, installation_id_hash, version, model, country, last_reported_at
    ) VALUES
      (date('now', '-1 day'), 'install-a', '2.15.0', 'model-a', 'GB', datetime('now', '-1 day')),
      (date('now'), 'install-a', '2.15.0', 'model-a', 'GB', datetime('now')),
      (date('now'), 'install-b', '2.15.0', 'model-b', 'US', datetime('now'))
  `).run();
  t.after(async () => {
    await usageDb.prepare(
      "DELETE FROM heartbeat_daily WHERE installation_id_hash IN ('install-a', 'install-b')",
    ).run();
  });

  const response = await mf.dispatchFetch("http://worker.test/dashboard?view=usage&days=7");
  const body = await response.text();

  assert.equal(response.status, 200);
  assert.match(body, /<title>YA-WAMF User Metrics<\/title>/);
  assert.match(body, /<body class="view-usage">/);
  assert.match(body, />User Metrics<\/a>/);
  assert.match(body, /Active installs by day/);
  assert.match(body, /aria-label="Daily active installs trend"/);
  assert.match(body, /aria-describedby="active-install-trend-data"/);
  assert.match(body, /id="active-install-trend-data">Daily values for the selected 7-day window/);
  assert.match(body, /<svg[^>]+class="trend-chart"/);
  assert.doesNotMatch(body, /Most-Recent Recovery Reasons/);
});

test("health data dashboard renders severity-led trends and concise issue details", async (t) => {
  await healthDb.prepare(`
    INSERT INTO health_issue_reports (
      report_key, installation_id_hash, issue_fingerprint, issue_component,
      issue_reason_code, severity, app_version, ip_country,
      occurrence_count, report_count, first_seen_at, last_seen_at, updated_at
    ) VALUES (
      'report-health', 'install-health', 'fingerprint-health', 'event_processor',
      'stage_failure', 'critical', '2.15.0', 'GB',
      4, 1, datetime('now'), datetime('now'), datetime('now')
    )
  `).run();
  await healthDb.prepare(`
    INSERT INTO health_report_batches (
      report_id, installation_id_hash, report_date, reported_at, event_groups_json
    ) VALUES (
      'batch-health', 'install-health', date('now'), datetime('now'),
      '[{"fingerprint":"fingerprint-health","event_ids":["event-a","event-b"]}]'
    )
  `).run();
  t.after(async () => {
    await healthDb.prepare(
      "DELETE FROM health_issue_reports WHERE installation_id_hash = 'install-health'",
    ).run();
    await healthDb.prepare(
      "DELETE FROM health_report_batches WHERE installation_id_hash = 'install-health'",
    ).run();
  });

  const response = await mf.dispatchFetch("http://worker.test/dashboard?view=health&days=7");
  const body = await response.text();

  assert.equal(response.status, 200);
  assert.match(body, /<title>YA-WAMF Health Data<\/title>/);
  assert.match(body, /<body class="view-health">/);
  assert.match(body, />Health Data<\/a>/);
  assert.match(body, /Reports by day/);
  assert.match(body, /aria-label="Daily health reports trend"/);
  assert.match(body, /aria-describedby="health-report-trend-data"/);
  assert.match(body, /severity-pill severity-critical/);
  assert.match(body, /Top recurring issues/);
  assert.match(body, /class="table-scroll" tabindex="0" role="region" aria-label="Top recurring issues; scroll horizontally for all columns"/);
  assert.doesNotMatch(body, /Usage Geography/);
});

test("heartbeat writes one bounded daily snapshot per installation", async () => {
  await usageDb.prepare(
    "INSERT INTO heartbeat_daily (report_date, installation_id_hash, last_reported_at) VALUES ('2020-01-01', 'expired', '2020-01-01T00:00:00Z')",
  ).run();
  const base = {
    installation_id: "test-installation",
    timestamp: "2026-07-25T10:00:00Z",
    version: "2.15.0",
    platform: "linux",
    machine: "x86_64",
  };
  for (const payload of [base, { ...base, timestamp: "2026-07-25T12:00:00Z", version: "2.15.1" }]) {
    const response = await mf.dispatchFetch("http://worker.test/heartbeat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    assert.equal(response.status, 200, await response.text());
  }

  const result = await usageDb.prepare(
    "SELECT COUNT(*) AS rows, MAX(version) AS version, MAX(installation_id_hash) AS installation_id_hash FROM heartbeat_daily",
  ).first();
  assert.equal(result.rows, 1);
  assert.equal(result.version, "2.15.1");
  assert.equal(result.installation_id_hash.length, 64);
  assert.notEqual(result.installation_id_hash, base.installation_id);
});

test("heartbeat bounds runtime health values and dashboard excludes hostile legacy categories", async (t) => {
  const testVersion = "runtime-normalization-test";
  t.after(async () => {
    await usageDb.prepare("DELETE FROM heartbeats WHERE app_version = ?").bind(testVersion).run();
    await usageDb.prepare("DELETE FROM heartbeat_daily WHERE version = ?").bind(testVersion).run();
  });

  const response = await mf.dispatchFetch("http://worker.test/heartbeat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      installation_id: "runtime-normalization-install",
      timestamp: "2026-07-25T12:00:00Z",
      version: testVersion,
      runtime: {
        inference_health_status: "attacker-controlled-status",
        inference_health_unhealthy_runtimes: -5,
        inference_health_degraded_runtimes: 50000,
        inference_health_total_runtimes: "not-a-number",
        last_recovery_reason: "<script>alert(1)</script>",
        last_recovery_status: "attacker-controlled-status",
      },
    }),
  });
  assert.equal(response.status, 200, await response.text());

  const stored = await usageDb.prepare(`
    SELECT inference_health_status, inference_health_unhealthy_runtimes,
           inference_health_degraded_runtimes, inference_health_total_runtimes,
           last_recovery_reason, last_recovery_status
    FROM heartbeats WHERE installation_id = 'runtime-normalization-install'
  `).first();
  assert.deepEqual(stored, {
    inference_health_status: null,
    inference_health_unhealthy_runtimes: 0,
    inference_health_degraded_runtimes: 1000,
    inference_health_total_runtimes: null,
    last_recovery_reason: null,
    last_recovery_status: null,
  });

  const validResponse = await mf.dispatchFetch("http://worker.test/heartbeat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      installation_id: "runtime-normalization-valid-install",
      timestamp: "2026-07-25T12:00:00Z",
      version: testVersion,
      runtime: {
        inference_health_status: "Degraded",
        inference_health_unhealthy_runtimes: 1,
        inference_health_degraded_runtimes: 2,
        inference_health_total_runtimes: 3,
        last_recovery_reason: "GPU_UNHEALTHY_FALLBACK",
        last_recovery_status: "Recovered",
      },
    }),
  });
  assert.equal(validResponse.status, 200, await validResponse.text());
  const validStored = await usageDb.prepare(`
    SELECT inference_health_status, inference_health_unhealthy_runtimes,
           inference_health_degraded_runtimes, inference_health_total_runtimes,
           last_recovery_reason, last_recovery_status
    FROM heartbeats WHERE installation_id = 'runtime-normalization-valid-install'
  `).first();
  assert.deepEqual(validStored, {
    inference_health_status: "degraded",
    inference_health_unhealthy_runtimes: 1,
    inference_health_degraded_runtimes: 2,
    inference_health_total_runtimes: 3,
    last_recovery_reason: "gpu_unhealthy_fallback",
    last_recovery_status: "recovered",
  });

  await usageDb.prepare(`
    WITH RECURSIVE categories(n) AS (
      SELECT 1 UNION ALL SELECT n + 1 FROM categories WHERE n < 20
    )
    INSERT INTO heartbeats (
      installation_id, app_version, inference_health_status,
      last_recovery_reason, last_recovery_status, last_seen
    )
    SELECT 'legacy-hostile-' || n, ?, 'hostile_status_' || n,
           '<SCRIPT>' || n, 'recovered', datetime('now')
    FROM categories
  `).bind(testVersion).run();

  const dashboard = await mf.dispatchFetch("http://worker.test/dashboard?view=health&days=30");
  const body = await dashboard.text();
  assert.equal(dashboard.status, 200);
  assert.doesNotMatch(body, /hostile_status_|&lt;script&gt;|<script>/i);
  assert.match(body, /gpu unhealthy fallback/);
});

test("ingestion rejects oversized bodies before D1 writes", async () => {
  const usageBefore = await usageDb.prepare("SELECT COUNT(*) AS rows FROM heartbeats").first();
  const healthBefore = await healthDb.prepare("SELECT COUNT(*) AS rows FROM health_report_batches").first();
  const body = JSON.stringify({
    installation_id: "oversized-installation",
    issues: [],
    padding: "x".repeat(128 * 1024),
  });

  for (const path of ["heartbeat", "health-issues"]) {
    const response = await mf.dispatchFetch(`http://worker.test/${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    });
    assert.equal(response.status, 413, await response.text());
  }

  const usageAfter = await usageDb.prepare("SELECT COUNT(*) AS rows FROM heartbeats").first();
  const healthAfter = await healthDb.prepare("SELECT COUNT(*) AS rows FROM health_report_batches").first();
  assert.deepEqual(usageAfter, usageBefore);
  assert.deepEqual(healthAfter, healthBefore);
});

test("ingestion fails closed when rate-limit bindings are unavailable", async () => {
  const script = await readFile(new URL("../.wrangler/dry-run/index.js", import.meta.url), "utf8");
  const guarded = new Miniflare({
    modules: true,
    script,
    compatibilityDate: "2024-01-01",
    bindings: { ALLOWED_ORIGIN: "*" },
    d1Databases: { DB: "guarded-usage", HEALTH_DB: "guarded-health" },
  });
  try {
    const response = await guarded.dispatchFetch("http://worker.test/heartbeat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ installation_id: "guarded-installation" }),
    });
    assert.equal(response.status, 500);
    assert.match(await response.text(), /rate limiter is unavailable/i);
  } finally {
    await guarded.dispose();
  }
});

test("replayed health report is idempotent and creates one trend batch", async () => {
  await healthDb.prepare(`
    INSERT INTO health_report_batches (
      report_id, installation_id_hash, report_date, reported_at
    ) VALUES ('expired', 'expired', '2020-01-01', '2020-01-01T00:00:00Z')
  `).run();
  const payload = {
    schema_version: "2026-07-25.health-issues.v2",
    report_id: "a".repeat(64),
    installation_id: "test-installation",
    timestamp: "2026-07-25T12:00:00Z",
    version: "2.15.1",
    issues: [{
      fingerprint: "b".repeat(32),
      source: "backend",
      component: "video_classifier",
      stage: "classify",
      reason_code: "video_timeout",
      severity: "error",
      count: 2,
      first_seen_at: "2026-07-25T11:00:00Z",
      last_seen_at: "2026-07-25T11:30:00Z",
      sample_context: {
        active_provider: "npu",
        secret_path: "/config/private/model.bin",
      },
      unexpected_secret: "must-not-be-stored",
    }],
  };

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await mf.dispatchFetch("http://worker.test/health-issues", {
      method: "POST",
      headers: { "content-type": "application/json", "cf-ipcountry": "GB" },
      body: JSON.stringify(payload),
    });
    assert.equal(response.status, 200, await response.text());
  }

  const batches = await healthDb.prepare("SELECT COUNT(*) AS rows FROM health_report_batches").first();
  const issue = await healthDb.prepare(
    "SELECT occurrence_count, report_count, sample_context_json, last_payload_json FROM health_issue_reports",
  ).first();
  assert.deepEqual(batches, { rows: 1 });
  assert.equal(issue.occurrence_count, 2);
  assert.equal(issue.report_count, 1);
  assert.deepEqual(JSON.parse(issue.sample_context_json), { active_provider: "npu" });
  assert.equal(issue.last_payload_json.includes("private"), false);
  assert.equal(issue.last_payload_json.includes("must-not-be-stored"), false);
});

test("v3 event identities remain idempotent across restart-shaped overlapping reports", async () => {
  const fingerprint = "restart-overlap";
  const base = {
    schema_version: "2026-07-25.health-issues.v3",
    installation_id: "restart-installation",
    timestamp: "2026-07-25T12:00:00Z",
    version: "2.15.1",
    issues: [{
      fingerprint,
      source: "backend",
      component: "video_classifier",
      reason_code: "video_timeout",
      severity: "error",
      count: 2,
      event_ids: ["1".repeat(64), "2".repeat(64)],
    }],
  };
  const first = { ...base, report_id: "d".repeat(64) };
  const afterRestart = structuredClone(base);
  afterRestart.report_id = "e".repeat(64);
  afterRestart.issues[0].count = 3;
  afterRestart.issues[0].event_ids.push("3".repeat(64));

  for (const payload of [first, afterRestart, afterRestart]) {
    const response = await mf.dispatchFetch("http://worker.test/health-issues", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    assert.equal(response.status, 200, await response.text());
  }

  const issue = await healthDb.prepare(
    "SELECT occurrence_count, report_count FROM health_issue_reports WHERE issue_fingerprint = ?",
  ).bind(fingerprint).first();
  const batches = await healthDb.prepare(
    "SELECT event_count FROM health_report_batches WHERE schema_version = ? ORDER BY reported_at, report_id",
  ).bind("2026-07-25.health-issues.v3").all();
  assert.deepEqual(issue, { occurrence_count: 3, report_count: 2 });
  assert.deepEqual(batches.results.map((row) => row.event_count).sort((a, b) => a - b), [1, 2]);
});

test("oversized allowed context remains bounded valid JSON", async () => {
  const allowedKeys = [
    "active_provider", "attempt", "backend", "batch_limit", "cache_enabled",
    "circuit_failures", "circuit_open", "compile_device", "compile_ok",
    "configured_provider", "cuda_available", "device", "error_type",
    "failure_count", "fallback_active", "inference_backend", "intel_gpu_available",
    "intel_npu_available", "kind", "lease_age_seconds",
  ];
  const sampleContext = Object.fromEntries(allowedKeys.map((key) => [key, "x".repeat(500)]));
  const response = await mf.dispatchFetch("http://worker/health-issues", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      schema_version: "2026-07-25.health-issues.v2",
      report_id: "c".repeat(64),
      installation_id: "install-context-limit",
      timestamp: "2026-07-25T14:00:00Z",
      version: "2.15.0",
      issues: [{
        fingerprint: "fp-context-limit",
        source: "test",
        component: "telemetry",
        reason_code: "context_limit",
        severity: "warning",
        count: 999999,
        sample_context: sampleContext,
      }],
    }),
  });
  assert.equal(response.status, 200);

  const stored = await healthDb.prepare(
    "SELECT occurrence_count, sample_context_json, last_payload_json FROM health_issue_reports WHERE issue_fingerprint = ?",
  ).bind("fp-context-limit").first();
  assert.equal(stored.occurrence_count, 250);
  assert.ok(stored.sample_context_json.length <= 2048);
  assert.ok(stored.last_payload_json.length <= 8192);
  assert.doesNotThrow(() => JSON.parse(stored.sample_context_json));
  assert.doesNotThrow(() => JSON.parse(stored.last_payload_json));
});

test("unchanged legacy snapshots without report IDs are also idempotent", async () => {
  const payload = {
    schema_version: "2026-05-03.health-issues.v1",
    installation_id: "legacy-installation",
    timestamp: "2026-07-25T12:00:00Z",
    version: "2.14.0",
    issues: [{
      fingerprint: "c".repeat(32),
      source: "backend",
      component: "event_processor",
      reason_code: "legacy_failure",
      severity: "warning",
      count: 3,
      first_seen_at: "2026-07-25T11:00:00Z",
      last_seen_at: "2026-07-25T11:30:00Z",
    }],
  };

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await mf.dispatchFetch("http://worker.test/health-issues", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    assert.equal(response.status, 200, await response.text());
  }

  const batches = await healthDb.prepare(
    "SELECT COUNT(*) AS rows FROM health_report_batches WHERE schema_version = ?",
  ).bind("2026-05-03.health-issues.v1").first();
  const issue = await healthDb.prepare(
    "SELECT occurrence_count, report_count FROM health_issue_reports WHERE issue_fingerprint = ?",
  ).bind("c".repeat(32)).first();
  assert.deepEqual(batches, { rows: 1 });
  assert.deepEqual(issue, { occurrence_count: 3, report_count: 1 });

  const expandedPayload = structuredClone(payload);
  expandedPayload.timestamp = "2026-07-25T13:00:00Z";
  expandedPayload.issues[0].count = 4;
  expandedPayload.issues[0].last_seen_at = "2026-07-25T12:30:00Z";
  const expandedResponse = await mf.dispatchFetch("http://worker.test/health-issues", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(expandedPayload),
  });
  assert.equal(expandedResponse.status, 200, await expandedResponse.text());

  const expandedIssue = await healthDb.prepare(
    "SELECT occurrence_count, report_count FROM health_issue_reports WHERE issue_fingerprint = ?",
  ).bind("c".repeat(32)).first();
  assert.deepEqual(expandedIssue, { occurrence_count: 4, report_count: 2 });
});

test("health ingestion removes bounded expired detail and marker rows", async () => {
  await healthDb.prepare(
    "UPDATE health_issue_reports SET updated_at = '2020-01-01T00:00:00Z' WHERE issue_fingerprint = ?",
  ).bind("fp-context-limit").run();
  await healthDb.prepare(`
    INSERT INTO health_report_batches (
      report_id, installation_id_hash, report_date, reported_at
    ) VALUES ('retention-expired', 'expired', '2020-01-01', '2020-01-01T00:00:00Z')
  `).run();

  const response = await mf.dispatchFetch("http://worker.test/health-issues", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      schema_version: "2026-07-25.health-issues.v2",
      report_id: "f".repeat(64),
      installation_id: "retention-trigger",
      version: "2.15.1",
      issues: [{ fingerprint: "retention-new", severity: "warning", count: 1 }],
    }),
  });
  assert.equal(response.status, 200, await response.text());

  const expiredIssue = await healthDb.prepare(
    "SELECT COUNT(*) AS rows FROM health_issue_reports WHERE issue_fingerprint = ?",
  ).bind("fp-context-limit").first();
  const expiredMarker = await healthDb.prepare(
    "SELECT COUNT(*) AS rows FROM health_report_batches WHERE report_id = 'retention-expired'",
  ).first();
  assert.deepEqual(expiredIssue, { rows: 0 });
  assert.deepEqual(expiredMarker, { rows: 0 });
});

test("shared daily budget rejects ingestion before telemetry rows are written", async () => {
  await usageDb.prepare(
    "UPDATE ingestion_daily_budget SET write_units = 39999 WHERE budget_date = date('now')",
  ).run();
  const before = await usageDb.prepare("SELECT COUNT(*) AS rows FROM heartbeats").first();
  try {
    const response = await mf.dispatchFetch("http://worker.test/heartbeat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ installation_id: "over-budget-installation", version: "2.15.1" }),
    });
    assert.equal(response.status, 503, await response.text());
    assert.equal(response.headers.get("retry-after"), "86400");
    const after = await usageDb.prepare("SELECT COUNT(*) AS rows FROM heartbeats").first();
    assert.deepEqual(after, before);
  } finally {
    await usageDb.prepare(
      "UPDATE ingestion_daily_budget SET write_units = 0 WHERE budget_date = date('now')",
    ).run();
  }
});
