// One in-app place to ask "are you sure?". Native confirm() is suppressed by embedded
// browsers and webviews, where it returns false without showing anything, so a
// destructive button there silently did nothing.

type ConfirmTone = 'danger' | 'default';

export interface ConfirmRequest {
    title: string;
    message: string;
    /** Names the effect, e.g. "Reset database", never a bare "OK". */
    confirmLabel: string;
    tone?: ConfirmTone;
}

interface PendingConfirmation extends Required<ConfirmRequest> {
    resolve: (confirmed: boolean) => void;
}

class ConfirmDialogStore {
    current = $state<PendingConfirmation | null>(null);

    request(options: ConfirmRequest): Promise<boolean> {
        // One question at a time: an unanswered one is treated as cancelled.
        this.answer(false);
        return new Promise<boolean>((resolve) => {
            this.current = { tone: 'danger', ...options, resolve };
        });
    }

    answer(confirmed: boolean): void {
        const pending = this.current;
        this.current = null;
        pending?.resolve(confirmed);
    }
}

export const confirmDialog = new ConfirmDialogStore();

export function confirmAction(options: ConfirmRequest): Promise<boolean> {
    return confirmDialog.request(options);
}
