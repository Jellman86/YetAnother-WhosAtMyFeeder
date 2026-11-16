import { describe, expect, it } from 'vitest';
import type { SetupSectionState } from '../../api/setup';
import { reviewStatusLabel, reviewStatusTone } from './review-status';

const t = (key: string, options?: { default?: string }): string => options?.default ?? key;
const section = (overrides: Partial<SetupSectionState>): SetupSectionState => ({ id: 'model', status: 'ok', detail_values: {}, ...overrides });

describe("the review's word for each section", () => {
    it('never calls a model that is not on this install configured', () => {
        expect(reviewStatusLabel(section({ status: 'attention', detail_code: 'model_missing' }), t)).toBe('Needs a download');
    });

    it('words a working model from the runtime report, and says only chosen when nobody checked', () => {
        expect(reviewStatusLabel(section({ detail_code: 'model_running' }), t)).toBe('Running');
        expect(reviewStatusLabel(section({ detail_code: 'model_ready' }), t)).toBe('Ready');
        expect(reviewStatusLabel(section({ detail_code: 'model_selected' }), t)).toBe('Chosen');
        expect(reviewStatusLabel(section({ detail_code: 'model_fallback' }), t)).toBe('Chosen');
    });

    it('says a model that is still loading is loading, in a neutral tone', () => {
        const loading = section({ status: 'optional', detail_code: 'model_loading' });
        expect(reviewStatusLabel(loading, t)).toBe('Loading');
        expect(reviewStatusTone(loading)).toBe('optional');
    });

    it('never calls a model whose files are here but could not be loaded ready', () => {
        expect(reviewStatusLabel(section({ status: 'attention', detail_code: 'model_failed' }), t)).toBe('Could not load');
        expect(reviewStatusTone(section({ status: 'attention', detail_code: 'model_failed' }))).toBe('attention');
    });

    it('names what was measured for the account and the connection', () => {
        expect(reviewStatusLabel(section({ id: 'account', status: 'optional', detail_code: 'account_auth_disabled' }), t)).toBe('No password');
        expect(reviewStatusLabel(section({ id: 'connection', detail_code: 'connection_connected' }), t)).toBe('Connected');
        expect(reviewStatusLabel(section({ id: 'connection', status: 'attention', detail_code: 'connection_unreachable' }), t)).toBe('Not reachable');
    });

    it('falls back to the section status', () => {
        expect(reviewStatusLabel(section({ id: 'cameras', detail_code: 'cameras_all' }), t)).toBe('Configured');
        expect(reviewStatusLabel(section({ id: 'model', status: 'attention', detail_code: 'model_retired' }), t)).toBe('Needs attention');
        expect(reviewStatusLabel(section({ id: 'integrations', status: 'optional' }), t)).toBe('Optional');
    });

    it('keeps green for what was measured: a model nobody checked is neutral', () => {
        expect(reviewStatusTone(section({ detail_code: 'model_running' }))).toBe('ok');
        expect(reviewStatusTone(section({ detail_code: 'model_selected' }))).toBe('optional');
        expect(reviewStatusTone(section({ detail_code: 'model_fallback' }))).toBe('optional');
        expect(reviewStatusTone(section({ status: 'attention', detail_code: 'model_missing' }))).toBe('attention');
    });

    it('words the model row from the classifier\'s report once it has arrived, as the model step does', () => {
        const model = section({ detail_code: 'model_ready' });
        expect(reviewStatusLabel(model, t, 'running')).toBe('Running');
        expect(reviewStatusTone(model, 'running')).toBe('ok');
        expect(reviewStatusLabel(model, t, 'ready')).toBe('Ready');
        expect(reviewStatusLabel(model, t, 'missing')).toBe('Needs a download');
        expect(reviewStatusTone(model, 'missing')).toBe('attention');
        expect(reviewStatusLabel(model, t, 'failed')).toBe('Could not load');
        expect(reviewStatusTone(model, 'failed')).toBe('attention');
        expect(reviewStatusTone(model, 'validating')).toBe('optional');
    });

    it('keeps the server\'s word until the classifier has answered, and for its own findings', () => {
        const model = section({ detail_code: 'model_ready' });
        expect(reviewStatusLabel(model, t, null)).toBe('Ready');
        expect(reviewStatusLabel(model, t, 'checking')).toBe('Ready');
        expect(reviewStatusLabel(section({ status: 'attention', detail_code: 'model_retired' }), t, 'running')).toBe('Needs attention');
        expect(reviewStatusLabel(section({ id: 'cameras', detail_code: 'cameras_all' }), t, 'missing')).toBe('Configured');
    });

    it('reads a loading model from the runtime report as loading, never as running or ready', () => {
        const saved = section({ detail_code: 'model_selected' });
        expect(reviewStatusLabel(saved, t, 'loading')).toBe('Loading');
        expect(reviewStatusTone(saved, 'loading')).toBe('optional');
    });

    it('says "Not reported", in a neutral tone, when the classifier answered with no evidence', () => {
        // Neither the server's "Chosen" nor an earlier "Running" survives a report that says nothing.
        for (const detail_code of ['model_selected', 'model_fallback', 'model_running', 'model_ready']) {
            const row = section({ status: 'ok', detail_code });
            expect(reviewStatusLabel(row, t, 'unknown')).toBe('Not reported');
            expect(reviewStatusTone(row, 'unknown')).toBe('optional');
        }
    });

    it("keeps the server's word only when there is no classifier response to read", () => {
        const row = section({ status: 'ok', detail_code: 'model_running' });
        expect(reviewStatusLabel(row, t, null)).toBe('Running');
        expect(reviewStatusLabel(section({ detail_code: 'model_selected' }), t, null)).toBe('Chosen');
    });

    it('shows work this app started on the model: a download or a hardware check', () => {
        const row = section({ status: 'attention', detail_code: 'model_missing' });
        expect(reviewStatusLabel(row, t, 'queued')).toBe('Downloading');
        expect(reviewStatusTone(row, 'queued')).toBe('optional');
        expect(reviewStatusLabel(row, t, 'validating')).toBe('Being checked on this hardware');
    });
});
