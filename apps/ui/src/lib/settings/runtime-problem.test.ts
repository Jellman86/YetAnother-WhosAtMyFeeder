import { describe, expect, it } from 'vitest';
import { RUNTIME_DISCLOSURES, RUNTIME_PROBLEM_OPENS, runtimeProblemKey } from './runtime-problem';

describe('the runtime problem a section opens for', () => {
    it('is none while the runtime reports nothing to act on', () => {
        expect(runtimeProblemKey(null, { videoCircuitOpen: false, autoVideoClassification: false })).toBeNull();
        expect(runtimeProblemKey({}, { videoCircuitOpen: true, autoVideoClassification: false })).toBeNull();
    });

    it('names the same problem the same way on every poll, and a different one differently', () => {
        const flags = { videoCircuitOpen: false, autoVideoClassification: false };
        const first = runtimeProblemKey({ fallback_reason: 'Intel GPU failed' }, flags);
        expect(runtimeProblemKey({ fallback_reason: 'Intel GPU failed', cuda_probe_error: null }, flags)).toBe(first);
        expect(runtimeProblemKey({ fallback_reason: 'CUDA missing' }, flags)).not.toBe(first);
        expect(runtimeProblemKey({}, { videoCircuitOpen: true, autoVideoClassification: true })).toContain('video');
    });
});

describe('what a new runtime problem opens', () => {
    it('opens Identifying birds\' More options first, so the report it opens inside Hardware is in view', () => {
        expect(RUNTIME_PROBLEM_OPENS).toEqual(['settings-more-identification', ...RUNTIME_DISCLOSURES]);
    });
});
