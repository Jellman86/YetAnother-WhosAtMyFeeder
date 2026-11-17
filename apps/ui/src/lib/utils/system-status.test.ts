import { describe, expect, it } from 'vitest';
import { alertsRow, audioRow, feedRow, healthAttention, openHealthItems, type StatusRow } from './system-status';
import { connectionProblems } from './connection-health';
import type { ServiceConnections } from '../api/diagnostics';
import type { LiveFeedState } from './live-feed-state';

const word = (row: StatusRow) => row.state.fallback;

describe('system status rows say each measured state in words', () => {
    it.each<[LiveFeedState, string, StatusRow['tone']]>([
        ['live', 'Live', 'ok'],
        ['connecting', 'Waiting for events', 'neutral'],
        ['broker_down', 'Not connected', 'attention'],
        ['frigate_down', 'Frigate not answering', 'attention'],
        ['app_only', 'Connected', 'neutral'],
        ['reconnecting', 'Reconnecting', 'neutral']
    ])('Frigate events while the feed is %s reads "%s" (%s)', (feed, expected, tone) => {
        const row = feedRow(feed);
        expect(word(row)).toBe(expected);
        expect(row.tone).toBe(tone);
    });

    it('is green only for a measured live feed, and amber only when a person must act', () => {
        const feeds: LiveFeedState[] = ['live', 'connecting', 'broker_down', 'frigate_down', 'app_only', 'reconnecting'];
        expect(feeds.filter((feed) => feedRow(feed).tone === 'ok')).toEqual(['live']);
        expect(feeds.filter((feed) => feedRow(feed).tone === 'attention')).toEqual(['broker_down', 'frigate_down']);
    });

    it('audio is Off by choice, and Listening only while the broker session is measured up', () => {
        expect(word(audioRow(false, 'live'))).toBe('Off');
        expect(audioRow(false, 'live').tone).toBe('neutral');
        expect(word(audioRow(true, 'live'))).toBe('Listening');
        expect(audioRow(true, 'live').tone).toBe('ok');
        // Frigate's API being down does not stop audio detections arriving through the broker.
        expect(word(audioRow(true, 'frigate_down'))).toBe('Listening');
    });

    it('audio never claims to listen without a measured broker session', () => {
        for (const feed of ['connecting', 'broker_down', 'reconnecting'] as const) {
            expect(word(audioRow(true, feed))).toBe('Not listening');
            // The Frigate events row already asks for the action; one cause is not flagged twice.
            expect(audioRow(true, feed).tone).toBe('neutral');
        }
        expect(word(audioRow(true, 'app_only'))).toBe('On');
        expect(audioRow(true, 'app_only').tone).toBe('neutral');
    });

    it('alerts are On or Off, and left out when they were not read', () => {
        expect(word(alertsRow(true)!)).toBe('On');
        expect(alertsRow(true)!.tone).toBe('ok');
        expect(word(alertsRow(false)!)).toBe('Off');
        expect(alertsRow(false)!.tone).toBe('neutral');
        expect(alertsRow(null)).toBeNull();
    });

    it('every row carries a label, a state and a sentence for its tooltip', () => {
        for (const row of [feedRow('live'), audioRow(true, 'live'), alertsRow(false)!]) {
            expect(row.label.key).toMatch(/^status\.row_/);
            expect(row.state.key).toMatch(/^status\.state_/);
            expect(row.detail.fallback.length).toBeGreaterThan(row.state.fallback.length);
        }
    });
});

describe('the Health link counts open issues only', () => {
    it('asks for attention with the number of open issues', () => {
        expect(healthAttention(2)).toEqual({ needsAttention: true, count: 2 });
        expect(healthAttention(1)).toEqual({ needsAttention: true, count: 1 });
    });

    it('is plain when nothing is open or nothing was read', () => {
        expect(healthAttention(0)).toEqual({ needsAttention: false, count: 0 });
        expect(healthAttention(null)).toEqual({ needsAttention: false, count: 0 });
        expect(healthAttention(Number.NaN)).toEqual({ needsAttention: false, count: 0 });
        expect(healthAttention(-3)).toEqual({ needsAttention: false, count: 0 });
    });
});

describe('the count is what the Health page lists as open', () => {
    const down = {
        mqtt: { state: 'disconnected', server: 'mqtt.invalid', port: 1883 },
        frigate: { state: 'unreachable', url: 'http://frigate.invalid:5000', availability: 'unknown' },
        generated_at: '2026-11-15T12:00:00Z'
    } as ServiceConnections;

    it('adds failed connections to unresolved incidents, as the page does', () => {
        expect(openHealthItems(null, null, 0)).toBe(0);
        expect(openHealthItems(null, null, 2)).toBe(2);
        expect(connectionProblems(down).length).toBeGreaterThan(0);
        expect(openHealthItems(down, null, 2)).toBe(connectionProblems(down).length + 2);
    });

    it('counts a missing identification model, which Health lists as open, and nothing optional', () => {
        const status = (cause: string, key = 'classifier') => ({ subsystems: [{ key, cause }] });
        expect(openHealthItems(null, status('model_missing'), 1)).toBe(2);
        expect(openHealthItems(null, status('not_downloaded', 'finder'), 0)).toBe(0);
    });
});
