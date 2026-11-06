import type { ExplorerSubjects } from '../utils/garden-explorer';

/**
 * Whether the Explorer shows birds, Garden captures, or both, for this browser.
 *
 * Both by default once Garden is on: turning Garden on for a camera is what puts its animals here.
 * Like the Cards/List choice it is a view preference kept per device, never a setting.
 */

const STORAGE_KEY = 'yawamf:explorer-subjects';

function readStored(): ExplorerSubjects {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        return stored === 'birds' || stored === 'garden' ? stored : 'all';
    } catch {
        // Private browsing, or storage disabled. Both still applies.
        return 'all';
    }
}

class ExplorerSubjectsStore {
    private chosen = $state<ExplorerSubjects>(readStored());

    get value(): ExplorerSubjects {
        return this.chosen;
    }

    set(next: ExplorerSubjects): void {
        this.chosen = next;
        try {
            if (next === 'all') localStorage.removeItem(STORAGE_KEY);
            else localStorage.setItem(STORAGE_KEY, next);
        } catch {
            // The choice still applies for this session; it just will not persist.
        }
    }
}

export const explorerSubjectsStore = new ExplorerSubjectsStore();
