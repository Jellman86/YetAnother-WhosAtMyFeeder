import { describe, expect, it } from 'vitest';

import { getDetectionModelGuidance } from './detection-model-guidance';

describe('getDetectionModelGuidance', () => {
    it('describes recommended and advanced model tradeoffs for the settings page', () => {
        expect(getDetectionModelGuidance()).toEqual({
            eyebrow: 'Tiered model lineup',
            title: 'Start with the recommended lineup',
            description:
                'Recommended models are ordered first and fit the broadest range of hardware and feeders.',
            advancedNote:
                'Advanced models are hidden by default because they usually need more RAM, run slower, or cover broader wildlife taxonomies than most installs need.',
        });
    });
});
