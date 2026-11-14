/**
 * Settings fields that hold a secret. Their values are never kept outside the form: a draft only
 * records that one was edited, so the owner can be told to type it again.
 */
export const SECRET_FIELDS = [
    'mqtt_password',
    'auth_password',
    'birdweather_station_token',
    'ha_weather_access_token',
    'ebird_api_key',
    'inaturalist_client_id',
    'inaturalist_client_secret',
    'llm_api_key',
    'notifications_discord_webhook_url',
    'notifications_pushover_user_key',
    'notifications_pushover_api_token',
    'notifications_telegram_bot_token',
    'notifications_telegram_chat_id',
    'notifications_email_gmail_client_secret',
    'notifications_email_outlook_client_secret',
    'notifications_email_smtp_password'
] as const;

const SECRETS: ReadonlySet<string> = new Set(SECRET_FIELDS);

/** Who is signed in, as far as a kept draft is concerned. */
export interface AccessState {
    authRequired: boolean;
    isAuthenticated: boolean;
    username: string | null;
    hasOwnerAccess: boolean;
    /** The session's token: a new sign-in, even by the same person, gets a new one. */
    token: string | null;
}

/**
 * The session a draft belongs to, or null when nobody with owner access is signed in. A sign-out,
 * an expired session, another person or another sign-in all give a different identity.
 */
export function accessIdentity(access: AccessState): string | null {
    if (!access.hasOwnerAccess) return null;
    if (!access.authRequired) return 'open';
    if (!access.isAuthenticated) return null;
    return JSON.stringify([access.username ?? '', access.token ?? '']);
}

/** Unsaved Settings edits, kept when Settings is left by Back or Forward. */
export interface UnsavedDraft {
    /** The session that made the edits (see accessIdentity). */
    identity: string;
    /** Non-secret values that differ from the saved copy, named as the save sends them. */
    values: Record<string, unknown>;
    /** For each drafted field, the saved value it was edited from. */
    baselines: Record<string, unknown>;
    /** Secret fields that had been edited; their values are not kept. */
    editedSecrets: string[];
}

const same = (a: unknown, b: unknown): boolean => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/**
 * The draft to keep from what the form would save: every non-secret value that differs from the
 * saved copy, with that saved value as its baseline, and which secret fields had changed. Null
 * when there is nothing to keep, or nobody with owner access to keep it for.
 */
export function draftFromForm(
    payload: Readonly<Record<string, unknown>>,
    saved: Readonly<Record<string, unknown>>,
    changedFields: readonly string[],
    identity: string | null
): UnsavedDraft | null {
    if (identity === null) return null;
    const values: Record<string, unknown> = {};
    const baselines: Record<string, unknown> = {};
    for (const [field, value] of Object.entries(payload)) {
        if (SECRETS.has(field) || value === undefined || same(value, saved[field])) continue;
        values[field] = value;
        baselines[field] = saved[field] ?? null;
    }
    const editedSecrets = SECRET_FIELDS.filter((field) => changedFields.includes(field));
    return Object.keys(values).length > 0 || editedSecrets.length > 0 ? { identity, values, baselines, editedSecrets } : null;
}

/** A drafted value whose saved value was changed elsewhere since the edit began. */
export interface DraftConflict {
    field: string;
    mine: unknown;
    saved: unknown;
}

/**
 * Lays a draft over a fresh read. A drafted value is restored only while its saved value is still
 * the one it was edited from; one changed elsewhere meanwhile is a conflict, left for the owner to
 * decide. Fields the draft never touched keep the fresh value.
 */
export function mergeDraft(
    draft: UnsavedDraft,
    fresh: Readonly<Record<string, unknown>>
): { restore: Record<string, unknown>; conflicts: DraftConflict[] } {
    const restore: Record<string, unknown> = {};
    const conflicts: DraftConflict[] = [];
    for (const [field, mine] of Object.entries(draft.values)) {
        if (same(fresh[field], draft.baselines[field])) restore[field] = mine;
        else conflicts.push({ field, mine, saved: fresh[field] ?? null });
    }
    return { restore, conflicts };
}

/**
 * Holds one draft for the rest of this page's life, in memory only (never in browser storage),
 * so it is gone on reload; reloading with unsaved changes is asked about instead. A draft is only
 * ever handed back to the session that kept it; any other caller drops it.
 */
class UnsavedDraftStore {
    private draft: UnsavedDraft | null = null;

    keep(draft: UnsavedDraft | null): void {
        this.draft = draft;
    }

    /** Whether a draft is waiting for this session (so the page reads afresh before using it). */
    pendingFor(identity: string | null): boolean {
        return this.draft !== null && identity !== null && this.draft.identity === identity;
    }

    /** The kept draft, which is then no longer kept. Another session's draft is dropped. */
    take(identity: string | null): UnsavedDraft | null {
        const draft = this.draft;
        this.draft = null;
        return draft && identity !== null && draft.identity === identity ? draft : null;
    }

    clear(): void {
        this.draft = null;
    }
}

export const unsavedDraft = new UnsavedDraftStore();
