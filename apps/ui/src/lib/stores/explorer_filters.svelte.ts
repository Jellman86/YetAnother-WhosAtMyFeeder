/**
 * Whether the Explorer's filter rail is collapsed, for this browser.
 *
 * The rail is 14rem of permanent screen width, and once a filter is set it
 * mostly restates what the chips above the results already say. Collapsing it
 * gives that width back to the detections, which is what the page is for.
 *
 * Per device and not synced, for the same reason as the layout choice: a phone
 * and a desktop want different answers, and this changes nothing on the server
 * so a viewer without owner access can use it too.
 */

const STORAGE_KEY = 'yawamf:explorer-filters-collapsed';

function readStored(): boolean {
    try {
        return localStorage.getItem(STORAGE_KEY) === 'collapsed';
    } catch {
        // Private browsing, or storage disabled. The rail simply starts open.
        return false;
    }
}

class ExplorerFiltersStore {
    collapsed = $state<boolean>(readStored());

    set(collapsed: boolean): void {
        this.collapsed = collapsed;
        try {
            localStorage.setItem(STORAGE_KEY, collapsed ? 'collapsed' : 'open');
        } catch {
            // The choice still applies for this session; it just will not persist.
        }
    }

    toggle(): void {
        this.set(!this.collapsed);
    }
}

export const explorerFiltersStore = new ExplorerFiltersStore();
