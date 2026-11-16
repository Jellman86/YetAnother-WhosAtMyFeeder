/**
 * Backend diagnostics carry a reason code and an English message written for logs ("Dropped event
 * due to classify_snapshot_timeout", "Stage classify failed: <exception>"). The message can hold an
 * exception's text, paths and URLs, so Health never leads with it: the codes an owner meets most get
 * a sentence of their own under `jobs.diagnostic_words.<key>.title` and `.next`, every other code the
 * generic one, and the backend's (redacted) message stays under Technical details.
 */
const WORDED = new Set([
    'classify_snapshot_timeout',
    'classify_snapshot_overloaded',
    'classify_snapshot_unavailable',
    'classifier_empty_results',
    'save_and_notify_failed',
    'stage_failure',
    'stage_timeout',
    'stale_job'
]);

export function diagnosticWordsKey(reasonCode: string | null | undefined): string {
    const code = (reasonCode ?? '').trim().toLowerCase();
    const key = code.startsWith('drop_') ? code.slice('drop_'.length) : code;
    return WORDED.has(key) ? key : 'generic';
}
