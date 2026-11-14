import { describe, expect, it } from 'vitest';
import { init, register } from 'svelte-i18n';
import { runSequentialDiagnostic, type DiagnosticStage } from './diagnostic-runner';

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
