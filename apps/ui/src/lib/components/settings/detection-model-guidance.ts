export type DetectionModelGuidance = {
    eyebrow: string;
    title: string;
    description: string;
    advancedNote: string;
};

export function getDetectionModelGuidance(): DetectionModelGuidance {
    return {
        eyebrow: 'Tiered model lineup',
        title: 'Start with the recommended lineup',
        description:
            'Recommended models are ordered first and fit the broadest range of hardware and feeders.',
        advancedNote:
            'Advanced models are hidden by default because they usually need more RAM, run slower, or cover broader wildlife taxonomies than most installs need.',
    };
}
