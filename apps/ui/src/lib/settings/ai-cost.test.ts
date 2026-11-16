import { describe, expect, it } from 'vitest';
import { costReading, formatUsd } from './ai-cost';

const usage = (overrides: Record<string, unknown> = {}) => ({
    calls: 3,
    estimated_cost_usd: 0.3 as number | null,
    priced_calls: 3,
    unpriced_calls: 0,
    unpriced_models: [] as string[],
    ...overrides
});

describe('what the AI usage view may say about cost', () => {
    it('says the cost is not estimated when the usage has no prices, never $0.00', () => {
        expect(costReading(usage({ estimated_cost_usd: null, priced_calls: 0, unpriced_calls: 3, unpriced_models: ['claude/claude-opus'] }))).toEqual({
            kind: 'not_estimated',
            unpricedModels: ['claude/claude-opus']
        });
    });

    it('gives a total with its coverage when only some usage is priced', () => {
        expect(costReading(usage({ priced_calls: 1, unpriced_calls: 2, unpriced_models: ['claude/claude-opus'] }))).toEqual({
            kind: 'partial',
            cost: 0.3,
            pricedCalls: 1,
            totalCalls: 3,
            unpricedModels: ['claude/claude-opus']
        });
    });

    it('gives the total for all requests when every model is priced', () => {
        expect(costReading(usage())).toEqual({ kind: 'estimated', cost: 0.3, totalCalls: 3 });
    });

    it('says there is nothing to cost when nothing was requested', () => {
        expect(costReading(usage({ calls: 0, estimated_cost_usd: 0, priced_calls: 0 }))).toEqual({ kind: 'no_usage' });
    });
});

describe('a dollar amount', () => {
    it('has the precision of a bill, and says so below a cent', () => {
        expect(formatUsd(0.3)).toBe('$0.30');
        expect(formatUsd(12.345)).toBe('$12.35');
        expect(formatUsd(0.004)).toBe('< $0.01');
        expect(formatUsd(0)).toBe('$0.00');
    });
});
