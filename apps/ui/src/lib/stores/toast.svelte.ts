// Toast notification store for displaying temporary messages to users

export interface Toast {
    id: string;
    message: string;
    type: 'success' | 'error' | 'warning' | 'info';
    duration?: number; // milliseconds, default 5000
    /** Stays until the reader dismisses it. Every error does: a failure must not vanish unread. */
    persistent: boolean;
    /** One button that acts on what the toast reports, such as undoing it. */
    action?: ToastAction;
}

interface ToastAction {
    label: string;
    run: () => void;
}

/** Long enough to read the message and reach the button, short enough that it is clearly temporary. */
const UNDO_WINDOW_MS = 10_000;

interface Countdown {
    remaining: number;
    startedAt: number;
    timer: ReturnType<typeof setTimeout> | null;
}

class ToastStore {
    toasts = $state<Toast[]>([]);
    private nextId = 0;
    private lastSignature = '';
    private lastShownAt = 0;
    private duplicateWindowMs = 1500;
    private countdowns = new Map<string, Countdown>();

    show(message: string, type: Toast['type'] = 'info', duration: number = 5000, action?: ToastAction) {
        const normalizedMessage = String(message ?? '').trim();
        const signature = `${type}:${normalizedMessage}`;
        const now = Date.now();
        if (signature === this.lastSignature && now - this.lastShownAt < this.duplicateWindowMs) {
            return '';
        }
        this.lastSignature = signature;
        this.lastShownAt = now;

        const persistent = type === 'error' || duration <= 0;
        // A persistent toast waits for the reader, so a repeat of one still on screen adds nothing.
        const waiting = persistent
            ? this.toasts.find((toast) => toast.persistent && toast.type === type && toast.message === (normalizedMessage || message))
            : undefined;
        if (waiting) return waiting.id;

        const id = `toast-${this.nextId++}`;
        const toast: Toast = { id, message: normalizedMessage || message, type, duration, persistent, action };

        this.toasts = [...this.toasts, toast];

        if (!persistent) {
            this.countdowns.set(id, { remaining: duration, startedAt: now, timer: null });
            this.resume(id);
        }

        return id;
    }

    /** Stops the countdown while the reader is pointing at or focused on the toast. */
    pause(id: string) {
        const countdown = this.countdowns.get(id);
        if (!countdown?.timer) return;
        clearTimeout(countdown.timer);
        countdown.timer = null;
        countdown.remaining = Math.max(0, countdown.remaining - (Date.now() - countdown.startedAt));
    }

    resume(id: string) {
        const countdown = this.countdowns.get(id);
        if (!countdown || countdown.timer) return;
        countdown.startedAt = Date.now();
        countdown.timer = setTimeout(() => this.remove(id), countdown.remaining);
    }

    remove(id: string) {
        const countdown = this.countdowns.get(id);
        if (countdown?.timer) clearTimeout(countdown.timer);
        this.countdowns.delete(id);
        this.toasts = this.toasts.filter(t => t.id !== id);
    }

    clear() {
        for (const countdown of this.countdowns.values()) {
            if (countdown.timer) clearTimeout(countdown.timer);
        }
        this.countdowns.clear();
        this.toasts = [];
    }

    /** Runs the toast's action once and takes the toast away; a lapsed toast does nothing. */
    runAction(id: string) {
        const toast = this.toasts.find((entry) => entry.id === id);
        if (!toast?.action) return;
        this.remove(id);
        toast.action.run();
    }

    /** Reports something just done and offers to undo it while the toast is up. */
    undoable(message: string, label: string, undo: () => void) {
        return this.show(message, 'info', UNDO_WINDOW_MS, { label, run: undo });
    }

    // Convenience methods
    success(message: string, duration?: number) {
        return this.show(message, 'success', duration);
    }

    error(message: string, duration?: number) {
        return this.show(message, 'error', duration);
    }

    warning(message: string, duration?: number) {
        return this.show(message, 'warning', duration);
    }

    info(message: string, duration?: number) {
        return this.show(message, 'info', duration);
    }
}

export const toastStore = new ToastStore();
