/**
 * Backend diagnostics carry a reason code and an English message written for logs ("Dropped event
 * due to classify_snapshot_timeout"). The codes an owner meets most get a sentence of their own,
 * under `jobs.diagnostic_words.<key>.title` and `.next`, so Health states the consequence and what
 * to try in the reader's language. Any other code keeps the backend's message.
 */
const WORDED = new Set([
    'classify_snapshot_timeout',
    'classify_snapshot_overloaded',
    'classify_snapshot_unavailable',
    'classifier_empty_results',
    'save_and_notify_failed',
    'stale_job'
]);

export function diagnosticWordsKey(reasonCode: string | null | undefined): string | null {
    const code = (reasonCode ?? '').trim().toLowerCase();
    const key = code.startsWith('drop_') ? code.slice('drop_'.length) : code;
    return WORDED.has(key) ? key : null;
}
