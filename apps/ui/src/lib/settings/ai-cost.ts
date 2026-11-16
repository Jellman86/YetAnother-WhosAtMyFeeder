/** The part of the AI usage answer the cost line is read from. */
interface UsageCost {
    calls: number;
    estimated_cost_usd?: number | null;
    priced_calls?: number;
    unpriced_calls?: number;
    unpriced_models?: string[];
}

/**
 * What the usage view may say about cost. A model with no price has no estimate, which is not a
 * cost of zero: the view then says the cost is not estimated, and a total over part of the usage
 * carries the share of requests it covers.
 */
export type CostReading =
    | { kind: 'no_usage' }
    | { kind: 'not_estimated'; unpricedModels: string[] }
    | { kind: 'partial'; cost: number; pricedCalls: number; totalCalls: number; unpricedModels: string[] }
    | { kind: 'estimated'; cost: number; totalCalls: number };

export function costReading(usage: UsageCost): CostReading {
    if (usage.calls <= 0) return { kind: 'no_usage' };
    const cost = usage.estimated_cost_usd;
    const unpricedModels = usage.unpriced_models ?? [];
    const unpricedCalls = usage.unpriced_calls ?? 0;
    if (cost === null || cost === undefined) return { kind: 'not_estimated', unpricedModels };
    if (unpricedCalls > 0) {
        return { kind: 'partial', cost, pricedCalls: usage.priced_calls ?? 0, totalCalls: usage.calls, unpricedModels };
    }
    return { kind: 'estimated', cost, totalCalls: usage.calls };
}

/** Cents are the precision a bill has; below a cent says so rather than printing a zero. */
export function formatUsd(value: number): string {
    if (value > 0 && value < 0.01) return '< $0.01';
    return '$' + value.toFixed(2);
}
