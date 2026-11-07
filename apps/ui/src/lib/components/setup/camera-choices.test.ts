import { describe, expect, it } from 'vitest';
import { cameraChoices, frigateCameraNames, parseCameraNames } from './camera-choices';

describe('wizard camera choices', () => {
    it('offers what Frigate has and keeps a saved name it does not, marked as missing', () => {
        expect(cameraChoices(['feeder', 'nestbox'], ['feedr', 'feeder'])).toEqual([
            { camera: 'feeder', missing: false },
            { camera: 'nestbox', missing: false },
            { camera: 'feedr', missing: true }
        ]);
    });

    it('reads camera names from Frigate config, and treats an unusable reply as unread', () => {
        expect(frigateCameraNames({ cameras: { feeder: {}, nestbox: {} } })).toEqual(['feeder', 'nestbox']);
        expect(frigateCameraNames({ cameras: {} })).toBeNull();
        expect(frigateCameraNames({ detail: 'nope' })).toBeNull();
        expect(frigateCameraNames(null)).toBeNull();
    });

    it('trims typed names and drops blanks and repeats', () => {
        expect(parseCameraNames(' feeder, ,nestbox,feeder ')).toEqual(['feeder', 'nestbox']);
    });
});
