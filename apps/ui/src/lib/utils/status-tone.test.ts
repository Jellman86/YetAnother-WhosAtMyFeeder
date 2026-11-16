import { describe, expect, it } from 'vitest';
import enJobs from '../i18n/locales/en/jobs.json';
import { KNOWN_STATUSES, STATUS_SURFACE, STATUS_TONE, statusLabelKey, statusTone, type StatusTone } from './status-tone';

const en = { jobs: enJobs };

/**
 * NT-04: the Errors panel painted running work amber while Notifications says a
 * job in flight needs nobody, and called "healthy" emerald in one place and brand
 * in the next. One mapping now serves the whole panel (layout-patterns.md §1.3, §1.5).
 */
describe('statusTone', () => {
    it('gives work in flight the brand colour, because it needs nobody', () => {
        for (const value of ['running', 'processing', 'queued', 'recovering', 'elevated']) expect(statusTone(value)).toBe('running');
    });

    it('reserves amber for a state a person should look at', () => {
        for (const value of ['warning', 'degraded', 'high']) expect(statusTone(value)).toBe('attention');
    });

    it('marks failures rose', () => {
        for (const value of ['critical', 'error', 'failing', 'failed', 'open']) expect(statusTone(value)).toBe('failure');
    });

    it('calls healthy states success in every theme', () => {
        for (const value of ['ok', 'healthy', 'normal', 'idle', 'clear', 'resolved', 'recovered']) expect(statusTone(value)).toBe('healthy');
    });

    it('never rounds an unmeasured or unrecognised state up to healthy', () => {
        for (const value of ['unknown', '', '   ', 'info', 'something new']) expect(statusTone(value)).toBe('unknown');
        expect(statusTone(null)).toBe('unknown');
        expect(statusTone(undefined)).toBe('unknown');
    });

    it('reads a status regardless of case or padding', () => {
        expect(statusTone('  DEGRADED ')).toBe('attention');
        expect(statusLabelKey(' Running ')).toBe('jobs.status.running');
    });
});

describe('statusLabelKey', () => {
    it('names a translated label for every status the panel knows', () => {
        const labels = en.jobs.status as Record<string, string>;
        for (const value of KNOWN_STATUSES) {
            expect(statusLabelKey(value)).toBe(`jobs.status.${value}`);
            expect(labels[value], value).toBeTruthy();
            // Sentence case, never the raw backend word shouted in capitals.
            expect(labels[value].charAt(0)).toBe(labels[value].charAt(0).toUpperCase());
            expect(labels[value].slice(1)).toBe(labels[value].slice(1).toLowerCase());
        }
    });

    it('labels a missing status as unknown, and leaves an unrecognised word to its fallback', () => {
        expect(statusLabelKey(null)).toBe('jobs.status.unknown');
        expect(statusLabelKey('')).toBe('jobs.status.unknown');
        expect(statusLabelKey('something new')).toBeNull();
    });
});

describe('status classes', () => {
    const tones: StatusTone[] = ['running', 'attention', 'failure', 'healthy', 'unknown'];

    it('maps running to info, attention to amber, healthy to ok, failure to fail and unknown to neutral', () => {
        expect(STATUS_TONE).toEqual({ running: 'info', attention: 'attention', failure: 'fail', healthy: 'ok', unknown: 'neutral' });
    });

    it('paints the verdict card with the semantic tokens only, so every mode resolves it', () => {
        for (const tone of tones) {
            expect(STATUS_SURFACE[tone]).not.toMatch(/(?:slate|rose|brand|success|attention|amber|emerald)-\d/);
            expect(STATUS_SURFACE[tone]).not.toContain('dark:');
        }
        expect(STATUS_SURFACE.attention).toContain('bg-status-attention-soft');
        expect(STATUS_SURFACE.failure).toContain('bg-status-fail-soft');
        expect(STATUS_SURFACE.healthy).toContain('bg-status-ok-soft');
    });
});
