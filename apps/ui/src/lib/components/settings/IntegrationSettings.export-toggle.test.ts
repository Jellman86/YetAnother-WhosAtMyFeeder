import { describe, expect, it } from 'vitest';

function computeExportUiState(
    exportEverything: boolean,
    fromDate: string,
    toDate: string
): {
    inputsDisabled: boolean;
    effectiveFrom?: string;
    effectiveTo?: string;
    hasRangeError: boolean;
} {
    const hasRangeError = !exportEverything && !!fromDate && !!toDate && fromDate > toDate;
    return {
        inputsDisabled: exportEverything,
        effectiveFrom: exportEverything ? undefined : fromDate || undefined,
        effectiveTo: exportEverything ? undefined : toDate || undefined,
        hasRangeError
    };
}

describe('IntegrationSettings eBird export toggle state', () => {
    it('disables and clears effective range when export everything is enabled', () => {
        const state = computeExportUiState(true, '2026-03-10', '2026-03-12');

        expect(state.inputsDisabled).toBe(true);
        expect(state.effectiveFrom).toBeUndefined();
        expect(state.effectiveTo).toBeUndefined();
        expect(state.hasRangeError).toBe(false);
    });

    it('keeps explicit range active when export everything is disabled', () => {
        const state = computeExportUiState(false, '2026-03-10', '2026-03-12');

        expect(state.inputsDisabled).toBe(false);
        expect(state.effectiveFrom).toBe('2026-03-10');
        expect(state.effectiveTo).toBe('2026-03-12');
        expect(state.hasRangeError).toBe(false);
    });

    it('still reports inverted ranges only in range mode', () => {
        expect(computeExportUiState(false, '2026-03-12', '2026-03-10').hasRangeError).toBe(true);
        expect(computeExportUiState(true, '2026-03-12', '2026-03-10').hasRangeError).toBe(false);
    });
});
