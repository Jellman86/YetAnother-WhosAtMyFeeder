/**
 * A gate that lets at most `limit` pieces of work run at once; the rest wait
 * their turn in order.
 *
 * A page that renders thirty cards should not fire thirty requests in the same
 * second. The backend serves them from a pool of five database connections, and
 * a burst like that turns every one of them into a queue: on a live install one
 * dashboard open produced fifteen waits of 300 to 650 ms. Bounding the fan-out at
 * the API client keeps every caller honest, including ones not written yet.
 */
export interface SlotGate {
    run<T>(work: () => Promise<T>): Promise<T>;
    /** How many pieces of work are running right now. For tests and diagnostics. */
    readonly active: number;
}

export function createSlotGate(limit: number): SlotGate {
    if (!Number.isInteger(limit) || limit < 1) throw new RangeError(`limit must be a positive integer, got ${limit}`);
    let active = 0;
    const waiting: Array<() => void> = [];

    function release(): void {
        const next = waiting.shift();
        if (next) {
            next();
        } else {
            active -= 1;
        }
    }

    function acquire(): Promise<void> {
        if (active < limit) {
            active += 1;
            return Promise.resolve();
        }
        return new Promise((resolve) => waiting.push(resolve));
    }

    return {
        async run<T>(work: () => Promise<T>): Promise<T> {
            await acquire();
            try {
                return await work();
            } finally {
                release();
            }
        },
        get active() {
            return active;
        }
    };
}
