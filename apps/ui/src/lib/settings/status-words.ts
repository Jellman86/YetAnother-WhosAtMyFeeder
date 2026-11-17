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
