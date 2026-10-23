import { describe, expect, it } from 'vitest';
import { formatModelSize, gardenModelRows, gardenSetupBlock } from './garden-models';
import type { GardenIdentificationStatus, GardenMotionStatus } from '../api/garden';

const identification: GardenIdentificationStatus = {
    country: 'GBR',
    catalogue_ready: true,
    busy: false,
    error: null,
    models: [
        { variant: '4.0.3a', installed: true, size_bytes: 223998782 },
        { variant: '4.0.3b', installed: false, size_bytes: 223999179 }
    ],
    automatic_message: 'No automatic check is due.'
};

const motion: GardenMotionStatus = {
    cameras: [], installed: false, model_bytes: 101228666, catalogue_ready: true, busy: false,
    state: 'disabled', message: 'Motion collection is off.'
};

describe('Garden model rows', () => {
    it('lists the three Garden models by role, never the bird model', () => {
        const rows = gardenModelRows(identification, motion, []);
        expect(rows.map(row => row.role)).toEqual(['automatic_check', 'species_suggestions', 'motion_detector']);
        expect(rows.map(row => row.install)).toEqual([
            { kind: 'speciesnet', variant: '4.0.3a' },
            { kind: 'speciesnet', variant: '4.0.3b' },
            { kind: 'motion' }
        ]);
    });

    it('reports measured install state and size from the backend', () => {
        const [check, suggestions, detector] = gardenModelRows(identification, motion, []);
        expect(check).toMatchObject({ state: 'ready', sizeBytes: 223998782, requirement: 'required' });
        expect(suggestions).toMatchObject({ state: 'missing', sizeBytes: 223999179, requirement: 'optional' });
        expect(detector).toMatchObject({ state: 'missing', sizeBytes: 101228666, requirement: 'optional' });
    });

    it('makes the motion detector required once a camera collects motion photos', () => {
        expect(gardenModelRows(identification, motion, ['patio'])[2].requirement).toBe('required');
    });

    it('never claims a model is ready when its status could not be read', () => {
        const rows = gardenModelRows(null, null, []);
        expect(rows.every(row => row.state === 'unknown')).toBe(true);
        expect(rows.every(row => row.sizeBytes === null)).toBe(true);
    });

    it('marks SpeciesNet unavailable when the catalogue or worker has failed, even if the file exists', () => {
        for (const broken of [{ catalogue_ready: false }, { error: 'Garden worker did not stop.' }]) {
            const [check, suggestions] = gardenModelRows({ ...identification, ...broken }, motion, []);
            expect(check.state).toBe('unavailable');
            expect(suggestions.state).toBe('unavailable');
        }
        expect(gardenModelRows(identification, { ...motion, catalogue_ready: false }, [])[2].state).toBe('unavailable');
    });

    it('treats a variant missing from the status as unknown rather than ready', () => {
        const [check] = gardenModelRows({ ...identification, models: [] }, motion, []);
        expect(check.state).toBe('unknown');
    });
});

describe('Garden download admission', () => {
    it('allows one explicit download when Garden is idle', () => {
        expect(gardenSetupBlock(identification, null)).toBeNull();
    });

    it('explains why downloads are unavailable', () => {
        expect(gardenSetupBlock(identification, 'motion_detector')).toBe('downloading');
        expect(gardenSetupBlock({ ...identification, busy: true }, null)).toBe('busy');
        expect(gardenSetupBlock({ ...identification, error: 'stopped' }, null)).toBe('error');
        expect(gardenSetupBlock(null, null)).toBe('unknown');
    });
});

describe('model size', () => {
    it('matches the decimal megabytes already shown on download buttons', () => {
        expect(formatModelSize(223998782)).toBe('224 MB');
        expect(formatModelSize(101228666)).toBe('101 MB');
    });
});
