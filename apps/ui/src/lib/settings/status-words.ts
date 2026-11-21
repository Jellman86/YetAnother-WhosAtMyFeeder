import type { SubsystemKey, SubsystemVerdict } from '../api/status';

/**
 * Causes whose own words say more than the state's: a model that is not on this install is not
 * merely "not working", and a finder that is not downloaded is not "under strain".
 */
const CAUSES_WITH_WORDS: ReadonlySet<string> = new Set(['classifier.model_missing', 'finder.not_downloaded']);

/** The i18n key that words a status chip's state: the cause's own words when it has them. */
export function statusStateKey(key: SubsystemKey, verdict: Pick<SubsystemVerdict, 'state' | 'cause'> | null): string {
    if (verdict && CAUSES_WITH_WORDS.has(`${key}.${verdict.cause}`)) return `settings.status.cause.${key}.${verdict.cause}`;
    return `settings.status.state.${verdict?.state ?? 'unknown'}`;
}

/**
 * Every cause a verdict can carry, as `backend/tests/fixtures/status_causes.json` lists them; the
 * backend is held to that list, and so is this one.
 */
const STATUS_CAUSES: Readonly<Record<SubsystemKey, readonly string[]>> = {
    mqtt: ['connected', 'connecting', 'disconnected', 'not_configured', 'stopped', 'pressure_high', 'pressure_critical', 'backlog', 'frigate_topic_silent'],
    frigate: ['reachable', 'unreachable', 'unchecked', 'cameras_offline'],
    classifier: ['ready', 'model_missing', 'unmeasured', 'model_not_loaded', 'runtime_failed', 'recovering', 'live_degraded', 'degraded'],
    finder: ['ready', 'unmeasured', 'cpu_fallback', 'none_selected', 'not_downloaded'],
    audio: ['hearing', 'nothing_heard', 'broker_down', 'disabled'],
    storage: ['writable', 'not_writable'],
    notifications: ['ready', 'none_enabled', 'dropped']
};

/** The causes, for a test to hold the list and every locale's words to it. */
export function statusCauses(): Readonly<Record<SubsystemKey, readonly string[]>> {
    return STATUS_CAUSES;
}

/**
 * The i18n key for a cause in words, or null for a cause this version cannot word: the chip's state
 * then stands alone, and the raw code is never shown.
 */
export function statusCauseKey(key: SubsystemKey, cause: string | null | undefined): string | null {
    return cause && STATUS_CAUSES[key]?.includes(cause) ? `settings.status.why.${key}.${cause}` : null;
}

/**
 * Whether the column words a verdict's cause. Never from a stale reading: the causes speak in the
 * present tense, and the column already says the reading is out of date. Above the settings on a
 * phone, only for a part that needs a look.
 */
export function showsCause(verdict: Pick<SubsystemVerdict, 'state'>, place: { detailed: boolean; stale: boolean }): boolean {
    if (place.stale) return false;
    return place.detailed || verdict.state !== 'ok';
}
