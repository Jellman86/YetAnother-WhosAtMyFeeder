export interface ActiveSlotItem {
    id: string;
}

export interface ActiveSlotAssignments {
    [jobId: string]: number;
}

export interface ActiveJobSlot<T extends ActiveSlotItem> {
    slotIndex: number;
    job: T | null;
}

function normalizeSlotCount(requestedSlots: number, activeJobs: number): number {
    const parsed = Number.isFinite(requestedSlots) ? Math.max(0, Math.floor(requestedSlots)) : 0;
    if (parsed > 0) return parsed;
    return activeJobs > 0 ? 1 : 0;
}

function nextFreeSlot(used: Set<number>, slotCount: number): number {
    for (let i = 0; i < slotCount; i += 1) {
        if (!used.has(i)) return i;
    }
    return slotCount;
}

export function buildStableActiveJobSlots<T extends ActiveSlotItem>(
    activeJobs: T[],
    previousAssignments: ActiveSlotAssignments,
    requestedSlots: number
): {
    slots: Array<ActiveJobSlot<T>>;
    assignments: ActiveSlotAssignments;
} {
    const slotCount = normalizeSlotCount(requestedSlots, activeJobs.length);
    const nextAssignments: ActiveSlotAssignments = {};
    const used = new Set<number>();

    for (const job of activeJobs) {
        const previousSlot = previousAssignments[job.id];
        if (
            Number.isInteger(previousSlot)
            && previousSlot >= 0
            && previousSlot < slotCount
            && !used.has(previousSlot)
        ) {
            nextAssignments[job.id] = previousSlot;
            used.add(previousSlot);
        }
    }

    for (const job of activeJobs) {
        if (nextAssignments[job.id] !== undefined) continue;
        const slotIndex = nextFreeSlot(used, slotCount);
        nextAssignments[job.id] = slotIndex;
        used.add(slotIndex);
    }

    const slots: Array<ActiveJobSlot<T>> = Array.from({ length: slotCount }, (_, slotIndex) => ({
        slotIndex,
        job: null
    }));

    for (const job of activeJobs) {
        const slotIndex = nextAssignments[job.id];
        if (slotIndex >= slots.length) {
            continue;
        }
        slots[slotIndex] = { slotIndex, job };
    }

    return { slots, assignments: nextAssignments };
}

export function sameActiveSlotAssignments(
    left: ActiveSlotAssignments,
    right: ActiveSlotAssignments
): boolean {
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    if (leftKeys.length !== rightKeys.length) return false;
    for (const key of leftKeys) {
        if (left[key] !== right[key]) return false;
    }
    return true;
}
