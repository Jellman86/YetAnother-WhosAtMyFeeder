import { describe, expect, it } from 'vitest';
import modelManagerSource from './ModelManager.svelte?raw';
import en from '../../i18n/locales/en.json';

describe('bird finder choice', () => {
    it('offers both accurate detectors as one labelled radio group on the default surface', () => {
        expect(modelManagerSource).toContain('<fieldset');
        expect(modelManagerSource).toContain('name="bird-finder"');
        expect(modelManagerSource).toContain('BIRD_FINDER_MODEL_IDS');
        // The finder is a model choice, not a thumbnail detail behind a disclosure.
        expect(modelManagerSource).not.toContain('model_manager_thumbnail_crop_title');
        const finder = modelManagerSource.indexOf('name="bird-finder"');
        const lastDetails = modelManagerSource.lastIndexOf('<details');
        expect(finder).toBeGreaterThan(lastDetails);
    });

    it('stages the choice in the settings form instead of saving it on click', () => {
        expect(modelManagerSource).toContain('birdFinder = $bindable');
        expect(modelManagerSource).not.toContain('updateSettings');
        expect(modelManagerSource).not.toContain('bird_finder_save_failed');
        expect(modelManagerSource).toContain('cropDetectorStatus.chosen_model_id');
    });

    it("states each finder's costs and the device it will use on this host", () => {
        expect(modelManagerSource).toContain('ramShortLabel(option.model.estimated_ram_mb)');
        expect(modelManagerSource).toContain('option.model.file_size_mb');
        expect(modelManagerSource).toContain('birdFinderDevice(getInstalledModel(option.model.id))');
        expect(en.settings.detection.bird_finder_device_cpu_unchecked).toMatch(/CPU/);
        expect(en.settings.detection.bird_finder_default_badge).toBe('Default');
    });

    it('says plainly when the chosen finder is not in use yet, and when a change waits for Apply', () => {
        expect(modelManagerSource).toContain("cropDetectorStatus?.reason === 'fallback_default_accurate'");
        expect(en.settings.detection.bird_finder_fallback).toMatch(/not downloaded yet/);
        expect(modelManagerSource).toContain('birdFinder !== savedBirdFinder');
        expect(en.settings.detection.bird_finder_pending).toMatch(/Apply settings/);
    });

    it('states the cost of the wide-frame finder up front, without em dashes', () => {
        expect(en.settings.detection.bird_finder_wide_desc).toMatch(/103 MB/);
        for (const key of Object.keys(en.settings.detection).filter((k) => k.startsWith('bird_finder'))) {
            expect(String((en.settings.detection as Record<string, string>)[key])).not.toContain('—');
        }
    });
});
