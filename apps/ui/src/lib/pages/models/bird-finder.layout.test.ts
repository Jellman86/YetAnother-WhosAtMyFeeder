import { describe, expect, it } from 'vitest';
import modelManagerSource from './ModelManager.svelte?raw';
import en from '../../i18n/locales/en.json';

describe('bird finder choice', () => {
    it('offers both accurate detectors as one labelled radio group', () => {
        expect(modelManagerSource).toContain('<fieldset');
        expect(modelManagerSource).toContain('name="bird-finder"');
        expect(modelManagerSource).toContain("rfdetr_nano: 'bird_crop_detector_accurate_rfdetr_nano'");
        expect(modelManagerSource).toContain("yolox_tiny: 'bird_crop_detector_accurate_yolox_tiny'");
    });

    it('saves only the detector choice and restores the previous choice when saving fails', () => {
        expect(modelManagerSource).toContain('updateSettings({ bird_crop_accurate_detector: choice })');
        expect(modelManagerSource).toContain('pendingBirdFinder = null;');
        expect(modelManagerSource).toContain('cropDetectorStatus?.chosen_model_id');
    });

    it('says plainly when the chosen finder is not in use yet', () => {
        expect(modelManagerSource).toContain("cropDetectorStatus?.reason === 'fallback_default_accurate'");
        expect(en.settings.detection.bird_finder_fallback).toMatch(/not downloaded yet/);
    });

    it('states the cost of the wide-frame finder up front', () => {
        expect(en.settings.detection.bird_finder_wide_desc).toMatch(/103 MB/);
        expect(en.settings.detection.bird_finder_wide_desc).not.toContain('—');
    });
});
