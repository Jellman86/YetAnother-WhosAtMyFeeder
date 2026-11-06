import { describe, expect, it } from 'vitest';
import type { RangeFilterStatus } from '../api/range-filter';
import { rangeAge, rangeNeighbourCount, rangeProblemKey, rangeRegionNote, summarizeRangeStatus } from './range-filter';

function status(overrides: Partial<RangeFilterStatus> = {}): RangeFilterStatus {
    return {
        enabled: true,
        filtering: true,
        reason: 'active',
        problem: null,
        source: 'ebird',
        location_precision: 'exact',
        region_level_setting: 'county',
        ebird_configured: true,
        birdnet_enabled: true,
        region: { code: 'GB-ENG-KEN', codes: ['GB-ENG-KEN'], name: 'Kent, England, GB', level: 'county', note: null },
        species_in_range: 412,
        region_species_total: 415,
        heard_species: 0,
        heard_only_species: 0,
        refreshed_at: '2026-10-29T12:00:00Z',
        next_refresh_at: null,
        stale_after: null,
        refreshing: false,
        last_error: null,
        last_attempt_at: null,
        model: null,
        recent: { window_days: 30, fallback: 0, skipped: 0 },
        ...overrides
    };
}

describe('range filter status summary', () => {
    it('claims to filter only when the server says it is filtering', () => {
        expect(summarizeRangeStatus(status())).toEqual({ tone: 'filtering', needsPerson: false, action: null });
        expect(summarizeRangeStatus(status({ filtering: false })).tone).toBe('not_filtering');
    });

    it('reads an off switch with a ready list as off, offering a refresh rather than asking for help', () => {
        expect(summarizeRangeStatus(status({ enabled: false, filtering: false, reason: 'ready' }))).toEqual({
            tone: 'off',
            needsPerson: false,
            action: 'refresh'
        });
    });

    it('asks a person for a location or key only once the filter is meant to be on', () => {
        expect(summarizeRangeStatus(status({ filtering: false, reason: 'needs_location' }))).toEqual({
            tone: 'not_filtering',
            needsPerson: true,
            action: 'location'
        });
        expect(summarizeRangeStatus(status({ enabled: false, filtering: false, reason: 'needs_ebird_key' }))).toEqual({
            tone: 'off',
            needsPerson: false,
            action: 'ebird_key'
        });
    });

    it('waits quietly while the first list is fetched', () => {
        expect(summarizeRangeStatus(status({ filtering: false, reason: 'waiting_for_list', refreshing: true }))).toEqual({
            tone: 'waiting',
            needsPerson: false,
            action: null
        });
    });

    it('sends a rejected key to the key, and other failures to a refresh', () => {
        expect(summarizeRangeStatus(status({ filtering: false, reason: 'lookup_failed', problem: 'ebird_key_rejected' })).action).toBe('ebird_key');
        expect(summarizeRangeStatus(status({ filtering: false, reason: 'list_stale' })).action).toBe('refresh');
    });
});

describe('range filter wording helpers', () => {
    const now = new Date('2026-10-31T12:00:00Z');

    it('states a list age in its largest whole unit', () => {
        expect(rangeAge('2026-10-31T11:59:40Z', now)).toEqual({ unit: 'just_now', count: 0 });
        expect(rangeAge('2026-10-31T11:15:00Z', now)).toEqual({ unit: 'minutes', count: 45 });
        expect(rangeAge('2026-10-30T12:00:00Z', now)).toEqual({ unit: 'hours', count: 24 });
        expect(rangeAge('2026-10-29T12:00:00Z', now)).toEqual({ unit: 'days', count: 2 });
        expect(rangeAge(null, now)).toBeNull();
        expect(rangeAge('not a date', now)).toBeNull();
    });

    it('maps every server problem onto a sentence that exists', () => {
        expect(rangeProblemKey('ebird_unreachable')).toBe('ebird_unreachable');
        expect(rangeProblemKey('list_poorly_mapped')).toBe('list_problem');
        expect(rangeProblemKey('invalid_region')).toBe('list_problem');
        expect(rangeProblemKey('something new')).toBe('refresh_failed');
        expect(rangeProblemKey(null)).toBeNull();
    });

    it('explains a region coarser than the setting asked for', () => {
        expect(rangeRegionNote(status({ location_precision: 'approximate' }))).toBe('approximate');
        expect(rangeRegionNote(status({ location_precision: 'country_only' }))).toBe('country_only');
        expect(
            rangeRegionNote(status({ region: { code: 'US-CA', codes: ['US-CA'], name: null, level: 'state', note: 'county_list_too_short' } }))
        ).toBe('county_too_short');
        expect(rangeRegionNote(status())).toBeNull();
    });

    it('counts neighbouring counties beyond the nearest', () => {
        expect(rangeNeighbourCount(status())).toBe(0);
        expect(
            rangeNeighbourCount(status({ region: { code: 'US-CA-097', codes: ['US-CA-097', 'US-CA-041'], name: null, level: 'county', note: null } }))
        ).toBe(1);
    });
});
