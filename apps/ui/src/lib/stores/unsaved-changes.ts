import { confirmAction, type ConfirmRequest } from './confirm_dialog.svelte';

/**
 * Says what leaving for `to` would lose, as the question to ask, or null when nothing would be.
 * A page holding unsaved work answers for its own routes: moving between them keeps the work.
 */
export type LeaveWarning = (to: string) => ConfirmRequest | null;

/**
 * One place the app asks before a navigation that would throw away unsaved work. A page holds
 * the guard while it has a draft; the router asks it before every route change.
 */
class UnsavedChangesGuard {
    private warning: LeaveWarning | null = null;

    /** Registers the page's warning; the returned function releases it. */
    hold(warning: LeaveWarning): () => void {
        this.warning = warning;
        return () => {
            if (this.warning === warning) this.warning = null;
        };
    }

    /** The question leaving for `to` needs, or null when leaving loses nothing. */
    warningFor(to: string): ConfirmRequest | null {
        return this.warning?.(to) ?? null;
    }

    /** Resolves true when leaving for `to` may go ahead: nothing is lost, or the person agreed. */
    async allowLeaving(to: string): Promise<boolean> {
        const warning = this.warningFor(to);
        return warning ? confirmAction(warning) : true;
    }
}

export const unsavedChanges = new UnsavedChangesGuard();
