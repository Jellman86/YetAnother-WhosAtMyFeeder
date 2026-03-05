import { API_BASE, apiFetch, handleResponse } from './core';

export interface VersionInfo {
    version: string;
    base_version: string;
    git_hash: string;
    branch: string;
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

export async function fetchVersion(): Promise<VersionInfo> {
    try {
        const response = await apiFetch(`${API_BASE}/version`);
        if (response.ok) {
            return await response.json();
        }
    } catch {
        // Ignore errors and return fallback below.
    }
    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;
    const appBranch = typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown';
    return {
        version: appVersion,
        base_version: appVersionBase,
        git_hash: typeof __GIT_HASH__ === 'string' ? __GIT_HASH__ : 'unknown',
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
