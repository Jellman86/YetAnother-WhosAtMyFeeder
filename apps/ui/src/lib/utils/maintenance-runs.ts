import type { MaintenanceLastRun } from '../api/maintenance';

type Translate = (key: string, options?: { default?: string; values?: Record<string, string | number> }) => string;
type RunKind = MaintenanceLastRun['kind'];

const COMPLETED: Record<RunKind, { key: string; fallback: string; none?: string }> = {
    taxonomy: { key: 'settings.maintenance.last_run_taxonomy', fallback: 'Last run {when}: {changed} of {checked} names repaired.' },
    timezone_scan: {
        key: 'settings.maintenance.last_run_timezone_scan',
        fallback: 'Last scan {when}: {changed} of {checked} captures need a repair.',
        none: 'Last scan {when}: none of {checked} captures need a repair.',
    },
    timezone_repair: { key: 'settings.maintenance.last_run_timezone_repair', fallback: 'Last repair {when}: {changed} captures repaired.' },
    analyze_unknowns: { key: 'settings.maintenance.last_run_analyze', fallback: 'Last run {when}: {changed} visits queued for video analysis.' },
    detections: { key: 'settings.maintenance.last_run_backfill', fallback: 'Last run {when}: {changed} visits added or updated from {checked} Frigate events.' },
    weather: { key: 'settings.maintenance.last_run_weather', fallback: 'Last run {when}: weather filled in for {changed} of {checked} captures.' },
};

/** One line per job: when it last ran and what it found, whether it is running, or that no run is recorded. */
export function lastRunSentence(
    run: MaintenanceLastRun | null | undefined,
    kind: RunKind,
    words: { translate: Translate; formatWhen: (value: string) => string }
): string {
    const { translate, formatWhen } = words;
    if (!run) return translate('settings.maintenance.last_run_none', { default: 'No run recorded yet.' });
    if (run.status === 'running') {
        return run.started_at
            ? translate('settings.maintenance.last_run_running', { default: 'Running now, started {when}.', values: { when: formatWhen(run.started_at) } })
            : translate('settings.maintenance.last_run_running_undated', { default: 'Running now.' });
    }
    const when = run.finished_at ? formatWhen(run.finished_at) : null;
    if (run.status === 'cancelled') {
        return when
            ? translate('settings.maintenance.last_run_cancelled', { default: 'The last run, {when}, was stopped before it finished.', values: { when } })
            : translate('settings.maintenance.last_run_cancelled_undated', { default: 'The last run was stopped before it finished.' });
    }
    if (run.status !== 'completed') {
        return when
            ? translate('settings.maintenance.last_run_unfinished', { default: 'The last run, {when}, did not finish.', values: { when } })
            : translate('settings.maintenance.last_run_unfinished_undated', { default: 'The last run did not finish.' });
    }
    const values = { when: when ?? '', checked: run.checked ?? 0, changed: run.changed ?? 0, unchecked: run.unchecked ?? 0 };
    // Detections Frigate did not answer for were not checked, so they are never an all-clear.
    if (kind === 'timezone_scan' && values.unchecked > 0) {
        const parts = [translate('settings.maintenance.last_run_timezone_scan_incomplete', { default: 'Last scan {when} could not check {unchecked} of {checked} captures (Frigate did not answer).', values })];
        if (values.changed > 0) parts.push(translate('settings.maintenance.last_run_timezone_scan_rest', { default: '{changed} of the rest need a repair.', values }));
        parts.push(translate('settings.maintenance.scan_again', { default: 'Scan again.' }));
        return parts.join(' ');
    }
    const wording = COMPLETED[kind];
    if (wording.none && values.changed === 0) {
        // The key is built here, so no search for the literal finds it: maintenance-runs.test.ts
        // holds every language to having it.
        return translate(`${wording.key}_none`, { default: wording.none, values });
    }
    return translate(wording.key, { default: wording.fallback, values });
}

/**
 * Why "Apply timezone repair" cannot run yet, said beside it; null when it can. Without a scan on
 * this visit, a recorded scan that checked everything and found nothing is reason enough; one that
 * could not check some detections asks for a new scan; otherwise a scan comes first.
 */
export function timezoneRepairBlockedReason(
    preview: { summary: { repair_candidate_count?: number | null; lookup_error_count?: number | null } } | null | undefined,
    lastScan?: MaintenanceLastRun | null
): 'scan_first' | 'nothing_to_repair' | 'nothing_last_scan' | 'scan_incomplete' | 'last_scan_incomplete' | null {
    if (!preview) {
        if (lastScan?.status !== 'completed') return 'scan_first';
        if ((lastScan.unchecked ?? 0) > 0) return 'last_scan_incomplete';
        return lastScan.changed === 0 ? 'nothing_last_scan' : 'scan_first';
    }
    if ((preview.summary.repair_candidate_count ?? 0) > 0) return null;
    return (preview.summary.lookup_error_count ?? 0) > 0 ? 'scan_incomplete' : 'nothing_to_repair';
}
