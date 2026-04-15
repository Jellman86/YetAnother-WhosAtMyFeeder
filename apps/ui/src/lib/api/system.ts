import { API_BASE, apiFetch, handleResponse } from './core';

export interface VersionInfo {
    version: string;
    base_version: string;
    git_hash: string;   // resolved from build-time constant; not returned by the API
    branch: string;     // resolved from build-time constant; not returned by the API
}

export interface HealthStatus {
    status: string;
    service: string;
    version?: string;
    startup_warnings?: { phase: string; error: string }[];
    startup_instance_id?: string;
    startup_started_at?: string;
}

export interface FrigateTestResult {
    status: string;
    frigate_url: string;
    version: string;
}

export interface RecordingClipCapability {
    supported: boolean;
    reason: string | null;
    recordings_enabled: boolean;
    retention_days: number | null;
    eligible_cameras: string[];
    ineligible_cameras: Record<string, string>;
}

export async function fetchVersion(): Promise<VersionInfo> {
    const gitHash = typeof __GIT_HASH__ === 'string' ? __GIT_HASH__ : 'unknown';
    const appBranch = typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown';
    try {
        const response = await apiFetch(`${API_BASE}/version`);
        if (response.ok) {
            const data = await response.json();
            // git_hash and branch are no longer returned by the API (reconnaissance
            // surface reduction) — fill them from build-time constants instead.
            return { ...data, git_hash: gitHash, branch: appBranch };
        }
    } catch {
        // Ignore errors and return fallback below.
    }
    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;
    return {
        version: appVersion,
        base_version: appVersionBase,
        git_hash: gitHash,
        branch: appBranch
    };
}

export async function checkHealth(): Promise<HealthStatus> {
    const response = await apiFetch('/health');
    return handleResponse<HealthStatus>(response);
}

export async function testFrigateConnection(): Promise<FrigateTestResult> {
    const response = await apiFetch(`${API_BASE}/frigate/test`);
    return handleResponse<FrigateTestResult>(response);
}

export async function fetchFrigateConfig(): Promise<any> {
    const response = await apiFetch(`${API_BASE}/frigate/config`);
    return handleResponse<any>(response);
}

export async function fetchRecordingClipCapability(): Promise<RecordingClipCapability> {
    const response = await apiFetch(`${API_BASE}/frigate/recording-clip-capability`);
    return handleResponse<RecordingClipCapability>(response);
}
