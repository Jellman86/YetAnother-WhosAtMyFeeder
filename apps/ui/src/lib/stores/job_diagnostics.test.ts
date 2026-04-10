import { beforeEach, describe, expect, it, vi } from 'vitest';
import { jobDiagnosticsStore } from './job_diagnostics.svelte';
import errorsPageSource from '../pages/Errors.svelte?raw';

describe('jobDiagnosticsStore', () => {
    beforeEach(() => {
        jobDiagnosticsStore.clear();
        jobDiagnosticsStore.clearBundles();
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-03-06T12:00:00.000Z'));
    });

    it('deduplicates repeated errors into one grouped record', () => {
        jobDiagnosticsStore.recordError({
            source: 'sse',
            component: 'event_pipeline',
            stage: 'classify_snapshot',
            reasonCode: 'stage_timeout',
            message: 'Stage timed out',
            severity: 'error',
            eventId: 'evt-1'
        });
        jobDiagnosticsStore.recordError({
            source: 'sse',
            component: 'event_pipeline',
            stage: 'classify_snapshot',
            reasonCode: 'stage_timeout',
            message: 'Stage timed out',
            severity: 'error',
            eventId: 'evt-2'
        });

        expect(jobDiagnosticsStore.groups.length).toBe(1);
        expect(jobDiagnosticsStore.groups[0].count).toBe(2);
        expect(jobDiagnosticsStore.groups[0].sampleEventIds).toEqual(['evt-2', 'evt-1']);
    });

    it('ingests health payload and records grouped health diagnostics', () => {
        jobDiagnosticsStore.ingestHealth({
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: {
                pressure_level: 'critical',
                in_flight: 200,
                in_flight_capacity: 200
            },
            event_pipeline: {
                critical_failures: 2,
                stage_timeouts: {
                    classify_snapshot: 4
                },
                stage_failures: {},
                last_stage_timeout: {
                    event_id: 'evt-timeout-9',
                    stage: 'classify_snapshot',
                    timeout_seconds: 30
                },
                last_drop: {
                    event_id: 'evt-timeout-9',
                    reason: 'classify_snapshot_unavailable'
                }
            },
            notification_dispatcher: {
                dropped_jobs: 3
            },
            video_classifier: {
                circuit_open: true,
                open_until: '2026-03-06T12:15:00.000Z',
                failure_count: 8,
                pending: 21,
                active: 0
            },
            db_pool: {
                acquire_wait_max_ms: 9000
            },
            startup_warnings: [
                { phase: 'mqtt_service_task_start', error: 'connection retrying' }
            ]
        });

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(1);
        const timeoutGroup = jobDiagnosticsStore.groups.find(
            (group) =>
                group.component === 'event_pipeline'
                && group.stage === 'classify_snapshot'
                && group.reasonCode === 'stage_timeout'
        );
        expect(timeoutGroup).toBeTruthy();
        expect(timeoutGroup?.count).toBe(1);
        const latestTimeoutGroup = jobDiagnosticsStore.groups.find(
            (group) => group.reasonCode === 'last_stage_timeout'
        );
        expect(latestTimeoutGroup?.sampleEventIds).toContain('evt-timeout-9');
        expect(jobDiagnosticsStore.groups.some((group) => group.component === 'mqtt')).toBe(true);
        expect(jobDiagnosticsStore.groups.some((group) => group.component === 'db_pool')).toBe(true);
        expect(
            jobDiagnosticsStore.groups.some(
                (group) =>
                    group.component === 'video_classifier'
                    && group.reasonCode === 'circuit_open'
            )
        ).toBe(true);
    });

    it('captures a new health snapshot when video classifier circuit state changes', () => {
        const base = {
            status: 'ok',
            startup_instance_id: 'abc123',
            mqtt: { pressure_level: 'normal' },
            event_pipeline: { critical_failures: 0, stage_timeouts: {}, stage_failures: {} },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 },
            startup_warnings: [],
            video_classifier: {
                circuit_open: false,
                open_until: null,
                failure_count: 0,
                pending: 0,
                active: 0
            }
        };

        jobDiagnosticsStore.ingestHealth(base);
        jobDiagnosticsStore.ingestHealth({
            ...base,
            video_classifier: {
                circuit_open: true,
                open_until: '2026-03-06T12:15:00.000Z',
                failure_count: 8,
                pending: 21,
                active: 0
            }
        });

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(2);
        expect(
            jobDiagnosticsStore.healthSnapshots[0].payload.video_classifier
        ).toMatchObject({
            circuit_open: true,
            failure_count: 8,
            pending: 21
        });
    });

    it('captures live image coordinator recovery in exported health snapshots', () => {
        jobDiagnosticsStore.ingestHealth({
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: { pressure_level: 'normal' },
            event_pipeline: { critical_failures: 0, stage_timeouts: {}, stage_failures: {} },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 },
            startup_warnings: [],
            ml: {
                status: 'ok',
                live_image: {
                    status: 'degraded',
                    pressure_level: 'critical',
                    max_concurrent: 2,
                    in_flight: 2,
                    queued: 3,
                    admission_timeout_seconds: 0.25,
                    admission_timeouts: 0,
                    abandoned: 1,
                    late_completions_ignored: 1,
                    oldest_running_age_seconds: 0.41,
                    recovery_active: true
                },
                background_image: {
                    queued: 1,
                    background_throttled: true
                }
            }
        });

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(1);
        expect(jobDiagnosticsStore.healthSnapshots[0].payload.ml).toMatchObject({
            status: 'ok',
            live_image: {
                status: 'degraded',
                pressure_level: 'critical',
                abandoned: 1,
                recovery_active: true
            },
            background_image: {
                queued: 1,
                background_throttled: true
            }
        });
        expect(
            jobDiagnosticsStore.groups.some(
                (group) =>
                    group.component === 'ml_live_image'
                    && group.reasonCode === 'recovery_active'
            )
        ).toBe(true);
    });

    it('captures subprocess worker pool breaker state in exported health snapshots', () => {
        jobDiagnosticsStore.ingestHealth({
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: { pressure_level: 'normal' },
            event_pipeline: { critical_failures: 0, stage_timeouts: {}, stage_failures: {} },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 },
            startup_warnings: [],
            ml: {
                status: 'ok',
                live_image: {
                    status: 'degraded',
                    pressure_level: 'critical',
                    max_concurrent: 2,
                    in_flight: 2,
                    queued: 2,
                    recovery_active: true,
                    recovery_reason: 'worker_circuit_open'
                },
                background_image: {
                    status: 'degraded',
                    queued: 4,
                    background_throttled: true
                },
                execution_mode: 'subprocess',
                worker_pools: {
                    late_results_ignored: 3,
                    live: {
                        workers: 2,
                        restarts: 4,
                        last_exit_reason: 'heartbeat_timeout',
                        circuit_open: true
                    },
                    background: {
                        workers: 1,
                        restarts: 1,
                        last_exit_reason: 'deadline_exceeded',
                        circuit_open: false
                    }
                }
            }
        });

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(1);
        expect(jobDiagnosticsStore.healthSnapshots[0].payload.ml).toMatchObject({
            execution_mode: 'subprocess',
            worker_pools: {
                late_results_ignored: 3,
                live: {
                    restarts: 4,
                    last_exit_reason: 'heartbeat_timeout',
                    circuit_open: true
                },
                background: {
                    restarts: 1,
                    last_exit_reason: 'deadline_exceeded',
                    circuit_open: false
                }
            }
        });
        expect(
            jobDiagnosticsStore.groups.some(
                (group) =>
                    group.component === 'ml_live_image'
                    && group.reasonCode === 'recovery_active'
                    && group.message === 'Live image classifier is recovering worker processes'
            )
        ).toBe(true);
        expect(jobDiagnosticsStore.healthSnapshots[0].payload.ml.live_image).toMatchObject({
            recovery_reason: 'worker_circuit_open'
        });
    });

    it('preserves worker runtime recovery evidence and video pool state in health snapshots', () => {
        jobDiagnosticsStore.ingestHealth({
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: { pressure_level: 'normal' },
            event_pipeline: { critical_failures: 0, stage_timeouts: {}, stage_failures: {} },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 },
            startup_warnings: [],
            ml: {
                status: 'ok',
                execution_mode: 'subprocess',
                live_image: {
                    status: 'degraded',
                    pressure_level: 'critical',
                    recovery_active: true,
                    recovery_reason: 'worker_circuit_open'
                },
                background_image: {
                    status: 'ok',
                    queued: 0,
                    background_throttled: false
                },
                worker_pools: {
                    late_results_ignored: 1,
                    live: {
                        workers: 2,
                        restarts: 3,
                        last_exit_reason: 'startup_timeout',
                        circuit_open: false,
                        last_runtime_recovery: {
                            failed_provider: 'GPU',
                            recovered_provider: 'intel_cpu'
                        },
                        last_stderr_excerpt: 'OpenVINO compile failed'
                    },
                    background: {
                        workers: 1,
                        restarts: 0,
                        last_exit_reason: null,
                        circuit_open: false
                    },
                    video: {
                        workers: 1,
                        restarts: 2,
                        last_exit_reason: 'deadline_exceeded',
                        circuit_open: true,
                        last_stderr_excerpt: 'video worker stderr'
                    }
                }
            }
        });

        expect(jobDiagnosticsStore.healthSnapshots[0].payload.ml.worker_pools.live).toMatchObject({
            last_runtime_recovery: {
                failed_provider: 'GPU',
                recovered_provider: 'intel_cpu'
            },
            last_stderr_excerpt: 'OpenVINO compile failed'
        });
        expect(jobDiagnosticsStore.healthSnapshots[0].payload.ml.worker_pools.video).toMatchObject({
            workers: 1,
            restarts: 2,
            last_exit_reason: 'deadline_exceeded',
            circuit_open: true,
            last_stderr_excerpt: 'video worker stderr'
        });
    });

    it('exports incident workspace bundle sections without dropping grouped evidence', () => {
        jobDiagnosticsStore.recordError({
            source: 'runtime',
            component: 'frontend',
            reasonCode: 'uncaught_exception',
            message: 'Owner page crashed',
            severity: 'error',
            eventId: 'evt-ui-1',
            context: { route: '/jobs?tab=errors' }
        });
        jobDiagnosticsStore.ingestHealth({
            status: 'degraded',
            startup_instance_id: 'abc123',
            startup_warnings: [],
            mqtt: { pressure_level: 'normal' },
            event_pipeline: { critical_failures: 0, stage_timeouts: {}, stage_failures: {} },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 }
        });

        const payload = jobDiagnosticsStore.exportJson();

        expect(payload.schema_version).toBe(3);
        expect(payload.environment).toMatchObject({
            app_version: expect.any(String),
            git_hash: expect.any(String)
        });
        expect(payload.health).toBeTruthy();
        expect(payload.client_context).toBeTruthy();
        expect(payload.workspace_snapshot).toBeNull();
        expect(payload.incidents).toEqual({ current: [], recent: [] });
        expect(payload.timeline).toEqual([]);
        expect(payload.raw_evidence).toMatchObject({
            error_groups: expect.any(Array),
            health_snapshots: expect.any(Array)
        });
        expect((payload.raw_evidence as { error_groups: unknown[] }).error_groups).toHaveLength(2);
    });

    it('exports focused backend diagnostics when workspace payload is provided', () => {
        const payload = jobDiagnosticsStore.exportJson({
            workspacePayload: {
            workspace_schema_version: '2026-03-12.owner-incident-workspace.v1',
            backend_diagnostics: {
                captured_at: '2026-04-01T20:29:40Z',
                capacity: 500,
                total_events: 2,
                filtered_events: 2,
                returned_events: 2,
                severity_counts: { error: 2 },
                component_counts: { auto_video_classifier: 2 },
                events: [
                    {
                        id: 'diag-video-open',
                        component: 'auto_video_classifier',
                        reason_code: 'video_circuit_opened',
                        severity: 'error',
                        message: 'Video classification circuit opened after repeated failures',
                        timestamp: '2026-04-01T20:28:00Z',
                        event_id: 'evt-video-1',
                        correlation_key: 'video:circuit_open',
                        worker_pool: 'video',
                        context: { last_error: 'video_timeout', failure_count: 5 }
                    },
                    {
                        id: 'diag-video-timeout',
                        component: 'auto_video_classifier',
                        reason_code: 'video_timeout',
                        severity: 'error',
                        message: 'Video classification exceeded the configured timeout',
                        timestamp: '2026-04-01T20:27:00Z',
                        event_id: 'evt-video-1',
                        correlation_key: 'video:evt-video-1',
                        worker_pool: 'video',
                        context: { timeout_seconds: 30 }
                    }
                ]
            },
            focused_diagnostics: {
                video_classifier: {
                    circuit_open: true,
                    open_until: '2026-04-01T20:42:13.797562+00:00',
                    failure_count: 5,
                    pending: 69,
                    active: 1,
                    latest_circuit_opened: {
                        id: 'diag-video-open',
                        component: 'auto_video_classifier',
                        reason_code: 'video_circuit_opened',
                        severity: 'error',
                        message: 'Video classification circuit opened after repeated failures',
                        timestamp: '2026-04-01T20:28:00Z',
                        context: { last_error: 'video_timeout', failure_count: 5 }
                    },
                    recent_events: [
                        {
                            id: 'diag-video-open',
                            component: 'auto_video_classifier',
                            reason_code: 'video_circuit_opened',
                            severity: 'error',
                            message: 'Video classification circuit opened after repeated failures',
                            timestamp: '2026-04-01T20:28:00Z',
                            context: { last_error: 'video_timeout', failure_count: 5 }
                        }
                    ]
                }
            },
            health: {
                status: 'degraded'
            },
            classifier: {
                active_provider: 'intel_gpu'
            },
            startup_warnings: []
            } as any,
            currentIssues: [{ id: 'issue-1', title: 'Active issue' }],
            recentIncidents: [{ id: 'issue-2', title: 'Resolved issue' }]
        });

        expect(payload.backend_diagnostics).toMatchObject({
            returned_events: 2,
            events: expect.any(Array)
        });
        expect(payload.focused_diagnostics).toMatchObject({
            video_classifier: {
                circuit_open: true,
                failure_count: 5,
                latest_circuit_opened: {
                    context: { last_error: 'video_timeout' }
                }
            }
        });
        expect(payload.classifier).toMatchObject({
            active_provider: 'intel_gpu'
        });
        expect(payload.workspace_snapshot).toMatchObject({
            workspace_schema_version: '2026-03-12.owner-incident-workspace.v1'
        });
        expect(payload.incidents).toEqual({
            current: [{ id: 'issue-1', title: 'Active issue' }],
            recent: [{ id: 'issue-2', title: 'Resolved issue' }]
        });
    });

    it('captures bundle report notes without clearing live diagnostics', () => {
        jobDiagnosticsStore.recordError({
            source: 'runtime',
            component: 'frontend',
            reasonCode: 'uncaught_exception',
            message: 'Owner page crashed',
            severity: 'error'
        });

        const bundle = jobDiagnosticsStore.captureBundle('incident repro', 'repro after database reset');

        expect(bundle).toBeTruthy();
        expect(jobDiagnosticsStore.groups).toHaveLength(1);
        expect(bundle?.payload.report).toMatchObject({
            label: 'incident repro',
            notes: 'repro after database reset',
            schema_version: 3
        });
    });

    it('captures a new health snapshot when subprocess worker breaker state changes', () => {
        const base = {
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: { pressure_level: 'normal' },
            event_pipeline: { critical_failures: 0, stage_timeouts: {}, stage_failures: {} },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 },
            startup_warnings: [],
            ml: {
                status: 'ok',
                live_image: {
                    status: 'ok',
                    pressure_level: 'normal',
                    max_concurrent: 2,
                    in_flight: 0,
                    queued: 0,
                    recovery_active: false
                },
                background_image: {
                    status: 'ok',
                    queued: 0,
                    background_throttled: false
                },
                execution_mode: 'subprocess',
                worker_pools: {
                    late_results_ignored: 0,
                    live: {
                        workers: 2,
                        restarts: 0,
                        last_exit_reason: null,
                        circuit_open: false
                    },
                    background: {
                        workers: 1,
                        restarts: 0,
                        last_exit_reason: null,
                        circuit_open: false
                    }
                }
            }
        };

        jobDiagnosticsStore.ingestHealth(base);
        jobDiagnosticsStore.ingestHealth({
            ...base,
            ml: {
                ...base.ml,
                live_image: {
                    ...base.ml.live_image,
                    status: 'degraded',
                    recovery_active: true
                },
                worker_pools: {
                    ...base.ml.worker_pools,
                    late_results_ignored: 2,
                    live: {
                        ...base.ml.worker_pools.live,
                        restarts: 3,
                        last_exit_reason: 'worker_crash',
                        circuit_open: true
                    }
                }
            }
        });

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(2);
    });

    it('deduplicates identical consecutive health snapshots and exports JSON', () => {
        const payload = {
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: { pressure_level: 'high' },
            event_pipeline: { critical_failures: 1, stage_timeouts: {}, stage_failures: {} },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 },
            startup_warnings: []
        };
        jobDiagnosticsStore.ingestHealth(payload);
        jobDiagnosticsStore.ingestHealth(payload);

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(1);

        const exported = jobDiagnosticsStore.exportJson();
        const summary = exported.summary as Record<string, unknown>;
        const app = exported.app as Record<string, unknown>;
        const groups = exported.error_groups as Array<Record<string, unknown>>;
        const snapshots = exported.health_snapshots as Array<Record<string, unknown>>;

        expect(typeof exported.generated_at).toBe('string');
        expect(typeof app.version).toBe('string');
        expect(Number(summary.error_groups)).toBeGreaterThan(0);
        expect(groups.length).toBeGreaterThan(0);
        expect(snapshots.length).toBe(1);
        expect(snapshots[0].status).toBe('degraded');
    });

    it('captures a new health snapshot when latest timeout event changes', () => {
        const base = {
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: { pressure_level: 'high' },
            event_pipeline: {
                critical_failures: 1,
                stage_timeouts: { classify_snapshot: 1 },
                stage_failures: {},
                last_stage_timeout: {
                    event_id: 'evt-a',
                    stage: 'classify_snapshot',
                    timeout_seconds: 30
                }
            },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 },
            startup_warnings: []
        };
        jobDiagnosticsStore.ingestHealth(base);
        jobDiagnosticsStore.ingestHealth({
            ...base,
            event_pipeline: {
                ...base.event_pipeline,
                last_stage_timeout: {
                    event_id: 'evt-b',
                    stage: 'classify_snapshot',
                    timeout_seconds: 30
                }
            }
        });

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(2);
    });

    it('captures and manages multiple bundles', () => {
        jobDiagnosticsStore.recordError({
            source: 'job',
            component: 'reclassify_queue',
            stage: 'poll',
            reasonCode: 'status_fetch_failed',
            message: 'Failed to fetch status',
            severity: 'warning'
        });

        const bundleA = jobDiagnosticsStore.captureBundle('First run');
        const bundleB = jobDiagnosticsStore.captureBundle('Second run');

        expect(bundleA).toBeTruthy();
        expect(bundleB).toBeTruthy();
        expect(jobDiagnosticsStore.bundles.length).toBe(2);
        expect(jobDiagnosticsStore.bundles[0].label).toBe('Second run');

        if (bundleA) {
            jobDiagnosticsStore.removeBundle(bundleA.id);
        }
        expect(jobDiagnosticsStore.bundles.length).toBe(1);

        jobDiagnosticsStore.clearBundles();
        expect(jobDiagnosticsStore.bundles.length).toBe(0);
    });

    it('renders one saved-bundle library and themed capture fields', () => {
        expect(errorsPageSource).toContain('System Status');
        expect(errorsPageSource).toContain('Recent Backend Diagnostics');
        expect(errorsPageSource).toContain('Export Current JSON');
        expect(errorsPageSource).toContain('Capture Bundle');
        expect(errorsPageSource).not.toContain('Latest Bundle');
        expect(errorsPageSource).not.toContain('Download Latest');
        expect(errorsPageSource).toContain('Newest');
        expect(errorsPageSource).toContain('No captured bundles available yet.');
        expect(errorsPageSource).toContain('Saved Bundles');
        expect(errorsPageSource).toContain('rounded-3xl border border-slate-200/80 bg-white/85 px-4 py-3');
        expect(errorsPageSource).toContain('rounded-2xl border border-slate-200/80 bg-white/85 px-3');
    });
});
