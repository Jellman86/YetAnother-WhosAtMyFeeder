// One in-app place to ask "are you sure?". Native confirm() is suppressed by embedded
// browsers and webviews, where it returns false without showing anything, so a
// destructive button there silently did nothing.

type ConfirmTone = 'danger' | 'default';

/** The words a question settles on once the figure it depends on has been read, or could not be. */
export interface ConfirmWording {
    message: string;
    confirmLabel?: string;
}

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
    /**
     * A figure the question states, such as how many records a delete removes. The question opens at
     * once with `message` saying what is being read and cannot be confirmed until `read` settles.
     * `unread` is asked when the read fails, so it must not state the figure.
     */
    reading?: { read: () => Promise<ConfirmWording>; unread: ConfirmWording };
}

interface PendingConfirmation extends Required<Omit<ConfirmRequest, 'alternative' | 'reading'>> {
    alternative?: ConfirmRequest['alternative'];
    /** True until the figure the question states has been read; it cannot be confirmed before then. */
    reading: boolean;
    resolve: (confirmed: boolean) => void;
}

class ConfirmDialogStore {
    current = $state<PendingConfirmation | null>(null);

    request(options: ConfirmRequest): Promise<boolean> {
        // One question at a time: an unanswered one is treated as cancelled.
        this.answer(false);
        const { reading, ...question } = options;
        return new Promise<boolean>((resolve) => {
            const pending: PendingConfirmation = { tone: 'danger', cancelLabel: '', ...question, reading: reading !== undefined, resolve };
            this.current = pending;
            if (reading) void this.settle(pending, reading);
        });
    }

    private async settle(pending: PendingConfirmation, reading: NonNullable<ConfirmRequest['reading']>): Promise<void> {
        const wording = await reading.read().catch(() => reading.unread);
        // Cancelled or replaced while it read: the answer belongs to no open question.
        if (this.current?.resolve !== pending.resolve) return;
        this.current = { ...pending, ...wording, reading: false };
    }

    answer(confirmed: boolean): void {
        const pending = this.current;
        if (confirmed && pending?.reading) return;
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
        } catch {
            // The alternative reports its own failure (a save says why in the save bar); here it
            // only means "do not go ahead", so the page stays.
            worked = false;
        } finally {
            pending.resolve(worked);
        }
    }
}

export const confirmDialog = new ConfirmDialogStore();

export function confirmAction(options: ConfirmRequest): Promise<boolean> {
    return confirmDialog.request(options);
}
