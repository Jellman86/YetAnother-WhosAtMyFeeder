import { describe, expect, it } from 'vitest';
import modalSource from './DetectionModal.svelte?raw';
import dataSettingsSource from './settings/DataSettings.svelte?raw';
import liveUpdatesSource from '../app/live-updates.ts?raw';
import enDetection from '../i18n/locales/en/detection.json';
import enSettings from '../i18n/locales/en/settings.json';

const en = { detection: enDetection, settings: enSettings };

describe('a favourite is durable, and says so (#178)', () => {
    it('shows the archive state beside the star and polls only while pending', () => {
        expect(modalSource).toContain('data-detection-archive-state={archiveState}');
        expect(modalSource).toContain("if (status.state === 'pending' && polls < ARCHIVE_POLL_LIMIT)");
        expect(modalSource).toContain('detection.archive_pending');
        expect(modalSource).toContain('detection.archive_durable');
        expect(modalSource).toContain('detection.archive_photo_only');
        expect(modalSource).toContain('detection.archive_unavailable');
        expect(modalSource).toContain('detection.archive_failed');
        // A failed archive is retried from where it is shown.
        expect(modalSource).toContain('{#if detection.is_favorite && archiveFailure}');
        expect(modalSource).toContain('void handleArchiveRetry()');
    });

    it('says what a failed copy did not keep, why, and what to do next', () => {
        // The cause comes from the code the archive worker stored, never a bare "Archive failed",
        // and only from a status read for this record: none is not "both failed, retries stopped".
        expect(modalSource).toContain('archiveFailureView(archiveStatusHere, archiveRead)');
        expect(modalSource).not.toContain('archiveStatus ?? {}');
        expect(modalSource).toContain("archiveStatus && archiveStatus.event_id === detection?.frigate_event ? archiveStatus : null");
        // A failed read says so and offers to check again.
        expect(modalSource).toContain('data-detection-archive-check-again');
        expect(en.detection.archive_unchecked).toContain('could not be checked');
        expect(modalSource).toContain('data-detection-archive-cause');
        expect(en.detection.archive_failed_both).toContain('could not be saved');
        expect(en.detection.archive_cause.frigate_unreachable).toContain('Check');
        expect(en.detection.archive_cause.disk_full).toContain('Free some space');
        // It says whether it will try again by itself, and that the visit itself is safe.
        expect(en.detection.archive_retry_scheduled).toContain('{at}');
        expect(en.detection.archive_retry_spent.toLowerCase()).toContain('stays in your history');
    });

    it('names what unfavouriting removes before it removes it', () => {
        expect(modalSource).toContain("$_('detection.unfavorite_confirm'");
        expect(modalSource).toContain('if (archivedBytes > 0)');
        expect(en.detection.unfavorite_confirm).toContain('{size}');
        expect(en.detection.unfavorite_confirm.toLowerCase()).toContain('stays in history');
    });

    it('carries the state through live updates and the favourite result', () => {
        expect(liveUpdatesSource).toContain('archive_state: archiveStateFrom(data.archive_state)');
        expect(modalSource).toContain("detection.archive_state = asArchiveState(result.archive_state) ?? 'pending'");
    });

    it('shows archive use apart from cache use, with the floor beside it', () => {
        expect(dataSettingsSource).toContain('data-archive-usage');
        expect(dataSettingsSource).toContain('cacheStats.archive_durable');
        expect(dataSettingsSource).toContain('data-archive-failed');
        expect(dataSettingsSource).toContain('value={cachePerSpeciesMinimum}');
    });

    it('every destructive action names the archive', () => {
        for (const copy of [en.settings.data.clear_favorites_confirm, en.settings.danger.confirm, en.settings.danger.reset_desc]) {
            expect(copy.toLowerCase()).toContain('archived');
        }
        // House rule: no em dashes.
        for (const value of Object.values(en.detection).filter((v) => typeof v === 'string' && v.includes('rchiv'))) {
            expect(value).not.toContain('—');
        }
    });
});
