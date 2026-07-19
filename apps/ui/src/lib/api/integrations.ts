import { API_BASE, apiFetch, getHeaders, handleResponse } from './core';
import type { paths } from './generated/openapi';

// Types are derived from the committed OpenAPI contract so the SPA and backend
// can't drift; the CI freshness check fails review if they do.
export type OAuthAuthorizeResponse = paths['/api/email/oauth/gmail/authorize']['get']['response'];
export type TestEmailRequest = paths['/api/email/test']['post']['requestBody'];
export type TestEmailResponse = paths['/api/email/test']['post']['response'];
export type EmailDisconnectResult = paths['/api/email/oauth/{provider}/disconnect']['delete']['response'];

export async function initiateGmailOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/email/oauth/gmail/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

export async function initiateOutlookOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/email/oauth/outlook/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

export async function disconnectEmailOAuth(provider: 'gmail' | 'outlook'): Promise<EmailDisconnectResult> {
    const response = await apiFetch(`${API_BASE}/email/oauth/${provider}/disconnect`, {
        method: 'DELETE'
    });
    return handleResponse<EmailDisconnectResult>(response);
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

export type InaturalistDraft = paths['/api/inaturalist/draft']['post']['response'];
export type InaturalistSubmitResult = paths['/api/inaturalist/submit']['post']['response'];
export type InaturalistDisconnectResult = paths['/api/inaturalist/oauth/disconnect']['delete']['response'];

export async function initiateInaturalistOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/inaturalist/oauth/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

export async function disconnectInaturalistOAuth(): Promise<InaturalistDisconnectResult> {
    const response = await apiFetch(`${API_BASE}/inaturalist/oauth/disconnect`, {
        method: 'DELETE'
    });
    return handleResponse<InaturalistDisconnectResult>(response);
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
