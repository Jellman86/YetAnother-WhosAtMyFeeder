import { API_BASE, apiFetch, getHeaders, handleResponse } from './core';

export interface OAuthAuthorizeResponse {
    authorization_url: string;
    state?: string;
}

export interface TestEmailRequest {
    test_subject?: string;
    test_message?: string;
}

export interface TestEmailResponse {
    message: string;
    to: string;
}

export async function initiateGmailOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/email/oauth/gmail/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

export async function initiateOutlookOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/email/oauth/outlook/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

export async function disconnectEmailOAuth(provider: 'gmail' | 'outlook'): Promise<{ message: string }> {
    const response = await apiFetch(`${API_BASE}/email/oauth/${provider}/disconnect`, {
        method: 'DELETE'
    });
    return handleResponse<{ message: string }>(response);
}

export async function sendTestEmail(request: TestEmailRequest = {}): Promise<TestEmailResponse> {
    const controller = new AbortController();
    const timeoutMs = 35000;
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await apiFetch(`${API_BASE}/email/test`, {
            method: 'POST',
            headers: getHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
                test_subject: request.test_subject || 'YA-WAMF Test Email',
                test_message: request.test_message || 'This is a test email from YA-WAMF to verify your email configuration.'
            }),
            signal: controller.signal,
        });
        return handleResponse<TestEmailResponse>(response);
    } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
            throw new Error('Test email request timed out. Check SMTP/OAuth settings and try again.');
        }
        throw error;
    } finally {
        window.clearTimeout(timeoutId);
    }
}

export interface InaturalistDraft {
    event_id: string;
    species_guess: string;
    taxon_id?: number | null;
    observed_on_string: string;
    time_zone: string;
    latitude?: number | null;
    longitude?: number | null;
    place_guess?: string | null;
    notes?: string | null;
    snapshot_url?: string | null;
}

export interface InaturalistSubmitResult {
    status: string;
    observation_id?: number;
}

export async function initiateInaturalistOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/inaturalist/oauth/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

export async function disconnectInaturalistOAuth(): Promise<{ status: string }> {
    const response = await apiFetch(`${API_BASE}/inaturalist/oauth/disconnect`, {
        method: 'DELETE'
    });
    return handleResponse<{ status: string }>(response);
}

export async function createInaturalistDraft(eventId: string): Promise<InaturalistDraft> {
    const response = await apiFetch(`${API_BASE}/inaturalist/draft`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ event_id: eventId })
    });
    return handleResponse<InaturalistDraft>(response);
}

export async function submitInaturalistObservation(payload: {
    event_id: string;
    notes?: string;
    latitude?: number | null;
    longitude?: number | null;
    place_guess?: string | null;
}): Promise<InaturalistSubmitResult> {
    const response = await apiFetch(`${API_BASE}/inaturalist/submit`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload)
    });
    return handleResponse<InaturalistSubmitResult>(response);
}
