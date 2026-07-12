import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';

// Types come straight from the generated OpenAPI contract (see code-quality standard).
export type SetupState = paths['/api/setup/state']['get']['response'];
export type SetupSectionState = SetupState['sections'][number];
export type SetupSectionId = SetupSectionState['id'];
export type SetupSectionStatus = SetupSectionState['status'];

/** Per-section setup readiness for the wizard's section map (owner-gated; open on first run). */
export async function fetchSetupState(): Promise<SetupState> {
    const response = await apiFetch(`${API_BASE}/setup/state`);
    return handleResponse<SetupState>(response);
}
