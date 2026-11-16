// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { ClassifierStatus } from '../api/classifier';
import type { GardenIdentificationStatus } from '../api/garden';
import { identificationStatus, type IdentificationStatus } from './identification-models';
import {
    activityPhase,
    chosenRecovery,
    classifierReadiness,
    gardenCheckAvailable,
    gardenCheckState,
    identificationReadiness,
    readinessAction,
    readinessLabel,
    readinessTone,
    setupEmphasis
} from './model-readiness';

const t = (key: string, options?: { default?: string }): string => options?.default ?? key;
const named = { modelId: 'small_birds', modelName: 'Small Birds' };

const missing: IdentificationStatus = { kind: 'missing', ...named };
const planned: IdentificationStatus = { kind: 'planned', ...named, device: 'CPU' };
const running: IdentificationStatus = { kind: 'running', ...named, device: 'CPU', species: 100, fallback: null };
const failed: IdentificationStatus = { kind: 'failed', ...named, cause: 'runtime', detail: 'boom' };
const unavailable: IdentificationStatus = { kind: 'unavailable', ...named };

describe('one readiness state for the identification model', () => {
    it('is loading while an in-app model is being loaded, and unknown when the report gives no evidence: neither is running', () => {
        expect(identificationReadiness({ kind: 'loading', ...named })).toBe('loading');
        expect(identificationReadiness({ kind: 'unknown', ...named })).toBe('unknown');
        expect(readinessLabel('loading', t)).toBe('Loading');
        expect(readinessLabel('unknown', t)).toBe('Not reported');
        // Neither is something the owner has to act on, and neither is a primary action's reason.
        expect(readinessAction('loading')).toBeNull();
        expect(readinessAction('unknown')).toBeNull();
    });

    it('is still checking until the classifier has answered', () => {
        expect(identificationReadiness({ kind: 'checking' })).toBe('checking');
        // Work cannot be claimed on a model nobody has reported on.
        expect(identificationReadiness({ kind: 'checking' }, 'downloading')).toBe('checking');
    });

    it('is missing until its files are here, and queued while they download', () => {
        expect(identificationReadiness(missing)).toBe('missing');
        expect(identificationReadiness(missing, 'downloading')).toBe('queued');
        // A repair download of a model that is here replaces its files: it is downloading too.
        expect(identificationReadiness(failed, 'downloading')).toBe('queued');
    });

    it('is validating while its hardware check runs, whatever it was before', () => {
        expect(identificationReadiness(planned, 'validating')).toBe('validating');
        expect(identificationReadiness(running, 'validating')).toBe('validating');
        expect(identificationReadiness(failed, 'validating')).toBe('validating');
        // A model that is not here cannot be validated.
        expect(identificationReadiness(missing, 'validating')).toBe('missing');
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

describe('the phase of a guided install, from the stage that is running', () => {
    const stages = (download: string, validate: string, enable: string) => [
        { id: 'download', state: download }, { id: 'validate', state: validate }, { id: 'enable', state: enable }
    ];

    it('is a download only while the download stage runs', () => {
        expect(activityPhase(stages('running', 'pending', 'pending'))).toBe('downloading');
    });

    it('is a check once the download has passed: validation is never called downloading', () => {
        expect(activityPhase(stages('passed', 'running', 'pending'))).toBe('validating');
        expect(activityPhase(stages('skipped', 'running', 'pending'))).toBe('validating');
        expect(activityPhase(stages('passed', 'passed', 'running'))).toBe('validating');
    });

    it('is nothing before it starts, after it ends, or once a stage has failed', () => {
        expect(activityPhase(stages('pending', 'pending', 'pending'))).toBeNull();
        expect(activityPhase(stages('passed', 'passed', 'passed'))).toBeNull();
        expect(activityPhase(stages('failed', 'skipped', 'skipped'))).toBeNull();
        expect(activityPhase([])).toBeNull();
    });
});

function garden(overrides: Partial<GardenIdentificationStatus> = {}): GardenIdentificationStatus {
    return {
        busy: false, catalogue_ready: true, country: 'GB', error: null,
        models: [{ variant: '4.0.3a', installed: true, size_bytes: 1 }, { variant: '4.0.3b', installed: false, size_bytes: 1 }],
        ...overrides
    };
}

describe("what stands before Garden's automatic check", () => {
    const model = (readiness: string) => ({ kind: 'model', readiness });

    it('is checking, never ready, when its status could not be read', () => {
        expect(gardenCheckState(null)).toEqual(model('checking'));
        expect(gardenCheckAvailable(gardenCheckState(null))).toBe(false);
    });

    it('is a missing model until downloaded, and a queued one while it downloads', () => {
        const absent = garden({ models: [{ variant: '4.0.3a', installed: false, size_bytes: 1 }] });
        expect(gardenCheckState(absent)).toEqual(model('missing'));
        expect(gardenCheckState(absent, 'downloading')).toEqual(model('queued'));
    });

    it('keeps what Garden measured: missing species data is not a model that could not load', () => {
        expect(gardenCheckState(garden({ catalogue_ready: false }))).toEqual({ kind: 'blocked', blocker: 'species_data', detail: null });
    });

    it('keeps the service error in its own words, such as a worker that would not stop', () => {
        const stuck = 'Garden worker did not stop. Restart the application before running more Garden work.';
        expect(gardenCheckState(garden({ error: stuck }))).toEqual({ kind: 'blocked', blocker: 'service', detail: stuck });
        // The service error comes first: it is why nothing else can be trusted.
        expect(gardenCheckState(garden({ error: stuck, catalogue_ready: false })).kind).toBe('blocked');
    });

    it('never reports a blocker as a failed model', () => {
        for (const broken of [garden({ catalogue_ready: false }), garden({ error: 'Garden worker did not stop.' })]) {
            const state = gardenCheckState(broken);
            expect(state.kind === 'model' ? state.readiness : null).not.toBe('failed');
            expect(gardenCheckAvailable(state)).toBe(false);
        }
    });

    it('is ready when installed and running while it works on a photo', () => {
        expect(gardenCheckState(garden())).toEqual(model('ready'));
        expect(gardenCheckState(garden({ busy: true }))).toEqual(model('running'));
        expect(gardenCheckAvailable(gardenCheckState(garden()))).toBe(true);
        expect(gardenCheckAvailable(gardenCheckState(garden({ busy: true })))).toBe(true);
    });
});

describe('the one thing to do about a state', () => {
    it('is a download for a missing model and a recovery for a failed one', () => {
        expect(readinessAction('missing')).toBe('download');
        expect(readinessAction('failed')).toBe('recover');
    });

    it('is nothing while the app is working, or when the model is ready', () => {
        for (const state of ['checking', 'queued', 'validating', 'loading', 'ready', 'running', 'unknown'] as const) {
            expect(readinessAction(state)).toBeNull();
        }
    });
});

describe('how the chosen model is recovered', () => {
    const here = { installed: true, complete: true, bundled: false };

    it('downloads a model that is not on this install', () => {
        expect(chosenRecovery('missing', { installed: false, complete: false, bundled: false })).toBe('download');
    });

    it('fetches incomplete files again when they can be fetched', () => {
        expect(chosenRecovery('failed', { ...here, complete: false })).toBe('repair_download');
    });

    it('checks and loads again a model whose files are complete', () => {
        expect(chosenRecovery('failed', here)).toBe('revalidate');
    });

    it('gives a bundled model that fails a recovery too: it cannot be downloaded, so it is loaded again', () => {
        expect(chosenRecovery('failed', { installed: true, complete: true, bundled: true })).toBe('revalidate');
        expect(chosenRecovery('failed', { installed: true, complete: false, bundled: true })).toBe('revalidate');
    });

    it('offers nothing while the app is working or the model needs nothing', () => {
        for (const state of ['checking', 'queued', 'validating', 'loading', 'ready', 'running', 'unknown'] as const) {
            expect(chosenRecovery(state, here)).toBeNull();
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
        for (const state of ['ready', 'running', 'queued', 'validating', 'checking', 'loading', 'unknown'] as const) {
            expect(setupEmphasis(state, 'other')).toBe('primary');
            expect(setupEmphasis(state, 'chosen')).toBe('primary');
        }
    });
});

describe('the word and the tone for each state, the same on every surface', () => {
    it('names each state once', () => {
        expect(readinessLabel('checking', t)).toBe('Checking…');
        expect(readinessLabel('missing', t)).toBe('Needs a download');
        expect(readinessLabel('queued', t)).toBe('Downloading');
        expect(readinessLabel('validating', t)).toBe('Being checked on this hardware');
        expect(readinessLabel('failed', t)).toBe('Could not load');
        expect(readinessLabel('loading', t)).toBe('Loading');
        expect(readinessLabel('ready', t)).toBe('Ready');
        expect(readinessLabel('running', t)).toBe('Running');
        expect(readinessLabel('unknown', t)).toBe('Not reported');
    });

    it('is green only on evidence the model works, amber only where a person must act', () => {
        expect(readinessTone('ready')).toBe('ok');
        expect(readinessTone('running')).toBe('ok');
        expect(readinessTone('missing')).toBe('attention');
        expect(readinessTone('failed')).toBe('attention');
        for (const state of ['checking', 'queued', 'validating', 'loading', 'unknown'] as const) expect(readinessTone(state)).toBe('neutral');
    });
});

describe('the readiness word and the server read a classifier report the same way', () => {
    // The cases the server's `identification_readiness` is tested against (backend/tests/pure).
    const shared = JSON.parse(
        readFileSync(new URL('../../../../../backend/tests/fixtures/model_readiness_cases.json', import.meta.url), 'utf8')
    ) as { cases: Array<{ name: string; status: ClassifierStatus | null; readiness: string }> };

    it.each(shared.cases)('$name', ({ status, readiness }) => {
        expect(identificationReadiness(identificationStatus(status))).toBe(readiness);
        expect(classifierReadiness(status)).toBe(readiness);
    });
});
