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

/** Unsaved Settings edits, kept when Settings is left by Back or Forward. */
export interface UnsavedDraft {
    /** Non-secret values that differ from the saved copy, named as the save sends them. */
    values: Record<string, unknown>;
    /** Secret fields that had been edited; their values are not kept. */
    editedSecrets: string[];
}

/**
 * The draft to keep from what the form would save: every non-secret value that differs from the
 * saved copy, and which secret fields had changed. Null when there is nothing to keep.
 */
export function draftFromForm(
    payload: Readonly<Record<string, unknown>>,
    saved: Readonly<Record<string, unknown>>,
    changedFields: readonly string[]
): UnsavedDraft | null {
    const values: Record<string, unknown> = {};
    for (const [field, value] of Object.entries(payload)) {
        if (SECRETS.has(field) || value === undefined) continue;
        if (JSON.stringify(value) !== JSON.stringify(saved[field] ?? null)) values[field] = value;
    }
    const editedSecrets = SECRET_FIELDS.filter((field) => changedFields.includes(field));
    return Object.keys(values).length > 0 || editedSecrets.length > 0 ? { values, editedSecrets } : null;
}

/**
 * Holds one draft for the rest of this page's life, in memory only (never in browser storage),
 * so it is gone on reload; reloading with unsaved changes is asked about instead.
 */
class UnsavedDraftStore {
    private draft: UnsavedDraft | null = null;

    keep(draft: UnsavedDraft | null): void {
        this.draft = draft;
    }

    /** The kept draft, which is then no longer kept. */
    take(): UnsavedDraft | null {
        const draft = this.draft;
        this.draft = null;
        return draft;
    }

    clear(): void {
        this.draft = null;
    }
}

export const unsavedDraft = new UnsavedDraftStore();
