// Toast notification store for displaying temporary messages to users

export interface Toast {
    id: string;
    message: string;
    type: 'success' | 'error' | 'warning' | 'info';
    duration?: number; // milliseconds, default 5000
}

class ToastStore {
    toasts = $state<Toast[]>([]);
    private nextId = 0;

    show(message: string, type: Toast['type'] = 'info', duration: number = 5000) {
        const id = `toast-${this.nextId++}`;
        const toast: Toast = { id, message, type, duration };

        this.toasts = [...this.toasts, toast];

        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                this.remove(id);
            }, duration);
        }

        return id;
    }

    remove(id: string) {
        this.toasts = this.toasts.filter(t => t.id !== id);
    }

    clear() {
        this.toasts = [];
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
