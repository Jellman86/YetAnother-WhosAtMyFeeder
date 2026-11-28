import { describe, expect, it } from 'vitest';
import { namesListedMoreThanOnce, sourceNameKey } from './audio-source-names';

describe('Sources that share a name are told apart by their id', () => {
    it('finds no shared name when every source has its own', () => {
        expect(namesListedMoreThanOnce([{ source_name: 'birdcam' }, { source_name: 'nestcam' }])).toEqual(new Set());
    });

    it('names a source listed twice, whatever its case or spacing', () => {
        const shared = namesListedMoreThanOnce([
            { source_name: 'birdcam' },
            { source_name: 'nestcam' },
            { source_name: ' BirdCam ' },
        ]);
        expect(shared).toEqual(new Set(['birdcam']));
        expect(shared.has(sourceNameKey('BirdCam'))).toBe(true);
        expect(shared.has(sourceNameKey('nestcam'))).toBe(false);
    });
});
