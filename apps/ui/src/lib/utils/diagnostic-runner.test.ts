import { describe, expect, it } from 'vitest';
import { init, register } from 'svelte-i18n';
import { diagnosticHeadline, runSequentialDiagnostic, type DiagnosticStage } from './diagnostic-runner';

register('en', () => Promise.resolve({}));
await init({ fallbackLocale: 'en', initialLocale: 'en' });

const failing = { id: 'frigate', label: 'Frigate API', run: async () => ({ status: 'error', message: 'Failed to connect to Frigate at http://frigate.invalid:5000' }) };
const passing = { id: 'mqtt', label: 'MQTT broker publish', run: async () => ({ status: 'ok', message: 'Test message published' }) };

describe('runSequentialDiagnostic', () => {
    it('skips the rest after a failure when each step depends on the one before', async () => {
        let stages: DiagnosticStage[] = [];
        const result = await runSequentialDiagnostic([failing, passing], (next) => (stages = next));
        expect(stages.map((stage) => stage.state)).toEqual(['failed', 'skipped']);
        expect(result.ok).toBe(false);
    });

    it('runs every independent check, so one failure does not hide the other result', async () => {
        let stages: DiagnosticStage[] = [];
        const result = await runSequentialDiagnostic([failing, passing], (next) => (stages = next), { independent: true });
        expect(stages.map((stage) => stage.state)).toEqual(['failed', 'passed']);
        expect(result.ok).toBe(false);
        // The summary names what failed instead of repeating the stage's own sentence.
        expect(result.message).toBe('1 of 2 checks did not pass: Frigate API.');
    });

    it('reports success only when every independent check passed', async () => {
        const result = await runSequentialDiagnostic([passing, { ...passing, id: 'other' }], () => {}, { independent: true });
        expect(result.ok).toBe(true);
    });
});

describe('diagnosticHeadline', () => {
    const stage = (state: DiagnosticStage['state'], label: string, message: string): DiagnosticStage => ({ id: label, label, state, message });

    it('names the failed check instead of repeating the sentence its row already shows', () => {
        const stages = [
            stage('failed', 'Frigate API', 'Failed to connect to Frigate at http://frigate.invalid:5000'),
            stage('skipped', 'MQTT broker publish', 'Not run because an earlier step failed.')
        ];
        const headline = diagnosticHeadline({ ok: false, message: 'Failed to connect to Frigate at http://frigate.invalid:5000' }, stages);
        expect(headline).toBe('1 of 2 checks did not pass: Frigate API.');
    });

    it('counts the passes instead of repeating the last row on success', () => {
        const stages = [stage('passed', 'Frigate API', 'Frigate 0.15 answered'), stage('passed', 'MQTT broker publish', 'Test message published')];
        expect(diagnosticHeadline({ ok: true, message: 'Test message published' }, stages)).toBe('All 2 checks passed.');
    });

    it('keeps a summary that says something no row says', () => {
        const stages = [stage('failed', 'Frigate API', 'Connection refused')];
        expect(diagnosticHeadline({ ok: false, message: 'Frigate is not reachable from this host.' }, stages)).toBe('Frigate is not reachable from this host.');
    });

    it('treats a warning row as the caveat it is', () => {
        const stages = [stage('passed', 'Load the model', 'Loaded'), stage('warning', 'Compare with CPU', 'Results differ from the CPU baseline')];
        expect(diagnosticHeadline({ ok: false, message: 'Results differ from the CPU baseline' }, stages)).toBe('1 of 2 checks did not pass: Compare with CPU.');
    });

    it('says one check passed in the singular', () => {
        expect(diagnosticHeadline({ ok: true, message: 'Sent' }, [stage('passed', 'Send a test', 'Sent')])).toBe('The check passed.');
    });
});
