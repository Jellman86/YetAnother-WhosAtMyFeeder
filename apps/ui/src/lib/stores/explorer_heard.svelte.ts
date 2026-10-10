/**
 * Whether the Explorer shows BirdNET-Go calls between its visits, for this browser.
 *
 * Off until someone turns it on: the Explorer is what the cameras saw, and calls outnumber
 * visits many times over on a busy day. The choice lives on the page, not in Settings, and
 * like the Cards/List choice it is a view preference kept per device, never synced.
 */

const STORAGE_KEY = 'yawamf:explorer-heard';

function readStored(): boolean {
    try {
        return localStorage.getItem(STORAGE_KEY) === 'on';
    } catch {
        // Private browsing, or storage disabled. Off still applies.
        return false;
    }
}

class ExplorerHeardStore {
    private shown = $state(readStored());

    get enabled(): boolean {
        return this.shown;
    }

    set(next: boolean): void {
        this.shown = next;
        try {
            if (next) localStorage.setItem(STORAGE_KEY, 'on');
            else localStorage.removeItem(STORAGE_KEY);
        } catch {
            // The choice still applies for this session; it just will not persist.
        }
    }
}

export const explorerHeardStore = new ExplorerHeardStore();
