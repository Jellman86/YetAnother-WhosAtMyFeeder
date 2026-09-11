import { describe, expect, it } from 'vitest';
import modalSource from './DetectionModal.svelte?raw';
import dataSettingsSource from './settings/DataSettings.svelte?raw';
import liveUpdatesSource from '../app/live-updates.ts?raw';
import en from '../i18n/locales/en.json';

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
        expect(modalSource).toContain("archiveState === 'failed' && hasOwnerDetectionActions");
        expect(modalSource).toContain('void handleArchiveRetry()');
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
        expect(dataSettingsSource).toContain('cacheStats?.archive_durable');
        expect(dataSettingsSource).toContain('data-archive-failed');
        expect(dataSettingsSource).toContain('bind:value={cachePerSpeciesMinimum}');
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
