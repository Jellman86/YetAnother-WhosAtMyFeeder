import { describe, expect, it } from 'vitest';
import type { GardenIdentificationStatus } from '../api/garden';
import type { IdentificationStatus } from './identification-models';
import { gardenCheckReadiness, identificationReadiness, readinessAction, readinessLabel, setupEmphasis } from './model-readiness';

const t = (key: string, options?: { default?: string }): string => options?.default ?? key;
const named = { modelId: 'small_birds', modelName: 'Small Birds' };

const missing: IdentificationStatus = { kind: 'missing', ...named };
const planned: IdentificationStatus = { kind: 'planned', ...named, device: 'CPU' };
const running: IdentificationStatus = { kind: 'running', ...named, device: 'CPU', species: 100, fallback: null };
const failed: IdentificationStatus = { kind: 'failed', ...named, cause: 'runtime', detail: 'boom' };
const unavailable: IdentificationStatus = { kind: 'unavailable', ...named };

describe('one readiness state for the identification model', () => {
    it('is still checking until the classifier has answered', () => {
        expect(identificationReadiness({ kind: 'checking' })).toBe('checking');
    });

    it('is missing until its files are here, and queued while they download', () => {
        expect(identificationReadiness(missing)).toBe('missing');
        expect(identificationReadiness(missing, { downloading: true })).toBe('queued');
    });

    it('is validating while its hardware check runs, whatever it was before', () => {
        expect(identificationReadiness(planned, { validating: true })).toBe('validating');
        expect(identificationReadiness(running, { validating: true })).toBe('validating');
        // A model that is not here cannot be validated.
        expect(identificationReadiness(missing, { validating: true })).toBe('missing');
    });

    it('is ready when installed and waiting for its first detection, and running once it names birds', () => {
        expect(identificationReadiness(planned)).toBe('ready');
        expect(identificationReadiness(running)).toBe('running');
    });

    it('is failed when installed but not loaded, never ready', () => {
        expect(identificationReadiness(failed)).toBe('failed');
        expect(identificationReadiness(unavailable)).toBe('failed');
    });
});

function garden(overrides: Partial<GardenIdentificationStatus> = {}): GardenIdentificationStatus {
    return {
        busy: false, catalogue_ready: true, country: 'GB', error: null,
        models: [{ variant: '4.0.3a', installed: true, size_bytes: 1 }, { variant: '4.0.3b', installed: false, size_bytes: 1 }],
        ...overrides
    };
}

describe("the same state for Garden's automatic check model", () => {
    it('is checking, never ready, when its status could not be read', () => {
        expect(gardenCheckReadiness(null)).toBe('checking');
    });

    it('is missing until downloaded and queued while it downloads', () => {
        const absent = garden({ models: [{ variant: '4.0.3a', installed: false, size_bytes: 1 }] });
        expect(gardenCheckReadiness(absent)).toBe('missing');
        expect(gardenCheckReadiness(absent, { downloading: true })).toBe('queued');
    });

    it('is failed when Garden reports an error or its species data is unavailable', () => {
        expect(gardenCheckReadiness(garden({ error: 'model file is corrupt' }))).toBe('failed');
        expect(gardenCheckReadiness(garden({ catalogue_ready: false }))).toBe('failed');
    });

    it('is ready when installed and running while it works on a photo', () => {
        expect(gardenCheckReadiness(garden())).toBe('ready');
        expect(gardenCheckReadiness(garden({ busy: true }))).toBe('running');
    });
});

describe('the one thing to do about a state', () => {
    it('is a download for a missing model and a recovery for a failed one', () => {
        expect(readinessAction('missing')).toBe('download');
        expect(readinessAction('failed')).toBe('recover');
    });

    it('is nothing while the app is working, or when the model is ready', () => {
        for (const state of ['checking', 'queued', 'validating', 'ready', 'running'] as const) {
            expect(readinessAction(state)).toBeNull();
        }
    });
});

describe('one primary setup action', () => {
    it('is the chosen model while it needs a download or a recovery, and no other model competes', () => {
        for (const state of ['missing', 'failed'] as const) {
            expect(setupEmphasis(state, 'chosen')).toBe('primary');
            expect(setupEmphasis(state, 'other')).toBe('secondary');
        }
    });

    it('leaves other models their own primary action once the chosen model needs nothing', () => {
        for (const state of ['ready', 'running', 'queued', 'validating', 'checking'] as const) {
            expect(setupEmphasis(state, 'other')).toBe('primary');
            expect(setupEmphasis(state, 'chosen')).toBe('primary');
        }
    });
});

describe('the word for each state, the same on every surface', () => {
    it('names each state once', () => {
        expect(readinessLabel('checking', t)).toBe('Checking…');
        expect(readinessLabel('missing', t)).toBe('Needs a download');
        expect(readinessLabel('queued', t)).toBe('Downloading');
        expect(readinessLabel('validating', t)).toBe('Being checked on this hardware');
        expect(readinessLabel('failed', t)).toBe('Could not load');
        expect(readinessLabel('ready', t)).toBe('Ready');
        expect(readinessLabel('running', t)).toBe('Running');
    });
});
