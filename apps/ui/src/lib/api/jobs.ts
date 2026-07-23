import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';

export type JobsSnapshot = paths['/api/jobs']['get']['response'];
export type ServerJob = JobsSnapshot['items'][number];
export type ServerJobLane = JobsSnapshot['lanes'][number];

export async function fetchJobsSnapshot(includeRoutine = true): Promise<JobsSnapshot> {
    const params = new URLSearchParams({ include_routine: String(includeRoutine) });
    const response = await apiFetch(`${API_BASE}/jobs?${params.toString()}`, {
        cache: 'no-store',
        timeoutMs: 10_000
    });
    return handleResponse<JobsSnapshot>(response);
}
