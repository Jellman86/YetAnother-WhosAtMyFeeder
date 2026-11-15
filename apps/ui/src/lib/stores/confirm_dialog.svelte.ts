// One in-app place to ask "are you sure?". Native confirm() is suppressed by embedded
// browsers and webviews, where it returns false without showing anything, so a
// destructive button there silently did nothing.

type ConfirmTone = 'danger' | 'default';

export interface ConfirmRequest {
    title: string;
    message: string;
    /** Names the effect, e.g. "Reset database", never a bare "OK". */
    confirmLabel: string;
    /** Names the safe answer when "Cancel" would misread, e.g. "Stay" on a leave prompt. Defaults to Cancel. */
    cancelLabel?: string;
    tone?: ConfirmTone;
    /**
     * A second way forward beside the confirm button, such as "Save and leave". It runs with the
     * question closed (it may ask one of its own), and the answer is whether it worked out.
     */
    alternative?: { label: string; run: () => Promise<boolean> };
}

interface PendingConfirmation extends Required<Omit<ConfirmRequest, 'alternative'>> {
    alternative?: ConfirmRequest['alternative'];
    resolve: (confirmed: boolean) => void;
}

class ConfirmDialogStore {
    current = $state<PendingConfirmation | null>(null);

    request(options: ConfirmRequest): Promise<boolean> {
        // One question at a time: an unanswered one is treated as cancelled.
        this.answer(false);
        return new Promise<boolean>((resolve) => {
            this.current = { tone: 'danger', cancelLabel: '', ...options, resolve };
        });
    }

    answer(confirmed: boolean): void {
        const pending = this.current;
        this.current = null;
        pending?.resolve(confirmed);
    }

    async runAlternative(): Promise<void> {
        const pending = this.current;
        if (!pending?.alternative) return;
        this.current = null;
        let worked = false;
        try {
            worked = await pending.alternative.run();
        } finally {
            pending.resolve(worked);
        }
    }
}

export const confirmDialog = new ConfirmDialogStore();

export function confirmAction(options: ConfirmRequest): Promise<boolean> {
    return confirmDialog.request(options);
}
