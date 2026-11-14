import { confirmAction, type ConfirmRequest } from './confirm_dialog.svelte';

/**
 * Says what leaving for `to` would lose, as the question to ask, or null when nothing would be.
 * A page holding unsaved work answers for its own routes: moving between them keeps the work.
 */
type LeaveWarning = (to: string) => ConfirmRequest | null;

/**
 * One place the app asks before an in-app navigation that would throw away unsaved work. A page
 * holds the guard while it has a draft; the router asks it before every link or menu navigation.
 * Back and Forward are not held: the page keeps its draft for the return instead.
 */
class UnsavedChangesGuard {
    private warning: LeaveWarning | null = null;
    private onLeave: (() => void) | null = null;

    /**
     * Registers the page's warning, and what to do once the person chooses to leave anyway (drop
     * the work they were warned about). The returned function releases both.
     */
    hold(warning: LeaveWarning, onLeave?: () => void): () => void {
        this.warning = warning;
        this.onLeave = onLeave ?? null;
        return () => {
            if (this.warning !== warning) return;
            this.warning = null;
            this.onLeave = null;
        };
    }

    /** The question leaving for `to` needs, or null when leaving loses nothing. */
    warningFor(to: string): ConfirmRequest | null {
        return this.warning?.(to) ?? null;
    }

    /** Resolves true when leaving for `to` may go ahead: nothing is lost, or the person agreed. */
    async allowLeaving(to: string): Promise<boolean> {
        const warning = this.warningFor(to);
        if (!warning) return true;
        const leave = await confirmAction(warning);
        if (leave) this.onLeave?.();
        return leave;
    }
}

export const unsavedChanges = new UnsavedChangesGuard();
