import { describe, expect, it } from 'vitest';
import source from './DataSettings.svelte?raw';


describe('high-quality snapshot settings', () => {
    it('presents one outcome-oriented automatic quality control', () => {
        expect(source).toContain('Best available event snapshots');
        expect(source).toContain('best crop available');
        expect(source).not.toContain('setting-cache-hq-bird-crop');
        expect(source).not.toContain('HQ Bird Crop Snapshots');
    });

    it('shows whether the crop detector is ready without exposing source selection', () => {
        expect(source).toContain('cropDetectorReady');
        expect(source).toContain('Crop detector ready');
        expect(source).not.toContain('bird_crop_source_priority');
    });
});
