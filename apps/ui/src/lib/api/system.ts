import { API_BASE, apiFetch, apiFetchJson, handleResponse, requestScope, type Guarded } from './core';
import type { paths } from './generated/openapi';
import { createSharedRead, STATUS_SHARE_MS } from './shared-read';

export type VersionInfo = paths['/api/version']['get']['response'] & {
    git_hash: string;   // resolved from build-time constant; not returned by the API
    branch: string;     // resolved from build-time constant; not returned by the API
};

export interface HealthStatus {
    status: string;
    service: string;
    version?: string;
    startup_warnings?: { phase: string; error: string }[];
    startup_instance_id?: string;
    startup_started_at?: string;
    ml?: {
        runtimes: {
            tflite: { installed: boolean };
            onnx: { installed: boolean };
        };
    };
}

type StartupState = 'starting' | 'ready' | 'failed';

export type StartupPhase =
    | 'launching'
    | 'detecting_hardware'
    | 'loading_model'
    | 'model_ready'
    | 'model_unavailable'
    | 'database'
    | 'starting_services'
    | 'finalizing'
    | 'ready';

export interface StartupStatus {
    status: StartupState;
    phase: StartupPhase;
    progress: number;
    started_at: string;
    updated_at: string;
}

const STARTUP_STATES = new Set<StartupState>(['starting', 'ready', 'failed']);
const STARTUP_PHASES = new Set<StartupPhase>([
    'launching',
    'detecting_hardware',
    'loading_model',
    'model_ready',
    'model_unavailable',
    'database',
    'starting_services',
    'finalizing',
    'ready'
]);

export function normalizeStartupStatus(payload: unknown): StartupStatus | null {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
    const record = payload as Record<string, unknown>;
    if (typeof record.status !== 'string' || !STARTUP_STATES.has(record.status as StartupState)) return null;
    if (typeof record.phase !== 'string' || !STARTUP_PHASES.has(record.phase as StartupPhase)) return null;
    if (typeof record.progress !== 'number' || !Number.isFinite(record.progress)) return null;
    if (typeof record.started_at !== 'string' || typeof record.updated_at !== 'string') return null;

    return {
        status: record.status as StartupState,
        phase: record.phase as StartupPhase,
        progress: Math.min(100, Math.max(0, Math.round(record.progress))),
        started_at: record.started_at,
        updated_at: record.updated_at
    };
}

export async function fetchStartupStatus(): Promise<StartupStatus | null> {
    try {
        const response = await apiFetch('/startup-status.json', {
            cache: 'no-store',
            headers: { Accept: 'application/json' },
            timeoutMs: 2_500
        });
        if (!response.ok || !response.headers.get('content-type')?.toLowerCase().includes('application/json')) {
            return null;
        }
        const payload: unknown = await response.json();
        return normalizeStartupStatus(payload);
    } catch {
        return null;
    }
}

export type FrigateTestResult = paths['/api/frigate/test']['get']['response'];

export type RecordingClipCapability = paths['/api/frigate/recording-clip-capability']['get']['response'];

/** The server's version; throws when it cannot be read, so a failure is never shared as a reading. */
async function requestVersion(): Promise<VersionInfo> {
    const response = await apiFetch(`${API_BASE}/version`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    // git_hash and branch are no longer returned by the API (reconnaissance
    // surface reduction) — fill them from build-time constants instead.
    return { ...data, ...buildIdentity() };
}

function buildIdentity(): Pick<VersionInfo, 'git_hash' | 'branch'> {
    return {
        git_hash: typeof __GIT_HASH__ === 'string' ? __GIT_HASH__ : 'unknown',
        branch: typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown'
    };
}

/** What the build itself says, shown while the server's own answer cannot be read. */
function buildVersion(): VersionInfo {
    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;
    return { version: appVersion, base_version: appVersionBase, ...buildIdentity() };
}

// The footer names the version on every page, and About and Settings name it again.
const sharedVersion = createSharedRead(requestVersion, { shareForMs: STATUS_SHARE_MS, scope: () => requestScope() });

/** The running version for a view that shows it; views mounting together share one request. */
export function readVersion(): Promise<VersionInfo> {
    return sharedVersion.read().catch(() => buildVersion());
}

export function checkHealth(): Guarded<HealthStatus> {
    return apiFetchJson<HealthStatus>('/health', { timeoutMs: 10_000 });
}

export type SystemTelemetry = paths['/api/system-telemetry']['get']['response'];
export type SystemTelemetryHistory = paths['/api/system-telemetry/history']['get']['response'];

/**
 * The owner's half hour of host load and this app's share of it; kept by the server. The timeout
 * and `signal` (the chart unmounting) cover the body as well as the headers.
 */
export function fetchSystemTelemetryHistory(signal?: AbortSignal): Guarded<SystemTelemetryHistory> {
    return apiFetchJson<SystemTelemetryHistory>(`${API_BASE}/system-telemetry/history`, {
        cache: 'no-store',
        timeoutMs: 5_000,
        signal
    });
}

export function fetchSystemTelemetry(): Guarded<SystemTelemetry> {
    return apiFetchJson<SystemTelemetry>(`${API_BASE}/system-telemetry`, {
        cache: 'no-store',
        timeoutMs: 2_500
    });
}

export interface UpdateStatus {
    current_version: string;
    channel: 'dev' | 'stable' | 'main' | string;
    latest_version: string | null;
    update_available: boolean;
    release_url: string;
    checked_at: string | null;
    enabled: boolean;
    error: string | null;
}

export async function fetchUpdateStatus(): Promise<UpdateStatus> {
    const response = await apiFetch(`${API_BASE}/update-status`, { cache: 'no-store' });
    return handleResponse<UpdateStatus>(response);
}

// The shell's update banner and About's instance summary both show this reading.
const sharedUpdateStatus = createSharedRead(fetchUpdateStatus, { shareForMs: STATUS_SHARE_MS, scope: () => requestScope() });

/** Whether an update is out, for a view that shows it; views mounting together share one request. */
export function readUpdateStatus(): Promise<UpdateStatus> {
    return sharedUpdateStatus.read();
}

/**
 * Whether to show the update banner. Dismissal is keyed on the version, so dismissing one
 * update won't hide the banner when a newer release later becomes available.
 */
export function shouldShowUpdateBanner(status: UpdateStatus | null | undefined, dismissedVersion: string | null): boolean {
    if (!status || !status.update_available || !status.latest_version) return false;
    return dismissedVersion !== status.latest_version;
}

export async function testFrigateConnection(url?: string): Promise<FrigateTestResult> {
    const query = url?.trim() ? `?${new URLSearchParams({ url: url.trim() }).toString()}` : '';
    const response = await apiFetch(`${API_BASE}/frigate/test${query}`);
    return handleResponse<FrigateTestResult>(response);
}

export async function fetchFrigateConfig(signal?: AbortSignal): Promise<unknown> {
    const response = await apiFetch(`${API_BASE}/frigate/config`, { signal });
    return handleResponse<unknown>(response);
}

export async function fetchRecordingClipCapability(): Promise<RecordingClipCapability> {
    const response = await apiFetch(`${API_BASE}/frigate/recording-clip-capability`);
    return handleResponse<RecordingClipCapability>(response);
}
