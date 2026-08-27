/**
 * How the Explorer draws its detections, for this browser.
 *
 * Settings → Appearance sets the install default. This is a per-device
 * override on top of it, because the choice is genuinely device-shaped: the
 * list exists so a phone can be scanned by time (#270), while a desktop has
 * the width for cards. Forcing one answer onto both would make the setting
 * worse than useless on whichever device lost.
 *
 * The override is deliberately not synced anywhere. It is a view preference,
 * not data, and a viewer without owner access can still use it.
 */

export type ExplorerView = 'cards' | 'list';

const STORAGE_KEY = 'yawamf:explorer-view';

function readStored(): ExplorerView | null {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw === 'cards' || raw === 'list' ? raw : null;
    } catch {
        // Private browsing, or storage disabled. The install default still applies.
        return null;
    }
}

class ExplorerViewStore {
    /** null means "no choice on this device", so the install default wins. */
    private override = $state<ExplorerView | null>(readStored());

    /** What the Explorer should draw, given the install default. */
    resolve(installDefault: ExplorerView | undefined | null): ExplorerView {
        return this.override ?? (installDefault === 'list' ? 'list' : 'cards');
    }

    /** Whether this device has made its own choice. */
    get hasOverride(): boolean {
        return this.override !== null;
    }

    set(view: ExplorerView): void {
        this.override = view;
        try {
            localStorage.setItem(STORAGE_KEY, view);
        } catch {
            // The choice still applies for this session; it just will not persist.
        }
    }

    /** Forget this device's choice and follow the install default again. */
    clear(): void {
        this.override = null;
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch {
            // Nothing stored to remove.
        }
    }
}

export const explorerViewStore = new ExplorerViewStore();
