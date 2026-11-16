import type { MaintenanceLastRun } from '../api/maintenance';

type Translate = (key: string, options?: { default?: string; values?: Record<string, string | number> }) => string;
type RunKind = MaintenanceLastRun['kind'];

const COMPLETED: Record<RunKind, { key: string; fallback: string; none?: string }> = {
    taxonomy: { key: 'settings.maintenance.last_run_taxonomy', fallback: 'Last run {when}: {changed} of {checked} names repaired.' },
    timezone_scan: {
        key: 'settings.maintenance.last_run_timezone_scan',
        fallback: 'Last scan {when}: {changed} of {checked} detections need a repair.',
        none: 'Last scan {when}: none of {checked} detections need a repair.',
    },
    timezone_repair: { key: 'settings.maintenance.last_run_timezone_repair', fallback: 'Last repair {when}: {changed} detections repaired.' },
    analyze_unknowns: { key: 'settings.maintenance.last_run_analyze', fallback: 'Last run {when}: {changed} visits queued for video analysis.' },
    detections: { key: 'settings.maintenance.last_run_backfill', fallback: 'Last run {when}: {changed} visits added or updated from {checked} Frigate events.' },
    weather: { key: 'settings.maintenance.last_run_weather', fallback: 'Last run {when}: weather filled in for {changed} of {checked} detections.' },
};

/** One line per job: when it last ran and what it found, or that no run is recorded. */
export function lastRunSentence(
    run: MaintenanceLastRun | null | undefined,
    kind: RunKind,
    words: { translate: Translate; formatWhen: (value: string) => string }
): string {
    const { translate, formatWhen } = words;
    if (!run) return translate('settings.maintenance.last_run_none', { default: 'No run recorded yet.' });
    const when = run.finished_at ? formatWhen(run.finished_at) : '';
    if (run.status !== 'completed') {
        return translate('settings.maintenance.last_run_unfinished', { default: 'The last run, {when}, did not finish.', values: { when } });
    }
    const wording = COMPLETED[kind];
    const values = { when, checked: run.checked ?? 0, changed: run.changed ?? 0 };
    if (wording.none && values.changed === 0) {
        return translate(`${wording.key}_none`, { default: wording.none, values });
    }
    return translate(wording.key, { default: wording.fallback, values });
}

/**
 * Why "Apply timezone repair" cannot run yet, said beside it; null when it can. Without a scan on
 * this visit, a recorded scan that found nothing is reason enough; otherwise a scan comes first.
 */
export function timezoneRepairBlockedReason(
    preview: { summary: { repair_candidate_count?: number | null } } | null | undefined,
    lastScan?: MaintenanceLastRun | null
): 'scan_first' | 'nothing_to_repair' | 'nothing_last_scan' | null {
    if (!preview) return lastScan?.status === 'completed' && lastScan.changed === 0 ? 'nothing_last_scan' : 'scan_first';
    return (preview.summary.repair_candidate_count ?? 0) > 0 ? null : 'nothing_to_repair';
}
